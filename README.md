# Python Lambda Function for OpenStack Instance Management

This AWS Lambda function manages OpenStack instances via shelve/unshelve operations to control compute costs.

## Quick Start

1. **Clone and setup:**
   ```bash
   git clone <your-repo-url>
   cd lambda_ovh
   ```

2. **Build deployment package:**
   - Linux/macOS: `./build_deps.sh`
   - Windows: `build_deps.bat`

3. **Deploy to AWS Lambda:**
   - Upload `lambda_deployment.zip`
   - Set handler: `lambda_function.lambda_handler`
   - Configure environment variables (see below)

4. **Test:**
   - GET `https://your-lambda-url?action=status`

## Prerequisites

- **Docker** - Required for building Linux-compatible dependencies
- **AWS Lambda** - Function runtime environment
- **OpenStack credentials** - With appropriate permissions

## Project Structure

- `lambda_function.py`: main Lambda function file
- `requirements.txt`: Python dependencies
- `build_deps.sh` / `build_deps.bat`: deployment build scripts
- `Dockerfile`: Linux dependency builder
- `.gitignore`: excludes dependencies and cache files from Git

## Requirements

- **Python 3.10+**
- **Docker** (for building Linux-compatible dependencies)
- **OpenStack API access** with required permissions

## Deploy to AWS Lambda

### Option 1: Using Docker (Recommended for Linux compatibility)

**Linux/macOS:**
```bash
./build_deps.sh
```

**Windows:**
```cmd
build_deps.bat
```

Then upload `lambda_deployment.zip` to AWS Lambda and set the handler name to `lambda_function.lambda_handler`.

### Option 2: Direct install (may cause compatibility issues on macOS)

1. Install dependencies: `pip install -r requirements.txt -t .`
2. Zip the entire folder (including modules and `lambda_function.py`)
3. Upload the zip file to AWS Lambda as source code
4. Set the handler name to `lambda_function.lambda_handler`

**Note:** Option 1 is recommended as it ensures Linux compatibility for AWS Lambda.

## Local Development & Testing

1. **Setup local environment:**

   ```bash
   pip install -r requirements.txt -t .
   ```

2. **Configure test credentials:**
   Edit the `_set_test_env()` function in `lambda_function.py` with your OpenStack credentials.

3. **Run locally:**

   ```bash
   python lambda_function.py
   ```

4. **Test different actions:**
   Modify the `test_event` in the `__main__` block:

   ```python
   test_event = {
       "queryStringParameters": {
           "action": "status"  # or "start" or "stop"
       }
   }
   ```

## Environment Variables

### Environment Variables

Configure these environment variables in your AWS Lambda function:

```bash
# Required Variables
OS_AUTH_URL=https://auth.cloud.ovh.net/v3
OS_USERNAME=myuser
OS_PASSWORD=mypassword
OS_PROJECT_ID=9460d381e9714cc8af9cccb5dc86a271

# Optional if provided via query parameters
OS_REGION_NAME=GRA9
INSTANCE_ID=54cbb827-fc6c-40e8-bc38-c5876f4c0573
```

`OS_REGION_NAME` and `INSTANCE_ID` can be overridden by passing
`region` and `instance_id` as query string parameters when invoking the
Lambda function.

## API Usage

The Lambda function accepts GET requests with query parameters:

- `action` (required) - `status`, `start` or `stop`
- `region` (optional) - overrides `OS_REGION_NAME` environment variable
- `instance_id` (optional) - overrides `INSTANCE_ID` environment variable

Example: `?action=status&region=GRA9&instance_id=54cbb827-fc6c-40e8-bc38-c5876f4c0573`

## Handler Example

```python
def lambda_handler(event, context):
    # Manages OpenStack instances via shelve/unshelve operations
    return {
        'statusCode': 200,
        'body': json.dumps({"message": "Instance operation completed"})
    }
```

## Required Permissions

The OpenStack user must have permissions for:

- `compute:server:get` - Read instance information
- `compute:server:start` - Start instances
- `compute:server:shelve` - Shelve instances (requires image creation permissions)
- `compute:server:unshelve` - Unshelve instances

## Troubleshooting

**Common Issues:**

1. **Import errors on Lambda:** Use Docker build (Option 1) to ensure Linux compatibility
2. **403 Forbidden errors:** Check OpenStack user permissions for compute and image operations
3. **Connection timeouts:** Verify OpenStack credentials and network connectivity
4. **Instance not found:** Confirm the `INSTANCE_ID` value (env var or query parameter) is correct

## Notes

- Do not commit environment, cache, or build files (see `.gitignore`)
- For local testing, you can simulate the Lambda event
- Shelve operations may fail without proper OpenStack permissions for image creation