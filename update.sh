#!/usr/bin/env bash
# Build the site and print the preview command. Sites keep a one-line
# update.sh that executes this script from the repository root.
set -euo pipefail
cd "$(dirname "$0")/.."

./scripts/build.sh

echo "✓ Site built."
echo "  Preview: ./_shared/serve.sh dist"
