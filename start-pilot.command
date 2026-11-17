#!/bin/zsh
set -eu
cd -- "${0:A:h}"
pilot_python=.local/pilot-venv/bin/python
if [[ -x .local/pilot-stage1-venv/bin/python ]]; then
  pilot_python=.local/pilot-stage1-venv/bin/python
fi
if [[ ! -x "$pilot_python" ]]; then
  print 'Create the isolated pilot environment first. See docs/pilot.md.'
  exit 1
fi
if [[ ! -f .local/pilot-config.json ]]; then
  print 'Configure .local/pilot-config.json first. See docs/pilot.md.'
  exit 1
fi
exec "$pilot_python" -m backend.pilot --config .local/pilot-config.json --port 4175 "$@"
