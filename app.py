import os
import subprocess
import tempfile
import logging
import shutil 
import glob 
import time
import sys

from flask import Flask, request, jsonify

# --- Konfiguration ---
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s %(levelname)s:%(name)s:%(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)

app = Flask(__name__)
app.logger.setLevel(logging.DEBUG)

# Konfiguration
MARKER_CMD = "/app/marker-wrapper.sh" 
FLASK_PORT = int(os.environ.get("PORT", 5000))
WORKDIR = "/app" 
# Fallback mit Pandoc, falls marker fehlschlägt
USE_PANDOC_FALLBACK = True
PANDOC_TIMEOUT = 60  # Sekunden

# Healthcheck-Endpunkt
@app.route('/', methods=['GET'])
def healthcheck():
    return jsonify({"status": "ok", "service": "marker-pdf-converter"}), 200

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

    try:
        # Temporären Input-Ordner erstellen
        tmp_input_dir = tempfile.mkdtemp()
        app.logger.info(f"Created temporary input directory {tmp_input_dir}")
        
        # PDF speichern
        tmp_input_pdf_path = os.path.join(tmp_input_dir, original_filename)
        file.save(tmp_input_pdf_path)
        app.logger.info(f"Saved uploaded PDF to temporary input directory: {tmp_input_pdf_path}")
        
        # Überprüfe ob die Datei existiert und ihre Größe
        if os.path.exists(tmp_input_pdf_path):
            app.logger.info(f"Confirmed file exists at {tmp_input_pdf_path}, size: {os.path.getsize(tmp_input_pdf_path)} bytes")
        else:
            app.logger.error(f"File does not exist at {tmp_input_pdf_path} after saving!")
            return jsonify({"error": "Failed to save PDF file"}), 500

        # Erwarteter Ausgabedateiname
        output_basename = f"{os.path.splitext(original_filename)[0]}.md"
        expected_output_path = os.path.join(tmp_input_dir, output_basename)
        app.logger.info(f"Expecting output file named: {output_basename}")

        # --- Versuch 1: Marker Wrapper ---
        marker_success = False
        try:
            app.logger.info("Attempting conversion with marker-wrapper.sh")
            cmd_list = [MARKER_CMD, tmp_input_dir]
            app.logger.info(f"Executing command: {' '.join(cmd_list)}")
            
            # Timeout-Schutz für den marker-Prozess
            process = subprocess.run(
                cmd_list,
                capture_output=True,
                text=True,
                timeout=120,  # 2 Minuten Timeout
                cwd=WORKDIR 
            )
            
            app.logger.info(f"Marker process completed with return code: {process.returncode}")
            
            if process.stdout:
                app.logger.info(f"Marker stdout: {process.stdout.strip()}")
            if process.stderr:
                app.logger.warning(f"Marker stderr: {process.stderr.strip()}")
            
            # Überprüfe ob Ausgabedatei existiert
            if os.path.exists(expected_output_path):
                app.logger.info(f"Found expected output file at: {expected_output_path}")
                try:
                    with open(expected_output_path, 'r', encoding='utf-8') as f:
                        markdown_output = f.read()
                    app.logger.info(f"Read markdown. Length: {len(markdown_output)}")
                    marker_success = True
                except Exception as read_err:
                    app.logger.error(f"Could not read output file {expected_output_path}: {read_err}")
            else:
                # Suche nach anderen MD-Dateien
                md_files = glob.glob(f"{tmp_input_dir}/*.md")
                if md_files:
                    app.logger.info(f"Found markdown files: {md_files}")
                    try:
                        with open(md_files[0], 'r', encoding='utf-8') as f:
                            markdown_output = f.read()
                        app.logger.info(f"Read markdown from {md_files[0]}. Length: {len(markdown_output)}")
                        marker_success = True
                    except Exception as read_err:
                        app.logger.error(f"Could not read found markdown file: {read_err}")
                else:
                    app.logger.warning("No markdown files found after marker conversion")
        except subprocess.TimeoutExpired:
            app.logger.error("Marker process timed out")
        except Exception as e:
            app.logger.error(f"Error during marker conversion: {e}")
        
        # --- Versuch 2: Pandoc-Fallback ---
        if not marker_success and USE_PANDOC_FALLBACK:
            app.logger.info("Marker conversion failed, trying pandoc fallback")
            
            try:
                # Überprüfe, ob pandoc installiert ist
                pandoc_version = subprocess.run(
                    ["pandoc", "--version"], 
                    capture_output=True, 
                    text=True
                )
                app.logger.info(f"Found pandoc: {pandoc_version.stdout.split('\n')[0]}")
                
                # Konvertiere mit pandoc
                app.logger.info(f"Converting {tmp_input_pdf_path} with pandoc")
                pandoc_result = subprocess.run(
                    ["pandoc", "-f", "pdf", "-t", "markdown", "-o", expected_output_path, tmp_input_pdf_path],
                    capture_output=True,
                    text=True,
                    timeout=PANDOC_TIMEOUT
                )
                
                app.logger.info(f"Pandoc completed with return code: {pandoc_result.returncode}")
                if pandoc_result.stderr:
                    app.logger.warning(f"Pandoc stderr: {pandoc_result.stderr}")
                
                # Überprüfe die Ausgabedatei
                if os.path.exists(expected_output_path):
                    app.logger.info(f"Pandoc created output file at: {expected_output_path}")
                    try:
                        with open(expected_output_path, 'r', encoding='utf-8') as f:
                            markdown_output = f.read()
                        app.logger.info(f"Read pandoc markdown. Length: {len(markdown_output)}")
                    except Exception as read_err:
                        app.logger.error(f"Could not read pandoc output file: {read_err}")
                else:
                    app.logger.error("Pandoc ran but did not create output file")
                    
                    # Versuche pdftotext als letzten Ausweg
                    app.logger.info("Trying pdftotext as last resort")
                    txt_path = os.path.join(tmp_input_dir, f"{os.path.splitext(original_filename)[0]}.txt")
                    
                    try:
                        pdftotext_result = subprocess.run(
                            ["pdftotext", tmp_input_pdf_path, txt_path],
                            capture_output=True,
                            text=True
                        )
                        
                        if os.path.exists(txt_path):
                            app.logger.info(f"pdftotext created {txt_path}")
                            
                            # Konvertiere Text zu Markdown
                            with open(txt_path, 'r', encoding='utf-8', errors='ignore') as f:
                                text_content = f.read()
                            
                            # Einfache Konvertierung zu Markdown
                            markdown_content = f"# {os.path.splitext(original_filename)[0]}\n\n"
                            
                            # Text in Absätze aufteilen
                            paragraphs = []
                            current_para = []
                            
                            for line in text_content.split('\n'):
                                if line.strip():
                                    current_para.append(line)
                                elif current_para:
                                    paragraphs.append(' '.join(current_para))
                                    current_para = []
                            
                            # Letzten Absatz hinzufügen, falls vorhanden
                            if current_para:
                                paragraphs.append(' '.join(current_para))
                            
                            # Absätze schreiben
                            for para in paragraphs:
                                markdown_content += f"{para}\n\n"
                            
                            # In MD-Datei speichern
                            with open(expected_output_path, 'w', encoding='utf-8') as f:
                                f.write(markdown_content)
                            
                            app.logger.info(f"Created markdown from text, saved to {expected_output_path}")
                            markdown_output = markdown_content
                        else:
                            app.logger.error("pdftotext failed to create output file")
                    except Exception as txt_err:
                        app.logger.error(f"Error using pdftotext: {txt_err}")
            except FileNotFoundError:
                app.logger.error("Pandoc not installed")
            except subprocess.TimeoutExpired:
                app.logger.error("Pandoc process timed out")
            except Exception as pandoc_err:
                app.logger.error(f"Error during pandoc conversion: {pandoc_err}")
        
        # Wenn keine Konvertierung erfolgreich war
        if markdown_output is None:
            error_output = "Failed to convert PDF to Markdown with both marker and pandoc"
            app.logger.error(error_output)

    except Exception as e:
        app.logger.exception("An unexpected error occurred during conversion")
        error_output = f"Unexpected error: {str(e)}"
    finally:
        # --- Temporäre Dateien und Ordner aufräumen ---
        if tmp_input_dir and os.path.exists(tmp_input_dir):
            try:
                shutil.rmtree(tmp_input_dir)
                app.logger.info(f"Removed temporary input directory {tmp_input_dir}")
            except OSError as e:
                app.logger.error(f"Error removing temporary input directory {tmp_input_dir}: {e}")

    # --- Antwort senden ---
    if error_output and markdown_output is None:
        app.logger.error(f"Returning error: {error_output}")
        return jsonify({"error": "Marker conversion failed", "details": error_output}), 500
    else:
        app.logger.info(f"Conversion successful - returning {len(markdown_output)} characters of markdown")
        return jsonify({"markdown": markdown_output})

# --- Server start point ---
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=FLASK_PORT, debug=False)
