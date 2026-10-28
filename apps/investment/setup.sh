#!/usr/bin/env sh
# Keep npm's generated lockfile and dependencies outside the source tree.
set -eu
DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
mkdir -p "$DIR/.generated"
cp "$DIR/package.json" "$DIR/.generated/package.json"
# Avoid npm 11 peer-resolution crashes; versions are pinned in package.json.
npm install --prefix "$DIR/.generated" --no-audit --no-fund --legacy-peer-deps
if [ ! -e "$DIR/node_modules" ]; then
    ln -s .generated/node_modules "$DIR/node_modules"
fi
