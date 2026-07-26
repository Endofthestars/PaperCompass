#!/usr/bin/env bash
# PostToolUse hook: whenever a research-direction session-state.json is
# written, run the full session validator and surface failures to the model
# (exit 2 feeds stderr back). Non-session writes exit 0 untouched.
#
# Write paths covered (BUGS.md P-05 / hook-bypass fix):
# - Claude Code Write/Edit: tool_input.file_path
# - Codex apply_patch (matches the Edit|Write aliases): tool_input.command
#   holding patch text with "*** Update File:" / "*** Add File:" headers
# - Bash on either runtime: tool_input.command mentioning a session-state path
set -euo pipefail

candidate_paths="$(python3 -c '
import json, re, sys

try:
    data = json.load(sys.stdin)
except ValueError:
    data = {}
tool_input = data.get("tool_input") or {}

found = []
file_path = tool_input.get("file_path")
if isinstance(file_path, str) and file_path:
    found.append(file_path)

command = tool_input.get("command")
if isinstance(command, str) and command:
    for line in command.splitlines():
        match = re.match(r"\*\*\* (?:Update|Add) File:\s*(.+?)\s*$", line)
        if match:
            found.append(match.group(1))
    found.extend(
        re.findall(
            r"[\w./~-]*reports/research-direction/[\w.-]+/session-state\.json",
            command,
        )
    )

seen = []
for path in found:
    if path not in seen:
        seen.append(path)
print("\n".join(seen))
')"

session_dirs=()
while IFS= read -r file_path; do
  case "$file_path" in
    */reports/research-direction/*/session-state.json) ;;
    reports/research-direction/*/session-state.json) ;;
    *) continue ;;
  esac
  session_dirs+=("$(dirname "$file_path")")
done <<<"$candidate_paths"

if [ "${#session_dirs[@]}" -eq 0 ]; then
  exit 0
fi

plugin_root="${CLAUDE_PLUGIN_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
validator="${plugin_root}/skills/research-direction-debate/scripts/validate_session.py"
if [ ! -f "$validator" ]; then
  echo "hotspot-to-rq hook misconfigured: session validator not found at ${validator}" >&2
  exit 2
fi

for session_dir in "${session_dirs[@]}"; do
  if output="$(python3 -B "$validator" "$session_dir" 2>&1)"; then
    continue
  fi

  # Bootstrap grace: the documented init order writes session-state.json
  # before the Markdown artifacts exist, so the very first write must not
  # surface a wall of "required artifact is missing" errors. Soft-pass only
  # while no artifact exists AND no controller transition has been committed.
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
    continue
  fi

  printf '%s\n' "$output" >&2
  exit 2
done

exit 0
