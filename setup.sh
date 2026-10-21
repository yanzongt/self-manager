#!/usr/bin/env sh
# Install the locked investment dependencies into the shared root environment.
set -eu
PROJECT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
export UV_PROJECT_ENVIRONMENT="$PROJECT_DIR/.venv"
exec uv sync --project "$PROJECT_DIR/apps/investment" --locked "$@"
