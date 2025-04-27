#!/bin/bash
# Simple wrapper for marker that sets special environment variables

# Force marker to use single process mode
export MARKER_FORCE_SINGLE_PROCESS=1

# Force Python multiprocessing to use "spawn" method instead of "fork"
# This is more reliable in container environments
export PYTHONMULTIPROCESSING=spawn

# Run marker with all arguments passed to this script
exec /home/appuser/.local/bin/marker "$@"
