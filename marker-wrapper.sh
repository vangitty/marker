#!/bin/bash
# Enhanced wrapper for marker that avoids multiprocessing conflicts
# Specifically designed to address issues on aarch64/ARM architectures

# Enable verbose bash debugging if DEBUG env var is set
if [ ! -z "$DEBUG" ]; then
  set -x
fi

# Set a trap to ensure cleanup
trap 'rm -f /tmp/run_marker.py' EXIT

# Log the command and arguments
echo "Running marker-wrapper with args: $@" >&2

# Create a temporary Python script with more error handling
cat > /tmp/run_marker.py << 'EOF'
#!/usr/bin/env python3
# Direct Python script to run marker with extensive error handling
import os
import sys
import traceback

# Set environment variables for multiprocessing
os.environ["MARKER_FORCE_SINGLE_PROCESS"] = "1"
os.environ["PYTHONMULTIPROCESSING"] = "spawn"
# Disable Ray usage completely if marker uses it
os.environ["RAY_DISABLE_IMPORT_WARNING"] = "1"
os.environ["RAY_DISABLE"] = "1"

# Print diagnostic info
print(f"Python version: {sys.version}", file=sys.stderr)
print(f"Arguments: {sys.argv}", file=sys.stderr)
print(f"Working directory: {os.getcwd()}", file=sys.stderr)

# Get input directory from args
input_dir = sys.argv[1] if len(sys.argv) > 1 else None
if input_dir:
    print(f"Input directory contents: {os.listdir(input_dir)}", file=sys.stderr)

# Import and run marker
try:
    # Try to import marker
    print("Importing marker...", file=sys.stderr)
    from marker.scripts.convert import convert_cli
    
    # Run marker's CLI function
    print("Running marker conversion...", file=sys.stderr)
    result = convert_cli()
    print(f"Marker conversion finished with return code: {result}", file=sys.stderr)
    sys.exit(result)
except ImportError as e:
    print(f"Error importing marker module: {e}", file=sys.stderr)
    traceback.print_exc(file=sys.stderr)
    sys.exit(2)
except Exception as e:
    print(f"Unexpected error running marker: {e}", file=sys.stderr)
    traceback.print_exc(file=sys.stderr)
    sys.exit(1)
EOF

# Make the script executable
chmod +x /tmp/run_marker.py

# Find python executable
PYTHON_PATH=$(command -v python || command -v python3)

if [ -z "$PYTHON_PATH" ]; then
    echo "Error: Python executable not found" >&2
    exit 1
fi

echo "Using Python at: $PYTHON_PATH" >&2
echo "Running marker directly from Python..." >&2

# Run our Python script with a minimal environment
exec $PYTHON_PATH /tmp/run_marker.py "$@"
