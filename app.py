import os
import subprocess
import tempfile
import logging
import shutil 
from flask import Flask, request, jsonify
import glob 

# --- Konfiguration ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s:%(name)s:%(message)s')

app = Flask(__name__)
app.logger.setLevel(logging.INFO) 

# Use our wrapper script instead of direct marker command
MARKER_CMD = "/app/marker-wrapper.sh" 
FLASK_PORT = int(os.environ.get("PORT", 5000))
WORKDIR = "/app" 

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
    output_md_path_found = None # Pfad zur gefundenen Markdown-Datei

    try:
        # 1. Temporären Input-Ordner erstellen
        tmp_input_dir = tempfile.mkdtemp()
        app.logger.info(f"Created temporary input directory {tmp_input_dir}")

        # 2. PDF *in* den Input-Ordner speichern
        tmp_input_pdf_path = os.path.join(tmp_input_dir, original_filename)
        file.save(tmp_input_pdf_path)
        app.logger.info(f"Saved uploaded PDF to temporary input directory: {tmp_input_pdf_path}")

        # Erwarteten Output-Dateinamen ermitteln
        output_basename = f"{os.path.splitext(original_filename)[0]}.md"
        expected_output_path = os.path.join(tmp_input_dir, output_basename)
        app.logger.info(f"Expecting output file named: {output_basename}")

        # 3. --- Marker Subprocess Aufruf (mit korrekten Optionen) ---
        try:
            # Pass the input directory to marker
            # marker uses the directory containing the PDF, not the PDF file itself
            cmd_list = [
                MARKER_CMD, 
                tmp_input_dir,
                "--device", "cpu",
                "--ocr"
            ]
            
            app.logger.info(f"Executing command: {' '.join(cmd_list)}")
            
            # Führe im WORKDIR aus
            process = subprocess.run(
                cmd_list,
                capture_output=True, 
                text=True,
                encoding='utf-8',
                check=True,
                cwd=WORKDIR 
            )
            app.logger.info("Marker execution apparently successful (return code 0).")
            
            # stderr loggen, enthält oft wichtige Infos oder Warnungen
            if process.stderr:
                app.logger.warning(f"Marker stderr: {process.stderr.strip()}")

            # 4. Überprüfe ob Output-Datei existiert
            if os.path.exists(expected_output_path):
                app.logger.info(f"Found expected output file at: {expected_output_path}")
                try:
                    with open(expected_output_path, 'r', encoding='utf-8') as f:
                        markdown_output = f.read()
                    app.logger.info(f"Read markdown. Length: {len(markdown_output)}")
                except Exception as read_err:
                    app.logger.error(f"Could not read output file {expected_output_path}: {read_err}")
                    error_output = f"Could not read output file: {read_err}"
            else:
                app.logger.error(f"Marker ran but expected output file '{expected_output_path}' not found.")
                
                # Erweiterte Suche nach der Ausgabedatei
                found_files = glob.glob(f"{tmp_input_dir}/*.md")
                app.logger.info(f"Looking for any markdown files in directory. Found: {found_files}")
                
                if found_files:
                    # Nutze die erste gefundene MD-Datei
                    output_md_path_found = found_files[0]
                    app.logger.info(f"Using alternative found markdown file: {output_md_path_found}")
                    try:
                        with open(output_md_path_found, 'r', encoding='utf-8') as f:
                            markdown_output = f.read()
                        app.logger.info(f"Read markdown from alternative file. Length: {len(markdown_output)}")
                    except Exception as read_err:
                        app.logger.error(f"Could not read alternative output file: {read_err}")
                        error_output = f"Could not read alternative output file: {read_err}"
                else:
                    # Check if the file might be in the working directory instead
                    workdir_output = os.path.join(WORKDIR, output_basename)
                    if os.path.exists(workdir_output):
                        app.logger.info(f"Found output file in working directory: {workdir_output}")
                        try:
                            with open(workdir_output, 'r', encoding='utf-8') as f:
                                markdown_output = f.read()
                            app.logger.info(f"Read markdown from working directory. Length: {len(markdown_output)}")
                            output_md_path_found = workdir_output
                        except Exception as read_err:
                            app.logger.error(f"Could not read output file from working directory: {read_err}")
                            error_output = f"Could not read output file from working directory: {read_err}"
                    else:
                        error_output = "Marker ran but markdown file not found in any location."

        except subprocess.CalledProcessError as e:
            app.logger.error(f"Marker execution failed with code {e.returncode}")
            # Gib die stderr aus dem Prozess zurück, da sie oft den Grund enthält
            detailed_error = e.stderr.strip() if e.stderr else "No stderr output"
            app.logger.error(f"Marker stderr: {detailed_error}")
            error_output = detailed_error # Setze details auf stderr
        except FileNotFoundError:
            app.logger.error(f"Error: The command '{MARKER_CMD}' was not found.")
            error_output = f"Command not found: {MARKER_CMD}"
        except Exception as e:
            app.logger.exception("An unexpected error occurred during marker conversion.")
            error_output = f"Unexpected error: {str(e)}"

    finally:
        # --- Temporäre Dateien und Ordner sicher löschen ---
        if output_md_path_found and os.path.exists(output_md_path_found) and output_md_path_found.startswith(WORKDIR):
            try:
                os.remove(output_md_path_found)
                app.logger.info(f"Removed output file in working directory: {output_md_path_found}")
            except OSError as e:
                app.logger.error(f"Error removing output file in working directory: {e}")
                
        if tmp_input_dir and os.path.exists(tmp_input_dir):
            try:
                shutil.rmtree(tmp_input_dir) # Löscht den Ordner und seinen Inhalt
                app.logger.info(f"Removed temporary input directory {tmp_input_dir}")
            except OSError as e:
                app.logger.error(f"Error removing temporary input directory {tmp_input_dir}: {e}")

    # --- Antwort senden ---
    if error_output:
        # Gib die Details (oft stderr von marker) im JSON zurück
        return jsonify({"error": "Marker conversion failed", "details": error_output}), 500
    elif markdown_output is None:
        # Sollte nicht passieren, wenn kein error_output gesetzt wurde, aber sicherheitshalber
        app.logger.error("Conversion finished without errors, but no markdown content was retrieved.")
        return jsonify({"error": "Marker conversion failed", "details": "No markdown content retrieved."}), 500
    else:
        # Erfolg!
        return jsonify({"markdown": markdown_output})

# --- Startpunkt für den Server ---
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=FLASK_PORT, debug=False)
