# Restricted Disposable Lab Environment for SENTINEL-X Verification (Layer 5)
FROM python:3.11-slim

# Install minimal system dependencies for patch application
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    patch \
    && rm -rf /var/lib/apt/lists/*

# Install Pytest
RUN pip install --no-cache-dir pytest

# Create restricted non-root user for execution
RUN useradd -m -u 1001 sandboxuser

# Create restricted workspace directory
WORKDIR /workspace
RUN chown -R sandboxuser:sandboxuser /workspace

# Environment configuration
ENV PYTHONPATH=/workspace
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Run as non-root unprivileged user
USER sandboxuser

# Default command
CMD ["pytest", "/workspace/verification/protected_tests", "-v"]
