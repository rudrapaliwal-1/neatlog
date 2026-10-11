# Test harness only; does not change the protected verification image.
FROM sentinel-verification-lab:latest
USER root
COPY requirements.txt /tmp/backend-test-requirements.txt
RUN pip install --no-cache-dir -r /tmp/backend-test-requirements.txt
USER sandboxuser
WORKDIR /workspace
ENV PYTHONDONTWRITEBYTECODE=1
