#!/usr/bin/env sh
# Launcher: finds a suitable Python and runs pypimgr.py with the same arguments.
d=$(cd "$(dirname "$0")" && pwd)
for py in python3 python; do
    command -v "$py" >/dev/null 2>&1 && exec "$py" "$d/pypimgr.py" "$@"
done
echo "pypimgr: Python 3.10+ not found" >&2; exit 1
