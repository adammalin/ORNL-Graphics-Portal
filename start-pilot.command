#!/bin/zsh
set -eu
cd -- "${0:A:h}"
if [[ ! -x .local/pilot-venv/bin/python ]]; then
  print 'Create the isolated pilot environment first. See docs/pilot.md.'
  exit 1
fi
if [[ ! -f .local/pilot-config.json ]]; then
  print 'Configure .local/pilot-config.json first. See docs/pilot.md.'
  exit 1
fi
exec .local/pilot-venv/bin/python -m backend.pilot --config .local/pilot-config.json --port 4175
