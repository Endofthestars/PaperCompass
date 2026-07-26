#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
codex_base="${CODEX_HOME:-${HOME}/.codex}"
plugin_root="${repo_root}/plugins/hotspot-to-rq"
skill_root="${plugin_root}/skills/research-direction-debate"

python3 -B -m unittest discover -s "${repo_root}/tests" -v
python3 -B "${codex_base}/skills/.system/plugin-creator/scripts/validate_plugin.py" \
  "${plugin_root}"
python3 -B "${codex_base}/skills/.system/skill-creator/scripts/quick_validate.py" \
  "${skill_root}"
python3 -B "${skill_root}/scripts/validate_controller_decision.py" --help >/dev/null
python3 -B "${skill_root}/scripts/validate_session.py" --help >/dev/null
python3 -m json.tool "${plugin_root}/.codex-plugin/plugin.json" >/dev/null
python3 -m json.tool "${repo_root}/.agents/plugins/marketplace.json" >/dev/null
git -C "${repo_root}" diff --check
