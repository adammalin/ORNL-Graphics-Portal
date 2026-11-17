#!/bin/zsh
set -eu
cd -- "${0:A:h}"
pilot_python=.local/pilot-venv/bin/python
if [[ -x .local/pilot-stage1-venv/bin/python ]]; then
  pilot_python=.local/pilot-stage1-venv/bin/python
fi
if [[ ! -x "$pilot_python" || ! -f .local/pilot-config.json ]]; then
  print 'Prepare the pilot environment and private config first. See docs/pilot.md.'
  exit 1
fi
exec "$pilot_python" -m backend.pilot_credentials --config .local/pilot-config.json
