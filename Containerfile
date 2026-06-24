# GS-VerCount - Replication verification and scheduling tool
# Containerfile for Podman/Docker

FROM python:3.11-slim-bookworm

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    JT400_JAR=/opt/jt400/jt400.jar

# Install system dependencies including ODBC for MSSQL
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    unixodbc-dev \
    openjdk-17-jre-headless \
    curl \
    ca-certificates \
    gnupg \
    && rm -rf /var/lib/apt/lists/*

# Install Microsoft ODBC Driver for SQL Server
RUN curl -fsSL https://packages.microsoft.com/keys/microsoft.asc | gpg --dearmor -o /usr/share/keyrings/microsoft-prod.gpg && \
    curl https://packages.microsoft.com/config/debian/12/prod.list | tee /etc/apt/sources.list.d/mssql-release.list && \
    apt-get update && \
    ACCEPT_EULA=Y apt-get install -y msodbcsql18 && \
    rm -rf /var/lib/apt/lists/*

# Download jt400.jar if needed (we rely on qadmcli structure)
RUN mkdir -p /opt/jt400

# Install qadmcli dependency
COPY qadmcli /opt/qadmcli
COPY lib/jt400.jar /opt/jt400/jt400.jar

RUN pip install --upgrade pip && \
    cd /opt/qadmcli && pip install .[agent] && \
    pip install fastapi uvicorn websockets requests pydantic aiofiles httpx

# Create app directory
WORKDIR /app

# Copy application code and sdk
COPY . /app/gs-vercount
COPY replica_msdk /app/replica_msdk
# Copy connection profiles
COPY config /app/gs-vercount/config

# Also set PYTHONPATH so imports work
ENV PYTHONPATH="/app"

# Make sure required directories exist with right permissions
RUN mkdir -p /app/gs-vercount/cache /app/gs-vercount/metrics /app/gs-vercount/logs /app/gs-vercount/reports

# Set default entrypoint to FastAPI
ENTRYPOINT ["uvicorn", "main:app", "--app-dir", "/app/gs-vercount/backend", "--host", "0.0.0.0", "--port", "8083"]
