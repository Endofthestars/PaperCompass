#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
codex_base="${CODEX_HOME:-${HOME}/.codex}"
plugin_root="${repo_root}/plugins/hotspot-to-rq"
skill_root="${plugin_root}/skills/research-direction-debate"
python_bin="${PYTHON_BIN:-python3}"

if [[ "${PYTHON_COVERAGE:-0}" = "1" ]]; then
  "${python_bin}" -B -m coverage erase
  "${python_bin}" -B -m coverage run --branch \
    -m unittest discover -s "${repo_root}/tests" -v
else
  "${python_bin}" -B -m unittest discover -s "${repo_root}/tests" -v
fi
plugin_validator="${CODEX_PLUGIN_VALIDATOR:-${codex_base}/skills/.system/plugin-creator/scripts/validate_plugin.py}"
skill_validator="${CODEX_SKILL_VALIDATOR:-${codex_base}/skills/.system/skill-creator/scripts/quick_validate.py}"
if [[ -n "${CODEX_PLUGIN_VALIDATOR:-}" || -n "${CODEX_SKILL_VALIDATOR:-}" ]]; then
  if [[ ! -f "${plugin_validator}" || ! -f "${skill_validator}" ]]; then
    echo "Configured Codex validator path is missing." >&2
    exit 1
  fi
fi
if [[ -f "${plugin_validator}" && -f "${skill_validator}" ]]; then
  "${python_bin}" -B "${plugin_validator}" "${plugin_root}"
  "${python_bin}" -B "${skill_validator}" "${skill_root}"
else
  echo "Skipping Codex-only plugin/skill validators (not installed in this environment)."
fi
claude_bin="${CLAUDE_CODE_BIN:-claude}"
if [[ -n "${CLAUDE_CODE_BIN:-}" ]] && ! command -v "${claude_bin}" >/dev/null 2>&1; then
  echo "Configured Claude Code binary is missing." >&2
  exit 1
fi
if command -v "${claude_bin}" >/dev/null 2>&1; then
  "${claude_bin}" plugin validate "${plugin_root}" --strict
  "${claude_bin}" plugin validate "${repo_root}" --strict
else
  echo "Skipping Claude Code plugin/marketplace validation (claude CLI not installed)."
fi
"${python_bin}" -B "${skill_root}/scripts/validate_controller_decision.py" --help >/dev/null
"${python_bin}" -B "${skill_root}/scripts/validate_session.py" --help >/dev/null
"${python_bin}" -B "${skill_root}/scripts/build_control_input.py" --help >/dev/null
"${python_bin}" -B "${skill_root}/scripts/build_context_capsule.py" --help >/dev/null
"${python_bin}" -B "${skill_root}/scripts/build_codex_dispatch.py" --help >/dev/null
"${python_bin}" -B "${skill_root}/scripts/validate_codex_dispatch_batch.py" --help >/dev/null
"${python_bin}" -m json.tool "${plugin_root}/.codex-plugin/plugin.json" >/dev/null
"${python_bin}" -m json.tool "${plugin_root}/.claude-plugin/plugin.json" >/dev/null
"${python_bin}" -m json.tool "${repo_root}/.agents/plugins/marketplace.json" >/dev/null
"${python_bin}" -m json.tool "${repo_root}/.claude-plugin/marketplace.json" >/dev/null
git -C "${repo_root}" diff --check
