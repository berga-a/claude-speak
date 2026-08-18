#!/usr/bin/env bash
# Install claude-speak: engine environment, voice model, /speak command, optional hook.
#
#   ./install.sh                 piper engine + /speak command
#   ./install.sh --kokoro        also install the Kokoro engine (slower, more natural)
#   ./install.sh --hook          also stop speech whenever you submit a new prompt
#   ./install.sh --voice NAME    piper voice (default en_US-lessac-high)
set -euo pipefail

ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
CFG=${CLAUDE_CONFIG_DIR:-$HOME/.claude}
BIN=$ROOT/bin/claude-speak
PIPER_VOICE=en_US-lessac-high
WANT_KOKORO=0
WANT_HOOK=0

while [ $# -gt 0 ]; do
  case "$1" in
    --kokoro) WANT_KOKORO=1 ;;
    --hook)   WANT_HOOK=1 ;;
    --voice)  PIPER_VOICE=${2:?}; shift ;;
    -h|--help) sed -n '2,8p' "$0"; exit 0 ;;
    *) echo "unknown option: $1" >&2; exit 1 ;;
  esac
  shift
done

need() { command -v "$1" >/dev/null || { echo "missing dependency: $1" >&2; exit 1; }; }
need python3
need jq

if ! command -v aplay >/dev/null && ! command -v pw-cat >/dev/null \
   && ! command -v play >/dev/null && ! command -v ffplay >/dev/null; then
  echo "warning: no audio player found (install alsa-utils, pipewire-utils, sox or ffmpeg)" >&2
fi

echo "==> piper engine"
[ -d "$ROOT/venv-piper" ] || python3 -m venv "$ROOT/venv-piper"
"$ROOT/venv-piper/bin/python" -m pip install -q --upgrade pip
"$ROOT/venv-piper/bin/python" -m pip install -q piper-tts
mkdir -p "$ROOT/voices"
if [ ! -f "$ROOT/voices/$PIPER_VOICE.onnx" ]; then
  echo "==> downloading voice $PIPER_VOICE"
  "$ROOT/venv-piper/bin/python" -m piper.download_voices "$PIPER_VOICE" --data-dir "$ROOT/voices"
fi

if [ "$WANT_KOKORO" = 1 ]; then
  echo "==> kokoro engine"
  [ -d "$ROOT/venv-kokoro" ] || python3 -m venv "$ROOT/venv-kokoro"
  "$ROOT/venv-kokoro/bin/python" -m pip install -q --upgrade pip
  "$ROOT/venv-kokoro/bin/python" -m pip install -q kokoro-onnx soundfile
  mkdir -p "$ROOT/models-kokoro"
  base=https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0
  for f in kokoro-v1.0.onnx voices-v1.0.bin; do
    [ -f "$ROOT/models-kokoro/$f" ] || curl -L --retry 2 -o "$ROOT/models-kokoro/$f" "$base/$f"
  done
fi

echo "==> /speak command"
mkdir -p "$CFG/commands"
sed "s|__BIN__|$BIN|g" "$ROOT/commands/speak.md.tmpl" > "$CFG/commands/speak.md"

echo "==> stop-on-new-prompt hook"
mkdir -p "$CFG/hooks"
sed "s|__BIN__|$BIN|g" "$ROOT/hooks/speak-stop.sh.tmpl" > "$CFG/hooks/claude-speak-stop.sh"
chmod +x "$CFG/hooks/claude-speak-stop.sh"

if [ "$WANT_HOOK" = 1 ]; then
  python3 - "$CFG" <<'PY'
import json, shutil, sys
from pathlib import Path

cfg = Path(sys.argv[1])
settings = cfg / "settings.json"
data = json.loads(settings.read_text()) if settings.exists() else {}
if settings.exists():
    shutil.copy(settings, settings.with_suffix(".json.bak"))

cmd = str(cfg / "hooks" / "claude-speak-stop.sh")
groups = data.setdefault("hooks", {}).setdefault("UserPromptSubmit", [])
if any(h.get("command") == cmd for g in groups for h in g.get("hooks", [])):
    print("    hook already registered")
else:
    groups.append({"matcher": "", "hooks": [{"type": "command", "command": cmd, "timeout": 5}]})
    settings.write_text(json.dumps(data, indent=2))
    print("    hook registered in settings.json (backup: settings.json.bak)")
PY
else
  echo "    installed but not registered — re-run with --hook to enable it"
fi

cat <<EOF

Installed. Try it:
  $BIN "hello from claude speak"
  /speak            in Claude Code (restart the session to pick up the command)

Engine: piper. Add --kokoro for a more natural but slower voice, then set
CLAUDE_SPEAK_ENGINE=kokoro.
EOF
