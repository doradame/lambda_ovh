import json
import os
import logging
import requests

log = logging.getLogger()
log.setLevel(logging.INFO)

# API KEY CONFIGURATION
# ====================
# To enable API key authentication, set ENABLE_API_KEY = True
# and configure the API_KEY environment variable.
# 
# When disabled (ENABLE_API_KEY = False), the lambda works without 
# authentication to maintain backward compatibility with previous versions.

# Required environment variables: we're back to username/password!
# REGION and INSTANCE_ID can be passed via query string.
REQUIRED_ENVS = [
    "OS_AUTH_URL",      # This is the endpoint for authentication
    "OS_USERNAME",
    "OS_PASSWORD",
    "OS_PROJECT_ID",
]

# API key configuration: set to True to enable authentication
ENABLE_API_KEY = False  # Disabled for backward compatibility

# If API key is enabled, add API_KEY to requirements
if ENABLE_API_KEY:
    REQUIRED_ENVS.append("API_KEY")

def _json(status, body):
    return {"statusCode": status, "headers": {"Content-Type": "application/json"},
            "body": json.dumps(body)}

def _require_envs():
    missing = [k for k in REQUIRED_ENVS if not os.environ.get(k)]
    if missing:
        raise RuntimeError(f"Missing required envs: {', '.join(missing)}")

def _check_api_key(event):
    """
    Verifies the API key from the request if enabled.
    The API key can be provided via:
    - Header 'X-API-Key'
    - Query parameter 'api_key'
    
    If ENABLE_API_KEY is False, this function does nothing.
    """
    if not ENABLE_API_KEY:
        log.info("API key authentication is disabled")
        return  # Skip API key validation
    
    expected_api_key = os.environ.get("API_KEY")
    if not expected_api_key:
        raise RuntimeError("API_KEY environment variable not configured")
    
    # Check in headers
    headers = (event or {}).get("headers") or {}
    provided_api_key = headers.get("X-API-Key") or headers.get("x-api-key")
    
    # If not found in headers, check query parameters
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
    Authenticate with username/password to get a token and Compute service endpoint.

    :param region: region name to use for the service catalog
    """
    auth_url = os.environ["OS_AUTH_URL"]
    username = os.environ["OS_USERNAME"]
    password = os.environ["OS_PASSWORD"]
    project_id = os.environ["OS_PROJECT_ID"]

    # OpenStack v3 authentication request body
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

    # The URL to get the token is the authentication endpoint + /auth/tokens
    token_url = f"{auth_url.rstrip('/')}/auth/tokens"
    
    log.info(f"Requesting token from: {token_url}")
    response = requests.post(token_url, json=auth_payload)
    response.raise_for_status()

    # The token is returned in the response headers!
    token = response.headers['X-Subject-Token']
    
    # The response body contains the "service catalog" with URLs of all services
    service_catalog = response.json()['token']['catalog']
    
    # Find the URL of the "compute" service for our region
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
    """Makes a request to the OpenStack Compute API."""
    url = f"{compute_endpoint.rstrip('/')}{path}"
    log.info(f"Making request to: {url}")
    
    headers = {
        "X-Auth-Token": token,
        "Content-Type": "application/json"
    }
    
    response = requests.request(method, url, headers=headers, json=data)
    response.raise_for_status()
    
    # Some responses (e.g., POST) might not have a body
    if response.status_code != 204 and response.content:
        return response.json()
    return None

def lambda_handler(event, context):
    try:
        _require_envs()
        
        # Verify API key only if enabled
        if ENABLE_API_KEY:
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

        # Get a fresh token on each execution!
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
        # Include more details in the error for debugging
        error_detail = f"{type(e).__name__}: {str(e)}"
        return _json(500, {"error": "internal_error", "detail": error_detail})
