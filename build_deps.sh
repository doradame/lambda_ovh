#!/bin/bash

# Build dependencies using Docker with Amazon Linux
echo "Building dependencies for AWS Lambda (Linux)..."

# Create output directory
mkdir -p lambda_deps

# Build Docker image
docker build -t lambda-deps-builder .

# Extract dependencies
docker run --rm -v "$(pwd)/lambda_deps:/output" lambda-deps-builder

echo "Dependencies extracted to lambda_deps/ folder"

# Copy lambda function
echo "Copying lambda_function.py..."
cp lambda_function.py lambda_deps/

# Create deployment zip
echo "Creating deployment zip..."
cd lambda_deps
zip -r ../lambda_deployment.zip .
cd ..

echo "✅ Deployment package created: lambda_deployment.zip"
echo "Ready to upload to AWS Lambda!"
