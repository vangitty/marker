#!/bin/bash
# Simplified wrapper for marker

# Create a temporary Python script to run marker directly
cat > /tmp/run_marker.py << 'EOF'
# Direct Python script to run marker
import os
import sys
import multiprocessing

# Force spawn method globally
multiprocessing.set_start_method('spawn', force=True)

# Set environment variables
os.environ["MARKER_FORCE_SINGLE_PROCESS"] = "1"
os.environ["PYTHONMULTIPROCESSING"] = "spawn"

# Import and run marker
try:
    from marker.scripts.convert import convert_cli
    sys.exit(convert_cli())
except Exception as e:
    print(f"Error running marker: {e}", file=sys.stderr)
    sys.exit(1)
EOF

# Find python executable
PYTHON_PATH=$(command -v python || command -v python3)

if [ -z "$PYTHON_PATH" ]; then
    echo "Error: Python executable not found"
    exit 1
fi

echo "Using Python at: $PYTHON_PATH"
echo "Running marker directly from Python..."

# Run our Python script with all arguments passed to this script
exec $PYTHON_PATH /tmp/run_marker.py "$@"
