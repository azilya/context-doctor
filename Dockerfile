# Minimal Dockerfile for context-doctor
# Uses Python 3.12 slim image and installs the project via pip using pyproject.toml

FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Max concurrent threads for handling requests
ENV MAX_CONCURRENT_RULE_ANALYSES=1

WORKDIR /app

# Install minimal OS-level build dependencies (kept small but enough for many wheels)
RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copy project files
COPY src/pyproject.toml src/README.md /app/
COPY src/context_doctor /app/context_doctor

# Upgrade pip and install the package (pyproject.toml defines dependencies)
RUN python -m pip install --upgrade pip setuptools wheel \
    && pip install .

# Default port for uvicorn
EXPOSE 8000

# Run the ASGI application using uvicorn
CMD ["uvicorn", "context_doctor.fastapi_app:app", "--host", "0.0.0.0", "--port", "8000", "--timeout-keep-alive", "1200", "--timeout-graceful-shutdown", "1200"]
