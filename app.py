import os
import subprocess
import tempfile
import logging
import shutil # Nicht mehr benötigt für Output-Ordner-Löschung
from flask import Flask, request, jsonify
import glob # Zum Suchen von Dateien

# --- Konfiguration ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s:%(name)s:%(message)s')

app = Flask(__name__)
app.logger.setLevel(logging.INFO) 

MARKER_CMD = "marker" 
FLASK_PORT = int(os.environ.get("PORT", 5000))
# Arbeitsverzeichnis im Container (aus Dockerfile)
WORKDIR = "/app" 

# --- API Endpunkt ---
@app.route('/convert', methods=['POST'])
def convert_pdf():
    app.logger.info("Received PDF conversion request for /convert")

    if 'file' not in request.files:
        app.logger.warning("No file part in the request")
        return jsonify({"error": "No file part in the request"}), 400
    
    file = request.files['file']
    if file.filename == '' or not file.filename.lower().endswith(".pdf"):
        app.logger.warning(f"No file selected or file is not a PDF: {file.filename}")
        return jsonify({"error": "No PDF file selected"}), 400

    tmp_input_pdf_path = None
    markdown_output = None
    error_output = None
    output_md_path_found = None # Pfad zur gefundenen Markdown-Datei

    try:
        # 1. Temporäre Input-Datei erstellen
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp_file:
            file.save(tmp_file.name)
            tmp_input_pdf_path = tmp_file.name 
            app.logger.info(f"Saved uploaded PDF temporarily to {tmp_input_pdf_path}")

        # Erwarteten Basisnamen für die Output-Datei ermitteln
        input_basename = os.path.splitext(os.path.basename(tmp_input_pdf_path))[0]
        expected_output_filename = f"{input_basename}.md"
        app.logger.info(f"Expecting output file named: {expected_output_filename}")

        # 2. --- Marker Subprocess Aufruf (NUR mit Input-Datei) ---
        try:
            # Marker nur mit Input-PDF aufrufen
            cmd_list = [MARKER_CMD, tmp_input_pdf_path] 
            
            app.logger.info(f"Executing command: {' '.join(cmd_list)}")
            # Hinweis: Lange Laufzeit möglich! Gunicorn Timeout beachten.
            # Führe den Prozess im WORKDIR aus, falls die Ausgabe dort landet
            process = subprocess.run(
                cmd_list,
                capture_output=True, 
                text=True,
                encoding='utf-8',
                check=True, # Löst CalledProcessError bei Fehler aus
                cwd=WORKDIR # Arbeitsverzeichnis setzen!
            )
            app.logger.info("Marker execution apparently successful (return code 0).")
            # Logge immer stderr, falls es Hinweise gibt
            if process.stderr:
                 app.logger.warning(f"Marker stderr: {process.stderr.strip()}")


            # 3. Suche nach der Output-Datei (zuerst im WORKDIR, dann im Temp-Dir)
            possible_paths = [
                os.path.join(WORKDIR, expected_output_filename),
                os.path.join(os.path.dirname(tmp_input_pdf_path), expected_output_filename) # = /tmp/...
            ]
            
            found_md = False
            for potential_path in possible_paths:
                if os.path.exists(potential_path):
                    output_md_path_found = potential_path
                    app.logger.info(f"Found output markdown file at: {output_md_path_found}")
                    try:
                        with open(output_md_path_found, 'r', encoding='utf-8') as f:
                            markdown_output = f.read()
                        app.logger.info(f"Read markdown. Length: {len(markdown_output)}")
                        found_md = True
                        break # Suche beenden
                    except Exception as read_err:
                        app.logger.error(f"Could not read output file {output_md_path_found}: {read_err}")
                        error_output = f"Could not read output file: {read_err}"
                        break # Suche bei Lesefehler abbrechen
            
            if not found_md and not error_output:
                 app.logger.error(f"Marker ran but expected output file '{expected_output_filename}' not found in searched paths.")
                 error_output = "Marker ran but markdown file not found."

        # ... (Rest der Fehlerbehandlung bleibt ähnlich) ...
        except subprocess.CalledProcessError as e:
            app.logger.error(f"Marker execution failed with code {e.returncode}")
            app.logger.error(f"Marker stderr: {e.stderr.strip()}")
            error_output = e.stderr.strip() # stderr enthält jetzt die wichtige Info
        except FileNotFoundError:
             app.logger.error(f"Error: The command '{MARKER_CMD}' was not found.")
             error_output = f"Command not found: {MARKER_CMD}"
        except Exception as e:
            app.logger.exception("An unexpected error occurred during marker conversion.")
            error_output = "Internal server error"

    finally:
        # --- Temporäre Dateien sicher löschen ---
        if tmp_input_pdf_path and os.path.exists(tmp_input_pdf_path):
            try:
                os.remove(tmp_input_pdf_path)
                app.logger.info(f"Removed temporary input file {tmp_input_pdf_path}")
            except OSError as e:
                app.logger.error(f"Error removing temporary input file {tmp_input_pdf_path}: {e}")
        # Lösche die Output-Datei, falls sie gefunden wurde
        if output_md_path_found and os.path.exists(output_md_path_found):
             try:
                os.remove(output_md_path_found)
                app.logger.info(f"Removed temporary output file {output_md_path_found}")
             except OSError as e:
                app.logger.error(f"Error removing temporary output file {output_md_path_found}: {e}")
        # Temporäres Output-Verzeichnis wird nicht mehr benötigt/erstellt


    # --- Antwort senden ---
    if error_output:
         return jsonify({"error": "Marker conversion failed", "details": error_output}), 500
    elif markdown_output is None:
         app.logger.error("Conversion finished without errors, but no markdown content was retrieved.")
         return jsonify({"error": "Marker conversion failed", "details": "No markdown content retrieved."}), 500
    else:
        return jsonify({"markdown": markdown_output})

# --- Startpunkt für den Server ---
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=FLASK_PORT, debug=False)
