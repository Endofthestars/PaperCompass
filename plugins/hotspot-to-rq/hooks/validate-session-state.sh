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
printf '%s\n' "$output" >&2
exit 2
