#!/bin/bash
# Simple wrapper for marker that sets special environment variables

# Force marker to use single process mode
export MARKER_FORCE_SINGLE_PROCESS=1

# Force Python multiprocessing to use "spawn" method instead of "fork"
# This is more reliable in container environments
export PYTHONMULTIPROCESSING=spawn

# Find the marker executable
MARKER_PATH=$(which marker)

if [ -z "$MARKER_PATH" ]; then
    echo "Error: marker executable not found in PATH"
    exit 1
fi

echo "Using marker at: $MARKER_PATH"

# Run marker with all arguments passed to this script
exec $MARKER_PATH "$@"
