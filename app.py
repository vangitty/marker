import os
import subprocess
import tempfile
import logging
import shutil # Wieder benötigt zum Löschen des Input-Ordners
from flask import Flask, request, jsonify
import glob 

# --- Konfiguration ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s:%(name)s:%(message)s')

app = Flask(__name__)
app.logger.setLevel(logging.INFO) 

MARKER_CMD = "marker" 
FLASK_PORT = int(os.environ.get("PORT", 5000))
WORKDIR = "/app" # Arbeitsverzeichnis, wo die Ausgabe landen könnte

# --- API Endpunkt ---
@app.route('/convert', methods=['POST'])
def convert_pdf():
    app.logger.info("Received PDF conversion request for /convert")

    if 'file' not in request.files:
        app.logger.warning("No file part in the request")
        return jsonify({"error": "No file part in the request"}), 400

    file = request.files['file']
    original_filename = file.filename 
    if original_filename == '' or not original_filename.lower().endswith(".pdf"):
        app.logger.warning(f"No file selected or file is not a PDF: {original_filename}")
        return jsonify({"error": "No PDF file selected"}), 400

    tmp_input_dir = None
    markdown_output = None
    error_output = None
    output_md_path_found = None # Pfad zur gefundenen Markdown-Datei im WORKDIR

    try:
        # 1. Temporären Input-Ordner erstellen
        tmp_input_dir = tempfile.mkdtemp()
        app.logger.info(f"Created temporary input directory {tmp_input_dir}")

        # 2. PDF *in* den Input-Ordner speichern
        tmp_input_pdf_path = os.path.join(tmp_input_dir, original_filename)
        file.save(tmp_input_pdf_path)
        app.logger.info(f"Saved uploaded PDF to temporary input directory: {tmp_input_pdf_path}")

        # Erwarteten Output-Dateinamen im WORKDIR (!) ermitteln
        expected_output_filename = f"{os.path.splitext(original_filename)[0]}.md"
        # Voller Pfad, wo wir die Datei nach dem Lauf erwarten
        output_md_path_expected_in_workdir = os.path.join(WORKDIR, expected_output_filename)
        app.logger.info(f"Expecting output file at: {output_md_path_expected_in_workdir}")


        # 3. --- Marker Subprocess Aufruf (NUR mit Input-Ordner) ---
        try:
            # Marker nur mit Input-Ordner aufrufen
            cmd_list = [MARKER_CMD, tmp_input_dir] 

            app.logger.info(f"Executing command: {' '.join(cmd_list)}")
            # Führe im WORKDIR aus, da wir die Ausgabe dort vermuten
            process = subprocess.run(
                cmd_list,
                capture_output=True, 
                text=True,
                encoding='utf-8',
                check=True,
                cwd=WORKDIR # Wichtig: Im Arbeitsverzeichnis ausführen
            )
            app.logger.info("Marker execution apparently successful (return code 0).")
            if process.stderr:
                 app.logger.warning(f"Marker stderr: {process.stderr.strip()}")

            # 4. Suche nach der Output-Datei im WORKDIR
            if os.path.exists(output_md_path_expected_in_workdir):
                output_md_path_found = output_md_path_expected_in_workdir
                app.logger.info(f"Found expected output markdown file at: {output_md_path_found}")
                try:
                    with open(output_md_path_found, 'r', encoding='utf-8') as f:
                        markdown_output = f.read()
                    app.logger.info(f"Read markdown. Length: {len(markdown_output)}")
                except Exception as read_err:
                    app.logger.error(f"Could not read output file {output_md_path_found}: {read_err}")
                    error_output = f"Could not read output file: {read_err}"
            else:
                 app.logger.error(f"Marker ran but expected output file '{expected_output_filename}' not found in workdir '{WORKDIR}'.")
                 error_output = "Marker ran but markdown file not found in workdir."

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
        # --- Temporäre Dateien und Ordner sicher löschen ---
        if tmp_input_dir and os.path.exists(tmp_input_dir):
            try:
                shutil.rmtree(tmp_input_dir) 
                app.logger.info(f"Removed temporary input directory {tmp_input_dir}")
            except OSError as e:
                app.logger.error(f"Error removing temporary input directory {tmp_input_dir}: {e}")

        # Lösche die Output-Datei im WORKDIR, falls sie gefunden wurde
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
