#!/bin/bash
# Robustes Wrapper-Skript für marker mit Timeout und besserer Fehlerbehandlung

# Aktiviere Bash-Debugging und Error-Handling
set -x
set -e

echo "=== Starting marker-wrapper.sh with args: $@ at $(date) ==="
echo "Current working directory: $(pwd)"
echo "Current user: $(whoami)"
echo "Python version: $(python3 --version)"
echo "System info: $(uname -a)"
echo "Available memory: $(free -h)"

# Schaue nach alternativen Konvertierungswerkzeugen
echo "Checking for pandoc..."
if command -v pandoc &> /dev/null; then
    echo "Pandoc found, will use as fallback"
    PANDOC_AVAILABLE=1
else
    echo "Pandoc not found"
    PANDOC_AVAILABLE=0
fi

# Erstelle ein temporäres Python-Skript mit Fallbacks
cat > /tmp/run_marker.py << 'EOF'
#!/usr/bin/env python3
# Robust conversion script with fallbacks
import os
import sys
import traceback
import subprocess
import glob
import logging
import signal
import time

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger("marker-wrapper")

# Set environment variables for multiprocessing
os.environ["MARKER_FORCE_SINGLE_PROCESS"] = "1"
os.environ["PYTHONMULTIPROCESSING"] = "spawn"
os.environ["RAY_DISABLE"] = "1"

# Get input directory from args
input_dir = sys.argv[1] if len(sys.argv) > 1 else None
if not input_dir or not os.path.exists(input_dir):
    logger.error(f"Input directory not provided or doesn't exist: {input_dir}")
    sys.exit(1)

logger.info(f"Input directory: {input_dir}")
logger.info(f"Contents: {os.listdir(input_dir)}")

# Find PDF files
pdf_files = glob.glob(f"{input_dir}/*.pdf")
if not pdf_files:
    logger.error("No PDF files found in input directory")
    sys.exit(1)

# Define conversion strategies
def try_marker_cli():
    """Try using marker's CLI functionality"""
    logger.info("Trying marker CLI conversion...")
    try:
        from marker.scripts.convert import convert_cli
        # Save the original argv and set new one for marker
        original_argv = sys.argv.copy()
        sys.argv = ["marker", input_dir]
        logger.info(f"Running marker with args: {sys.argv}")
        result = convert_cli()
        sys.argv = original_argv
        return result == 0
    except Exception as e:
        logger.error(f"Error using marker CLI: {e}")
        traceback.print_exc()
        return False

def try_marker_direct():
    """Try using marker's direct API"""
    logger.info("Trying direct marker conversion...")
    try:
        from marker.convert import pdf_to_markdown
        success = False
        for pdf_file in pdf_files:
            output_file = os.path.splitext(pdf_file)[0] + ".md"
            logger.info(f"Converting {pdf_file} to {output_file}...")
            try:
                markdown = pdf_to_markdown(pdf_file)
                with open(output_file, 'w', encoding='utf-8') as f:
                    f.write(markdown)
                logger.info(f"Successfully wrote markdown to {output_file}")
                success = True
            except Exception as e:
                logger.error(f"Error converting {pdf_file}: {e}")
        return success
    except Exception as e:
        logger.error(f"Error in direct conversion: {e}")
        traceback.print_exc()
        return False

def try_pandoc():
    """Try using pandoc as a fallback"""
    logger.info("Trying pandoc conversion...")
    success = False
    for pdf_file in pdf_files:
        output_file = os.path.splitext(pdf_file)[0] + ".md"
        try:
            logger.info(f"Running pandoc on {pdf_file}...")
            result = subprocess.run(
                ["pandoc", "-f", "pdf", "-t", "markdown", "-o", output_file, pdf_file],
                capture_output=True,
                text=True,
                check=False
            )
            if result.returncode == 0:
                logger.info(f"Pandoc successfully converted to {output_file}")
                success = True
            else:
                logger.error(f"Pandoc error: {result.stderr}")
        except Exception as e:
            logger.error(f"Error running pandoc: {e}")
    return success

