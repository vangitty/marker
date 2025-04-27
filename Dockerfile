# === Base Image ===
FROM python:3.11-slim-bullseye

# === System Dependencies (Pandoc) ===
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y --no-install-recommends \
    pandoc \
    poppler-utils \
# Cleanup (gehört zum selben RUN-Befehl)
&& apt-get clean \
&& rm -rf /var/lib/apt/lists/*

# === Setup Application Directory and User ===
WORKDIR /app
# Erstelle User UND stelle sicher, dass sein Home + Cache-Verzeichnis ihm gehört
RUN useradd --create-home --shell /bin/bash appuser \
    && mkdir -p /home/appuser/.cache \
    && mkdir -p /home/appuser/.cache/datalab \
    && chmod -R 777 /home/appuser/.cache \
    && chown -R appuser:appuser /home/appuser

# === Install Python Dependencies ===
# Kopiere requirements.txt (Besitzer root ist ok)
COPY requirements.txt . 
# Wechsle zum non-root user
USER appuser
# Installiere Pakete als appuser ins Home-Verzeichnis
RUN pip install --no-cache-dir --user -r requirements.txt

# === Update PATH (als appuser) ===
# Füge Python User bin zum PATH hinzu
ENV PATH="/home/appuser/.local/bin:${PATH}"

# === Copy Application Code ===
# Kopiere app.py (Besitzer wird appuser sein)
COPY app.py . 

# === Expose Port and Define Start Command ===
EXPOSE 5000
# CMD läuft als appuser
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--timeout", "300", "app:app"]
