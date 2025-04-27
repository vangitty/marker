import os
import subprocess
import tempfile
import logging
import shutil # Zum Löschen von Verzeichnissen
from flask import Flask, request, jsonify

# --- Konfiguration ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s:%(name)s:%(message)s')

app = Flask(__name__)
app.logger.setLevel(logging.INFO) 

MARKER_CMD = "marker" # Marker sollte im PATH sein nach pip install --user und ENV PATH
FLASK_PORT = int(os.environ.get("PORT", 5000))

# --- API Endpunkt ---
@app.route('/convert', methods=['POST'])
def convert_pdf():
    """
    Nimmt eine PDF-Datei per Form-Data ('file') entgegen
    und gibt Markdown im JSON-Body zurück ({ "markdown": "..." }).
    """
    app.logger.info("Received PDF conversion request for /convert")

    if 'file' not in request.files:
        app.logger.warning("No file part in the request")
        return jsonify({"error": "No file part in the request"}), 400
    
    file = request.files['file']
    if file.filename == '' or not file.filename.lower().endswith(".pdf"):
        app.logger.warning(f"No file selected or file is not a PDF: {file.filename}")
        return jsonify({"error": "No PDF file selected"}), 400

    tmp_input_pdf_path = None
    tmp_output_dir = None
    markdown_output = None
    error_output = None

    try:
        # 1. Temporäre Input-Datei erstellen
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp_file:
            file.save(tmp_file.name)
            tmp_input_pdf_path = tmp_file.name 
            app.logger.info(f"Saved uploaded PDF temporarily to {tmp_input_pdf_path}")

        # 2. Temporäres Output-Verzeichnis erstellen
        tmp_output_dir = tempfile.mkdtemp()
        app.logger.info(f"Created temporary output directory {tmp_output_dir}")

        # 3. --- Marker Subprocess Aufruf ---
        try:
            # Marker aufrufen: marker <input_pdf> <output_dir>
            # Füge hier ggf. weitere Marker-Argumente hinzu (siehe Marker Doku, z.B. --batch_multiplier)
            cmd_list = [MARKER_CMD, tmp_input_pdf_path, tmp_output_dir] 
            
            app.logger.info(f"Executing command: {' '.join(cmd_list)}")
            # Hinweis: Marker kann sehr lange laufen! Gunicorn Timeout beachten.
            process = subprocess.run(
                cmd_list,
                capture_output=True, 
                text=True,
                encoding='utf-8',
                check=True # Löst CalledProcessError bei Fehler aus
            )
            # Marker gibt viel auf stdout/stderr aus, nicht unbedingt das Ergebnis
            app.logger.info("Marker execution apparently successful (return code 0).")
            app.logger.debug(f"Marker stdout: {process.stdout.strip()}")
            # Wichtige Fehler könnten auch in stderr stehen, auch bei return code 0
            if process.stderr:
                 app.logger.warning(f"Marker stderr: {process.stderr.strip()}")


            # 4. Finde und lese die erzeugte .md Datei
            output_md_path = None
            found_md = False
            for filename in os.listdir(tmp_output_dir):
                if filename.lower().endswith(".md"):
                    output_md_path = os.path.join(tmp_output_dir, filename)
                    try:
                        with open(output_md_path, 'r', encoding='utf-8') as f:
                            markdown_output = f.read()
                        app.logger.info(f"Read markdown from {output_md_path}. Length: {len(markdown_output)}")
                        found_md = True
                        break # Nimm die erste gefundene .md Datei
                    except Exception as read_err:
                        app.logger.error(f"Could not read output file {output_md_path}: {read_err}")
                        error_output = f"Could not read output file: {read_err}"
                        break # Breche Suche ab, wenn Lesen fehlschlägt
            
            if not found_md and not error_output:
                 app.logger.error("Marker ran but no .md file found in output directory.")
                 error_output = "Marker ran but no markdown file produced."

        except subprocess.CalledProcessError as e:
            app.logger.error(f"Marker execution failed with code {e.returncode}")
            app.logger.error(f"Marker stderr: {e.stderr.strip()}")
            error_output = e.stderr.strip()
        except FileNotFoundError:
             app.logger.error(f"Error: The command '{MARKER_CMD}' was not found.")
             error_output = f"Command not found: {MARKER_CMD}"
        except Exception as e:
            app.logger.exception("An unexpected error occurred during marker conversion.")
            error_output = "Internal server error"

    finally:
        # --- Temporäre Dateien und Verzeichnisse sicher löschen ---
        if tmp_input_pdf_path and os.path.exists(tmp_input_pdf_path):
            try:
                os.remove(tmp_input_pdf_path)
                app.logger.info(f"Removed temporary input file {tmp_input_pdf_path}")
            except OSError as e:
                app.logger.error(f"Error removing temporary input file {tmp_input_pdf_path}: {e}")
        
        if tmp_output_dir and os.path.exists(tmp_output_dir):
            try:
                shutil.rmtree(tmp_output_dir) # Verzeichnis rekursiv löschen
                app.logger.info(f"Removed temporary output directory {tmp_output_dir}")
            except OSError as e:
                app.logger.error(f"Error removing temporary output directory {tmp_output_dir}: {e}")


    # --- Antwort senden ---
    if error_output:
         # Fehlername im JSON anpassen
         return jsonify({"error": "Marker conversion failed", "details": error_output}), 500
    elif markdown_output is None:
        # Fallback, falls aus irgendeinem Grund kein Markdown gelesen wurde, aber kein Fehler gemeldet wurde
         app.logger.error("Conversion finished without errors, but no markdown content was retrieved.")
         return jsonify({"error": "Marker conversion failed", "details": "No markdown content retrieved."}), 500
    else:
        # Erfolgreich
        return jsonify({"markdown": markdown_output})

# --- Startpunkt für den Server ---
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=FLASK_PORT, debug=False)
