#!/bin/zsh
# Local DEV service; the API token is requested interactively and never saved.
set -eu
PORTAL_DIR="${0:A:h}"
cd "$PORTAL_DIR"
if [[ ! -f .local/dev-config.json ]]; then
  print 'Create .local/dev-config.json as described in docs/local-dev.md first.'
  exit 1
fi
export PYTHONDONTWRITEBYTECODE=1
exec python3 backend/server.py --dev-write --config .local/dev-config.json --port 4174
