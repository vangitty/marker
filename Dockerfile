# === Base Image ===
# Standard Python-Image. Marker/PyTorch benötigen keine spezielle Basis für CPU.
FROM python:3.11-slim-bullseye

# === System Dependencies ===
ENV DEBIAN_FRONTEND=noninteractive
# Marker benötigt evtl. keine speziellen apt-Pakete, aber Grundlegendes schadet nicht
# poppler-utils wird manchmal für PDF-Tools gebraucht, fügen wir es sicherheitshalber hinzu
RUN apt-get update && apt-get install -y --no-install-recommends \
    poppler-utils \
    # Füge hier weitere hinzu, falls Marker/PyTorch Fehler werfen
# Cleanup
&& apt-get clean \
&& rm -rf /var/lib/apt/lists/*

# === Setup Application Directory and User ===
WORKDIR /app
RUN useradd --create-home --shell /bin/bash appuser

# === Install Python Dependencies ===
# Kopiere requirements.txt zuerst (Besitzer root ist ok)
COPY requirements.txt . 
# Wechsle zum non-root user
USER appuser
# Installiere Pakete als appuser ins Home-Verzeichnis
# ACHTUNG: Dieser Schritt kann lange dauern und viel Speicherplatz benötigen (PyTorch)!
RUN pip install --no-cache-dir --user -r requirements.txt

# === Update PATH (als appuser) ===
# Füge Python User bin zum PATH hinzu (für gunicorn und ggf. marker, falls es dort landet)
ENV PATH="/home/appuser/.local/bin:${PATH}"

# === Copy Application Code ===
# Kopiere app.py (Besitzer wird appuser sein)
COPY app.py . 

# === Expose Port and Define Start Command ===
# Port für den Gunicorn-Server
EXPOSE 5000
# CMD läuft als appuser
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--timeout", "300", "app:app"]
# WICHTIG: --timeout 300 (5 Minuten) hinzugefügt, da Marker-Verarbeitung lange dauern kann! Passe ggf. an.
