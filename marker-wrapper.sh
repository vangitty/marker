#!/bin/bash
# Simple wrapper for marker that sets special environment variables

# Force marker to use single process mode
export MARKER_FORCE_SINGLE_PROCESS=1

# Force Python multiprocessing to use "spawn" method instead of "fork"
# This is more reliable in container environments
export PYTHONMULTIPROCESSING=spawn

# Try different possible paths for marker
for possible_path in \
    "/app/.local/bin/marker" \
    "/home/appuser/.local/bin/marker" \
    "/usr/local/bin/marker"
do
    if [ -x "$possible_path" ]; then
        echo "Found marker at: $possible_path"
        exec "$possible_path" "$@"
        exit 0
    fi
done

# If we reach here, we couldn't find marker
echo "Error: marker executable not found in common paths"
exit 1
