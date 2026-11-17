#!/bin/zsh
set -eu
cd -- "${0:A:h}"
if [[ ! -x .local/bin/devtunnel || ! -f .local/pilot-config.json ]]; then
  print 'Configure the official Dev Tunnels CLI and private pilot config first. See docs/pilot.md.'
  exit 1
fi
TASK_PILOT_TUNNEL_ID=$(python3 -c 'import json,re; from pathlib import Path; value=json.loads(Path(".local/pilot-config.json").read_text()).get("tunnelId", ""); assert re.fullmatch(r"[a-z0-9-]+\.[a-z0-9]+", value), "Set tunnelId in the private pilot config"; print(value)')
export DOTNET_BUNDLE_EXTRACT_BASE_DIR="$PWD/.local/dotnet-extract"
.local/bin/devtunnel update "$TASK_PILOT_TUNNEL_ID" --host-header unchanged --origin-header unchanged
exec .local/bin/devtunnel host "$TASK_PILOT_TUNNEL_ID"