def try_pdftotext():
    """Try using pdftotext as a last resort"""
    logger.info("Trying pdftotext conversion...")
    success = False
    for pdf_file in pdf_files:
        base_name = os.path.splitext(os.path.basename(pdf_file))[0]
        txt_file = os.path.join(input_dir, f"{base_name}.txt")
        md_file = os.path.join(input_dir, f"{base_name}.md")
        
        try:
            # First convert to text
            logger.info(f"Running pdftotext on {pdf_file}...")
            subprocess.run(
                ["pdftotext", pdf_file, txt_file],
                capture_output=True,
                check=False
            )
            
            if os.path.exists(txt_file):
                # Then convert text to markdown
                logger.info(f"Converting text to markdown: {txt_file} -> {md_file}")
                with open(txt_file, 'r', encoding='utf-8', errors='ignore') as f:
                    text_content = f.read()
                
                # Simple conversion to markdown
                with open(md_file, 'w', encoding='utf-8') as f:
                    f.write(f"# {base_name}\n\n")
                    
                    # Split by lines and convert to paragraphs
                    paragraphs = []
                    current_para = []
                    
                    for line in text_content.split('\n'):
                        if line.strip():
                            current_para.append(line)
                        elif current_para:
                            paragraphs.append(' '.join(current_para))
                            current_para = []
                    
                    # Add the last paragraph if there is one
                    if current_para:
                        paragraphs.append(' '.join(current_para))
                    
                    # Write paragraphs
                    for para in paragraphs:
                        f.write(f"{para}\n\n")
                
                logger.info(f"Created markdown file: {md_file}")
                success = True
        except Exception as e:
            logger.error(f"Error in pdftotext conversion: {e}")
    
    return success

# Apply conversion strategies
success = False

# Set a timeout handler
def timeout_handler(signum, frame):
    logger.error("Timeout reached!")
    raise TimeoutError("The operation timed out")

# Try marker CLI with timeout
try:
    signal.signal(signal.SIGALRM, timeout_handler)
    signal.alarm(30)  # 30 second timeout
    success = try_marker_cli()
    signal.alarm(0)  # Cancel the alarm
except TimeoutError:
    logger.error("Marker CLI timed out")
except Exception as e:
    logger.error(f"Unexpected error in marker CLI: {e}")

# Check for output files
md_files = glob.glob(f"{input_dir}/*.md")
if not md_files:
    logger.info("No markdown files found after marker CLI attempt")

    # Try direct conversion
    if not success:
        try:
            signal.alarm(30)  # 30 second timeout
            success = try_marker_direct()
            signal.alarm(0)  # Cancel the alarm
        except TimeoutError:
            logger.error("Direct marker conversion timed out")
        except Exception as e:
            logger.error(f"Unexpected error in direct conversion: {e}")
    
    # Check again
    md_files = glob.glob(f"{input_dir}/*.md")
    if not md_files:
        logger.info("No markdown files found after direct conversion attempt")
        
        # Try pandoc
        if not success and "PANDOC_AVAILABLE" in os.environ and os.environ["PANDOC_AVAILABLE"] == "1":
            try:
                success = try_pandoc()
            except Exception as e:
                logger.error(f"Error in pandoc fallback: {e}")
        
        # Check again
        md_files = glob.glob(f"{input_dir}/*.md")
        if not md_files:
            logger.info("No markdown files found after pandoc attempt")
            
            # Last resort: pdftotext
            if not success:
                try:
                    success = try_pdftotext()
                except Exception as e:
                    logger.error(f"Error in pdftotext fallback: {e}")

# Final check
md_files = glob.glob(f"{input_dir}/*.md")
if md_files:
    logger.info(f"Markdown files found: {md_files}")
    for md_file in md_files:
        try:
            with open(md_file, 'r', encoding='utf-8') as f:
                content = f.read()
            logger.info(f"Content of {md_file}, length: {len(content)} characters")
            if len(content) > 0:
                logger.info("Conversion successful!")
                sys.exit(0)
        except Exception as e:
            logger.error(f"Error reading {md_file}: {e}")
    
    logger.error("Markdown files found but they are empty or unreadable")
    sys.exit(1)
else:
    logger.error("No markdown files produced by any conversion method")
    sys.exit(1)
EOF

# Make the script executable
chmod +x /tmp/run_marker.py

# Find Python
PYTHON_PATH=$(command -v python3 || command -v python)

if [ -z "$PYTHON_PATH" ]; then
    echo "Error: Python executable not found" >&2
    exit 1
fi

# Set pandoc availability for the script
if [ "$PANDOC_AVAILABLE" -eq 1 ]; then
    export PANDOC_AVAILABLE=1
else
    export PANDOC_AVAILABLE=0
fi

echo "Using Python at: $PYTHON_PATH"
echo "Running conversion script..."

# Run with timeout protection
timeout 60s $PYTHON_PATH /tmp/run_marker.py "$@"
EXIT_CODE=$?

if [ $EXIT_CODE -eq 124 ]; then
    echo "Conversion script timed out after 60 seconds"
    exit 1
elif [ $EXIT_CODE -ne 0 ]; then
    echo "Conversion script failed with exit code $EXIT_CODE"
    exit $EXIT_CODE
else
    echo "Conversion script completed successfully"
    exit 0
fi
