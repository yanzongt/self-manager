#!/usr/bin/env sh
# Always use the backtest environment when available, regardless of working directory.
set -eu
PROJECT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
if [ -x "$PROJECT_DIR/f-analysis/.venv/bin/python" ]; then
    exec "$PROJECT_DIR/f-analysis/.venv/bin/python" "$PROJECT_DIR/serve.py" "$@"
fi
exec python3 "$PROJECT_DIR/serve.py" "$@"
