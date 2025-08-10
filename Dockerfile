# Use Amazon Linux 2 base image (same as Lambda runtime)
FROM public.ecr.aws/lambda/python:3.10

# Copy requirements
COPY requirements.txt .

# Install dependencies in the same directory structure as Lambda
# Exclude problematic packages that aren't needed
RUN pip install -r requirements.txt -t /var/task/ && \
    find /var/task -name "psutil*" -exec rm -rf {} + 2>/dev/null || true && \
    find /var/task -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true

# Create a script to copy dependencies to host
RUN echo '#!/bin/bash' > /extract_deps.sh && \
    echo 'cp -r /var/task/* /output/' >> /extract_deps.sh && \
    chmod +x /extract_deps.sh

ENTRYPOINT ["/extract_deps.sh"]
