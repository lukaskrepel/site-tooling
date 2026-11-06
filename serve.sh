#!/usr/bin/env bash
# serve.sh — serve a build directory for local preview.
#
# Usage: serve.sh [DIRECTORY] [PORT]
set -euo pipefail

dir=${1:-dist}
port=${2:-${PORT:-8000}}

if [ ! -d "$dir" ]; then
	printf 'error: directory not found: %s\n' "$dir" >&2
	exit 1
fi

printf 'Serving %s on http://localhost:%s\n' "$dir" "$port"
exec python3 -m http.server "$port" --directory "$dir"
