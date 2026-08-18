#!/usr/bin/env bash
# Remove the /speak command and the stop hook. Leaves the repo and models in place.
set -euo pipefail
CFG=${CLAUDE_CONFIG_DIR:-$HOME/.claude}

rm -f "$CFG/commands/speak.md"
python3 - "$CFG" <<'PY'
import json, sys
from pathlib import Path

cfg = Path(sys.argv[1])
settings = cfg / "settings.json"
if not settings.exists():
    raise SystemExit(0)
data = json.loads(settings.read_text())
cmd = str(cfg / "hooks" / "claude-speak-stop.sh")
groups = data.get("hooks", {}).get("UserPromptSubmit", [])
kept = [g for g in groups if not any(h.get("command") == cmd for h in g.get("hooks", []))]
if len(kept) != len(groups):
    data["hooks"]["UserPromptSubmit"] = kept
    settings.write_text(json.dumps(data, indent=2))
    print("hook unregistered")
PY
rm -f "$CFG/hooks/claude-speak-stop.sh"
echo "uninstalled (repo, venvs and models left in place)"
