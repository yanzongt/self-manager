#!/usr/bin/env sh
# Use the shared environment first, regardless of the working directory.
set -eu
PROJECT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
for FRONTEND in checkins pdca sensor-fov; do
    if [ ! -f "$PROJECT_DIR/apps/$FRONTEND/.generated/static/index.html" ]; then
        "$PROJECT_DIR/apps/$FRONTEND/setup.sh"
        npm run build --prefix "$PROJECT_DIR/apps/$FRONTEND"
    fi
done
if [ -x "$PROJECT_DIR/.venv/bin/python" ]; then
    exec "$PROJECT_DIR/.venv/bin/python" "$PROJECT_DIR/serve.py" "$@"
fi
if [ -x "$PROJECT_DIR/apps/investment/.venv/bin/python" ]; then
    exec "$PROJECT_DIR/apps/investment/.venv/bin/python" "$PROJECT_DIR/serve.py" "$@"
fi
exec python3 "$PROJECT_DIR/serve.py" "$@"
