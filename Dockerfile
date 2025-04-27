# === Base Image ===
FROM python:3.11-slim-bullseye

# === System Dependencies (Pandoc) ===
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y --no-install-recommends \
    pandoc \
    poppler-utils \
    which \
# Cleanup (gehört zum selben RUN-Befehl)
&& apt-get clean \
&& rm -rf /var/lib/apt/lists/*

# === Setup Application Directory and User ===
WORKDIR /app
# Erstelle User UND stelle sicher, dass sein Home + Cache-Verzeichnis ihm gehört
RUN useradd --create-home --shell /bin/bash appuser \
    && mkdir -p /app/cache/datalab \
    && chmod -R 777 /app/cache \
    && chown -R appuser:appuser /app

# === Install Python Dependencies ===
# Kopiere requirements.txt (Besitzer root ist ok)
COPY requirements.txt . 
# Wechsle zum non-root user
USER appuser

# Set environment variables to redirect cache paths
ENV XDG_CACHE_HOME=/app/cache
ENV PYTHONUSERBASE=/app/.local
# Force spawn instead of fork for multiprocessing
ENV PYTHONMULTIPROCESSING=spawn
# Force marker to use single process
ENV MARKER_FORCE_SINGLE_PROCESS=1

# Installiere Pakete als appuser ins Home-Verzeichnis
RUN pip install --no-cache-dir --user -r requirements.txt

# === Update PATH (als appuser) ===
# Füge Python User bin zum PATH hinzu - mehrere mögliche Pfade
ENV PATH="/app/.local/bin:/home/appuser/.local/bin:${PATH}"

# === Create wrapper script ===
USER root
COPY marker-wrapper.sh /app/marker-wrapper.sh
RUN chmod +x /app/marker-wrapper.sh && chown appuser:appuser /app/marker-wrapper.sh

# Find where marker is actually installed and create a symbolic link if needed
RUN su - appuser -c "pip show -f marker-pdf | grep -E 'bin/marker$' || true" > /tmp/marker_location.txt \
    && if [ -s /tmp/marker_location.txt ]; then \
         MARKER_PATH=$(cat /tmp/marker_location.txt | tr -d ' '); \
         if [ -n "$MARKER_PATH" ]; then \
           SITE_PACKAGES=$(pip show marker-pdf | grep Location | cut -d' ' -f2); \
           FULL_PATH="$SITE_PACKAGES/$MARKER_PATH"; \
           if [ -f "$FULL_PATH" ]; then \
             echo "Found marker at $FULL_PATH"; \
             mkdir -p /app/.local/bin; \
             ln -sf "$FULL_PATH" /app/.local/bin/marker; \
             chown -R appuser:appuser /app/.local; \
           fi; \
         fi; \
       fi

USER appuser

# === Copy Application Code ===
# Kopiere app.py (Besitzer wird appuser sein)
COPY app.py . 

# === Debug: Show where marker is actually installed ===
RUN which marker || echo "marker not in path" \
    && find / -name marker -type f 2>/dev/null || echo "marker not found"

# === Expose Port and Define Start Command ===
EXPOSE 5000
# CMD läuft als appuser
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--timeout", "300", "app:app"]
