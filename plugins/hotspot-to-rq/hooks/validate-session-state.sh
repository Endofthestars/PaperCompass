#!/usr/bin/env bash
# PostToolUse hook: whenever a research-direction session-state.json is
# written, run the full session validator and surface failures to the model
# (exit 2 feeds stderr back). Non-session writes exit 0 untouched.
set -euo pipefail

file_path="$(python3 -c '
import json, sys
try:
    data = json.load(sys.stdin)
except ValueError:
    data = {}
tool_input = data.get("tool_input") or {}
print(tool_input.get("file_path") or "")
')"

case "$file_path" in
  */reports/research-direction/*/session-state.json) ;;
  reports/research-direction/*/session-state.json) ;;
  *) exit 0 ;;
esac

session_dir="$(dirname "$file_path")"
plugin_root="${CLAUDE_PLUGIN_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
validator="${plugin_root}/skills/research-direction-debate/scripts/validate_session.py"

if output="$(python3 -B "$validator" "$session_dir" 2>&1)"; then
  exit 0
fi

# Bootstrap grace: the documented init order writes session-state.json before
# the Markdown artifacts exist, so the very first write must not surface a
# wall of "required artifact is missing" errors. Soft-pass only while no
# artifact exists AND no controller transition has been committed yet.
if python3 - "$session_dir" <<'PYEOF'
import json
import sys
from pathlib import Path

session_dir = Path(sys.argv[1])
if any(session_dir.glob("*.md")):
    sys.exit(1)
try:
    state = json.loads((session_dir / "session-state.json").read_text())
except (OSError, ValueError):
    sys.exit(1)
control = state.get("mainline_control")
transition_log = control.get("transition_log") if isinstance(control, dict) else None
sys.exit(0 if not transition_log else 1)
PYEOF
then
  echo "session-state bootstrap in progress (no artifacts yet); full validation deferred to the next write" >&2
  exit 0
fi

printf '%s\n' "$output" >&2
exit 2
