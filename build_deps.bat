@echo off

REM Build dependencies using Docker with Amazon Linux
echo Building dependencies for AWS Lambda (Linux)...

REM Create output directory
if not exist lambda_deps mkdir lambda_deps

REM Build Docker image
echo Building Docker image...
docker build -t lambda-deps-builder .

REM Extract dependencies
echo Extracting dependencies...
docker run --rm -v "%cd%\lambda_deps:/output" lambda-deps-builder

echo Dependencies extracted to lambda_deps\ folder

REM Copy lambda function
echo Copying lambda_function.py...
copy lambda_function.py lambda_deps\

REM Create deployment zip
echo Creating deployment zip...
cd lambda_deps
powershell -command "Compress-Archive -Path * -DestinationPath ..\lambda_deployment.zip -Force"
cd ..

echo.
echo ✅ Deployment package created: lambda_deployment.zip
echo Ready to upload to AWS Lambda!
pause
