#!/bin/bash
# Advanced wrapper for marker that modifies Python to fix multiprocessing issues

# Create a temporary Python patch file
cat > /tmp/mp_patch.py << 'EOF'
# Monkey-patch Python's multiprocessing to avoid semaphore leaks
import os
import sys
import multiprocessing.spawn
import multiprocessing.util

# Force spawn method globally
multiprocessing.set_start_method('spawn', force=True)

# Override the cleanup function to be more aggressive
original_cleanup = multiprocessing.util._cleanup_remaining_children

def patched_cleanup():
    try:
        original_cleanup()
    except Exception as e:
        print(f"Warning: Error during cleanup: {e}", file=sys.stderr)
    # Force kill any remaining child processes
    os.system("pkill -P $$")

multiprocessing.util._cleanup_remaining_children = patched_cleanup

# Now import and run marker
from marker.scripts.convert import convert_cli
sys.exit(convert_cli())
EOF

# Force marker to use single process mode and spawn method
export MARKER_FORCE_SINGLE_PROCESS=1
export PYTHONMULTIPROCESSING=spawn

# Find python executable
PYTHON_PATH=$(which python || which python3)

if [ -z "$PYTHON_PATH" ]; then
    echo "Error: Python executable not found"
    exit 1
fi

echo "Using Python at: $PYTHON_PATH"
echo "Running marker with patched multiprocessing..."

# Run our patched Python script with all arguments passed to this script
exec $PYTHON_PATH /tmp/mp_patch.py "$@"
