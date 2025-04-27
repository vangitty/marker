import os
import subprocess
import tempfile
import logging
import shutil 
import glob
import time
import threading
from flask import Flask, request, jsonify

# --- Configuration ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s:%(name)s:%(message)s')

app = Flask(__name__)
app.logger.setLevel(logging.INFO) 

# Use our wrapper script instead of direct marker command
MARKER_CMD = "/app/marker-wrapper.sh" 
FLASK_PORT = int(os.environ.get("PORT", 5000))
WORKDIR = "/app"
# Timeout for marker process (in seconds)
MARKER_TIMEOUT = int(os.environ.get("MARKER_TIMEOUT", 240))

# --- Helper function to kill a process and its children ---
def kill_process_tree(process):
    """Kill a process and all its children."""
    try:
        # First try gentle termination
        process.terminate()
        # Give it 5 seconds to terminate gracefully
        time.sleep(5)
        # If still running, kill forcefully
        if process.poll() is None:
            process.kill()
    except Exception as e:
        app.logger.error(f"Error killing process: {e}")

# --- API Endpoint ---
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
    output_md_path_found = None # Path to found markdown file
    marker_process = None

    try:
        # 1. Create temporary input directory
        tmp_input_dir = tempfile.mkdtemp()
        app.logger.info(f"Created temporary input directory {tmp_input_dir}")

        # 2. Save PDF to input directory
        tmp_input_pdf_path = os.path.join(tmp_input_dir, original_filename)
        file.save(tmp_input_pdf_path)
        app.logger.info(f"Saved uploaded PDF to temporary input directory: {tmp_input_pdf_path}")

        # Determine expected output filename
        output_basename = f"{os.path.splitext(original_filename)[0]}.md"
        expected_output_path = os.path.join(tmp_input_dir, output_basename)
        app.logger.info(f"Expecting output file named: {output_basename}")

        # 3. --- Marker subprocess call with proper options ---
        try:
            # Pass just the input directory to marker - minimal options
            cmd_list = [
                MARKER_CMD, 
                tmp_input_dir
            ]
            
            app.logger.info(f"Executing command: {' '.join(cmd_list)}")
            
            # Execute in WORKDIR
            marker_process = subprocess.Popen(
                cmd_list,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding='utf-8',
                cwd=WORKDIR 
            )
            
            # Set up a timeout using a Timer
            timer = threading.Timer(MARKER_TIMEOUT, lambda: kill_process_tree(marker_process))
            timer.start()
            
            try:
                stdout, stderr = marker_process.communicate()
                # Cancel the timer if process completes naturally
                timer.cancel()
                
                if marker_process.returncode != 0:
                    app.logger.error(f"Marker execution failed with code {marker_process.returncode}")
                    error_output = f"Marker execution failed with code {marker_process.returncode}: {stderr.strip()}"
                else:
                    app.logger.info("Marker execution successful (return code 0).")
                    # Log stderr and stdout for diagnostic purposes
                    if stderr:
                        app.logger.warning(f"Marker stderr: {stderr.strip()}")
                    if stdout:
                        app.logger.info(f"Marker stdout: {stdout.strip()}")
            except Exception as e:
                # Make sure to cancel and cleanup the timer
                timer.cancel()
                app.logger.error(f"Error during marker process communication: {e}")
                error_output = f"Process communication error: {str(e)}"
                
                # Try to forcefully terminate the process if it's still running
                if marker_process and marker_process.poll() is None:
                    kill_process_tree(marker_process)

            # 4. Check for output file
            # First check expected path
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
                app.logger.warning(f"Expected output file '{expected_output_path}' not found.")
                
                # Extended search for the output file
                found_files = glob.glob(f"{tmp_input_dir}/*.md")
                app.logger.info(f"Looking for any markdown files in directory. Found: {found_files}")
                
                if found_files:
                    # Use the first found MD file
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
                    # Check if the file might be in the working directory
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
                        # Last resort - try all markdown files in the working directory
                        workdir_md_files = glob.glob(f"{WORKDIR}/*.md")
                        if workdir_md_files:
                            app.logger.info(f"Found potential output files in working directory: {workdir_md_files}")
                            for md_file in workdir_md_files:
                                # Skip obviously unrelated files
                                if os.path.basename(md_file).startswith(os.path.splitext(original_filename)[0]):
                                    try:
                                        with open(md_file, 'r', encoding='utf-8') as f:
                                            markdown_output = f.read()
                                        app.logger.info(f"Read markdown from {md_file}. Length: {len(markdown_output)}")
                                        output_md_path_found = md_file
                                        break
                                    except Exception as read_err:
                                        app.logger.error(f"Could not read potential output file: {read_err}")
                        
                        if markdown_output is None:
                            error_output = "Marker ran but markdown file not found in any location."

        except subprocess.CalledProcessError as e:
            app.logger.error(f"Marker execution failed with code {e.returncode}")
            detailed_error = e.stderr.strip() if e.stderr else "No stderr output"
            app.logger.error(f"Marker stderr: {detailed_error}")
            error_output = detailed_error
        except FileNotFoundError:
            app.logger.error(f"Error: The command '{MARKER_CMD}' was not found.")
            error_output = f"Command not found: {MARKER_CMD}"
        except Exception as e:
            app.logger.exception("An unexpected error occurred during marker conversion.")
            error_output = f"Unexpected error: {str(e)}"

    finally:
        # --- Safely clean up temporary files and directories ---
        if marker_process and marker_process.poll() is None:
            try:
                kill_process_tree(marker_process)
                app.logger.info("Killed marker process")
            except Exception as e:
                app.logger.error(f"Error killing marker process: {e}")
        
        if output_md_path_found and os.path.exists(output_md_path_found) and output_md_path_found.startswith(WORKDIR):
            try:
                os.remove(output_md_path_found)
                app.logger.info(f"Removed output file in working directory: {output_md_path_found}")
            except OSError as e:
                app.logger.error(f"Error removing output file in working directory: {e}")
                
        if tmp_input_dir and os.path.exists(tmp_input_dir):
            try:
                shutil.rmtree(tmp_input_dir)
                app.logger.info(f"Removed temporary input directory {tmp_input_dir}")
            except OSError as e:
                app.logger.error(f"Error removing temporary input directory {tmp_input_dir}: {e}")

    # --- Send response ---
    if error_output:
        app.logger.error(f"Returning error: {error_output}")
        return jsonify({"error": "Marker conversion failed", "details": error_output}), 500
    elif markdown_output is None:
        app.logger.error("Conversion finished without errors, but no markdown content was retrieved.")
        return jsonify({"error": "Marker conversion failed", "details": "No markdown content retrieved."}), 500
    else:
        app.logger.info(f"Conversion successful - returning {len(markdown_output)} characters of markdown")
        return jsonify({"markdown": markdown_output})

# --- Server start point ---
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=FLASK_PORT, debug=False)
