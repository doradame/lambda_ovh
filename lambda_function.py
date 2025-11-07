import json
import os
import logging
import requests

log = logging.getLogger()
log.setLevel(logging.INFO)

# Variabili d'ambiente necessarie: siamo tornati a username/password!
# REGION e INSTANCE_ID possono essere passati via query string.
REQUIRED_ENVS = [
    "OS_AUTH_URL",      # Questo è l'endpoint per l'autenticazione
    "OS_USERNAME",
    "OS_PASSWORD",
    "OS_PROJECT_ID",
    "API_KEY",          # API key per autenticare le chiamate alla lambda
]

def _json(status, body):
    return {"statusCode": status, "headers": {"Content-Type": "application/json"},
            "body": json.dumps(body)}

def _require_envs():
    missing = [k for k in REQUIRED_ENVS if not os.environ.get(k)]
    if missing:
        raise RuntimeError(f"Missing required envs: {', '.join(missing)}")

def _check_api_key(event):
    """
    Verifica l'API key dalla richiesta.
    L'API key può essere fornita tramite:
    - Header 'X-API-Key'
    - Query parameter 'api_key'
    """
    expected_api_key = os.environ.get("API_KEY")
    if not expected_api_key:
        raise RuntimeError("API_KEY environment variable not configured")
    
    # Controlla negli headers
    headers = (event or {}).get("headers") or {}
    provided_api_key = headers.get("X-API-Key") or headers.get("x-api-key")
    
    # Se non trovata negli headers, controlla nei query parameters
    if not provided_api_key:
        qs = (event or {}).get("queryStringParameters") or {}
        provided_api_key = qs.get("api_key")
    
    if not provided_api_key:
        raise RuntimeError("API key not provided. Use X-API-Key header or api_key query parameter")
    
    if provided_api_key != expected_api_key:
        raise RuntimeError("Invalid API key")
    
    log.info("API key validation successful")

def _get_token_and_compute_url(region):
    """
    Autenticati con username/password per ottenere un token e l'endpoint del servizio Compute.

    :param region: nome della regione da utilizzare per il service catalog
    """
    auth_url = os.environ["OS_AUTH_URL"]
    username = os.environ["OS_USERNAME"]
    password = os.environ["OS_PASSWORD"]
    project_id = os.environ["OS_PROJECT_ID"]

    # Corpo della richiesta di autenticazione v3 di OpenStack
    auth_payload = {
        "auth": {
            "identity": {
                "methods": ["password"],
                "password": {
                    "user": {
                        "name": username,
                        "domain": {"id": "default"},
                        "password": password
                    }
                }
            },
            "scope": {
                "project": {
                    "id": project_id
                }
            }
        }
    }

    # L'URL per ottenere il token è l'endpoint di autenticazione + /auth/tokens
    token_url = f"{auth_url.rstrip('/')}/auth/tokens"
    
    log.info(f"Requesting token from: {token_url}")
    response = requests.post(token_url, json=auth_payload)
    response.raise_for_status()

    # Il token viene restituito negli header della risposta!
    token = response.headers['X-Subject-Token']
    
    # Il corpo della risposta contiene il "service catalog" con gli URL di tutti i servizi
    service_catalog = response.json()['token']['catalog']
    
    # Troviamo l'URL del servizio "compute" per la nostra regione
    compute_endpoint = None
    for service in service_catalog:
        if service['type'] == 'compute':
            for endpoint in service['endpoints']:
                if endpoint['region_id'] == region and endpoint['interface'] == 'public':
                    compute_endpoint = endpoint['url']
                    break
            if compute_endpoint:
                break
    
    if not token or not compute_endpoint:
        raise RuntimeError("Could not retrieve token or compute endpoint from OpenStack.")

    log.info(f"Token obtained successfully. Compute endpoint: {compute_endpoint}")
    return token, compute_endpoint

def _make_compute_request(method, path, token, compute_endpoint, data=None):
    """Fa una richiesta all'API di OpenStack Compute."""
    url = f"{compute_endpoint.rstrip('/')}{path}"
    log.info(f"Making request to: {url}")
    
    headers = {
        "X-Auth-Token": token,
        "Content-Type": "application/json"
    }
    
    response = requests.request(method, url, headers=headers, json=data)
    response.raise_for_status()
    
    # Alcune risposte (es. POST) potrebbero non avere corpo
    if response.status_code != 204 and response.content:
        return response.json()
    return None

def lambda_handler(event, context):
    try:
        _require_envs()
        
        # Verifica API key prima di tutto
        try:
            _check_api_key(event)
        except RuntimeError as e:
            log.warning(f"API key validation failed: {str(e)}")
            return _json(401, {"error": "unauthorized", "message": str(e)})
        
        qs = (event or {}).get("queryStringParameters") or {}
        action = (qs.get("action") or "status").lower().strip()

        allowed = {"start", "stop", "status"}
        if action not in allowed:
            return _json(400, {"error": "invalid_action", "allowed": list(allowed)})

        region = qs.get("region") or os.environ.get("OS_REGION_NAME")
        instance_id = qs.get("instance_id") or os.environ.get("INSTANCE_ID")

        missing = []
        if not region:
            missing.append("region")
        if not instance_id:
            missing.append("instance_id")
        if missing:
            return _json(400, {"error": "missing_parameters", "missing": missing})

        # Ottieni un token fresco a ogni esecuzione!
        token, compute_endpoint = _get_token_and_compute_url(region)

        server_data = _make_compute_request("GET", f"/servers/{instance_id}", token, compute_endpoint)
        if not server_data or "server" not in server_data:
             return _json(404, {"error": "instance_not_found or invalid response", "instance_id": instance_id})
        
        server = server_data["server"]
        state = server["status"].upper()
        log.info(f"Instance {instance_id} state: {state}")

        if action == "status":
            return _json(200, {"instance_id": instance_id, "state": state})

        if action == "start":
            if state in {"SHELVED", "SHELVED_OFFLOADED"}:
                _make_compute_request("POST", f"/servers/{instance_id}/action", token, compute_endpoint, {"unshelve": None})
                return _json(200, {"message": "unshelve requested", "from_state": state})
            if state == "ACTIVE":
                return _json(200, {"message": "already active"})
            _make_compute_request("POST", f"/servers/{instance_id}/action", token, compute_endpoint, {"os-start": None})
            return _json(200, {"message": "start requested", "from_state": state})

        if action == "stop":
            if state in {"SHELVED", "SHELVED_OFFLOADED"}:
                return _json(200, {"message": "already shelved"})
            if state == "ACTIVE":
                _make_compute_request("POST", f"/servers/{instance_id}/action", token, compute_endpoint, {"shelve": None})
                return _json(200, {"message": "shelve requested from ACTIVE"})
            if state == "SHUTOFF":
                _make_compute_request("POST", f"/servers/{instance_id}/action", token, compute_endpoint, {"shelve": None})
                return _json(200, {"message": "shelve requested from SHUTOFF"})
            # fallback: try shelve anyway
            _make_compute_request("POST", f"/servers/{instance_id}/action", token, compute_endpoint, {"shelve": None})
            return _json(200, {"message": "shelve requested", "from_state": state})

    except Exception as e:
        log.exception("Unhandled error")
        # Includi più dettagli nell'errore per il debug
        error_detail = f"{type(e).__name__}: {str(e)}"
        return _json(500, {"error": "internal_error", "detail": error_detail})
