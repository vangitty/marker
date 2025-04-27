import os
import subprocess
import tempfile
import logging
import shutil # Zum Löschen von Verzeichnissen
from flask import Flask, request, jsonify
import glob 

# --- Konfiguration ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s:%(name)s:%(message)s')

app = Flask(__name__)
app.logger.setLevel(logging.INFO) 

MARKER_CMD = "marker" 
FLASK_PORT = int(os.environ.get("PORT", 5000))

# --- API Endpunkt ---
@app.route('/convert', methods=['POST'])
def convert_pdf():
    app.logger.info("Received PDF conversion request for /convert")

    if 'file' not in request.files:
        app.logger.warning("No file part in the request")
        return jsonify({"error": "No file part in the request"}), 400
    
    file = request.files['file']
    # Original-Dateinamen für später merken
    original_filename = file.filename 
    if original_filename == '' or not original_filename.lower().endswith(".pdf"):
        app.logger.warning(f"No file selected or file is not a PDF: {original_filename}")
        return jsonify({"error": "No PDF file selected"}), 400

    tmp_input_dir = None
    tmp_output_dir = None
    markdown_output = None
    error_output = None
    output_md_path_found = None # Pfad zur gefundenen Markdown-Datei

    try:
        # 1. Temporären Input-Ordner erstellen
        tmp_input_dir = tempfile.mkdtemp()
        app.logger.info(f"Created temporary input directory {tmp_input_dir}")

        # 2. Pfad zur PDF *innerhalb* des Input-Ordners erstellen
        # Wichtig: Verwende den originalen Dateinamen, damit Marker ihn verarbeiten kann
        tmp_input_pdf_path = os.path.join(tmp_input_dir, original_filename)
        file.save(tmp_input_pdf_path)
        app.logger.info(f"Saved uploaded PDF to temporary input directory: {tmp_input_pdf_path}")

        # 3. Temporären Output-Ordner erstellen
        tmp_output_dir = tempfile.mkdtemp()
        app.logger.info(f"Created temporary output directory {tmp_output_dir}")

        # 4. --- Marker Subprocess Aufruf (mit Input- UND Output-Ordner) ---
        try:
            # Marker aufrufen: marker <input_FOLDER> <output_FOLDER>
            cmd_list = [MARKER_CMD, tmp_input_dir, tmp_output_dir] 
            
            app.logger.info(f"Executing command: {' '.join(cmd_list)}")
            process = subprocess.run(
                cmd_list,
                capture_output=True, 
                text=True,
                encoding='utf-8',
                check=True 
            )
            app.logger.info("Marker execution apparently successful (return code 0).")
            if process.stderr:
                 app.logger.warning(f"Marker stderr: {process.stderr.strip()}")

            # 5. Finde und lese die erzeugte .md Datei im Output-Ordner
            # Der Dateiname sollte dem Original entsprechen, aber mit .md
            expected_output_filename = f"{os.path.splitext(original_filename)[0]}.md"
            output_md_path_expected = os.path.join(tmp_output_dir, expected_output_filename)
            
            if os.path.exists(output_md_path_expected):
                output_md_path_found = output_md_path_expected
                app.logger.info(f"Found expected output markdown file at: {output_md_path_found}")
                try:
                    with open(output_md_path_found, 'r', encoding='utf-8') as f:
                        markdown_output = f.read()
                    app.logger.info(f"Read markdown. Length: {len(markdown_output)}")
                except Exception as read_err:
                    app.logger.error(f"Could not read output file {output_md_path_found}: {read_err}")
                    error_output = f"Could not read output file: {read_err}"
            else:
                 app.logger.error(f"Marker ran but expected output file '{expected_output_filename}' not found in output directory '{tmp_output_dir}'.")
                 # Liste den Inhalt des Output-Ordners zur Diagnose auf
                 try:
                     dir_content = os.listdir(tmp_output_dir)
                     app.logger.error(f"Actual content of output dir: {dir_content}")
                 except Exception as list_err:
                      app.logger.error(f"Could not list output directory content: {list_err}")
                 error_output = "Marker ran but markdown file not found in output directory."

        # ... (Rest der Fehlerbehandlung: CalledProcessError, FileNotFoundError, etc.) ...
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
        # --- Temporäre Ordner sicher löschen ---
        if tmp_input_dir and os.path.exists(tmp_input_dir):
            try:
                shutil.rmtree(tmp_input_dir) 
                app.logger.info(f"Removed temporary input directory {tmp_input_dir}")
            except OSError as e:
                app.logger.error(f"Error removing temporary input directory {tmp_input_dir}: {e}")
        
        if tmp_output_dir and os.path.exists(tmp_output_dir):
            try:
                shutil.rmtree(tmp_output_dir) 
                app.logger.info(f"Removed temporary output directory {tmp_output_dir}")
            except OSError as e:
                app.logger.error(f"Error removing temporary output directory {tmp_output_dir}: {e}")


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
