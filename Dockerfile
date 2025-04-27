# === Base Image ===
FROM python:3.11-slim-bullseye

# === Set environment variables ===
ENV DEBIAN_FRONTEND=noninteractive
# Force marker to use single process mode
ENV MARKER_FORCE_SINGLE_PROCESS=1
# Force spawn instead of fork for multiprocessing - critical for ARM64
ENV PYTHONMULTIPROCESSING=spawn
# Disable Ray if marker uses it
ENV RAY_DISABLE=1
ENV RAY_DISABLE_IMPORT_WARNING=1
# Redirect cache paths
ENV XDG_CACHE_HOME=/app/cache
ENV PYTHONUSERBASE=/app/.local
# Set timeouts
ENV MARKER_TIMEOUT=60

# === System Dependencies ===
RUN apt-get update && apt-get install -y --no-install-recommends \
    pandoc \
    poppler-utils \
    procps \
    # poppler-utils enthält bereits pdftotext
    xpdf \
    # For debugging
    htop \
    vim \
    curl \
    # ARM64 specific dependencies
    python3-dev \
    build-essential \
    # Cleanup
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# === Setup Application Directory and User ===
WORKDIR /app
RUN useradd --create-home --shell /bin/bash appuser \
    && mkdir -p /app/cache/datalab \
    && chmod -R 777 /app/cache \
    && chown -R appuser:appuser /app

# === Install Python Dependencies ===
COPY requirements.txt .
USER appuser

# Update PATH
ENV PATH="/app/.local/bin:/home/appuser/.local/bin:${PATH}"

# Install packages as appuser
RUN pip install --no-cache-dir --user -r requirements.txt

# === Create wrapper script ===
USER root
COPY marker-wrapper.sh /app/marker-wrapper.sh
RUN chmod +x /app/marker-wrapper.sh && chown appuser:appuser /app/marker-wrapper.sh

USER appuser

# === Copy Application Code ===
COPY app.py .

# === Health check ===
HEALTHCHECK --interval=30s --timeout=30s --start-period=5s --retries=3 CMD curl -f http://localhost:5000/ || exit 1

# === Expose Port and Define Start Command ===
EXPOSE 5000
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--timeout", "300", "app:app"]
