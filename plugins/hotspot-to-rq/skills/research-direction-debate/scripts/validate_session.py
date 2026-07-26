#!/usr/bin/env python3
"""Validate a research-direction-debate session using only the Python standard library."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any


BASE_ARTIFACTS = (
    "project-evidence-pack.md",
    "direction-map.md",
    "candidate-directions.md",
    "debate-transcript.md",
    "external-evidence.md",
    "decision-packet.md",
)
RQ_ARTIFACT = "rq-brief.md"
EVALUATION_BASE_ARTIFACTS = (
    "experiment-evidence-pack.md",
    "result-validation.md",
    "claim-evidence-matrix.md",
    "evaluation-debate.md",
    "external-positioning.md",
    "evaluation-decision.md",
)
EVALUATION_NEXT_ARTIFACT = "next-experiment-plan.md"
SESSION_STATUSES = {
    "SCANNING",
    "DIRECTION_GATE",
    "CANDIDATE_GENERATION",
    "DEBATING",
    "USER_GATE",
    "RQ_REFINEMENT",
    "COMPLETE",
    "BLOCKED",
    "EVIDENCE_INTAKE",
    "RESULT_VALIDATION",
    "EXTERNAL_POSITIONING",
    "EVALUATION_DEBATE",
    "DECISION_GATE",
    "NEXT_EXPERIMENT",
}
DISCOVERY_STATUSES = {
    "SCANNING",
    "DIRECTION_GATE",
    "CANDIDATE_GENERATION",
    "DEBATING",
    "USER_GATE",
    "RQ_REFINEMENT",
    "COMPLETE",
    "BLOCKED",
}
EVALUATION_STATUSES = {
    "EVIDENCE_INTAKE",
    "RESULT_VALIDATION",
    "EXTERNAL_POSITIONING",
    "EVALUATION_DEBATE",
    "DECISION_GATE",
    "NEXT_EXPERIMENT",
    "COMPLETE",
    "BLOCKED",
}
CANDIDATE_STATUSES = {
    "SCREENED_OUT",
    "ACTIVE",
    "READY_FOR_GATE",
    "DOWNGRADED",
    "DEFERRED",
    "ELIMINATED",
    "SELECTED",
}
JUDGE_VERDICTS = {
    "CONTINUE",
    "SEARCH",
    "REVISE",
    "DOWNGRADE",
    "DEFER",
    "ELIMINATE",
    "USER_GATE",
    "CONVERGED",
}
CONFIDENCE_LEVELS = {"low", "medium", "high"}
EARLY_EXIT_CODES = {
    "DIRECT_PRIOR",
    "UNREPAIRABLE_CRITICAL_FLAW",
    "INACCESSIBLE_REQUIRED_DATA",
    "NO_DEFENSIBLE_CONTRIBUTION",
}
REJECTION_CODES = {
    "SESSION_MISMATCH",
    "PROJECT_MISMATCH",
    "CANDIDATE_MISMATCH",
    "ROUND_MISMATCH",
    "ROLE_CONTRACT_VIOLATION",
    "CONTEXT_CONTAMINATION",
    "UNTRUSTED_INSTRUCTION_FOLLOWED",
    "CONTROL_STALE_REVISION",
    "CONTROL_STALE_STATE",
    "CONTROL_INVALID_TRANSITION",
    "CONTROL_SCOPE_VIOLATION",
    "CONTROL_CONTRACT_VIOLATION",
    "CONTROL_PRECONDITION_FAILED",
    "OTHER",
}
VERIFICATION_LEVELS = {
    "SOURCE_EXISTS",
    "CLAIM_SUPPORTED_BY_SOURCE",
    "ARTIFACT_INSPECTED",
    "LOCALLY_REPRODUCED",
    "UNRESOLVED",
}
CLAIM_STATUSES = {
    "SUPPORTED",
    "CONTRADICTED",
    "INFERRED",
    "PROPOSED",
    "UNRESOLVED",
}
SOURCE_KINDS = {
    "paper",
    "proceedings",
    "repository",
    "dataset",
    "metadata",
    "official-doc",
}
PUBLICATION_STATUSES = {
    "peer-reviewed",
    "preprint",
    "repository",
    "dataset",
    "official-record",
    "other",
}
IDENTIFICATION_VERDICTS = {"PASS", "PASS_WITH_LIMITS", "REVISE", "BLOCK"}
GATE_STATUSES = {"READY_FOR_GATE", "DOWNGRADED", "SELECTED"}
EXECUTION_MODES = {"MULTI_AGENT", "DEGRADED_INLINE"}
INTERACTION_MODES = {"GUIDED", "AUTONOMOUS"}
MACRO_DIRECTION_STATUSES = {"PROPOSED", "SELECTED", "NOT_SELECTED"}
DIRECTION_SELECTION_SOURCES = {
    "USER",
    "PANEL_DELEGATED",
    "PANEL_AUTONOMOUS",
    "PRESEEDED",
}
EVALUATION_DECISIONS = {
    "CONTINUE",
    "REPAIR",
    "PIVOT",
    "STOP",
    "INSUFFICIENT_EVIDENCE",
}
EXPERIMENT_STATUSES = {"OBSERVED", "PARTIAL", "UNRESOLVED"}
CLAIM_EVIDENCE_STATUSES = {
    "SUPPORTED",
    "PARTIALLY_SUPPORTED",
    "CONTRADICTED",
    "INSUFFICIENT_EVIDENCE",
}
PHASE_ROLES = {
    "CONTROL": {
        "Mainline Workflow Controller",
        "Deterministic Mainline Fallback",
    },
    "DIRECTION_MAPPING": {"Macro Direction Mapper"},
    "DIRECTION_SELECTION": {"Panel Judge"},
    "HOTSPOT": {"Hotspot Analyst"},
    "SCREENING": {"Panel Judge"},
    "DEBATE": {
        "Socratic Mentor",
        "Evidence Researcher",
        "Search and Verification Specialist",
        "Devil's Advocate",
        "Panel Judge",
    },
    "IDENTIFICATION": {"Methodology Architect"},
    "FINAL_SELECTION": {"Panel Judge"},
    "RQ_REFINEMENT": {"Research Question Architect"},
    "EVIDENCE_INTAKE": {"Experiment Auditor"},
    "RESULT_VALIDATION": {"Statistical Reviewer", "Reproducibility Auditor"},
    "EXTERNAL_POSITIONING": {"Search and Verification Specialist"},
    "EVALUATION_DEBATE": {
        "Socratic Mentor",
        "Evidence Researcher",
        "Search and Verification Specialist",
        "Devil's Advocate",
        "Panel Judge",
    },
    "EVALUATION_DECISION": {"Panel Judge"},
    "NEXT_EXPERIMENT": {"Experiment Planner"},
}
DISCOVERY_DISPATCH_PHASES_BY_STATUS = {
    "SCANNING": {"DIRECTION_MAPPING", "DIRECTION_SELECTION"},
    "DIRECTION_GATE": set(),
    "CANDIDATE_GENERATION": {
        "DIRECTION_SELECTION",
        "HOTSPOT",
        "SCREENING",
    },
    "DEBATING": {"SCREENING", "DEBATE", "IDENTIFICATION", "FINAL_SELECTION"},
    "USER_GATE": set(),
    "RQ_REFINEMENT": {"RQ_REFINEMENT"},
    "COMPLETE": set(),
    "BLOCKED": set(),
}
EVALUATION_DISPATCH_PHASES_BY_STATUS = {
    "EVIDENCE_INTAKE": {"EVIDENCE_INTAKE"},
    "RESULT_VALIDATION": {"RESULT_VALIDATION"},
    "EXTERNAL_POSITIONING": {"EXTERNAL_POSITIONING"},
    "EVALUATION_DEBATE": {"EVALUATION_DEBATE", "EVALUATION_DECISION"},
    "DECISION_GATE": set(),
    "NEXT_EXPERIMENT": {"NEXT_EXPERIMENT"},
    "COMPLETE": set(),
    "BLOCKED": set(),
}
CONTROL_ACTIONS = {
    "ADVANCE",
    "HOLD_FOR_USER",
    "REPAIR_STATE",
    "RETRY_ROLE",
    "BLOCK_SESSION",
    "COMPLETE",
}
CONTROL_REQUIRED_ACTIONS = {
    "BUILD_PROJECT_EVIDENCE_PACK",
    "BUILD_EVALUATION_INPUT_SNAPSHOT",
    "APPLY_USER_DIRECTION_SELECTION",
    "APPLY_PANEL_DIRECTION_SELECTION",
    "APPLY_CANDIDATE_SELECTION",
    "APPLY_RQ_CONFIRMATION",
    "APPLY_RQ_REVISION",
    "APPLY_EVALUATION_DECISION",
    "APPLY_USER_REPAIR",
    "REPAIR_ARTIFACT_METADATA",
    "REPAIR_SESSION_STATE",
    "RECORD_UNRESOLVED_BLOCKER",
}
CONTROL_REQUIRED_CHECKS = {
    "PERSIST_STATE",
    "VERIFY_ENVELOPES",
    "ENFORCE_BUDGET",
    "RUN_SESSION_VALIDATOR",
    "VERIFY_GATE_RECEIPT",
    "VERIFY_PREREQUISITES",
}
DISPATCH_ARTIFACT_REQUIREMENTS = {
    "DIRECTION_MAPPING": {"PROJECT_EVIDENCE_PACK"},
    "DIRECTION_SELECTION": {"DIRECTION_MAP"},
    "HOTSPOT": {"PROJECT_EVIDENCE_PACK", "DIRECTION_MAP"},
    "SCREENING": {"CANDIDATE_DIRECTIONS"},
    "DEBATE": {"CANDIDATE_DIRECTIONS"},
    "IDENTIFICATION": {"DEBATE_TRANSCRIPT"},
    "FINAL_SELECTION": {"DEBATE_TRANSCRIPT"},
    "RQ_REFINEMENT": {"DECISION_PACKET"},
    "EVIDENCE_INTAKE": {"EVALUATION_INPUT_SNAPSHOT"},
    "RESULT_VALIDATION": {"EXPERIMENT_EVIDENCE_PACK"},
    "EXTERNAL_POSITIONING": {"RESULT_VALIDATION"},
    "EVALUATION_DEBATE": {"RESULT_VALIDATION", "EXTERNAL_POSITIONING"},
    "EVALUATION_DECISION": {"EVALUATION_DEBATE"},
    "NEXT_EXPERIMENT": {"EVALUATION_DECISION"},
}
CONTROL_INPUT_SNAPSHOT_KEYS = {
    "control_revision",
    "state_digest",
    "observed_status",
    "mode",
    "interaction_mode",
    "checkpoint",
    "completed_packet_ids",
    "failed_packets",
    "active_lanes",
    "accepted_verdicts",
    "artifact_readiness",
    "latest_validation",
    "budget_flags",
    "unresolved_blockers",
    "user_event",
    "allowed_target_statuses",
}
CONTROL_CHECKPOINTS = {
    "SESSION_INIT",
    "PHASE_BOUNDARY",
    "ROLE_BOUNDARY",
    "ROUND_BOUNDARY",
    "PRE_USER_GATE",
    "POST_USER_GATE",
    "RECOVERY",
    "RESUME",
    "PRE_COMPLETE",
}
CONTROLLER_STATUSES = {"ACTIVE", "DEGRADED_FALLBACK"}
PENDING_USER_GATES = {
    "DIRECTION_SELECTION",
    "CANDIDATE_SELECTION",
    "RQ_CONFIRMATION",
    "EVALUATION_DECISION",
}
GATE_STATUS_REQUIREMENTS = {
    "DIRECTION_GATE": "DIRECTION_SELECTION",
    "USER_GATE": "CANDIDATE_SELECTION",
    "DECISION_GATE": "EVALUATION_DECISION",
}
GATE_RECEIPT_ACTIONS = {
    "DIRECTION_SELECTION": {"SELECT", "DELEGATE", "REVISE"},
    "CANDIDATE_SELECTION": {"SELECT", "REJECT", "BROADEN"},
    "RQ_CONFIRMATION": {"CONFIRM", "REVISE"},
    "EVALUATION_DECISION": {"CONFIRM", "OVERRIDE"},
    "BLOCKER_DECISION": {"REPAIR", "STOP"},
}
RECEIPT_TARGETS = {
    ("DIRECTION_SELECTION", "SELECT"): {"CANDIDATE_GENERATION"},
    ("DIRECTION_SELECTION", "DELEGATE"): {"SCANNING"},
    ("DIRECTION_SELECTION", "REVISE"): {"SCANNING"},
    ("CANDIDATE_SELECTION", "SELECT"): {"RQ_REFINEMENT"},
    ("CANDIDATE_SELECTION", "REJECT"): {
        "CANDIDATE_GENERATION",
        "DEBATING",
    },
    ("CANDIDATE_SELECTION", "BROADEN"): {
        "CANDIDATE_GENERATION",
        "DEBATING",
    },
    ("RQ_CONFIRMATION", "CONFIRM"): {"RQ_REFINEMENT"},
    ("RQ_CONFIRMATION", "REVISE"): {"RQ_REFINEMENT"},
    ("EVALUATION_DECISION", "CONFIRM"): {"NEXT_EXPERIMENT"},
    ("EVALUATION_DECISION", "OVERRIDE"): {
        "NEXT_EXPERIMENT",
        "EVALUATION_DEBATE",
        "RESULT_VALIDATION",
    },
}
DISCOVERY_TRANSITIONS = {
    "SCANNING": {"SCANNING", "DIRECTION_GATE", "CANDIDATE_GENERATION", "BLOCKED"},
    "DIRECTION_GATE": {
        "SCANNING",
        "DIRECTION_GATE",
        "CANDIDATE_GENERATION",
        "BLOCKED",
    },
    "CANDIDATE_GENERATION": {
        "CANDIDATE_GENERATION",
        "DEBATING",
        "USER_GATE",
        "BLOCKED",
    },
    "DEBATING": {"DEBATING", "USER_GATE", "BLOCKED"},
    "USER_GATE": {
        "USER_GATE",
        "RQ_REFINEMENT",
        "CANDIDATE_GENERATION",
        "DEBATING",
        "BLOCKED",
    },
    "RQ_REFINEMENT": {
        "RQ_REFINEMENT",
        "DEBATING",
        "USER_GATE",
        "COMPLETE",
        "BLOCKED",
    },
    "BLOCKED": DISCOVERY_STATUSES - {"COMPLETE"},
    "COMPLETE": {"COMPLETE"},
}
EVALUATION_TRANSITIONS = {
    "EVIDENCE_INTAKE": {"EVIDENCE_INTAKE", "RESULT_VALIDATION", "BLOCKED"},
    "RESULT_VALIDATION": {"RESULT_VALIDATION", "EXTERNAL_POSITIONING", "BLOCKED"},
    "EXTERNAL_POSITIONING": {
        "EXTERNAL_POSITIONING",
        "EVALUATION_DEBATE",
        "BLOCKED",
    },
    "EVALUATION_DEBATE": {"EVALUATION_DEBATE", "DECISION_GATE", "BLOCKED"},
    "DECISION_GATE": {
        "DECISION_GATE",
        "NEXT_EXPERIMENT",
        "EVALUATION_DEBATE",
        "RESULT_VALIDATION",
        "BLOCKED",
    },
    "NEXT_EXPERIMENT": {
        "NEXT_EXPERIMENT",
        "DECISION_GATE",
        "COMPLETE",
        "BLOCKED",
    },
    "BLOCKED": EVALUATION_STATUSES - {"COMPLETE"},
    "COMPLETE": {"COMPLETE"},
}
CORE_ROUND_ROLES = {
    "Socratic Mentor",
    "Evidence Researcher",
    "Devil's Advocate",
    "Panel Judge",
}
SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
CODE = re.compile(r"^[A-Z][A-Z0-9_]*$")
HEADER = re.compile(
    r"\A---[ \t]*\r?\n(?P<body>.*?)\r?\n---[ \t]*(?:\r?\n|\Z)",
    re.DOTALL,
)
TEN_MIB = 10 * 1024 * 1024


def is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def nonempty_string(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def key_component(value: Any) -> Any:
    if value is None or isinstance(value, str) or is_int(value):
        return value
    return f"<INVALID_{type(value).__name__.upper()}>"


def duplicate_values(values: list[Any]) -> list[Any]:
    seen: list[Any] = []
    duplicates: list[Any] = []
    for value in values:
        if value in seen and value not in duplicates:
            duplicates.append(value)
        elif value not in seen:
            seen.append(value)
    return duplicates


def is_sha256(value: Any) -> bool:
    return isinstance(value, str) and bool(re.fullmatch(r"[0-9a-f]{64}", value))


def require_keys(
    value: Any,
    keys: tuple[str, ...],
    location: str,
    errors: list[str],
) -> bool:
    if not isinstance(value, dict):
        errors.append(f"{location} must be an object")
        return False
    missing = [key for key in keys if key not in value]
    for key in missing:
        errors.append(f"{location}.{key} is required")
    return not missing


def parse_markdown_header(path: Path, errors: list[str]) -> dict[str, str] | None:
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        errors.append(f"{path.name}: cannot read file: {exc}")
        return None

    match = HEADER.match(text)
    if not match:
        errors.append(f"{path.name}: missing leading metadata header")
        return None

    metadata: dict[str, str] = {}
    for raw_line in match.group("body").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if ":" not in line:
            errors.append(f"{path.name}: malformed metadata line {raw_line!r}")
            continue
        key, value = line.split(":", 1)
        metadata[key.strip()] = value.strip().strip("\"'")
    return metadata


def validate_artifacts(
    session_dir: Path,
    session_id: str,
    status: str,
    mode: str,
    errors: list[str],
) -> None:
    if mode == "evaluate":
        artifact_names = list(EVALUATION_BASE_ARTIFACTS)
        next_path = session_dir / EVALUATION_NEXT_ARTIFACT
        if status in {"NEXT_EXPERIMENT", "COMPLETE"}:
            artifact_names.append(EVALUATION_NEXT_ARTIFACT)
        elif next_path.exists():
            errors.append(
                f"{EVALUATION_NEXT_ARTIFACT}: must not exist before "
                "NEXT_EXPERIMENT status"
            )
    else:
        artifact_names = list(BASE_ARTIFACTS)
        rq_path = session_dir / RQ_ARTIFACT
        if status == "COMPLETE":
            artifact_names.append(RQ_ARTIFACT)
        elif rq_path.exists():
            errors.append(
                f"{RQ_ARTIFACT}: must not exist before final confirmation and COMPLETE status"
            )

    for name in artifact_names:
        path = session_dir / name
        if not path.is_file():
            errors.append(f"{name}: required artifact is missing")
            continue
        metadata = parse_markdown_header(path, errors)
        if metadata is None:
            continue
        if metadata.get("session_id") != session_id:
            errors.append(
                f"{name}: session_id {metadata.get('session_id')!r} "
                f"does not match {session_id!r}"
            )
        if metadata.get("artifact") != name:
            errors.append(
                f"{name}: artifact metadata must equal the exact filename"
            )
        if metadata.get("status") != status:
            errors.append(
                f"{name}: status {metadata.get('status')!r} does not match {status!r}"
            )
        if not nonempty_string(metadata.get("updated_at")):
            errors.append(f"{name}: updated_at metadata is required")
        if name in {RQ_ARTIFACT, EVALUATION_NEXT_ARTIFACT}:
            try:
                text = path.read_text(encoding="utf-8")
            except (OSError, UnicodeError):
                continue
            header = HEADER.match(text)
            if header is not None and not text[header.end():].strip():
                errors.append(f"{name}: final artifact body must not be empty")


def validate_search_usage(
    usage: Any,
    location: str,
    errors: list[str],
) -> None:
    required = (
        "query_batches",
        "queries",
        "sources_inspected",
        "budget_extension",
    )
    if not require_keys(usage, required, location, errors):
        return

    query_batches = usage.get("query_batches")
    queries = usage.get("queries")
    sources = usage.get("sources_inspected")
    for key, value in (
        ("query_batches", query_batches),
        ("queries", queries),
        ("sources_inspected", sources),
    ):
        if not is_int(value) or value < 0:
            errors.append(f"{location}.{key} must be a non-negative integer")

    if not all(is_int(value) and value >= 0 for value in (query_batches, queries, sources)):
        return

    max_batches = 2
    max_sources = 8
    extension = usage.get("budget_extension")
    if extension is not None:
        if not require_keys(
            extension,
            ("judge_reason", "extra_query_batches", "extra_sources"),
            f"{location}.budget_extension",
            errors,
        ):
            return
        reason = extension.get("judge_reason")
        extra_batches = extension.get("extra_query_batches")
        extra_sources = extension.get("extra_sources")
        if not nonempty_string(reason):
            errors.append(
                f"{location}.budget_extension.judge_reason must be non-empty"
            )
        if not is_int(extra_batches) or not 0 <= extra_batches <= 1:
            errors.append(
                f"{location}.budget_extension.extra_query_batches must be 0 or 1"
            )
        else:
            max_batches += extra_batches
        if not is_int(extra_sources) or not 0 <= extra_sources <= 4:
            errors.append(
                f"{location}.budget_extension.extra_sources must be between 0 and 4"
            )
        else:
            max_sources += extra_sources

    if query_batches > max_batches:
        errors.append(
            f"{location}.query_batches exceeds the allowed budget of {max_batches}"
        )
    if queries > query_batches * 4:
        errors.append(
            f"{location}.queries exceeds four queries per recorded batch"
        )
    if sources > max_sources:
        errors.append(
            f"{location}.sources_inspected exceeds the allowed budget of {max_sources}"
        )


def validate_identification_audit(
    audit: Any,
    location: str,
    errors: list[str],
    require_passing: bool,
) -> None:
    fields = (
        "estimand",
        "unit_of_analysis",
        "treatment_or_contrast",
        "identifying_assumptions",
        "falsifier",
        "prohibited_interpretations",
        "power_or_information_gate",
        "validity_threats",
        "resource_requirements",
        "verdict",
        "limitations",
    )
    if not require_keys(audit, fields, location, errors):
        return

    for key in (
        "estimand",
        "unit_of_analysis",
        "treatment_or_contrast",
        "falsifier",
        "power_or_information_gate",
    ):
        if not nonempty_string(audit.get(key)):
            errors.append(f"{location}.{key} must be non-empty")
    for key in (
        "identifying_assumptions",
        "prohibited_interpretations",
        "validity_threats",
        "resource_requirements",
        "limitations",
    ):
        if not isinstance(audit.get(key), list):
            errors.append(f"{location}.{key} must be an array")

    verdict = audit.get("verdict")
    if verdict not in IDENTIFICATION_VERDICTS:
        errors.append(
            f"{location}.verdict must be one of {sorted(IDENTIFICATION_VERDICTS)}"
        )
    if require_passing and verdict not in {"PASS", "PASS_WITH_LIMITS"}:
        errors.append(f"{location}.verdict must pass before the user gate")


def validate_macro_directions(
    state: dict[str, Any],
    errors: list[str],
) -> None:
    mode = state.get("mode")
    interaction_mode = state.get("interaction_mode")
    status = state.get("status")
    directions = state.get("macro_directions")
    selected = state.get("selected_macro_direction_ids")
    selection = state.get("direction_selection")

    if mode == "evaluate":
        if directions != []:
            errors.append(
                "session-state.json: evaluate mode must keep macro_directions empty"
            )
        if selected != []:
            errors.append(
                "session-state.json: evaluate mode must keep selected_macro_direction_ids empty"
            )
        if selection is not None:
            errors.append(
                "session-state.json: evaluate mode must keep direction_selection null"
            )
        return

    if not isinstance(directions, list):
        errors.append("session-state.json: macro_directions must be an array")
        return
    if not isinstance(selected, list):
        errors.append(
            "session-state.json: selected_macro_direction_ids must be an array"
        )
        return
    if not all(nonempty_string(value) for value in selected):
        errors.append(
            "session-state.json: selected_macro_direction_ids must contain "
            "only non-empty strings"
        )
    duplicates = duplicate_values(selected)
    if duplicates:
        errors.append(
            "session-state.json: selected_macro_direction_ids contains "
            f"duplicates {duplicates}"
        )

    direction_ids: list[str] = []
    by_id: dict[str, dict[str, Any]] = {}
    required = (
        "direction_id",
        "title",
        "scope",
        "local_signals",
        "plausible_contribution_types",
        "indicative_cost",
        "indicative_risk",
        "uncertainty",
        "panel_note",
        "status",
    )
    for index, direction in enumerate(directions):
        location = f"macro_directions[{index}]"
        if not require_keys(direction, required, location, errors):
            continue
        direction_id = direction.get("direction_id")
        if not nonempty_string(direction_id) or not re.fullmatch(
            r"D[0-9]{2,}", direction_id
        ):
            errors.append(f"{location}.direction_id must use D01-style IDs")
            continue
        direction_ids.append(direction_id)
        if direction_id in by_id:
            errors.append(f"{location}.direction_id duplicates {direction_id!r}")
            continue
        by_id[direction_id] = direction

        for key in ("title", "scope", "panel_note"):
            if not nonempty_string(direction.get(key)):
                errors.append(f"{location}.{key} must be non-empty")
        for key in (
            "local_signals",
            "plausible_contribution_types",
            "uncertainty",
        ):
            value = direction.get(key)
            if not isinstance(value, list):
                errors.append(f"{location}.{key} must be an array")
            elif key != "uncertainty" and not value:
                errors.append(f"{location}.{key} must not be empty")
        for key in ("indicative_cost", "indicative_risk"):
            if direction.get(key) not in {"low", "medium", "high", "unknown"}:
                errors.append(
                    f"{location}.{key} must be low, medium, high, or unknown"
                )
        if direction.get("status") not in MACRO_DIRECTION_STATUSES:
            errors.append(
                f"{location}.status must be one of "
                f"{sorted(MACRO_DIRECTION_STATUSES)}"
            )

    duplicate_ids = duplicate_values(direction_ids)
    if duplicate_ids:
        errors.append(
            f"session-state.json: duplicate macro direction IDs {duplicate_ids}"
        )
    for direction_id in selected:
        if direction_id not in by_id:
            errors.append(
                f"session-state.json: selected macro direction "
                f"{direction_id!r} does not exist"
            )

    mapping_required = status not in {"SCANNING", "BLOCKED"}
    if mode == "discover":
        if mapping_required and not 4 <= len(directions) <= 6:
            errors.append(
                "session-state.json: discover mode requires 4-6 macro directions"
            )
        if not mapping_required and len(directions) not in {0, 4, 5, 6}:
            errors.append(
                "session-state.json: discover mode macro direction count "
                "must be 0 or 4-6"
            )
    elif mapping_required and not 1 <= len(directions) <= 6:
        errors.append(
            "session-state.json: refine/rq-only mode requires 1-6 macro directions"
        )

    if status == "SCANNING":
        if selected:
            errors.append(
                "session-state.json: no macro direction may be selected while SCANNING"
            )
        if selection is not None:
            errors.append(
                "session-state.json: direction_selection must be null while SCANNING"
            )
        return

    if status == "DIRECTION_GATE":
        if interaction_mode != "GUIDED":
            errors.append(
                "session-state.json: DIRECTION_GATE is only valid in GUIDED mode"
            )
        if selected:
            errors.append(
                "session-state.json: DIRECTION_GATE must wait with no selected "
                "macro directions"
            )
        if selection is not None:
            errors.append(
                "session-state.json: direction_selection must be null at "
                "DIRECTION_GATE"
            )
        for direction_id, direction in by_id.items():
            if direction.get("status") != "PROPOSED":
                errors.append(
                    f"macro direction {direction_id!r}: status must remain PROPOSED "
                    "at DIRECTION_GATE"
                )
        return

    selection_required = status in {
        "CANDIDATE_GENERATION",
        "DEBATING",
        "USER_GATE",
        "RQ_REFINEMENT",
        "COMPLETE",
    }
    if selection_required:
        if not 1 <= len(selected) <= 2:
            errors.append(
                "session-state.json: one or two macro directions must be selected"
            )
        if not require_keys(
            selection,
            ("selected_by", "selected_at", "rationale"),
            "direction_selection",
            errors,
        ):
            return
        selected_by = selection.get("selected_by")
        if selected_by not in DIRECTION_SELECTION_SOURCES:
            errors.append(
                "direction_selection.selected_by must be one of "
                f"{sorted(DIRECTION_SELECTION_SOURCES)}"
            )
        if not nonempty_string(selection.get("selected_at")):
            errors.append("direction_selection.selected_at must be non-empty")
        if not nonempty_string(selection.get("rationale")):
            errors.append("direction_selection.rationale must be non-empty")

        if interaction_mode == "GUIDED" and selected_by not in {
            "USER",
            "PANEL_DELEGATED",
            "PRESEEDED",
        }:
            errors.append(
                "direction_selection: GUIDED mode requires USER, "
                "PANEL_DELEGATED, or PRESEEDED"
            )
        if interaction_mode == "AUTONOMOUS" and selected_by not in {
            "PANEL_AUTONOMOUS",
            "PRESEEDED",
        }:
            errors.append(
                "direction_selection: AUTONOMOUS mode requires "
                "PANEL_AUTONOMOUS or PRESEEDED"
            )
        if mode == "discover" and selected_by == "PRESEEDED":
            errors.append(
                "direction_selection: PRESEEDED is only valid in refine or "
                "rq-only mode"
            )

        for direction_id, direction in by_id.items():
            expected = "SELECTED" if direction_id in selected else "NOT_SELECTED"
            if direction.get("status") != expected:
                errors.append(
                    f"macro direction {direction_id!r}: status must be {expected}"
                )
    elif status == "BLOCKED" and selected:
        if selection is None:
            errors.append(
                "session-state.json: blocked state with selected directions "
                "requires direction_selection"
            )


def validate_candidates(
    state: dict[str, Any],
    errors: list[str],
) -> None:
    mode = state.get("mode")
    interaction_mode = state.get("interaction_mode")
    status = state.get("status")
    min_rounds = state.get("min_rounds")
    max_rounds = state.get("max_rounds")
    selected_macro_ids = state.get("selected_macro_direction_ids")
    generated = state.get("generated_candidate_ids")
    initial = state.get("initial_debate_candidate_ids")
    gate_ids = state.get("user_gate_candidate_ids")
    candidates = state.get("candidates")

    for key, value in (
        ("generated_candidate_ids", generated),
        ("initial_debate_candidate_ids", initial),
        ("user_gate_candidate_ids", gate_ids),
        ("candidates", candidates),
    ):
        if not isinstance(value, list):
            errors.append(f"session-state.json: {key} must be an array")
    if not all(isinstance(value, list) for value in (generated, initial, gate_ids, candidates)):
        return

    if mode == "evaluate":
        if generated or initial or gate_ids or candidates:
            errors.append(
                "session-state.json: evaluate mode must keep generated and candidate fields empty"
            )
        if state.get("selected_candidate_id") is not None:
            errors.append(
                "session-state.json: evaluate mode must keep selected_candidate_id null"
            )
        return

    for key, values in (
        ("generated_candidate_ids", generated),
        ("initial_debate_candidate_ids", initial),
        ("user_gate_candidate_ids", gate_ids),
    ):
        if not all(nonempty_string(value) for value in values):
            errors.append(f"session-state.json: {key} must contain only non-empty strings")
        duplicates = duplicate_values(values)
        if duplicates:
            errors.append(f"session-state.json: {key} contains duplicates {duplicates}")

    strict_candidate_counts = status not in {
        "SCANNING",
        "DIRECTION_GATE",
        "CANDIDATE_GENERATION",
        "BLOCKED",
    }
    if status in {"SCANNING", "DIRECTION_GATE"}:
        if generated or initial or candidates:
            errors.append(
                f"session-state.json: {status} must not contain detailed candidates"
            )
    elif mode == "discover" and strict_candidate_counts:
        if interaction_mode == "GUIDED" and not 3 <= len(generated) <= 6:
            errors.append(
                "session-state.json: GUIDED discover mode requires "
                "3-6 generated candidates"
            )
        if interaction_mode == "AUTONOMOUS" and not 5 <= len(generated) <= 8:
            errors.append(
                "session-state.json: AUTONOMOUS discover mode requires "
                "5-8 generated candidates"
            )
    elif strict_candidate_counts and not 1 <= len(generated) <= 8:
        errors.append(
            "session-state.json: refine/rq-only mode requires 1-8 seeded candidates"
        )
    elif status == "CANDIDATE_GENERATION" and generated:
        if (
            mode == "discover"
            and interaction_mode == "GUIDED"
            and not 3 <= len(generated) <= 6
        ):
            errors.append(
                "session-state.json: GUIDED candidate generation must contain "
                "0 or 3-6 candidates"
            )
        if (
            mode == "discover"
            and interaction_mode == "AUTONOMOUS"
            and not 5 <= len(generated) <= 8
        ):
            errors.append(
                "session-state.json: AUTONOMOUS candidate generation must "
                "contain 0 or 5-8 candidates"
            )
        if mode in {"refine", "rq-only"} and not 1 <= len(generated) <= 8:
            errors.append(
                "session-state.json: refine/rq-only candidate generation must "
                "contain 0 or 1-8 candidates"
            )

    if len(initial) > 3:
        errors.append(
            "session-state.json: at most three candidates may enter initial debate"
        )
    if strict_candidate_counts and not initial:
        errors.append(
            "session-state.json: at least one candidate must enter debate"
        )
    for candidate_id in initial:
        if candidate_id not in generated:
            errors.append(
                f"session-state.json: initial candidate {candidate_id!r} "
                "is not in generated_candidate_ids"
            )

    if status in {"USER_GATE", "RQ_REFINEMENT", "COMPLETE"}:
        if not 1 <= len(gate_ids) <= 3:
            errors.append(
                "session-state.json: user gate requires one to three candidate IDs"
            )
    elif gate_ids:
        errors.append(
            "session-state.json: user_gate_candidate_ids must be empty before USER_GATE"
        )

    by_id: dict[str, dict[str, Any]] = {}
    for index, candidate in enumerate(candidates):
        location = f"candidates[{index}]"
        fields = (
            "candidate_id",
            "macro_direction_id",
            "origin",
            "parent_id",
            "status",
            "gate_ready",
            "rounds_completed",
            "rounds",
            "early_exit_reason",
            "identification_audit",
        )
        if not require_keys(candidate, fields, location, errors):
            continue

        candidate_id = candidate.get("candidate_id")
        if not nonempty_string(candidate_id) or not SAFE_ID.fullmatch(candidate_id):
            errors.append(f"{location}.candidate_id is invalid")
            continue
        if candidate_id in by_id:
            errors.append(f"{location}.candidate_id duplicates {candidate_id!r}")
            continue
        by_id[candidate_id] = candidate

        macro_direction_id = candidate.get("macro_direction_id")
        if not nonempty_string(macro_direction_id):
            errors.append(f"{location}.macro_direction_id must be non-empty")
        elif not isinstance(selected_macro_ids, list) or macro_direction_id not in selected_macro_ids:
            errors.append(
                f"{location}.macro_direction_id must reference a selected "
                "macro direction"
            )

        origin = candidate.get("origin")
        parent_id = candidate.get("parent_id")
        if origin not in {"GENERATED", "DERIVED"}:
            errors.append(f"{location}.origin must be GENERATED or DERIVED")
        if origin == "GENERATED":
            if parent_id is not None:
                errors.append(f"{location}.parent_id must be null for GENERATED")
            if candidate_id not in generated:
                errors.append(
                    f"{location}: generated candidate is absent from generated_candidate_ids"
                )
        if origin == "DERIVED":
            if not nonempty_string(parent_id):
                errors.append(f"{location}.parent_id is required for DERIVED")
            elif not candidate_id.startswith(f"{parent_id}-R"):
                errors.append(
                    f"{location}.candidate_id must preserve parent lineage as <parent>-R<n>"
                )

        candidate_status = candidate.get("status")
        if candidate_status not in CANDIDATE_STATUSES:
            errors.append(
                f"{location}.status must be one of {sorted(CANDIDATE_STATUSES)}"
            )
        if candidate_status == "DOWNGRADED" and origin != "DERIVED":
            errors.append(f"{location}: DOWNGRADED status requires DERIVED origin")
        if not isinstance(candidate.get("gate_ready"), bool):
            errors.append(f"{location}.gate_ready must be boolean")

        rounds = candidate.get("rounds")
        rounds_completed = candidate.get("rounds_completed")
        if not isinstance(rounds, list):
            errors.append(f"{location}.rounds must be an array")
            continue
        if not is_int(rounds_completed) or rounds_completed < 0:
            errors.append(f"{location}.rounds_completed must be a non-negative integer")
            continue
        if rounds_completed != len(rounds):
            errors.append(
                f"{location}.rounds_completed does not equal the number of round records"
            )
        if is_int(max_rounds) and rounds_completed > max_rounds:
            errors.append(f"{location}.rounds_completed exceeds max_rounds")
        if candidate_status == "SCREENED_OUT" and rounds_completed != 0:
            errors.append(f"{location}: SCREENED_OUT candidates must have zero rounds")

        for round_index, round_record in enumerate(rounds, start=1):
            round_location = f"{location}.rounds[{round_index - 1}]"
            if not require_keys(
                round_record,
                ("round", "verdict", "confidence", "search_usage"),
                round_location,
                errors,
            ):
                continue
            if (
                not is_int(round_record.get("round"))
                or round_record.get("round") != round_index
            ):
                errors.append(
                    f"{round_location}.round must be sequential and equal {round_index}"
                )
            if round_record.get("verdict") not in JUDGE_VERDICTS:
                errors.append(
                    f"{round_location}.verdict must be one of {sorted(JUDGE_VERDICTS)}"
                )
            validate_search_usage(
                round_record.get("search_usage"),
                f"{round_location}.search_usage",
                errors,
            )

        audit = candidate.get("identification_audit")
        if audit is not None:
            validate_identification_audit(
                audit,
                f"{location}.identification_audit",
                errors,
                require_passing=candidate_id in gate_ids,
            )

        if candidate_status == "DEFERRED":
            reason = candidate.get("early_exit_reason")
            if not isinstance(reason, dict) or reason.get("code") != "USER_OWNED_CONSTRAINT":
                errors.append(
                    f"{location}: DEFERRED requires early_exit_reason code "
                    "USER_OWNED_CONSTRAINT"
                )

        debated = candidate_id in initial or origin == "DERIVED"
        if (
            debated
            and candidate_status == "ELIMINATED"
            and is_int(min_rounds)
            and rounds_completed < min_rounds
        ):
            reason = candidate.get("early_exit_reason")
            code = reason.get("code") if isinstance(reason, dict) else None
            last_verdict = (
                rounds[-1].get("verdict")
                if rounds and isinstance(rounds[-1], dict)
                else None
            )
            allowed = code in EARLY_EXIT_CODES
            material_rescope = (
                code == "MATERIAL_RESCOPING" and last_verdict == "DOWNGRADE"
            )
            if not (allowed or material_rescope):
                errors.append(
                    f"{location}: elimination before min_rounds requires an allowed "
                    "early-exit code or a DOWNGRADE/MATERIAL_RESCOPING transition"
                )

    for candidate_id in generated:
        if candidate_id not in by_id:
            errors.append(
                f"session-state.json: generated candidate {candidate_id!r} has no object"
            )

    for candidate_id, candidate in by_id.items():
        if candidate.get("origin") != "DERIVED":
            continue
        parent_id = candidate.get("parent_id")
        parent = by_id.get(parent_id)
        if parent is None:
            errors.append(
                f"candidate {candidate_id!r}: parent {parent_id!r} does not exist"
            )
            continue
        if parent.get("status") != "ELIMINATED":
            errors.append(
                f"candidate {candidate_id!r}: derived parent must be ELIMINATED"
            )
        if candidate.get("macro_direction_id") != parent.get("macro_direction_id"):
            errors.append(
                f"candidate {candidate_id!r}: derived candidate must inherit "
                "the parent's macro_direction_id"
            )
        parent_rounds = parent.get("rounds")
        last_verdict = (
            parent_rounds[-1].get("verdict")
            if isinstance(parent_rounds, list)
            and parent_rounds
            and isinstance(parent_rounds[-1], dict)
            else None
        )
        reason = parent.get("early_exit_reason")
        reason_code = reason.get("code") if isinstance(reason, dict) else None
        if last_verdict != "DOWNGRADE" or reason_code != "MATERIAL_RESCOPING":
            errors.append(
                f"candidate {candidate_id!r}: parent must end with "
                "DOWNGRADE and MATERIAL_RESCOPING"
            )

    for candidate_id in gate_ids:
        candidate = by_id.get(candidate_id)
        if candidate is None:
            errors.append(
                f"session-state.json: gate candidate {candidate_id!r} does not exist"
            )
            continue
        if candidate.get("status") not in GATE_STATUSES:
            errors.append(
                f"candidate {candidate_id!r}: status is not eligible for the user gate"
            )
        if candidate.get("gate_ready") is not True:
            errors.append(
                f"candidate {candidate_id!r}: gate_ready must be true"
            )
        rounds_completed = candidate.get("rounds_completed")
        if is_int(min_rounds) and (
            not is_int(rounds_completed) or rounds_completed < min_rounds
        ):
            errors.append(
                f"candidate {candidate_id!r}: user-gate candidates require "
                f"at least {min_rounds} rounds"
            )
        rounds = candidate.get("rounds")
        last_verdict = (
            rounds[-1].get("verdict")
            if isinstance(rounds, list)
            and rounds
            and isinstance(rounds[-1], dict)
            else None
        )
        early_exit_reason = candidate.get("early_exit_reason")
        maximum_round_stop = (
            is_int(max_rounds)
            and rounds_completed == max_rounds
            and isinstance(early_exit_reason, dict)
            and early_exit_reason.get("code") == "MAX_ROUND_NONCONVERGENCE"
        )
        if last_verdict != "CONVERGED" and not maximum_round_stop:
            errors.append(
                f"candidate {candidate_id!r}: user gate requires CONVERGED or "
                "a marked maximum-round non-convergence stop"
            )
        audit = candidate.get("identification_audit")
        if audit is None:
            errors.append(
                f"candidate {candidate_id!r}: identification_audit is required"
            )

    selected = state.get("selected_candidate_id")
    selected_status_ids = [
        candidate_id
        for candidate_id, candidate in by_id.items()
        if candidate.get("status") == "SELECTED"
    ]
    if status == "USER_GATE" and selected_status_ids:
        errors.append(
            "session-state.json: candidates must not be SELECTED before the "
            "candidate gate receipt"
        )
    if status in {"RQ_REFINEMENT", "COMPLETE"}:
        if not nonempty_string(selected):
            errors.append(
                "session-state.json: selected_candidate_id is required after USER_GATE"
            )
        elif selected not in gate_ids:
            errors.append(
                "session-state.json: selected_candidate_id must be a user-gate candidate"
            )
        elif selected in by_id and by_id[selected].get("status") != "SELECTED":
            errors.append(
                f"candidate {selected!r}: selected candidate status must be SELECTED"
            )
        if selected_status_ids != [selected]:
            errors.append(
                "session-state.json: exactly the selected_candidate_id must "
                "have candidate status SELECTED"
            )
    elif selected is not None:
        errors.append(
            "session-state.json: selected_candidate_id must be null before selection"
        )


def validate_evaluation_state(state: dict[str, Any], errors: list[str]) -> None:
    if state.get("mode") != "evaluate":
        return

    status = state.get("status")
    target = state.get("evaluation_target")
    inventory = state.get("experiment_inventory")
    matrix = state.get("claim_evidence_matrix")
    rounds = state.get("evaluation_rounds")
    decision = state.get("evaluation_decision")
    next_experiment = state.get("next_experiment")

    if not require_keys(
        target,
        ("direction", "primary_claim", "study_type", "constraints"),
        "evaluation_target",
        errors,
    ):
        target = None
    if isinstance(target, dict):
        missing_codes = {
            "direction": "EVALUATION_DIRECTION",
            "primary_claim": "PRIMARY_CLAIM",
            "study_type": "STUDY_TYPE",
        }
        user_required = state.get("user_required")
        user_required_codes = {
            value
            for value in user_required
            if nonempty_string(value)
        } if isinstance(user_required, list) else set()
        for key, missing_code in missing_codes.items():
            if nonempty_string(target.get(key)):
                continue
            if status == "EVIDENCE_INTAKE" and missing_code in user_required_codes:
                continue
            errors.append(
                f"evaluation_target.{key} must be non-empty outside a matching "
                f"EVIDENCE_INTAKE user_required code {missing_code}"
            )
        if not isinstance(target.get("constraints"), list):
            errors.append("evaluation_target.constraints must be an array")

    if not isinstance(inventory, list):
        errors.append("session-state.json: experiment_inventory must be an array")
        inventory = []
    experiment_ids: set[str] = set()
    for index, experiment in enumerate(inventory):
        location = f"experiment_inventory[{index}]"
        if not require_keys(
            experiment,
            ("experiment_id", "hypothesis", "artifact_paths", "outcome_summary", "status"),
            location,
            errors,
        ):
            continue
        experiment_id = experiment.get("experiment_id")
        if not nonempty_string(experiment_id) or not SAFE_ID.fullmatch(experiment_id):
            errors.append(f"{location}.experiment_id is invalid")
        elif experiment_id in experiment_ids:
            errors.append(f"{location}.experiment_id duplicates {experiment_id!r}")
        else:
            experiment_ids.add(experiment_id)
        for key in ("hypothesis", "outcome_summary"):
            if not nonempty_string(experiment.get(key)):
                errors.append(f"{location}.{key} must be non-empty")
        paths = experiment.get("artifact_paths")
        if not isinstance(paths, list) or not paths or not all(nonempty_string(path) for path in paths):
            errors.append(f"{location}.artifact_paths must be a non-empty string array")
        if experiment.get("status") not in EXPERIMENT_STATUSES:
            errors.append(
                f"{location}.status must be one of {sorted(EXPERIMENT_STATUSES)}"
            )

    if not isinstance(matrix, list):
        errors.append("session-state.json: claim_evidence_matrix must be an array")
        matrix = []
    claim_ids: set[str] = set()
    for index, row in enumerate(matrix):
        location = f"claim_evidence_matrix[{index}]"
        if not require_keys(
            row,
            ("claim_id", "claim", "evidence_ids", "support_status", "limitations"),
            location,
            errors,
        ):
            continue
        claim_id = row.get("claim_id")
        if not nonempty_string(claim_id) or not SAFE_ID.fullmatch(claim_id):
            errors.append(f"{location}.claim_id is invalid")
        elif claim_id in claim_ids:
            errors.append(f"{location}.claim_id duplicates {claim_id!r}")
        else:
            claim_ids.add(claim_id)
        if not nonempty_string(row.get("claim")):
            errors.append(f"{location}.claim must be non-empty")
        evidence_ids = row.get("evidence_ids")
        if not isinstance(evidence_ids, list) or not evidence_ids:
            errors.append(f"{location}.evidence_ids must be a non-empty array")
        elif not all(nonempty_string(value) for value in evidence_ids):
            errors.append(f"{location}.evidence_ids must contain non-empty strings")
        elif unknown := [value for value in evidence_ids if value not in experiment_ids]:
            errors.append(f"{location}.evidence_ids reference unknown experiments {unknown}")
        if row.get("support_status") not in CLAIM_EVIDENCE_STATUSES:
            errors.append(
                f"{location}.support_status must be one of {sorted(CLAIM_EVIDENCE_STATUSES)}"
            )
        if not isinstance(row.get("limitations"), list):
            errors.append(f"{location}.limitations must be an array")

    if not isinstance(rounds, list):
        errors.append("session-state.json: evaluation_rounds must be an array")
        rounds = []
    max_rounds = state.get("max_rounds")
    for index, round_record in enumerate(rounds, start=1):
        location = f"evaluation_rounds[{index - 1}]"
        if not require_keys(
            round_record,
            ("round", "verdict", "confidence", "search_usage"),
            location,
            errors,
        ):
            continue
        if (
            not is_int(round_record.get("round"))
            or round_record.get("round") != index
        ):
            errors.append(f"{location}.round must be sequential and equal {index}")
        if round_record.get("verdict") not in JUDGE_VERDICTS:
            errors.append(
                f"{location}.verdict must be one of {sorted(JUDGE_VERDICTS)}"
            )
        validate_search_usage(round_record.get("search_usage"), f"{location}.search_usage", errors)
    if is_int(max_rounds) and len(rounds) > max_rounds:
        errors.append("session-state.json: evaluation_rounds exceeds max_rounds")

    evidence_ready = status not in {"EVIDENCE_INTAKE", "BLOCKED"}
    if evidence_ready and (not inventory or not matrix):
        errors.append(
            "session-state.json: evaluation must have an experiment inventory and claim-evidence matrix after EVIDENCE_INTAKE"
        )

    decision_required = status in {"DECISION_GATE", "NEXT_EXPERIMENT", "COMPLETE"}
    if decision_required:
        min_rounds = state.get("min_rounds")
        if is_int(min_rounds) and len(rounds) < min_rounds:
            errors.append(
                f"session-state.json: evaluation decision requires at least {min_rounds} rounds"
            )
        if not require_keys(
            decision,
            (
                "verdict",
                "confidence",
                "rationale",
                "decisive_evidence",
                "strongest_objection",
                "unresolved",
                "next_action",
            ),
            "evaluation_decision",
            errors,
        ):
            decision = None
        if isinstance(decision, dict):
            if decision.get("verdict") not in EVALUATION_DECISIONS:
                errors.append(
                    "evaluation_decision.verdict must be one of "
                    f"{sorted(EVALUATION_DECISIONS)}"
                )
            for key in ("rationale", "strongest_objection", "next_action"):
                if not nonempty_string(decision.get(key)):
                    errors.append(f"evaluation_decision.{key} must be non-empty")
            for key in ("decisive_evidence", "unresolved"):
                if not isinstance(decision.get(key), list):
                    errors.append(f"evaluation_decision.{key} must be an array")
    elif decision is not None:
        errors.append(
            "session-state.json: evaluation_decision must be null before DECISION_GATE"
        )

    next_required = status in {"NEXT_EXPERIMENT", "COMPLETE"}
    if next_required:
        if not require_keys(
            next_experiment,
            (
                "action",
                "question",
                "design",
                "expected_outcomes",
                "decision_rule",
                "resource_requirements",
                "stop_condition",
            ),
            "next_experiment",
            errors,
        ):
            return
        if next_experiment.get("action") not in {"RUN", "REFRAME", "NONE"}:
            errors.append("next_experiment.action must be RUN, REFRAME, or NONE")
        for key in ("question", "design", "decision_rule", "stop_condition"):
            if not nonempty_string(next_experiment.get(key)):
                errors.append(f"next_experiment.{key} must be non-empty")
        for key in ("expected_outcomes", "resource_requirements"):
            if not isinstance(next_experiment.get(key), list):
                errors.append(f"next_experiment.{key} must be an array")
        verdict = decision.get("verdict") if isinstance(decision, dict) else None
        if verdict == "STOP" and next_experiment.get("action") != "NONE":
            errors.append("next_experiment.action must be NONE after a STOP decision")
        if verdict != "STOP" and next_experiment.get("action") == "NONE":
            errors.append("next_experiment.action NONE is only valid after STOP")
    elif next_experiment is not None:
        errors.append(
            "session-state.json: next_experiment must be null before NEXT_EXPERIMENT"
        )


def validate_source_ledger(state: dict[str, Any], errors: list[str]) -> None:
    ledger = state.get("source_ledger")
    if not isinstance(ledger, list):
        errors.append("session-state.json: source_ledger must be an array")
        return

    source_ids: list[str] = []
    required = (
        "source_id",
        "title",
        "url",
        "source_kind",
        "publication_status",
        "version_or_commit",
        "published_or_updated",
        "claim_locator",
        "verification_level",
        "claim_status",
        "limitations",
    )
    for index, row in enumerate(ledger):
        location = f"source_ledger[{index}]"
        if not require_keys(row, required, location, errors):
            continue
        for key in (
            "source_id",
            "title",
            "url",
            "source_kind",
            "publication_status",
            "version_or_commit",
            "published_or_updated",
            "claim_locator",
            "verification_level",
            "claim_status",
        ):
            if not nonempty_string(row.get(key)):
                errors.append(f"{location}.{key} must be non-empty")
        source_id = row.get("source_id")
        if nonempty_string(source_id):
            source_ids.append(source_id)
        url = row.get("url")
        if nonempty_string(url) and not url.startswith(("https://", "http://")):
            errors.append(f"{location}.url must be a direct HTTP(S) URL")
        if row.get("source_kind") not in SOURCE_KINDS:
            errors.append(
                f"{location}.source_kind must be one of {sorted(SOURCE_KINDS)}"
            )
        if row.get("publication_status") not in PUBLICATION_STATUSES:
            errors.append(
                f"{location}.publication_status must be one of "
                f"{sorted(PUBLICATION_STATUSES)}"
            )
        if row.get("verification_level") not in VERIFICATION_LEVELS:
            errors.append(
                f"{location}.verification_level must be one of "
                f"{sorted(VERIFICATION_LEVELS)}"
            )
        if row.get("claim_status") not in CLAIM_STATUSES:
            errors.append(
                f"{location}.claim_status must be one of {sorted(CLAIM_STATUSES)}"
            )
        if not isinstance(row.get("limitations"), list):
            errors.append(f"{location}.limitations must be an array")

        if row.get("verification_level") == "LOCALLY_REPRODUCED":
            reproduction = row.get("reproduction")
            if not require_keys(
                reproduction,
                ("environment", "procedure", "result", "artifact_path"),
                f"{location}.reproduction",
                errors,
            ):
                continue
            for key in ("environment", "procedure", "result", "artifact_path"):
                if not nonempty_string(reproduction.get(key)):
                    errors.append(f"{location}.reproduction.{key} must be non-empty")

    duplicates = duplicate_values(source_ids)
    if duplicates:
        errors.append(f"session-state.json: duplicate source IDs {duplicates}")


def validate_search_budget(state: dict[str, Any], errors: list[str]) -> None:
    budget = state.get("search_budget")
    if not require_keys(
        budget,
        ("profile", "large_downloads"),
        "search_budget",
        errors,
    ):
        return
    if budget.get("profile") != "standard":
        errors.append("search_budget.profile must be standard")
    downloads = budget.get("large_downloads")
    if not isinstance(downloads, list):
        errors.append("search_budget.large_downloads must be an array")
        return
    for index, download in enumerate(downloads):
        location = f"search_budget.large_downloads[{index}]"
        if not require_keys(
            download,
            ("url", "size_bytes", "necessity", "user_approved"),
            location,
            errors,
        ):
            continue
        if not nonempty_string(download.get("url")):
            errors.append(f"{location}.url must be non-empty")
        size = download.get("size_bytes")
        if not is_int(size) or size <= 0:
            errors.append(f"{location}.size_bytes must be a positive integer")
            continue
        if size > TEN_MIB:
            if not nonempty_string(download.get("necessity")):
                errors.append(
                    f"{location}.necessity is required for downloads over 10 MiB"
                )
            if download.get("user_approved") is not True:
                errors.append(
                    f"{location}.user_approved must be true for downloads over 10 MiB"
                )


def validate_rejections(state: dict[str, Any], errors: list[str]) -> None:
    rejections = state.get("rejected_work_products")
    if not isinstance(rejections, list):
        errors.append("session-state.json: rejected_work_products must be an array")
        return
    fields = (
        "role",
        "packet_id",
        "candidate_id",
        "round",
        "reason_code",
        "reason",
    )
    for index, rejection in enumerate(rejections):
        location = f"rejected_work_products[{index}]"
        if not require_keys(rejection, fields, location, errors):
            continue
        if not nonempty_string(rejection.get("role")):
            errors.append(f"{location}.role must be non-empty")
        if not nonempty_string(rejection.get("packet_id")):
            errors.append(f"{location}.packet_id must be non-empty")
        if rejection.get("candidate_id") is not None and not nonempty_string(
            rejection.get("candidate_id")
        ):
            errors.append(f"{location}.candidate_id must be a string or null")
        if rejection.get("round") is not None and (
            not is_int(rejection.get("round")) or rejection.get("round") < 1
        ):
            errors.append(f"{location}.round must be a positive integer or null")
        reason_code = rejection.get("reason_code")
        if (
            not isinstance(reason_code, str)
            or reason_code not in REJECTION_CODES
        ):
            errors.append(
                f"{location}.reason_code must be one of {sorted(REJECTION_CODES)}"
            )
        if not nonempty_string(rejection.get("reason")):
            errors.append(f"{location}.reason must be non-empty")


def expected_context_fingerprint(product: dict[str, Any]) -> str:
    identity = {
        key: product.get(key)
        for key in (
            "session_id",
            "project_root",
            "project_snapshot",
            "phase",
            "role",
            "candidate_id",
            "round",
            "packet_id",
        )
    }
    if product.get("phase") == "CONTROL":
        identity["control_revision"] = product.get("control_revision")
        identity["state_digest"] = product.get("state_digest")
        identity["control_input_digest"] = product.get("control_input_digest")
    compact = json.dumps(
        identity,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    return hashlib.sha256(compact.encode("utf-8")).hexdigest()


def validate_accepted_work_products(
    state: dict[str, Any],
    errors: list[str],
) -> None:
    products = state.get("accepted_work_products")
    if not isinstance(products, list):
        errors.append("session-state.json: accepted_work_products must be an array")
        return

    candidates = state.get("candidates")
    candidate_ids = {
        candidate.get("candidate_id")
        for candidate in candidates
        if isinstance(candidate, dict) and nonempty_string(candidate.get("candidate_id"))
    } if isinstance(candidates, list) else set()
    packet_ids: list[str] = []
    indexed: dict[tuple[str, str | None, int | None], set[str]] = {}
    fields = (
        "packet_id",
        "phase",
        "role",
        "session_id",
        "project_root",
        "project_snapshot",
        "candidate_id",
        "round",
        "context_fingerprint",
    )

    for index, product in enumerate(products):
        location = f"accepted_work_products[{index}]"
        if not require_keys(product, fields, location, errors):
            continue
        packet_id = product.get("packet_id")
        phase = product.get("phase")
        role = product.get("role")
        candidate_id = product.get("candidate_id")
        round_number = product.get("round")
        fingerprint = product.get("context_fingerprint")

        if not nonempty_string(packet_id):
            errors.append(f"{location}.packet_id must be non-empty")
        else:
            packet_ids.append(packet_id)
        if not isinstance(phase, str) or phase not in PHASE_ROLES:
            errors.append(f"{location}.phase must be one of {sorted(PHASE_ROLES)}")
        elif not isinstance(role, str) or role not in PHASE_ROLES[phase]:
            errors.append(
                f"{location}.role {role!r} is not allowed in phase {phase!r}"
            )
        if not nonempty_string(role):
            errors.append(f"{location}.role must be non-empty")

        if phase == "CONTROL":
            if state.get("schema_version") != "1.3":
                errors.append(f"{location}: CONTROL requires schema_version 1.3")
            if "control_revision" not in product:
                errors.append(f"{location}.control_revision is required for CONTROL")
            elif (
                not is_int(product.get("control_revision"))
                or product.get("control_revision") < 0
            ):
                errors.append(
                    f"{location}.control_revision must be a non-negative integer"
                )
            if "state_digest" not in product:
                errors.append(f"{location}.state_digest is required for CONTROL")
            elif not is_sha256(product.get("state_digest")):
                errors.append(
                    f"{location}.state_digest must be a lowercase SHA-256 digest"
                )
            if "control_input_digest" not in product:
                errors.append(
                    f"{location}.control_input_digest is required for CONTROL"
                )
            elif not is_sha256(product.get("control_input_digest")):
                errors.append(
                    f"{location}.control_input_digest must be a lowercase "
                    "SHA-256 digest"
                )

        for key in ("session_id", "project_root", "project_snapshot"):
            if product.get(key) != state.get(key):
                errors.append(
                    f"{location}.{key} does not match the session identity"
                )

        if candidate_id is not None:
            if not nonempty_string(candidate_id):
                errors.append(f"{location}.candidate_id must be a string or null")
            elif candidate_id not in candidate_ids:
                errors.append(
                    f"{location}.candidate_id {candidate_id!r} does not exist"
                )
        if round_number is not None and (
            not is_int(round_number) or round_number < 1
        ):
            errors.append(f"{location}.round must be a positive integer or null")

        if isinstance(phase, str) and phase in {
            "CONTROL",
            "DIRECTION_MAPPING",
            "DIRECTION_SELECTION",
            "HOTSPOT",
            "SCREENING",
            "FINAL_SELECTION",
            "EVIDENCE_INTAKE",
            "RESULT_VALIDATION",
            "EXTERNAL_POSITIONING",
            "EVALUATION_DECISION",
            "NEXT_EXPERIMENT",
        }:
            if candidate_id is not None or round_number is not None:
                errors.append(
                    f"{location}: {phase} requires null candidate_id and round"
                )
        elif phase == "DEBATE":
            if candidate_id is None or round_number is None:
                errors.append(
                    f"{location}: DEBATE requires candidate_id and round"
                )
        elif phase == "EVALUATION_DEBATE":
            if candidate_id is not None or round_number is None:
                errors.append(
                    f"{location}: EVALUATION_DEBATE requires a null candidate_id and round"
                )
        elif (
            isinstance(phase, str)
            and phase in {"IDENTIFICATION", "RQ_REFINEMENT"}
        ):
            if candidate_id is None or round_number is not None:
                errors.append(
                    f"{location}: {phase} requires candidate_id and a null round"
                )

        if not is_sha256(fingerprint):
            errors.append(
                f"{location}.context_fingerprint must be a lowercase SHA-256 digest"
            )
        elif fingerprint != expected_context_fingerprint(product):
            errors.append(
                f"{location}.context_fingerprint does not match its identity fields"
            )

        if (
            isinstance(phase, str)
            and phase in PHASE_ROLES
            and isinstance(role, str)
        ):
            key = (
                phase,
                candidate_id if isinstance(candidate_id, str) else None,
                round_number if is_int(round_number) else None,
            )
            indexed.setdefault(key, set()).add(role)

    duplicates = duplicate_values(packet_ids)
    if duplicates:
        errors.append(
            f"session-state.json: duplicate accepted packet IDs {duplicates}"
        )

    status = state.get("status")
    mode = state.get("mode")
    direction_selection = state.get("direction_selection")
    macro_directions = state.get("macro_directions")
    generated = state.get("generated_candidate_ids")
    initial = state.get("initial_debate_candidate_ids")
    gate_ids = state.get("user_gate_candidate_ids")

    evaluation_only_phases = {
        "EVIDENCE_INTAKE",
        "RESULT_VALIDATION",
        "EXTERNAL_POSITIONING",
        "EVALUATION_DEBATE",
        "EVALUATION_DECISION",
        "NEXT_EXPERIMENT",
    }
    discovery_only_phases = {
        "DIRECTION_MAPPING",
        "DIRECTION_SELECTION",
        "HOTSPOT",
        "SCREENING",
        "DEBATE",
        "IDENTIFICATION",
        "FINAL_SELECTION",
        "RQ_REFINEMENT",
    }
    indexed_phases = {phase for phase, _candidate_id, _round in indexed}
    wrong_mode_phases = (
        indexed_phases & discovery_only_phases
        if mode == "evaluate"
        else indexed_phases & evaluation_only_phases
    )
    if wrong_mode_phases:
        errors.append(
            "accepted_work_products: mode contains incompatible phases "
            f"{sorted(wrong_mode_phases)}"
        )

    if mode == "evaluate":
        allowed_phases_by_status = {
            "EVIDENCE_INTAKE": {"EVIDENCE_INTAKE"},
            "RESULT_VALIDATION": {"EVIDENCE_INTAKE", "RESULT_VALIDATION"},
            "EXTERNAL_POSITIONING": {
                "EVIDENCE_INTAKE",
                "RESULT_VALIDATION",
                "EXTERNAL_POSITIONING",
            },
            "EVALUATION_DEBATE": {
                "EVIDENCE_INTAKE",
                "RESULT_VALIDATION",
                "EXTERNAL_POSITIONING",
                "EVALUATION_DEBATE",
            },
            "DECISION_GATE": {
                "EVIDENCE_INTAKE",
                "RESULT_VALIDATION",
                "EXTERNAL_POSITIONING",
                "EVALUATION_DEBATE",
                "EVALUATION_DECISION",
            },
            "NEXT_EXPERIMENT": {
                "EVIDENCE_INTAKE",
                "RESULT_VALIDATION",
                "EXTERNAL_POSITIONING",
                "EVALUATION_DEBATE",
                "EVALUATION_DECISION",
                "NEXT_EXPERIMENT",
            },
            "COMPLETE": {
                "EVIDENCE_INTAKE",
                "RESULT_VALIDATION",
                "EXTERNAL_POSITIONING",
                "EVALUATION_DEBATE",
                "EVALUATION_DECISION",
                "NEXT_EXPERIMENT",
            },
        }
        allowed = allowed_phases_by_status.get(status)
        if allowed is not None:
            allowed = allowed | {"CONTROL"}
            premature = sorted(
                {phase for phase, _candidate_id, _round in indexed if phase not in allowed}
            )
            if premature:
                errors.append(
                    f"accepted_work_products: {status} contains premature phases {premature}"
                )

        phase_requirements = (
            ("RESULT_VALIDATION", "EVIDENCE_INTAKE", {"Experiment Auditor"}),
            (
                "EXTERNAL_POSITIONING",
                "RESULT_VALIDATION",
                {"Statistical Reviewer", "Reproducibility Auditor"},
            ),
            (
                "EVALUATION_DEBATE",
                "EXTERNAL_POSITIONING",
                {"Search and Verification Specialist"},
            ),
            (
                "DECISION_GATE",
                "EVALUATION_DECISION",
                {"Panel Judge"},
            ),
            (
                "NEXT_EXPERIMENT",
                "NEXT_EXPERIMENT",
                {"Experiment Planner"},
            ),
            (
                "COMPLETE",
                "NEXT_EXPERIMENT",
                {"Experiment Planner"},
            ),
        )
        phase_order = {
            "EVIDENCE_INTAKE": 1,
            "RESULT_VALIDATION": 2,
            "EXTERNAL_POSITIONING": 3,
            "EVALUATION_DEBATE": 4,
            "DECISION_GATE": 5,
            "NEXT_EXPERIMENT": 6,
            "COMPLETE": 7,
        }
        current_order = phase_order.get(status, 0)
        for required_status, phase, roles in phase_requirements:
            if current_order >= phase_order[required_status]:
                missing = roles - indexed.get((phase, None, None), set())
                if missing:
                    errors.append(
                        f"accepted_work_products: evaluation requires {phase} roles {sorted(missing)}"
                    )

        evaluation_rounds = state.get("evaluation_rounds")
        if isinstance(evaluation_rounds, list):
            for round_record in evaluation_rounds:
                if not isinstance(round_record, dict):
                    continue
                round_number = round_record.get("round")
                if not is_int(round_number):
                    continue
                roles = indexed.get(("EVALUATION_DEBATE", None, round_number), set())
                missing_roles = CORE_ROUND_ROLES - roles
                if missing_roles:
                    errors.append(
                        "accepted_work_products: evaluation round "
                        f"{round_number} is missing roles {sorted(missing_roles)}"
                    )
                search_usage = round_record.get("search_usage")
                search_used = isinstance(search_usage, dict) and any(
                    is_int(search_usage.get(key)) and search_usage.get(key) > 0
                    for key in ("query_batches", "queries", "sources_inspected")
                )
                if search_used and "Search and Verification Specialist" not in roles:
                    errors.append(
                        "accepted_work_products: evaluation round "
                        f"{round_number} records search but has no Search and Verification Specialist product"
                    )
        return

    if status not in {"SCANNING", "BLOCKED"}:
        if mode == "discover" and macro_directions:
            if "Macro Direction Mapper" not in indexed.get(
                ("DIRECTION_MAPPING", None, None), set()
            ):
                errors.append(
                    "accepted_work_products: discover mode requires a clean "
                    "DIRECTION_MAPPING/Macro Direction Mapper product"
                )
        if mode == "discover" and generated:
            if "Hotspot Analyst" not in indexed.get(("HOTSPOT", None, None), set()):
                errors.append(
                    "accepted_work_products: discover mode requires a clean "
                    "HOTSPOT/Hotspot Analyst product"
                )
        if initial:
            if "Panel Judge" not in indexed.get(("SCREENING", None, None), set()):
                errors.append(
                    "accepted_work_products: initial debate selection requires a "
                    "clean SCREENING/Panel Judge product"
                )

    selected_by = (
        direction_selection.get("selected_by")
        if isinstance(direction_selection, dict)
        else None
    )
    if selected_by in {"PANEL_DELEGATED", "PANEL_AUTONOMOUS"}:
        if "Panel Judge" not in indexed.get(
            ("DIRECTION_SELECTION", None, None), set()
        ):
            errors.append(
                "accepted_work_products: panel-selected macro directions require "
                "a clean DIRECTION_SELECTION/Panel Judge product"
            )
    if status == "DIRECTION_GATE":
        forbidden_phases = {
            "DIRECTION_SELECTION",
            "HOTSPOT",
            "SCREENING",
            "DEBATE",
            "IDENTIFICATION",
            "FINAL_SELECTION",
            "RQ_REFINEMENT",
        }
        premature = sorted(
            phase
            for phase, _candidate_id, _round in indexed
            if phase in forbidden_phases
        )
        if premature:
            errors.append(
                "accepted_work_products: DIRECTION_GATE contains premature "
                f"phases {sorted(set(premature))}"
            )
    if status == "CANDIDATE_GENERATION":
        forbidden_phases = {
            "DEBATE",
            "IDENTIFICATION",
            "FINAL_SELECTION",
            "RQ_REFINEMENT",
        }
        premature = sorted(
            phase
            for phase, _candidate_id, _round in indexed
            if phase in forbidden_phases
        )
        if premature:
            errors.append(
                "accepted_work_products: CANDIDATE_GENERATION contains "
                f"premature phases {sorted(set(premature))}"
            )

    if isinstance(candidates, list):
        for candidate in candidates:
            if not isinstance(candidate, dict):
                continue
            candidate_id = candidate.get("candidate_id")
            rounds = candidate.get("rounds")
            if not nonempty_string(candidate_id) or not isinstance(rounds, list):
                continue
            for round_record in rounds:
                if not isinstance(round_record, dict):
                    continue
                round_number = round_record.get("round")
                if not is_int(round_number):
                    continue
                roles = indexed.get(("DEBATE", candidate_id, round_number), set())
                missing_roles = CORE_ROUND_ROLES - roles
                if missing_roles:
                    errors.append(
                        f"accepted_work_products: candidate {candidate_id!r} round "
                        f"{round_number} is missing roles {sorted(missing_roles)}"
                    )
                search_usage = round_record.get("search_usage")
                search_used = False
                if isinstance(search_usage, dict):
                    search_used = any(
                        is_int(search_usage.get(key)) and search_usage.get(key) > 0
                        for key in ("query_batches", "queries", "sources_inspected")
                    )
                if search_used and "Search and Verification Specialist" not in roles:
                    errors.append(
                        f"accepted_work_products: candidate {candidate_id!r} round "
                        f"{round_number} records search but has no Search and "
                        "Verification Specialist product"
                    )

    if isinstance(gate_ids, list):
        for candidate_id in gate_ids:
            roles = indexed.get(("IDENTIFICATION", candidate_id, None), set())
            if "Methodology Architect" not in roles:
                errors.append(
                    f"accepted_work_products: gate candidate {candidate_id!r} "
                    "requires an IDENTIFICATION/Methodology Architect product"
                )

    if status in {"USER_GATE", "RQ_REFINEMENT", "COMPLETE"}:
        if "Panel Judge" not in indexed.get(("FINAL_SELECTION", None, None), set()):
            errors.append(
                "accepted_work_products: user gate requires a fresh "
                "FINAL_SELECTION/Panel Judge product"
            )
    if status == "COMPLETE":
        selected_candidate = state.get("selected_candidate_id")
        if nonempty_string(selected_candidate) and "Research Question Architect" not in indexed.get(
            ("RQ_REFINEMENT", selected_candidate, None), set()
        ):
            errors.append(
                "accepted_work_products: COMPLETE requires an "
                "RQ_REFINEMENT/Research Question Architect product for the "
                "selected candidate"
            )


def validate_string_array(
    value: Any,
    location: str,
    errors: list[str],
) -> list[str]:
    if not isinstance(value, list):
        errors.append(f"{location} must be an array")
        return []
    if not all(nonempty_string(item) for item in value):
        errors.append(f"{location} must contain only non-empty strings")
        return [item for item in value if nonempty_string(item)]
    duplicates = duplicate_values(value)
    if duplicates:
        errors.append(f"{location} contains duplicates {duplicates}")
    return value


def validate_lane_search_requests(
    value: Any,
    location: str,
    errors: list[str],
) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        errors.append(f"{location} must be an array")
        return []
    requests: list[dict[str, Any]] = []
    lane_keys: set[tuple[Any, ...]] = set()
    fields = (
        "phase",
        "candidate_id",
        "round",
        "source_packet_id",
        "reason_codes",
    )
    for index, request in enumerate(value):
        item_location = f"{location}[{index}]"
        if not require_keys(request, fields, item_location, errors):
            continue
        assert isinstance(request, dict)
        phase = request.get("phase")
        candidate_id = request.get("candidate_id")
        round_number = request.get("round")
        if (
            not isinstance(phase, str)
            or phase not in {"DEBATE", "EVALUATION_DEBATE"}
        ):
            errors.append(f"{item_location}.phase is invalid")
        if phase == "DEBATE" and not nonempty_string(candidate_id):
            errors.append(f"{item_location}.candidate_id is required for DEBATE")
        if phase == "EVALUATION_DEBATE" and candidate_id is not None:
            errors.append(
                f"{item_location}.candidate_id must be null for EVALUATION_DEBATE"
            )
        if not is_int(round_number) or round_number < 1:
            errors.append(f"{item_location}.round must be a positive integer")
        source_packet_id = request.get("source_packet_id")
        if (
            not nonempty_string(source_packet_id)
            or not SAFE_ID.fullmatch(source_packet_id)
        ):
            errors.append(f"{item_location}.source_packet_id is invalid")
        reason_codes = validate_string_array(
            request.get("reason_codes"),
            f"{item_location}.reason_codes",
            errors,
        )
        if not reason_codes:
            errors.append(f"{item_location}.reason_codes must not be empty")
        elif any(not CODE.fullmatch(code) for code in reason_codes):
            errors.append(
                f"{item_location}.reason_codes must contain uppercase codes"
            )
        lane_key = tuple(
            key_component(component)
            for component in (phase, candidate_id, round_number)
        )
        if lane_key in lane_keys:
            errors.append(f"{location} contains duplicate lane request {lane_key!r}")
        lane_keys.add(lane_key)
        requests.append(request)
    return requests


def validate_control_dispatch(
    dispatch: Any,
    location: str,
    candidate_ids: set[str],
    accepted_packet_ids: set[str],
    errors: list[str],
) -> str | None:
    fields = (
        "packet_id",
        "phase",
        "role",
        "candidate_id",
        "round",
        "depends_on_packet_ids",
    )
    if not require_keys(dispatch, fields, location, errors):
        return None

    packet_id = dispatch.get("packet_id")
    phase = dispatch.get("phase")
    role = dispatch.get("role")
    candidate_id = dispatch.get("candidate_id")
    round_number = dispatch.get("round")

    if not nonempty_string(packet_id) or not SAFE_ID.fullmatch(packet_id):
        errors.append(f"{location}.packet_id is invalid")
        packet_id = None
    if (
        not isinstance(phase, str)
        or phase == "CONTROL"
        or phase not in PHASE_ROLES
    ):
        errors.append(
            f"{location}.phase must be a non-CONTROL phase in "
            f"{sorted(PHASE_ROLES)}"
        )
    elif not isinstance(role, str) or role not in PHASE_ROLES[phase]:
        errors.append(
            f"{location}.role {role!r} is not allowed in phase {phase!r}"
        )

    if candidate_id is not None:
        if not nonempty_string(candidate_id):
            errors.append(f"{location}.candidate_id must be a string or null")
        elif candidate_id not in candidate_ids:
            errors.append(
                f"{location}.candidate_id {candidate_id!r} does not exist"
            )
    if round_number is not None and (
        not is_int(round_number) or round_number < 1
    ):
        errors.append(f"{location}.round must be a positive integer or null")

    null_lane_phases = {
        "DIRECTION_MAPPING",
        "DIRECTION_SELECTION",
        "HOTSPOT",
        "SCREENING",
        "FINAL_SELECTION",
        "EVIDENCE_INTAKE",
        "RESULT_VALIDATION",
        "EXTERNAL_POSITIONING",
        "EVALUATION_DECISION",
        "NEXT_EXPERIMENT",
    }
    if isinstance(phase, str) and phase in null_lane_phases:
        if candidate_id is not None or round_number is not None:
            errors.append(
                f"{location}: {phase} requires null candidate_id and round"
            )
    elif phase == "DEBATE":
        if candidate_id is None or round_number is None:
            errors.append(f"{location}: DEBATE requires candidate_id and round")
    elif phase == "EVALUATION_DEBATE":
        if candidate_id is not None or round_number is None:
            errors.append(
                f"{location}: EVALUATION_DEBATE requires null candidate_id "
                "and a non-null round"
            )
    elif (
        isinstance(phase, str)
        and phase in {"IDENTIFICATION", "RQ_REFINEMENT"}
    ):
        if candidate_id is None or round_number is not None:
            errors.append(
                f"{location}: {phase} requires candidate_id and a null round"
            )

    dependencies = validate_string_array(
        dispatch.get("depends_on_packet_ids"),
        f"{location}.depends_on_packet_ids",
        errors,
    )
    unknown = sorted(set(dependencies) - accepted_packet_ids)
    if unknown:
        errors.append(
            f"{location}.depends_on_packet_ids reference unaccepted packets {unknown}"
        )
    if packet_id is not None and packet_id in dependencies:
        errors.append(f"{location} cannot depend on its own packet_id")
    return packet_id


def validate_committed_dispatch_prerequisites(
    dispatch: dict[str, Any],
    state: dict[str, Any],
    accepted_packet_ids: set[str],
    prior_dispatches: dict[str, dict[str, Any]],
    dependencies: list[str],
    location: str,
    errors: list[str],
    control_snapshot: dict[str, Any] | None = None,
) -> None:
    phase = dispatch.get("phase")
    role = dispatch.get("role")
    candidate_id = dispatch.get("candidate_id")
    round_number = dispatch.get("round")
    snapshot_verdicts = (
        control_snapshot.get("accepted_verdicts")
        if isinstance(control_snapshot, dict)
        and isinstance(control_snapshot.get("accepted_verdicts"), list)
        else None
    )
    if not isinstance(phase, str) or not isinstance(role, str):
        return

    def historical_verdicts(
        archived_candidate_id: str | None,
    ) -> list[dict[str, Any]]:
        if not isinstance(snapshot_verdicts, list):
            return []
        return sorted(
            [
                verdict
                for verdict in snapshot_verdicts
                if isinstance(verdict, dict)
                and verdict.get("candidate_id") == archived_candidate_id
                and is_int(verdict.get("round"))
                and isinstance(verdict.get("verdict"), str)
            ],
            key=lambda verdict: verdict["round"],
        )

    def latest(**coordinates: Any) -> str | None:
        for packet_id, prior in reversed(list(prior_dispatches.items())):
            if packet_id in accepted_packet_ids and all(
                prior.get(field) == value
                for field, value in coordinates.items()
            ):
                return packet_id
        return None

    def require(label: str, **coordinates: Any) -> str | None:
        packet_id = latest(**coordinates)
        if packet_id is None:
            errors.append(f"{location} requires an accepted {label} prerequisite")
        elif packet_id not in dependencies:
            errors.append(
                f"{location}.depends_on_packet_ids must include {label} "
                f"packet {packet_id!r}"
            )
        return packet_id

    if phase == "DIRECTION_MAPPING":
        return
    if phase == "DIRECTION_SELECTION":
        require("direction map", phase="DIRECTION_MAPPING")
        receipts = state.get("gate_receipts")
        if (
            state.get("interaction_mode") == "GUIDED"
            and not (
                isinstance(receipts, list)
                and any(
                    isinstance(receipt, dict)
                    and receipt.get("gate") == "DIRECTION_SELECTION"
                    and receipt.get("action") == "DELEGATE"
                    for receipt in receipts
                )
            )
        ):
            errors.append(
                f"{location} requires AUTONOMOUS interaction mode or a "
                "DIRECTION_SELECTION/DELEGATE receipt"
            )
        return
    if phase == "HOTSPOT":
        selected = state.get("selected_macro_direction_ids")
        if not isinstance(selected, list) or not selected:
            errors.append(
                f"{location} requires at least one selected macro direction"
            )
        direction_choice = latest(phase="DIRECTION_SELECTION")
        if direction_choice is not None:
            if direction_choice not in dependencies:
                errors.append(
                    f"{location}.depends_on_packet_ids must include direction "
                    f"selection packet {direction_choice!r}"
                )
        else:
            require("direction map", phase="DIRECTION_MAPPING")
        return
    if phase == "SCREENING":
        require("hotspot analysis", phase="HOTSPOT")
        return

    if phase in {"DEBATE", "EVALUATION_DEBATE"}:
        lane = {
            "phase": phase,
            "candidate_id": candidate_id,
            "round": round_number,
        }
        if role == "Socratic Mentor":
            if phase == "DEBATE":
                candidate = next(
                    (
                        value
                        for value in state.get("candidates", [])
                        if isinstance(value, dict)
                        and value.get("candidate_id") == candidate_id
                    ),
                    None,
                )
                initial = state.get("initial_debate_candidate_ids")
                eligible_lane = (
                    isinstance(initial, list) and candidate_id in initial
                ) or (
                    isinstance(candidate, dict)
                    and candidate.get("origin") == "DERIVED"
                )
                if not eligible_lane:
                    errors.append(
                        f"{location} requires an initially selected or eligible "
                        "derived debate candidate"
                    )
            if is_int(round_number) and round_number > 1:
                require(
                    "previous-round Judge",
                    phase=phase,
                    role="Panel Judge",
                    candidate_id=candidate_id,
                    round=round_number - 1,
                )
                historical_rounds = historical_verdicts(candidate_id)
                previous_record = next(
                    (
                        verdict
                        for verdict in historical_rounds
                        if verdict.get("round") == round_number - 1
                    ),
                    None,
                )
                if previous_record is None and snapshot_verdicts is None:
                    round_records = (
                        state.get("evaluation_rounds")
                        if phase == "EVALUATION_DEBATE"
                        else next(
                            (
                                candidate.get("rounds")
                                for candidate in state.get("candidates", [])
                                if isinstance(candidate, dict)
                                and candidate.get("candidate_id") == candidate_id
                            ),
                            None,
                        )
                    )
                    previous_record = (
                        round_records[round_number - 2]
                        if isinstance(round_records, list)
                        and len(round_records) >= round_number - 1
                        and isinstance(round_records[round_number - 2], dict)
                        else None
                    )
                if (
                    not isinstance(previous_record, dict)
                    or previous_record.get("verdict")
                    not in {"CONTINUE", "SEARCH", "REVISE"}
                ):
                    errors.append(
                        f"{location} requires a previous-round verdict that "
                        "permits another round"
                    )
            elif phase == "DEBATE":
                require("candidate screening", phase="SCREENING")
            else:
                require("external positioning", phase="EXTERNAL_POSITIONING")
        elif role == "Evidence Researcher":
            require("current-round Mentor", role="Socratic Mentor", **lane)
        elif role == "Devil's Advocate":
            require("current-round Evidence", role="Evidence Researcher", **lane)
        elif role == "Search and Verification Specialist":
            require("current-round challenge", role="Devil's Advocate", **lane)
            control = state.get("mainline_control")
            requests = (
                control.get("lane_search_requests")
                if isinstance(control, dict)
                and isinstance(control.get("lane_search_requests"), list)
                else []
            )
            if not any(
                isinstance(request, dict)
                and request.get("phase") == phase
                and request.get("candidate_id") == candidate_id
                and request.get("round") == round_number
                for request in requests
            ):
                errors.append(
                    f"{location} requires a persisted same-lane search request"
                )
        elif role == "Panel Judge":
            require("current-round Mentor", role="Socratic Mentor", **lane)
            require("current-round Evidence", role="Evidence Researcher", **lane)
            require("current-round challenge", role="Devil's Advocate", **lane)
            control = state.get("mainline_control")
            requests = (
                control.get("lane_search_requests")
                if isinstance(control, dict)
                and isinstance(control.get("lane_search_requests"), list)
                else []
            )
            has_search_request = any(
                isinstance(request, dict)
                and request.get("phase") == phase
                and request.get("candidate_id") == candidate_id
                and request.get("round") == round_number
                for request in requests
            )
            search_packet = latest(
                role="Search and Verification Specialist",
                **lane,
            )
            if has_search_request and search_packet is None:
                errors.append(
                    f"{location} cannot judge a lane with a persisted search "
                    "request before the same-round search is accepted"
                )
            if search_packet is not None and search_packet not in dependencies:
                errors.append(
                    f"{location}.depends_on_packet_ids must include current-round "
                    f"search packet {search_packet!r}"
                )
            if has_search_request or search_packet is not None:
                evidence_packets = [
                    packet_id
                    for packet_id, prior in prior_dispatches.items()
                    if packet_id in accepted_packet_ids
                    and prior.get("phase") == phase
                    and prior.get("role") == "Evidence Researcher"
                    and prior.get("candidate_id") == candidate_id
                    and prior.get("round") == round_number
                ]
                if len(evidence_packets) != 2:
                    errors.append(
                        f"{location} requires exactly one revised Evidence "
                        "Researcher answer after same-round search"
                    )
                elif evidence_packets[-1] not in dependencies:
                    errors.append(
                        f"{location}.depends_on_packet_ids must include revised "
                        f"Evidence packet {evidence_packets[-1]!r}"
                    )
        return

    if phase == "IDENTIFICATION":
        candidate = next(
            (
                value
                for value in state.get("candidates", [])
                if isinstance(value, dict)
                and value.get("candidate_id") == candidate_id
            ),
            None,
        )
        archived_rounds = historical_verdicts(candidate_id)
        rounds = (
            archived_rounds
            if snapshot_verdicts is not None
            else candidate.get("rounds")
            if isinstance(candidate, dict)
            else None
        )
        rounds_completed = (
            len(archived_rounds)
            if snapshot_verdicts is not None
            else candidate.get("rounds_completed")
            if isinstance(candidate, dict)
            else None
        )
        min_rounds = state.get("min_rounds")
        max_rounds = state.get("max_rounds")
        last_verdict = (
            rounds[-1].get("verdict")
            if isinstance(rounds, list)
            and rounds
            and isinstance(rounds[-1], dict)
            else None
        )
        early_exit_reason = (
            candidate.get("early_exit_reason")
            if isinstance(candidate, dict)
            else None
        )
        maximum_round_stop = (
            is_int(max_rounds)
            and rounds_completed == max_rounds
            and isinstance(early_exit_reason, dict)
            and early_exit_reason.get("code") == "MAX_ROUND_NONCONVERGENCE"
        )
        if (
            not is_int(rounds_completed)
            or not is_int(min_rounds)
            or rounds_completed < min_rounds
            or not (
                last_verdict == "CONVERGED"
                or maximum_round_stop
            )
        ):
            errors.append(
                f"{location} requires completed minimum rounds and either "
                "CONVERGED or the maximum-round stop"
            )
        packet_id = latest(
            phase="DEBATE",
            role="Panel Judge",
            candidate_id=candidate_id,
        )
        if packet_id is None:
            errors.append(
                f"{location} requires an accepted candidate Judge prerequisite"
            )
        elif packet_id not in dependencies:
            errors.append(
                f"{location}.depends_on_packet_ids must include latest Judge "
                f"packet {packet_id!r}"
            )
        return
    if phase == "FINAL_SELECTION":
        ready_candidate_ids = [
            candidate.get("candidate_id")
            for candidate in state.get("candidates", [])
            if isinstance(candidate, dict)
            and candidate.get("gate_ready") is True
            and nonempty_string(candidate.get("candidate_id"))
        ]
        if not ready_candidate_ids:
            errors.append(
                f"{location} requires at least one gate-ready candidate"
            )
        for ready_candidate_id in ready_candidate_ids:
            require(
                f"identification audit for {ready_candidate_id}",
                phase="IDENTIFICATION",
                candidate_id=ready_candidate_id,
            )
        return
    if phase == "RQ_REFINEMENT":
        if not nonempty_string(state.get("selected_candidate_id")):
            errors.append(f"{location} requires selected_candidate_id")
        require("final selection", phase="FINAL_SELECTION")
        return
    if phase == "RESULT_VALIDATION":
        require("experiment audit", phase="EVIDENCE_INTAKE")
        return
    if phase == "EXTERNAL_POSITIONING":
        require(
            "statistical review",
            phase="RESULT_VALIDATION",
            role="Statistical Reviewer",
        )
        require(
            "reproducibility review",
            phase="RESULT_VALIDATION",
            role="Reproducibility Auditor",
        )
        return
    if phase == "EVALUATION_DECISION":
        archived_rounds = historical_verdicts(None)
        rounds = (
            archived_rounds
            if snapshot_verdicts is not None
            else state.get("evaluation_rounds")
        )
        min_rounds = state.get("min_rounds")
        max_rounds = state.get("max_rounds")
        last_verdict = (
            rounds[-1].get("verdict")
            if isinstance(rounds, list)
            and rounds
            and isinstance(rounds[-1], dict)
            else None
        )
        if (
            not isinstance(rounds, list)
            or not is_int(min_rounds)
            or len(rounds) < min_rounds
            or not (
                last_verdict == "CONVERGED"
                or (is_int(max_rounds) and len(rounds) == max_rounds)
            )
        ):
            errors.append(
                f"{location} requires minimum evaluation rounds and either "
                "CONVERGED or the maximum-round stop"
            )
        require(
            "evaluation Judge",
            phase="EVALUATION_DEBATE",
            role="Panel Judge",
        )
        return
    if phase == "NEXT_EXPERIMENT":
        require(
            "evaluation decision",
            phase="EVALUATION_DECISION",
            role="Panel Judge",
        )
        receipts = state.get("gate_receipts")
        if not isinstance(receipts, list) or not any(
            isinstance(receipt, dict)
            and receipt.get("gate") == "EVALUATION_DECISION"
            and receipt.get("action") in {"CONFIRM", "OVERRIDE"}
            for receipt in receipts
        ):
            errors.append(
                f"{location} requires an EVALUATION_DECISION user receipt"
            )


def parse_strict_json_bytes(
    raw: bytes,
    location: str,
    errors: list[str],
) -> Any:
    def reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        parsed: dict[str, Any] = {}
        for key, value in pairs:
            if key in parsed:
                raise ValueError(f"duplicate object key {key!r}")
            parsed[key] = value
        return parsed

    def reject_nonfinite(value: str) -> Any:
        raise ValueError(f"non-finite number {value}")

    try:
        return json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=reject_duplicate_keys,
            parse_constant=reject_nonfinite,
        )
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        errors.append(f"{location} is not strict UTF-8 JSON: {exc}")
        return None


def historical_rq_resolution(
    prior_dispatches: dict[str, dict[str, Any]],
    completed_ids: set[str],
    failed_ids: set[str],
    candidate_id: str,
) -> tuple[str | None, str | None, list[str]]:
    matching = [
        packet_id
        for packet_id, dispatch in prior_dispatches.items()
        if dispatch.get("phase") == "RQ_REFINEMENT"
        and dispatch.get("role") == "Research Question Architect"
        and dispatch.get("candidate_id") == candidate_id
        and dispatch.get("round") is None
    ]
    latest = matching[-1] if matching else None
    unresolved = [
        packet_id
        for packet_id in matching
        if packet_id not in completed_ids and packet_id not in failed_ids
    ]
    latest_completed = latest if latest in completed_ids else None
    return latest, latest_completed, unresolved


def expected_archived_active_lanes(
    snapshot: dict[str, Any],
    transition: dict[str, Any],
    state: dict[str, Any],
    prior_dispatches: dict[str, dict[str, Any]],
    completed_ids: set[str],
    failed_ids: set[str],
) -> list[dict[str, Any]]:
    """Recompute the lane projection from information available at invocation."""
    debate_statuses = {
        transition.get("from_status"),
        transition.get("to_status"),
    }
    archived_verdicts = (
        snapshot.get("accepted_verdicts")
        if isinstance(snapshot.get("accepted_verdicts"), list)
        else []
    )
    verdict_by_lane = {
        (verdict.get("candidate_id"), verdict.get("round")): verdict.get(
            "verdict"
        )
        for verdict in archived_verdicts
        if isinstance(verdict, dict)
        and (
            verdict.get("candidate_id") is None
            or isinstance(verdict.get("candidate_id"), str)
        )
        and is_int(verdict.get("round"))
        and isinstance(verdict.get("verdict"), str)
    }
    max_rounds = state.get("max_rounds")
    lane_coordinates: list[tuple[str, str | None, int]] = []

    if "DEBATING" in debate_statuses:
        candidate_ids: list[str] = []
        initial = state.get("initial_debate_candidate_ids")
        if isinstance(initial, list):
            candidate_ids.extend(
                candidate_id
                for candidate_id in initial
                if nonempty_string(candidate_id)
            )
        candidates = state.get("candidates")
        if isinstance(candidates, list):
            for candidate in candidates:
                if (
                    not isinstance(candidate, dict)
                    or candidate.get("origin") != "DERIVED"
                    or not nonempty_string(candidate.get("candidate_id"))
                ):
                    continue
                candidate_id = candidate["candidate_id"]
                parent_id = candidate.get("parent_id")
                already_dispatched = any(
                    dispatch.get("phase") == "DEBATE"
                    and dispatch.get("candidate_id") == candidate_id
                    for dispatch in prior_dispatches.values()
                )
                parent_downgraded = any(
                    archived_candidate_id == parent_id
                    and verdict == "DOWNGRADE"
                    for (
                        archived_candidate_id,
                        _round_number,
                    ), verdict in verdict_by_lane.items()
                )
                if already_dispatched or parent_downgraded:
                    candidate_ids.append(candidate_id)

        seen_candidate_ids: set[str] = set()
        for candidate_id in candidate_ids:
            if candidate_id in seen_candidate_ids:
                continue
            seen_candidate_ids.add(candidate_id)
            completed_judge_rounds = [
                dispatch.get("round")
                for packet_id, dispatch in prior_dispatches.items()
                if packet_id in completed_ids
                and dispatch.get("phase") == "DEBATE"
                and dispatch.get("role") == "Panel Judge"
                and dispatch.get("candidate_id") == candidate_id
                and is_int(dispatch.get("round"))
            ]
            last_round = max(completed_judge_rounds, default=0)
            last_verdict = verdict_by_lane.get((candidate_id, last_round))
            terminal = last_verdict in {
                "DOWNGRADE",
                "DEFER",
                "ELIMINATE",
                "USER_GATE",
                "CONVERGED",
            }
            exhausted = is_int(max_rounds) and last_round >= max_rounds
            if not terminal and not exhausted:
                lane_coordinates.append(
                    ("DEBATE", candidate_id, last_round + 1)
                )

    if "EVALUATION_DEBATE" in debate_statuses:
        completed_judge_rounds = [
            dispatch.get("round")
            for packet_id, dispatch in prior_dispatches.items()
            if packet_id in completed_ids
            and dispatch.get("phase") == "EVALUATION_DEBATE"
            and dispatch.get("role") == "Panel Judge"
            and is_int(dispatch.get("round"))
        ]
        last_round = max(completed_judge_rounds, default=0)
        terminal = verdict_by_lane.get((None, last_round)) == "CONVERGED"
        exhausted = is_int(max_rounds) and last_round >= max_rounds
        if not terminal and not exhausted:
            lane_coordinates.append(
                ("EVALUATION_DEBATE", None, last_round + 1)
            )

    control = state.get("mainline_control")
    search_requests = (
        control.get("lane_search_requests")
        if isinstance(control, dict)
        and isinstance(control.get("lane_search_requests"), list)
        else []
    )
    search_keys = {
        (
            request.get("phase"),
            request.get("candidate_id"),
            request.get("round"),
        )
        for request in search_requests
        if isinstance(request, dict)
        and isinstance(request.get("phase"), str)
        and (
            request.get("candidate_id") is None
            or isinstance(request.get("candidate_id"), str)
        )
        and is_int(request.get("round"))
        and isinstance(request.get("source_packet_id"), str)
        and request.get("source_packet_id") in completed_ids
        and request.get("source_packet_id") in prior_dispatches
    }
    resolved_ids = completed_ids | failed_ids
    revision = transition.get("observed_revision")
    lanes: list[dict[str, Any]] = []
    for phase, candidate_id, round_number in lane_coordinates:
        lane_dispatches = [
            (packet_id, dispatch)
            for packet_id, dispatch in prior_dispatches.items()
            if dispatch.get("phase") == phase
            and dispatch.get("candidate_id") == candidate_id
            and dispatch.get("round") == round_number
        ]
        accepted_lane = [
            (packet_id, dispatch)
            for packet_id, dispatch in lane_dispatches
            if packet_id in completed_ids
        ]
        pending_lane = [
            packet_id
            for packet_id, _dispatch in lane_dispatches
            if packet_id not in resolved_ids
        ]
        by_role: dict[str, list[str]] = {}
        for packet_id, dispatch in accepted_lane:
            role = dispatch.get("role")
            if isinstance(role, str):
                by_role.setdefault(role, []).append(packet_id)
        mentor = by_role.get("Socratic Mentor", [])
        evidence = by_role.get("Evidence Researcher", [])
        challenge = by_role.get("Devil's Advocate", [])
        search = by_role.get("Search and Verification Specialist", [])
        judge = by_role.get("Panel Judge", [])
        search_required = (phase, candidate_id, round_number) in search_keys

        dependencies: list[str] = []
        if pending_lane:
            next_role = "WAIT_FOR_RESULT"
        elif judge:
            next_role = "COMMIT_ROUND"
            dependencies = [judge[-1]]
        elif search and len(evidence) == 1:
            next_role = "Evidence Researcher"
            dependencies = [
                packet_id
                for packet_id in (
                    mentor[-1] if mentor else None,
                    evidence[-1],
                    search[-1],
                )
                if packet_id is not None
            ]
        elif challenge and search_required and not search:
            next_role = "Search and Verification Specialist"
            dependencies = [challenge[-1]]
        elif challenge:
            next_role = "Panel Judge"
            dependencies = [
                packet_id
                for packet_id in (
                    mentor[-1] if mentor else None,
                    evidence[-1] if evidence else None,
                    challenge[-1],
                    search[-1] if search else None,
                )
                if packet_id is not None
            ]
        elif evidence:
            next_role = "Devil's Advocate"
            dependencies = [evidence[-1]]
        elif mentor:
            next_role = "Evidence Researcher"
            dependencies = [mentor[-1]]
        else:
            next_role = "Socratic Mentor"
            prerequisite_phase = (
                "SCREENING" if phase == "DEBATE" else "EXTERNAL_POSITIONING"
            )
            prerequisite_role = (
                "Panel Judge" if round_number > 1 else None
            )
            prerequisite_round = round_number - 1 if round_number > 1 else None
            prerequisite = next(
                (
                    packet_id
                    for packet_id, dispatch in reversed(
                        list(prior_dispatches.items())
                    )
                    if packet_id in completed_ids
                    and dispatch.get("phase")
                    == (phase if round_number > 1 else prerequisite_phase)
                    and (
                        prerequisite_role is None
                        or dispatch.get("role") == prerequisite_role
                    )
                    and (
                        round_number == 1
                        or (
                            dispatch.get("candidate_id") == candidate_id
                            and dispatch.get("round") == prerequisite_round
                        )
                    )
                ),
                None,
            )
            if prerequisite is not None:
                dependencies = [prerequisite]

        lanes.append(
            {
                "phase": phase,
                "candidate_id": candidate_id,
                "round": round_number,
                "last_resolved_role": (
                    accepted_lane[-1][1].get("role")
                    if accepted_lane
                    else None
                ),
                "next_role": next_role,
                "dependency_packet_ids": dependencies,
                "search_required": search_required,
                "lane_revision": revision,
            }
        )
    return lanes


def validate_control_input_snapshot(
    snapshot: dict[str, Any],
    transition: dict[str, Any],
    state: dict[str, Any],
    location: str,
    errors: list[str],
) -> None:
    missing = sorted(CONTROL_INPUT_SNAPSHOT_KEYS - set(snapshot))
    extra = sorted(set(snapshot) - CONTROL_INPUT_SNAPSHOT_KEYS)
    if missing or extra:
        errors.append(
            f"{location} has invalid keys; missing={missing}, extra={extra}"
        )

    expected_scalars = {
        "control_revision": transition.get("observed_revision"),
        "state_digest": transition.get("observed_state_digest"),
        "observed_status": transition.get("from_status"),
        "mode": state.get("mode"),
        "interaction_mode": state.get("interaction_mode"),
        "checkpoint": transition.get("checkpoint"),
    }
    for field, expected in expected_scalars.items():
        if snapshot.get(field) != expected:
            errors.append(f"{location}.{field} must equal {expected!r}")
    if not is_int(snapshot.get("control_revision")):
        errors.append(f"{location}.control_revision must be an integer")
    if not is_sha256(snapshot.get("state_digest")):
        errors.append(f"{location}.state_digest must be lowercase SHA-256")
    observed_status = snapshot.get("observed_status")
    if (
        not isinstance(observed_status, str)
        or observed_status not in (EVALUATION_STATUSES | DISCOVERY_STATUSES)
    ):
        errors.append(f"{location}.observed_status is invalid")
    snapshot_mode = snapshot.get("mode")
    if (
        not isinstance(snapshot_mode, str)
        or snapshot_mode not in {"discover", "refine", "rq-only", "evaluate"}
    ):
        errors.append(f"{location}.mode is invalid")
    interaction_mode = snapshot.get("interaction_mode")
    if (
        not isinstance(interaction_mode, str)
        or interaction_mode not in INTERACTION_MODES
    ):
        errors.append(f"{location}.interaction_mode is invalid")
    snapshot_checkpoint = snapshot.get("checkpoint")
    if (
        not isinstance(snapshot_checkpoint, str)
        or snapshot_checkpoint not in CONTROL_CHECKPOINTS
    ):
        errors.append(f"{location}.checkpoint is invalid")

    for field in (
        "completed_packet_ids",
        "budget_flags",
        "unresolved_blockers",
        "allowed_target_statuses",
    ):
        values = validate_string_array(
            snapshot.get(field),
            f"{location}.{field}",
            errors,
        )
        if field in {"budget_flags", "unresolved_blockers"} and any(
            not CODE.fullmatch(value) for value in values
        ):
            errors.append(f"{location}.{field} must contain uppercase codes")

    failed_packets = snapshot.get("failed_packets")
    if not isinstance(failed_packets, list):
        errors.append(f"{location}.failed_packets must be an array")
    else:
        failed_ids: list[str] = []
        for index, failed in enumerate(failed_packets):
            failed_location = f"{location}.failed_packets[{index}]"
            expected_keys = {
                "packet_id",
                "phase",
                "role",
                "candidate_id",
                "round",
                "reason_code",
                "retry_count",
            }
            if not isinstance(failed, dict):
                errors.append(f"{failed_location} must be an object")
                continue
            if set(failed) != expected_keys:
                errors.append(f"{failed_location} has invalid keys")
            packet_id = failed.get("packet_id")
            if not nonempty_string(packet_id) or not SAFE_ID.fullmatch(packet_id):
                errors.append(f"{failed_location}.packet_id is invalid")
            else:
                failed_ids.append(packet_id)
            failed_phase = failed.get("phase")
            if not isinstance(failed_phase, str) or failed_phase not in PHASE_ROLES:
                errors.append(f"{failed_location}.phase is invalid")
            if not nonempty_string(failed.get("role")):
                errors.append(f"{failed_location}.role must be non-empty")
            if failed.get("candidate_id") is not None and not nonempty_string(
                failed.get("candidate_id")
            ):
                errors.append(
                    f"{failed_location}.candidate_id must be a string or null"
                )
            if failed.get("round") is not None and (
                not is_int(failed.get("round")) or failed.get("round") < 1
            ):
                errors.append(
                    f"{failed_location}.round must be positive integer or null"
                )
            if (
                not nonempty_string(failed.get("reason_code"))
                or not CODE.fullmatch(failed.get("reason_code"))
            ):
                errors.append(f"{failed_location}.reason_code is invalid")
            retry_count = failed.get("retry_count")
            if not is_int(retry_count) or retry_count not in {0, 1}:
                errors.append(
                    f"{failed_location}.retry_count must be integer 0 or 1"
                )
        if duplicate_values(failed_ids):
            errors.append(f"{location}.failed_packets contains duplicate IDs")

    active_lanes = snapshot.get("active_lanes")
    if not isinstance(active_lanes, list):
        errors.append(f"{location}.active_lanes must be an array")
    else:
        lane_keys: list[tuple[Any, ...]] = []
        for index, lane in enumerate(active_lanes):
            lane_location = f"{location}.active_lanes[{index}]"
            expected_keys = {
                "phase",
                "candidate_id",
                "round",
                "last_resolved_role",
                "next_role",
                "dependency_packet_ids",
                "search_required",
                "lane_revision",
            }
            if not isinstance(lane, dict):
                errors.append(f"{lane_location} must be an object")
                continue
            if set(lane) != expected_keys:
                errors.append(f"{lane_location} has invalid keys")
            lane_phase = lane.get("phase")
            if (
                not isinstance(lane_phase, str)
                or lane_phase not in {"DEBATE", "EVALUATION_DEBATE"}
            ):
                errors.append(f"{lane_location}.phase is invalid")
            if lane.get("candidate_id") is not None and not nonempty_string(
                lane.get("candidate_id")
            ):
                errors.append(
                    f"{lane_location}.candidate_id must be a string or null"
                )
            if not is_int(lane.get("round")) or lane.get("round") < 1:
                errors.append(f"{lane_location}.round must be positive integer")
            if lane.get("last_resolved_role") is not None and not nonempty_string(
                lane.get("last_resolved_role")
            ):
                errors.append(
                    f"{lane_location}.last_resolved_role must be string or null"
                )
            next_role = lane.get("next_role")
            if not isinstance(next_role, str) or next_role not in {
                "Socratic Mentor",
                "Evidence Researcher",
                "Devil's Advocate",
                "Search and Verification Specialist",
                "Panel Judge",
                "WAIT_FOR_RESULT",
                "COMMIT_ROUND",
            }:
                errors.append(f"{lane_location}.next_role is invalid")
            validate_string_array(
                lane.get("dependency_packet_ids"),
                f"{lane_location}.dependency_packet_ids",
                errors,
            )
            if not isinstance(lane.get("search_required"), bool):
                errors.append(f"{lane_location}.search_required must be boolean")
            if not is_int(lane.get("lane_revision")):
                errors.append(f"{lane_location}.lane_revision must be integer")
            elif lane.get("lane_revision") != transition.get("observed_revision"):
                errors.append(
                    f"{lane_location}.lane_revision must equal observed revision"
                )
            lane_keys.append(
                (
                    lane.get("phase"),
                    lane.get("candidate_id"),
                    lane.get("round"),
                )
            )
        if duplicate_values(lane_keys):
            errors.append(f"{location}.active_lanes contains duplicate lanes")

    verdicts = snapshot.get("accepted_verdicts")
    if not isinstance(verdicts, list):
        errors.append(f"{location}.accepted_verdicts must be an array")
    else:
        for index, verdict in enumerate(verdicts):
            verdict_location = f"{location}.accepted_verdicts[{index}]"
            if not isinstance(verdict, dict) or set(verdict) != {
                "candidate_id",
                "round",
                "verdict",
            }:
                errors.append(f"{verdict_location} has invalid shape")
                continue
            if verdict.get("candidate_id") is not None and not nonempty_string(
                verdict.get("candidate_id")
            ):
                errors.append(
                    f"{verdict_location}.candidate_id must be string or null"
                )
            if not is_int(verdict.get("round")) or verdict.get("round") < 1:
                errors.append(f"{verdict_location}.round must be positive integer")
            verdict_value = verdict.get("verdict")
            if (
                not isinstance(verdict_value, str)
                or verdict_value not in JUDGE_VERDICTS
            ):
                errors.append(f"{verdict_location}.verdict is invalid")

    readiness = snapshot.get("artifact_readiness")
    if not isinstance(readiness, dict):
        errors.append(f"{location}.artifact_readiness must be an object")
    else:
        for key, value in readiness.items():
            if (
                not nonempty_string(key)
                or not CODE.fullmatch(key)
                or not isinstance(value, str)
                or value not in {"READY", "NOT_READY", "STALE", "UNRESOLVED"}
            ):
                errors.append(
                    f"{location}.artifact_readiness[{key!r}] is invalid"
                )

    validation = snapshot.get("latest_validation")
    if not isinstance(validation, dict) or set(validation) != {
        "result",
        "error_codes",
    }:
        errors.append(f"{location}.latest_validation has invalid shape")
    else:
        validation_result = validation.get("result")
        if (
            not isinstance(validation_result, str)
            or validation_result not in {"PASS", "FAIL", "NOT_RUN"}
        ):
            errors.append(f"{location}.latest_validation.result is invalid")
        validation_codes = validate_string_array(
            validation.get("error_codes"),
            f"{location}.latest_validation.error_codes",
            errors,
        )
        if any(not CODE.fullmatch(code) for code in validation_codes):
            errors.append(
                f"{location}.latest_validation.error_codes must be uppercase codes"
            )
        if validation.get("result") == "FAIL" and not validation_codes:
            errors.append(
                f"{location}.latest_validation FAIL requires error_codes"
            )

    user_event = snapshot.get("user_event")
    if not isinstance(user_event, dict) or set(user_event) != {
        "kind",
        "receipt_id",
        "selected_ids",
    }:
        errors.append(f"{location}.user_event has invalid shape")
    else:
        event_kind = user_event.get("kind")
        if (
            not isinstance(event_kind, str)
            or event_kind not in {"NONE"} | set(GATE_RECEIPT_ACTIONS)
        ):
            errors.append(f"{location}.user_event.kind is invalid")
        receipt_id = user_event.get("receipt_id")
        if receipt_id is not None and (
            not nonempty_string(receipt_id) or not SAFE_ID.fullmatch(receipt_id)
        ):
            errors.append(f"{location}.user_event.receipt_id is invalid")
        selected_ids = validate_string_array(
            user_event.get("selected_ids"),
            f"{location}.user_event.selected_ids",
            errors,
        )
        if user_event.get("kind") == "NONE" and (
            receipt_id is not None or selected_ids
        ):
            errors.append(
                f"{location}.user_event NONE requires null receipt and no IDs"
            )

    mode = state.get("mode")
    statuses = EVALUATION_STATUSES if mode == "evaluate" else DISCOVERY_STATUSES
    transition_graph = (
        EVALUATION_TRANSITIONS if mode == "evaluate" else DISCOVERY_TRANSITIONS
    )
    allowed_targets = validate_string_array(
        snapshot.get("allowed_target_statuses"),
        f"{location}.allowed_target_statuses",
        [],
    )
    if isinstance(snapshot.get("allowed_target_statuses"), list):
        legal_targets = transition_graph.get(transition.get("from_status"), set())
        if not allowed_targets:
            errors.append(f"{location}.allowed_target_statuses must not be empty")
        if any(
            target not in statuses or target not in legal_targets
            for target in allowed_targets
        ):
            errors.append(
                f"{location}.allowed_target_statuses contains illegal targets"
            )
        if transition.get("to_status") not in allowed_targets:
            errors.append(
                f"{location}.allowed_target_statuses must contain the "
                "transition target"
            )

    dispatches = transition.get("dispatches")
    dispatches = dispatches if isinstance(dispatches, list) else []
    completed_ids = set(
        validate_string_array(
            snapshot.get("completed_packet_ids"),
            f"{location}.completed_packet_ids",
            [],
        )
    )
    control = state.get("mainline_control")
    transition_log = (
        control.get("transition_log")
        if isinstance(control, dict)
        and isinstance(control.get("transition_log"), list)
        else []
    )
    current_revision = transition.get("revision")
    prior_transition_records = [
        record
        for record in transition_log
        if isinstance(record, dict)
        and is_int(record.get("revision"))
        and is_int(current_revision)
        and record.get("revision") < current_revision
    ]
    prior_dispatches = {
        dispatch.get("packet_id"): dispatch
        for record in prior_transition_records
        for dispatch in (
            record.get("dispatches")
            if isinstance(record.get("dispatches"), list)
            else []
        )
        if isinstance(dispatch, dict)
        and nonempty_string(dispatch.get("packet_id"))
    }
    accepted_ids = {
        product.get("packet_id")
        for product in state.get("accepted_work_products", [])
        if isinstance(product, dict)
        and product.get("phase") != "CONTROL"
        and nonempty_string(product.get("packet_id"))
    }
    rejected_ids = {
        product.get("packet_id")
        for product in state.get("rejected_work_products", [])
        if isinstance(product, dict)
        and product.get("role")
        not in {
            "Mainline Workflow Controller",
            "Deterministic Mainline Fallback",
        }
        and nonempty_string(product.get("packet_id"))
    }
    rejected_by_id = {
        product.get("packet_id"): product
        for product in state.get("rejected_work_products", [])
        if isinstance(product, dict)
        and product.get("role")
        not in {
            "Mainline Workflow Controller",
            "Deterministic Mainline Fallback",
        }
        and nonempty_string(product.get("packet_id"))
    }
    invalid_completed = sorted(
        completed_ids - (accepted_ids & set(prior_dispatches))
    )
    if invalid_completed:
        errors.append(
            f"{location}.completed_packet_ids includes packets that were not "
            f"accepted prior dispatches {invalid_completed}"
        )
    failed_packets_value = snapshot.get("failed_packets")
    archived_failed_ids = {
        failed.get("packet_id")
        for failed in failed_packets_value
        if isinstance(failed_packets_value, list)
        and isinstance(failed, dict)
        and nonempty_string(failed.get("packet_id"))
    } if isinstance(failed_packets_value, list) else set()
    invalid_failed = sorted(
        archived_failed_ids - (rejected_ids & set(prior_dispatches))
    )
    if invalid_failed:
        errors.append(
            f"{location}.failed_packets includes packets that were not rejected "
            f"prior dispatches {invalid_failed}"
        )
    retry_counts = (
        control.get("retry_counts")
        if isinstance(control, dict)
        and isinstance(control.get("retry_counts"), dict)
        else {}
    )
    if isinstance(failed_packets_value, list):
        for failed_index, failed in enumerate(failed_packets_value):
            if not isinstance(failed, dict):
                continue
            failed_packet_id = failed.get("packet_id")
            valid_failed_packet_id = (
                failed_packet_id
                if isinstance(failed_packet_id, str)
                else None
            )
            rejection = rejected_by_id.get(valid_failed_packet_id)
            original_dispatch = prior_dispatches.get(valid_failed_packet_id)
            expected_failed_fields = {
                "phase": (
                    original_dispatch.get("phase")
                    if isinstance(original_dispatch, dict)
                    else None
                ),
                "role": (
                    original_dispatch.get("role")
                    if isinstance(original_dispatch, dict)
                    else None
                ),
                "candidate_id": (
                    original_dispatch.get("candidate_id")
                    if isinstance(original_dispatch, dict)
                    else None
                ),
                "round": (
                    original_dispatch.get("round")
                    if isinstance(original_dispatch, dict)
                    else None
                ),
                "reason_code": (
                    rejection.get("reason_code")
                    if isinstance(rejection, dict)
                    else None
                ),
                "retry_count": retry_counts.get(valid_failed_packet_id, 0),
            }
            for field, expected in expected_failed_fields.items():
                if failed.get(field) != expected:
                    errors.append(
                        f"{location}.failed_packets[{failed_index}].{field} "
                        f"must equal persisted value {expected!r}"
                    )
    if completed_ids & archived_failed_ids:
        errors.append(
            f"{location}: completed_packet_ids and failed_packets must be disjoint"
        )

    if (
        transition.get("action") == "HOLD_FOR_USER"
        and transition.get("pending_user_gate") == "RQ_CONFIRMATION"
    ):
        selected_candidate_id = state.get("selected_candidate_id")
        latest_rq_packet = None
        unresolved_rq_packets: list[str] = []
        if nonempty_string(selected_candidate_id):
            (
                _latest_dispatched_rq,
                latest_rq_packet,
                unresolved_rq_packets,
            ) = historical_rq_resolution(
                prior_dispatches,
                completed_ids,
                archived_failed_ids,
                selected_candidate_id,
            )
        if unresolved_rq_packets:
            errors.append(
                f"{location}: RQ_CONFIRMATION cannot open while RQ packets are "
                f"unresolved {unresolved_rq_packets}"
            )
        if latest_rq_packet is None:
            errors.append(
                f"{location}: RQ_CONFIRMATION requires the latest prior RQ "
                "dispatch in archived completed_packet_ids"
            )
        receipts = state.get("gate_receipts")
        matching_rq_receipts = [
            receipt
            for receipt in receipts
            if isinstance(receipts, list)
            and isinstance(receipt, dict)
            and receipt.get("gate") == "RQ_CONFIRMATION"
            and receipt.get("based_on_revision") == transition.get("revision")
        ] if isinstance(receipts, list) else []
        for receipt in matching_rq_receipts:
            if (
                receipt.get("action") == "CONFIRM"
                and receipt.get("values")
                != [selected_candidate_id, latest_rq_packet]
            ):
                errors.append(
                    f"{location}: RQ confirmation receipt must bind the exact "
                    "RQ packet completed before this HOLD"
                )

    if transition.get("checkpoint") == "RECOVERY":
        latest_validation = snapshot.get("latest_validation")
        has_recovery_event = bool(
            failed_packets_value
            or snapshot.get("budget_flags")
            or snapshot.get("unresolved_blockers")
            or (
                isinstance(latest_validation, dict)
                and latest_validation.get("result") == "FAIL"
            )
            or transition.get("from_status") == "BLOCKED"
        )
        if not has_recovery_event:
            errors.append(
                f"{location}: RECOVERY requires a failed packet, budget flag, "
                "blocker, failed validation, or BLOCKED source status"
            )

    predecessor = (
        prior_transition_records[-1] if prior_transition_records else None
    )
    predecessor_dispatches = (
        predecessor.get("dispatches")
        if isinstance(predecessor, dict)
        and isinstance(predecessor.get("dispatches"), list)
        else []
    )
    if transition.get("checkpoint") == "POST_USER_GATE":
        predecessor_gate = (
            predecessor.get("pending_user_gate")
            if isinstance(predecessor, dict)
            and predecessor.get("action") == "HOLD_FOR_USER"
            else None
        )
        receipts = state.get("gate_receipts")
        matching_receipts = [
            receipt
            for receipt in receipts
            if isinstance(receipts, list)
            and isinstance(receipt, dict)
            and receipt.get("gate") == predecessor_gate
            and receipt.get("based_on_revision") == predecessor.get("revision")
        ] if isinstance(receipts, list) and isinstance(predecessor, dict) else []
        user_event = snapshot.get("user_event")
        if (
            len(matching_receipts) != 1
            or not isinstance(user_event, dict)
            or user_event.get("kind") != predecessor_gate
            or user_event.get("receipt_id")
            != matching_receipts[0].get("receipt_id")
            or user_event.get("selected_ids")
            != matching_receipts[0].get("values")
        ):
            errors.append(
                f"{location}.user_event must exactly project the receipt "
                "consumed at POST_USER_GATE"
            )
    if transition.get("checkpoint") == "ROLE_BOUNDARY":
        predecessor_packet_ids = {
            dispatch.get("packet_id")
            for dispatch in predecessor_dispatches
            if isinstance(dispatch, dict)
            and nonempty_string(dispatch.get("packet_id"))
        }
        if not predecessor_packet_ids & (completed_ids | archived_failed_ids):
            errors.append(
                f"{location}: ROLE_BOUNDARY requires at least one predecessor "
                "packet in the archived completion/failure projection"
            )
    if transition.get("checkpoint") == "ROUND_BOUNDARY":
        prior_resolved = {
            packet_id
            for packet_id in prior_dispatches
            if packet_id in (accepted_ids | rejected_ids)
        }
        missing_prior_resolutions = sorted(
            prior_resolved - (completed_ids | archived_failed_ids)
        )
        if missing_prior_resolutions:
            errors.append(
                f"{location}: ROUND_BOUNDARY omits prior resolved packets "
                f"{missing_prior_resolutions}"
            )
    readiness = (
        snapshot.get("artifact_readiness")
        if isinstance(snapshot.get("artifact_readiness"), dict)
        else {}
    )
    active_lanes = (
        [lane for lane in snapshot.get("active_lanes", []) if isinstance(lane, dict)]
        if isinstance(snapshot.get("active_lanes"), list)
        else []
    )
    lanes_by_key = {
        (lane.get("phase"), lane.get("candidate_id"), lane.get("round")): lane
        for lane in active_lanes
        if isinstance(lane.get("phase"), str)
        and (
            lane.get("candidate_id") is None
            or isinstance(lane.get("candidate_id"), str)
        )
        and is_int(lane.get("round"))
    }
    expected_lanes = expected_archived_active_lanes(
        snapshot,
        transition,
        state,
        prior_dispatches,
        completed_ids,
        archived_failed_ids,
    )
    expected_lanes_by_key = {
        (lane["phase"], lane["candidate_id"], lane["round"]): lane
        for lane in expected_lanes
    }
    if set(lanes_by_key) != set(expected_lanes_by_key):
        errors.append(
            f"{location}.active_lanes must exactly match the historical lane "
            f"projection; expected={sorted(expected_lanes_by_key, key=repr)}, "
            f"actual={sorted(lanes_by_key, key=repr)}"
        )
    for lane_key in set(lanes_by_key) & set(expected_lanes_by_key):
        archived_lane = lanes_by_key[lane_key]
        expected_lane = expected_lanes_by_key[lane_key]
        for field in (
            "last_resolved_role",
            "next_role",
            "dependency_packet_ids",
            "search_required",
            "lane_revision",
        ):
            if archived_lane.get(field) != expected_lane.get(field):
                errors.append(
                    f"{location}.active_lanes[{lane_key!r}].{field} must equal "
                    f"historical projection {expected_lane.get(field)!r}"
                )
    candidate_records = {
        candidate.get("candidate_id"): candidate
        for candidate in state.get("candidates", [])
        if isinstance(candidate, dict)
        and nonempty_string(candidate.get("candidate_id"))
    }
    dispatched_lane_keys: set[tuple[Any, ...]] = set()
    for index, dispatch in enumerate(dispatches):
        if not isinstance(dispatch, dict):
            continue
        dispatch_location = f"{location}.transition.dispatches[{index}]"
        dependencies = dispatch.get("depends_on_packet_ids")
        if isinstance(dependencies, list):
            dependency_ids = {
                dependency
                for dependency in dependencies
                if isinstance(dependency, str)
            }
            missing_completed = sorted(dependency_ids - completed_ids)
            if missing_completed:
                errors.append(
                    f"{dispatch_location}.depends_on_packet_ids are absent from "
                    f"completed_packet_ids {missing_completed}"
                )
        dispatch_phase = dispatch.get("phase")
        required_artifacts = DISPATCH_ARTIFACT_REQUIREMENTS.get(
            dispatch_phase if isinstance(dispatch_phase, str) else None,
            set(),
        )
        not_ready = sorted(
            artifact
            for artifact in required_artifacts
            if readiness.get(artifact) != "READY"
        )
        if not_ready:
            errors.append(
                f"{dispatch_location} requires READY artifacts {not_ready}"
            )
        if (
            not isinstance(dispatch_phase, str)
            or dispatch_phase not in {"DEBATE", "EVALUATION_DEBATE"}
        ):
            continue
        lane_key = (
            dispatch.get("phase"),
            dispatch.get("candidate_id"),
            dispatch.get("round"),
        )
        if not (
            isinstance(lane_key[0], str)
            and (lane_key[1] is None or isinstance(lane_key[1], str))
            and is_int(lane_key[2])
        ):
            continue
        lane = lanes_by_key.get(lane_key)
        if lane is None:
            errors.append(
                f"{dispatch_location} has no matching archived active lane"
            )
            continue
        dispatched_lane_keys.add(lane_key)
        if dispatch.get("role") != lane.get("next_role"):
            errors.append(
                f"{dispatch_location}.role must equal archived next_role "
                f"{lane.get('next_role')!r}"
            )
        lane_dependencies = lane.get("dependency_packet_ids")
        if isinstance(dependencies, list) and isinstance(lane_dependencies, list):
            missing_lane_dependencies = sorted(
                {
                    dependency
                    for dependency in lane_dependencies
                    if isinstance(dependency, str)
                }
                - {
                    dependency
                    for dependency in dependencies
                    if isinstance(dependency, str)
                }
            )
            if missing_lane_dependencies:
                errors.append(
                    f"{dispatch_location}.depends_on_packet_ids omits archived "
                    f"lane dependencies {missing_lane_dependencies}"
                )

    if (
        transition.get("action") == "ADVANCE"
        and transition.get("to_status") in {"DEBATING", "EVALUATION_DEBATE"}
        and transition.get("checkpoint")
        in {"PHASE_BOUNDARY", "ROLE_BOUNDARY", "ROUND_BOUNDARY", "RESUME"}
    ):
        if transition.get("checkpoint") == "ROUND_BOUNDARY":
            ready_lane_keys = {
                key
                for key, lane in lanes_by_key.items()
                if lane.get("next_role") == "Socratic Mentor"
            }
        else:
            ready_lane_keys = {
                key
                for key, lane in lanes_by_key.items()
                if lane.get("next_role")
                not in {"WAIT_FOR_RESULT", "COMMIT_ROUND"}
                and not (
                    transition.get("checkpoint") == "ROLE_BOUNDARY"
                    and lane.get("next_role") == "Socratic Mentor"
                    and is_int(lane.get("round"))
                    and lane.get("round") > 1
                )
            }
        missing_lanes = sorted(
            ready_lane_keys - dispatched_lane_keys,
            key=repr,
        )
        ineligible_lanes = sorted(
            dispatched_lane_keys - ready_lane_keys,
            key=repr,
        )
        if missing_lanes:
            errors.append(
                f"{location}: debate ADVANCE must coalesce every ready archived "
                f"lane; missing {missing_lanes}"
            )
        if ineligible_lanes:
            errors.append(
                f"{location}: {transition.get('checkpoint')} dispatched lanes "
                f"that are not eligible at this barrier {ineligible_lanes}"
            )
        if transition.get("checkpoint") == "ROUND_BOUNDARY":
            incomplete = [
                key
                for key, lane in lanes_by_key.items()
                if lane.get("next_role") != "Socratic Mentor"
            ]
            if incomplete:
                errors.append(
                    f"{location}: ROUND_BOUNDARY requires every continuing lane "
                    f"to be ready for its next Mentor; incomplete {incomplete}"
                )

    archived_verdicts = (
        snapshot.get("accepted_verdicts")
        if isinstance(snapshot.get("accepted_verdicts"), list)
        else []
    )
    archived_verdict_keys = {
        (
            verdict.get("candidate_id"),
            verdict.get("round"),
            verdict.get("verdict"),
        )
        for verdict in archived_verdicts
        if isinstance(verdict, dict)
        and (
            verdict.get("candidate_id") is None
            or isinstance(verdict.get("candidate_id"), str)
        )
        and is_int(verdict.get("round"))
        and isinstance(verdict.get("verdict"), str)
    }
    expected_verdict_keys: set[tuple[Any, ...]] = set()
    evaluation_rounds = state.get("evaluation_rounds")
    for packet_id, dispatch in prior_dispatches.items():
        if (
            packet_id not in completed_ids
            or dispatch.get("role") != "Panel Judge"
            or dispatch.get("phase") not in {"DEBATE", "EVALUATION_DEBATE"}
        ):
            continue
        round_number = dispatch.get("round")
        records = (
            evaluation_rounds
            if dispatch.get("phase") == "EVALUATION_DEBATE"
            else candidate_records.get(dispatch.get("candidate_id"), {}).get(
                "rounds"
            )
        )
        record = (
            records[round_number - 1]
            if isinstance(records, list)
            and is_int(round_number)
            and 1 <= round_number <= len(records)
            and isinstance(records[round_number - 1], dict)
            else None
        )
        if not isinstance(record, dict):
            errors.append(
                f"{location}: completed Judge packet {packet_id!r} has no "
                "persisted round verdict"
            )
            continue
        expected_verdict_keys.add(
            (
                dispatch.get("candidate_id"),
                round_number,
                record.get("verdict"),
            )
        )
    if archived_verdict_keys != expected_verdict_keys:
        errors.append(
            f"{location}.accepted_verdicts must exactly project completed prior "
            "Judge packets"
        )

    if transition.get("action") == "BLOCK_SESSION":
        validation = snapshot.get("latest_validation")
        validation_codes = (
            validation.get("error_codes", [])
            if isinstance(validation, dict)
            and isinstance(validation.get("error_codes"), list)
            else []
        )
        failed_packets = snapshot.get("failed_packets")
        failed_codes = {
            failed.get("reason_code")
            for failed in failed_packets
            if isinstance(failed_packets, list)
            and isinstance(failed, dict)
            and nonempty_string(failed.get("reason_code"))
        } if isinstance(failed_packets, list) else set()
        budget_codes = set(
            validate_string_array(
                snapshot.get("budget_flags"),
                f"{location}.budget_flags",
                [],
            )
        )
        unresolved_codes = set(
            validate_string_array(
                snapshot.get("unresolved_blockers"),
                f"{location}.unresolved_blockers",
                [],
            )
        )
        validated_codes = {
            code for code in validation_codes if isinstance(code, str)
        }
        transition_blocking_codes = set(
            validate_string_array(
                transition.get("blocking_reasons"),
                f"{location}.transition.blocking_reasons",
                [],
            )
        )
        authoritative_blockers = (
            budget_codes
            | unresolved_codes
            | validated_codes
            | failed_codes
        )
        unsupported = sorted(
            transition_blocking_codes - authoritative_blockers
        )
        if unsupported:
            errors.append(
                f"{location}: blocking_reasons are absent from the archived "
                f"control input {unsupported}"
            )


def validate_mainline_control(
    state: dict[str, Any],
    errors: list[str],
    session_dir: Path | None = None,
) -> None:
    if state.get("schema_version") != "1.3":
        return

    control = state.get("mainline_control")
    fields = (
        "controller_id",
        "controller_status",
        "revision",
        "last_checkpoint",
        "pending_user_gate",
        "last_controller_packet_id",
        "retry_counts",
        "lane_search_requests",
        "transition_log",
    )
    if not require_keys(control, fields, "mainline_control", errors):
        return

    if control.get("controller_id") != "MAINLINE":
        errors.append("mainline_control.controller_id must equal MAINLINE")
    controller_status = control.get("controller_status")
    if (
        not isinstance(controller_status, str)
        or controller_status not in CONTROLLER_STATUSES
    ):
        errors.append(
            "mainline_control.controller_status must be one of "
            f"{sorted(CONTROLLER_STATUSES)}"
        )

    revision = control.get("revision")
    if not is_int(revision) or revision < 0:
        errors.append(
            "mainline_control.revision must be a non-negative integer"
        )
        revision = -1

    retry_counts = control.get("retry_counts")
    if not isinstance(retry_counts, dict):
        errors.append("mainline_control.retry_counts must be an object")
        retry_counts = {}
    else:
        for retry_key, count in retry_counts.items():
            if (
                not nonempty_string(retry_key)
                or not SAFE_ID.fullmatch(retry_key)
            ):
                errors.append(
                    "mainline_control.retry_counts keys must be valid packet IDs"
                )
            if not is_int(count) or count != 1:
                errors.append(
                    f"mainline_control.retry_counts[{retry_key!r}] must equal "
                    "the integer 1"
                )

    lane_search_requests = validate_lane_search_requests(
        control.get("lane_search_requests"),
        "mainline_control.lane_search_requests",
        errors,
    )

    transitions = control.get("transition_log")
    if not isinstance(transitions, list):
        errors.append("mainline_control.transition_log must be an array")
        return

    products = state.get("accepted_work_products")
    accepted_products = (
        [product for product in products if isinstance(product, dict)]
        if isinstance(products, list)
        else []
    )
    control_products = {
        product.get("packet_id"): product
        for product in accepted_products
        if product.get("phase") == "CONTROL"
        and nonempty_string(product.get("packet_id"))
    }
    accepted_packet_ids = {
        product.get("packet_id")
        for product in accepted_products
        if nonempty_string(product.get("packet_id"))
    }
    rejected = state.get("rejected_work_products")
    rejected_products = {
        product.get("packet_id"): product
        for product in rejected
        if isinstance(product, dict) and nonempty_string(product.get("packet_id"))
    } if isinstance(rejected, list) else {}
    rejected_packet_ids = set(rejected_products)
    candidates = state.get("candidates")
    candidate_ids = {
        candidate.get("candidate_id")
        for candidate in candidates
        if isinstance(candidate, dict)
        and nonempty_string(candidate.get("candidate_id"))
    } if isinstance(candidates, list) else set()

    if revision == 0:
        initial_status = (
            "EVIDENCE_INTAKE"
            if state.get("mode") == "evaluate"
            else "SCANNING"
        )
        if transitions:
            errors.append(
                "mainline_control: bootstrap revision 0 requires an empty "
                "transition_log"
            )
        if control.get("last_checkpoint") is not None:
            errors.append(
                "mainline_control.last_checkpoint must be null at bootstrap"
            )
        if control.get("pending_user_gate") is not None:
            errors.append(
                "mainline_control.pending_user_gate must be null at bootstrap"
            )
        if control.get("last_controller_packet_id") is not None:
            errors.append(
                "mainline_control.last_controller_packet_id must be null at "
                "bootstrap"
            )
        if state.get("status") != initial_status:
            errors.append(
                f"mainline_control: bootstrap status must be {initial_status}"
            )
        if accepted_products:
            errors.append(
                "mainline_control: bootstrap must have no accepted work products"
            )
        receipts = state.get("gate_receipts")
        if isinstance(receipts, list) and receipts:
            errors.append("mainline_control: bootstrap must have no gate receipts")
        return

    if revision != len(transitions):
        errors.append(
            "mainline_control.revision must equal the transition_log length"
        )
    if not transitions:
        errors.append(
            "mainline_control.transition_log must be non-empty after bootstrap"
        )
        return

    transition_fields = (
        "revision",
        "observed_revision",
        "packet_id",
        "observed_state_digest",
        "control_input_digest",
        "control_input_path",
        "checkpoint",
        "from_status",
        "action",
        "to_status",
        "pending_user_gate",
        "dispatches",
        "required_actions",
        "required_checks",
        "reason_codes",
        "blocking_reasons",
        "retry_key",
        "recorded_at",
    )
    transition_packet_ids: list[str] = []
    dispatch_packet_ids: list[str] = []
    dispatches_by_packet_id: dict[str, dict[str, Any]] = {}
    retry_keys: list[str] = []
    retry_dispatch_packet_ids: set[str] = set()
    archived_snapshots_by_revision: dict[int, dict[str, Any]] = {}
    previous_status: str | None = None
    mode = state.get("mode")
    statuses = EVALUATION_STATUSES if mode == "evaluate" else DISCOVERY_STATUSES
    transitions_by_status = (
        EVALUATION_TRANSITIONS if mode == "evaluate" else DISCOVERY_TRANSITIONS
    )
    dispatch_phases_by_status = (
        EVALUATION_DISPATCH_PHASES_BY_STATUS
        if mode == "evaluate"
        else DISCOVERY_DISPATCH_PHASES_BY_STATUS
    )

    for index, transition in enumerate(transitions, start=1):
        location = f"mainline_control.transition_log[{index - 1}]"
        if not require_keys(transition, transition_fields, location, errors):
            continue

        entry_revision = transition.get("revision")
        observed_revision = transition.get("observed_revision")
        packet_id = transition.get("packet_id")
        digest = transition.get("observed_state_digest")
        control_input_digest = transition.get("control_input_digest")
        control_input_path = transition.get("control_input_path")
        checkpoint = transition.get("checkpoint")
        from_status = transition.get("from_status")
        action = transition.get("action")
        to_status = transition.get("to_status")
        pending_gate = transition.get("pending_user_gate")
        retry_key = transition.get("retry_key")
        control_snapshot: dict[str, Any] | None = None
        historical_completed_ids = set(accepted_packet_ids)
        historical_failed_ids = set(rejected_packet_ids)

        if not is_int(entry_revision) or entry_revision != index:
            errors.append(f"{location}.revision must equal integer {index}")
        if not is_int(observed_revision) or observed_revision != index - 1:
            errors.append(
                f"{location}.observed_revision must equal integer {index - 1}"
            )
        if not nonempty_string(packet_id) or not SAFE_ID.fullmatch(packet_id):
            errors.append(f"{location}.packet_id is invalid")
        else:
            transition_packet_ids.append(packet_id)
        if not is_sha256(digest):
            errors.append(
                f"{location}.observed_state_digest must be a lowercase "
                "SHA-256 digest"
            )
        if not is_sha256(control_input_digest):
            errors.append(
                f"{location}.control_input_digest must be a lowercase "
                "SHA-256 digest"
            )
        valid_packet_path_id = bool(
            nonempty_string(packet_id) and SAFE_ID.fullmatch(packet_id)
        )
        expected_control_input_path = (
            f"control-inputs/{packet_id}.json" if valid_packet_path_id else None
        )
        if control_input_path != expected_control_input_path:
            errors.append(
                f"{location}.control_input_path must equal "
                f"{expected_control_input_path!r}"
            )
        elif session_dir is not None and valid_packet_path_id:
            snapshot_dir = session_dir / "control-inputs"
            snapshot_path = snapshot_dir / f"{packet_id}.json"
            try:
                if snapshot_dir.is_symlink():
                    raise OSError("control-inputs directory must not be a symlink")
                resolved_dir = snapshot_dir.resolve()
                if snapshot_path.is_symlink():
                    raise OSError("control input snapshot must not be a symlink")
                resolved_snapshot = snapshot_path.resolve()
                if resolved_snapshot.parent != resolved_dir:
                    raise OSError("control input snapshot escapes control-inputs")
                if not snapshot_path.is_file():
                    raise OSError("control input snapshot is not a regular file")
                snapshot_raw = snapshot_path.read_bytes()
            except OSError as exc:
                errors.append(
                    f"{location}.control_input_path cannot be read: {exc}"
                )
            else:
                snapshot_digest = hashlib.sha256(snapshot_raw).hexdigest()
                if snapshot_digest != control_input_digest:
                    errors.append(
                        f"{location}.control_input_path digest does not match "
                        "control_input_digest"
                    )
                snapshot = parse_strict_json_bytes(
                    snapshot_raw,
                    f"{location}.control_input_path",
                    errors,
                )
                if snapshot is not None and not isinstance(snapshot, dict):
                    errors.append(
                        f"{location}.control_input_path must contain an object"
                    )
                elif isinstance(snapshot, dict):
                    control_snapshot = snapshot
                    if is_int(entry_revision):
                        archived_snapshots_by_revision[entry_revision] = snapshot
                    historical_completed_ids = {
                        value
                        for value in snapshot.get("completed_packet_ids", [])
                        if isinstance(snapshot.get("completed_packet_ids"), list)
                        and isinstance(value, str)
                    }
                    historical_failed_ids = {
                        failed.get("packet_id")
                        for failed in snapshot.get("failed_packets", [])
                        if isinstance(snapshot.get("failed_packets"), list)
                        and isinstance(failed, dict)
                        and isinstance(failed.get("packet_id"), str)
                    }
                    validate_control_input_snapshot(
                        snapshot,
                        transition,
                        state,
                        f"{location}.control_input_path",
                        errors,
                    )
        if (
            not isinstance(checkpoint, str)
            or checkpoint not in CONTROL_CHECKPOINTS
        ):
            errors.append(
                f"{location}.checkpoint must be one of "
                f"{sorted(CONTROL_CHECKPOINTS)}"
            )
        if not isinstance(from_status, str) or from_status not in statuses:
            errors.append(f"{location}.from_status is invalid for mode {mode!r}")
        if not isinstance(to_status, str) or to_status not in statuses:
            errors.append(f"{location}.to_status is invalid for mode {mode!r}")
        if previous_status is not None and from_status != previous_status:
            errors.append(
                f"{location}.from_status must equal the prior to_status "
                f"{previous_status!r}"
            )
        if index == 1:
            expected_initial = (
                "EVIDENCE_INTAKE" if mode == "evaluate" else "SCANNING"
            )
            if checkpoint != "SESSION_INIT":
                errors.append(
                    f"{location}.checkpoint must be SESSION_INIT for the first "
                    "schema-1.3 transition"
                )
            if from_status != expected_initial:
                errors.append(
                    f"{location}.from_status must begin at {expected_initial!r}"
                )
        elif checkpoint == "SESSION_INIT":
            errors.append(
                f"{location}.checkpoint SESSION_INIT is valid only for the "
                "first transition"
            )
        if checkpoint == "RESUME" and index == 1:
            errors.append(
                f"{location}.checkpoint RESUME requires existing schema-1.3 "
                "control history"
            )
        if (
            isinstance(from_status, str)
            and from_status in transitions_by_status
            and (
                not isinstance(to_status, str)
                or to_status not in transitions_by_status[from_status]
            )
        ):
            errors.append(
                f"{location}: transition {from_status!r} -> {to_status!r} "
                "is not allowed"
            )
        previous_status = to_status if isinstance(to_status, str) else previous_status

        if not isinstance(action, str) or action not in CONTROL_ACTIONS:
            errors.append(
                f"{location}.action must be one of {sorted(CONTROL_ACTIONS)}"
            )
        if checkpoint == "PRE_USER_GATE" and action != "HOLD_FOR_USER":
            errors.append(
                f"{location}: PRE_USER_GATE requires HOLD_FOR_USER"
            )
        if checkpoint == "PRE_COMPLETE" and action != "COMPLETE":
            errors.append(f"{location}: PRE_COMPLETE requires COMPLETE")
        if action == "COMPLETE" and checkpoint != "PRE_COMPLETE":
            errors.append(f"{location}: COMPLETE requires PRE_COMPLETE")
        if checkpoint == "ROUND_BOUNDARY" and from_status not in {
            "DEBATING",
            "EVALUATION_DEBATE",
        }:
            errors.append(
                f"{location}: ROUND_BOUNDARY is invalid outside a debate status"
            )
        if checkpoint == "ROLE_BOUNDARY" and from_status not in {
            "DEBATING",
            "EVALUATION_DEBATE",
        }:
            errors.append(
                f"{location}: ROLE_BOUNDARY is invalid outside a debate status"
            )
        if (
            isinstance(checkpoint, str)
            and checkpoint in {"ROLE_BOUNDARY", "ROUND_BOUNDARY"}
        ):
            predecessor = transitions[index - 2] if index >= 2 else None
            predecessor_dispatches = (
                predecessor.get("dispatches")
                if isinstance(predecessor, dict)
                and isinstance(predecessor.get("dispatches"), list)
                else []
            )
            if checkpoint == "ROLE_BOUNDARY" and (
                not predecessor_dispatches
                or not any(
                    isinstance(dispatch, dict)
                    and dispatch.get("packet_id")
                    in (historical_completed_ids | historical_failed_ids)
                    for dispatch in predecessor_dispatches
                )
            ):
                errors.append(
                    f"{location}: ROLE_BOUNDARY requires a resolved dispatch "
                    "from the immediately preceding controller batch"
                )
            if checkpoint == "ROUND_BOUNDARY":
                judge_ids = [
                    dispatch.get("packet_id")
                    for dispatch in predecessor_dispatches
                    if isinstance(dispatch, dict)
                    and dispatch.get("role") == "Panel Judge"
                    and dispatch.get("phase")
                    in {"DEBATE", "EVALUATION_DEBATE"}
                ]
                if (
                    not judge_ids
                    or any(
                        judge_id not in historical_completed_ids
                        for judge_id in judge_ids
                    )
                ):
                    errors.append(
                        f"{location}: ROUND_BOUNDARY requires accepted Judge "
                        "outputs from the immediately preceding batch"
                    )
        if checkpoint == "POST_USER_GATE":
            predecessor = transitions[index - 2] if index >= 2 else None
            if (
                not isinstance(predecessor, dict)
                or predecessor.get("action") != "HOLD_FOR_USER"
                or not isinstance(
                    predecessor.get("pending_user_gate"),
                    str,
                )
                or predecessor.get("pending_user_gate") not in PENDING_USER_GATES
            ):
                errors.append(
                    f"{location}: POST_USER_GATE must immediately follow a "
                    "HOLD_FOR_USER boundary"
                )
        if pending_gate is not None and (
            not isinstance(pending_gate, str)
            or pending_gate not in PENDING_USER_GATES
        ):
            errors.append(
                f"{location}.pending_user_gate must be null or one of "
                f"{sorted(PENDING_USER_GATES)}"
            )

        dispatches = transition.get("dispatches")
        if not isinstance(dispatches, list):
            errors.append(f"{location}.dispatches must be an array")
            dispatches = []
        transition_reason_codes = transition.get("reason_codes")
        prior_dispatches_before_batch = dict(dispatches_by_packet_id)
        current_dispatch_ids: list[str] = []
        for dispatch_index, dispatch in enumerate(dispatches):
            dispatch_id = validate_control_dispatch(
                dispatch,
                f"{location}.dispatches[{dispatch_index}]",
                candidate_ids,
                historical_completed_ids,
                errors,
            )
            if dispatch_id is not None:
                current_dispatch_ids.append(dispatch_id)
                dispatch_packet_ids.append(dispatch_id)
                if isinstance(dispatch, dict):
                    dispatches_by_packet_id.setdefault(dispatch_id, dispatch)
                    dispatch_phase = dispatch.get("phase")
                    if dispatch_phase == "RQ_REFINEMENT" and any(
                        isinstance(prior, dict)
                        and prior.get("required_actions")
                        == ["APPLY_RQ_CONFIRMATION"]
                        for prior in transitions[: index - 1]
                    ):
                        errors.append(
                            f"{location}.dispatches[{dispatch_index}]: "
                            "RQ_REFINEMENT is frozen after the user-confirmed "
                            "version has been applied"
                        )
                    schedulable_phases = dispatch_phases_by_status.get(
                        to_status if isinstance(to_status, str) else None,
                        set(),
                    )
                    if (
                        not isinstance(dispatch_phase, str)
                        or dispatch_phase not in schedulable_phases
                    ):
                        errors.append(
                            f"{location}.dispatches[{dispatch_index}].phase "
                            f"{dispatch_phase!r} is not schedulable while "
                            f"targeting status {to_status!r}"
                        )
                    if (
                        dispatch_phase == "DIRECTION_SELECTION"
                        and state.get("interaction_mode") == "GUIDED"
                    ):
                        predecessor = (
                            transitions[index - 2] if index >= 2 else None
                        )
                        receipts = state.get("gate_receipts")
                        delegated = (
                            checkpoint == "POST_USER_GATE"
                            and isinstance(predecessor, dict)
                            and predecessor.get("action") == "HOLD_FOR_USER"
                            and predecessor.get("pending_user_gate")
                            == "DIRECTION_SELECTION"
                            and isinstance(receipts, list)
                            and any(
                                isinstance(receipt, dict)
                                and receipt.get("gate")
                                == "DIRECTION_SELECTION"
                                and receipt.get("action") == "DELEGATE"
                                and receipt.get("based_on_revision")
                                == predecessor.get("revision")
                                for receipt in receipts
                            )
                        )
                        if not delegated:
                            errors.append(
                                f"{location}.dispatches[{dispatch_index}]: "
                                "GUIDED DIRECTION_SELECTION requires the "
                                "immediately preceding delegated user gate"
                            )
                    if dispatch_phase == "EVIDENCE_INTAKE":
                        evaluation_target = state.get("evaluation_target")
                        missing_target_fields = [
                            field
                            for field in (
                                "direction",
                                "primary_claim",
                                "study_type",
                            )
                            if not isinstance(evaluation_target, dict)
                            or not nonempty_string(evaluation_target.get(field))
                        ]
                        if missing_target_fields:
                            errors.append(
                                f"{location}.dispatches[{dispatch_index}]: "
                                "EVIDENCE_INTAKE cannot dispatch the Experiment "
                                "Auditor until target fields are resolved "
                                f"{missing_target_fields}"
                            )
                    dispatch_key = tuple(
                        key_component(component)
                        for component in (
                            dispatch.get("phase"),
                            dispatch.get("role"),
                            dispatch.get("candidate_id"),
                            dispatch.get("round"),
                        )
                    )
                    matching_accepted_dispatches = [
                        prior_id
                        for prior_id, prior in prior_dispatches_before_batch.items()
                        if prior_id in historical_completed_ids
                        and tuple(
                            key_component(prior.get(field))
                            for field in (
                                "phase",
                                "role",
                                "candidate_id",
                                "round",
                            )
                        )
                        == dispatch_key
                    ]
                    superseded_packet = (
                        matching_accepted_dispatches[-1]
                        if matching_accepted_dispatches
                        else None
                    )
                    dependencies = [
                        dependency
                        for dependency in (
                            dispatch.get("depends_on_packet_ids")
                            if isinstance(
                                dispatch.get("depends_on_packet_ids"),
                                list,
                            )
                            else []
                        )
                        if isinstance(dependency, str)
                    ]
                    unknown_prior_dependencies = sorted(
                        set(dependencies) - set(prior_dispatches_before_batch)
                    )
                    if unknown_prior_dependencies:
                        errors.append(
                            f"{location}.dispatches[{dispatch_index}]."
                            "depends_on_packet_ids must reference prior "
                            "controller dispatches "
                            f"{unknown_prior_dependencies}"
                        )
                    validate_committed_dispatch_prerequisites(
                        dispatch,
                        state,
                        historical_completed_ids,
                        prior_dispatches_before_batch,
                        dependencies,
                        f"{location}.dispatches[{dispatch_index}]",
                        errors,
                        control_snapshot,
                    )
                    if superseded_packet is not None:
                        dispatch_role = dispatch.get("role")
                        if (
                            dispatch_phase in {"DEBATE", "EVALUATION_DEBATE"}
                            and dispatch_role != "Evidence Researcher"
                        ):
                            errors.append(
                                f"{location}.dispatches[{dispatch_index}] "
                                "repeats an accepted debate-round role call"
                            )
                        else:
                            if (
                                not isinstance(transition_reason_codes, list)
                                or "SUPERSEDE_ACCEPTED_CALL"
                                not in transition_reason_codes
                            ):
                                errors.append(
                                    f"{location}.dispatches[{dispatch_index}] "
                                    "repeats an accepted call without "
                                    "reason code SUPERSEDE_ACCEPTED_CALL"
                                )
                            if superseded_packet not in dependencies:
                                errors.append(
                                    f"{location}.dispatches[{dispatch_index}] "
                                    "must depend on the latest accepted packet "
                                    f"it supersedes: {superseded_packet!r}"
                                )
                            if (
                                dispatch_phase
                                in {"DEBATE", "EVALUATION_DEBATE"}
                                and dispatch_role == "Evidence Researcher"
                            ):
                                accepted_evidence_count = (
                                    len(matching_accepted_dispatches)
                                )
                                if accepted_evidence_count >= 2:
                                    errors.append(
                                        f"{location}.dispatches[{dispatch_index}] "
                                        "exceeds the one permitted revised "
                                        "Evidence Researcher answer"
                                    )
                                search_packet = next(
                                    (
                                        prior_id
                                        for prior_id, prior in reversed(
                                            list(
                                                prior_dispatches_before_batch.items()
                                            )
                                        )
                                        if prior_id in historical_completed_ids
                                        and prior.get("phase") == dispatch_phase
                                        and prior.get("role")
                                        == "Search and Verification Specialist"
                                        and prior.get("candidate_id")
                                        == dispatch.get("candidate_id")
                                        and prior.get("round")
                                        == dispatch.get("round")
                                    ),
                                    None,
                                )
                                if search_packet is None:
                                    errors.append(
                                        f"{location}.dispatches[{dispatch_index}] "
                                        "may supersede Evidence only after an "
                                        "accepted same-round search"
                                    )
                                elif search_packet not in dependencies:
                                    errors.append(
                                        f"{location}.dispatches[{dispatch_index}]."
                                        "depends_on_packet_ids must include "
                                        f"same-round search packet {search_packet!r}"
                                    )
        duplicate_dispatches = duplicate_values(current_dispatch_ids)
        if duplicate_dispatches:
            errors.append(
                f"{location}.dispatches contain duplicate packet IDs "
                f"{duplicate_dispatches}"
            )

        required_actions = validate_string_array(
            transition.get("required_actions"),
            f"{location}.required_actions",
            errors,
        )
        required_checks = validate_string_array(
            transition.get("required_checks"),
            f"{location}.required_checks",
            errors,
        )
        reason_codes = validate_string_array(
            transition.get("reason_codes"),
            f"{location}.reason_codes",
            errors,
        )
        blocking_reasons = validate_string_array(
            transition.get("blocking_reasons"),
            f"{location}.blocking_reasons",
            errors,
        )
        unknown_actions = sorted(
            set(required_actions) - CONTROL_REQUIRED_ACTIONS
        )
        if unknown_actions:
            errors.append(
                f"{location}.required_actions contains unsupported actions "
                f"{unknown_actions}"
            )
        unknown_checks = sorted(
            set(required_checks) - CONTROL_REQUIRED_CHECKS
        )
        if unknown_checks:
            errors.append(
                f"{location}.required_checks contains unsupported checks "
                f"{unknown_checks}"
            )
        if index == 1:
            expected_init_action = (
                "BUILD_EVALUATION_INPUT_SNAPSHOT"
                if mode == "evaluate"
                else "BUILD_PROJECT_EVIDENCE_PACK"
            )
            if required_actions != [expected_init_action]:
                errors.append(
                    f"{location}: SESSION_INIT must require exactly "
                    f"{expected_init_action}"
                )
            if dispatches:
                errors.append(
                    f"{location}: SESSION_INIT must build the evidence pack "
                    "before any role dispatch"
                )

        predecessor = transitions[index - 2] if index >= 2 else None
        receipts = state.get("gate_receipts")
        gate_receipt = None
        if (
            checkpoint == "POST_USER_GATE"
            and isinstance(predecessor, dict)
            and isinstance(receipts, list)
        ):
            matching_receipts = [
                receipt
                for receipt in receipts
                if isinstance(receipt, dict)
                and receipt.get("gate") == predecessor.get("pending_user_gate")
                and receipt.get("based_on_revision")
                == predecessor.get("revision")
            ]
            if len(matching_receipts) == 1:
                gate_receipt = matching_receipts[0]

        blocking_transition = next(
            (
                prior
                for prior in reversed(transitions[: index - 1])
                if isinstance(prior, dict)
                and prior.get("action") == "BLOCK_SESSION"
                and prior.get("from_status") != "BLOCKED"
                and prior.get("to_status") == "BLOCKED"
            ),
            None,
        )
        blocker_receipt = None
        if isinstance(blocking_transition, dict) and isinstance(receipts, list):
            blocker_matches = [
                receipt
                for receipt in receipts
                if isinstance(receipt, dict)
                and receipt.get("gate") == "BLOCKER_DECISION"
                and receipt.get("based_on_revision")
                == blocking_transition.get("revision")
            ]
            if len(blocker_matches) == 1:
                blocker_receipt = blocker_matches[0]

        def has_prior_accepted_phase(phase: str) -> bool:
            return any(
                packet_id in accepted_packet_ids
                and dispatch.get("phase") == phase
                for packet_id, dispatch in prior_dispatches_before_batch.items()
            )

        def has_delegated_panel_product() -> bool:
            if not isinstance(receipts, list):
                return False
            for prior_index, prior in enumerate(
                transitions[: index - 1]
            ):
                if (
                    prior_index == 0
                    or not isinstance(prior, dict)
                    or prior.get("checkpoint") != "POST_USER_GATE"
                    or not isinstance(prior.get("dispatches"), list)
                ):
                    continue
                hold = transitions[prior_index - 1]
                if (
                    not isinstance(hold, dict)
                    or hold.get("action") != "HOLD_FOR_USER"
                    or hold.get("pending_user_gate")
                    != "DIRECTION_SELECTION"
                ):
                    continue
                if not any(
                    isinstance(receipt, dict)
                    and receipt.get("gate") == "DIRECTION_SELECTION"
                    and receipt.get("action") == "DELEGATE"
                    and receipt.get("based_on_revision")
                    == hold.get("revision")
                    for receipt in receipts
                ):
                    continue
                if any(
                    isinstance(dispatch, dict)
                    and dispatch.get("phase") == "DIRECTION_SELECTION"
                    and dispatch.get("packet_id") in accepted_packet_ids
                    for dispatch in prior["dispatches"]
                ):
                    return True
            return False

        for required_action in required_actions:
            applicable = True
            if required_action == "BUILD_PROJECT_EVIDENCE_PACK":
                applicable = (
                    index == 1
                    and mode != "evaluate"
                    and checkpoint == "SESSION_INIT"
                    and action == "ADVANCE"
                )
            elif required_action == "BUILD_EVALUATION_INPUT_SNAPSHOT":
                applicable = (
                    index == 1
                    and mode == "evaluate"
                    and checkpoint == "SESSION_INIT"
                    and action == "ADVANCE"
                )
            elif required_action == "APPLY_USER_DIRECTION_SELECTION":
                applicable = (
                    action == "ADVANCE"
                    and mode == "discover"
                    and checkpoint == "POST_USER_GATE"
                    and isinstance(gate_receipt, dict)
                    and gate_receipt.get("gate") == "DIRECTION_SELECTION"
                    and gate_receipt.get("action") == "SELECT"
                )
            elif required_action == "APPLY_PANEL_DIRECTION_SELECTION":
                applicable = (
                    action == "ADVANCE"
                    and mode != "evaluate"
                    and checkpoint in {"PHASE_BOUNDARY", "POST_USER_GATE"}
                    and has_prior_accepted_phase("DIRECTION_SELECTION")
                    and (
                        state.get("interaction_mode") == "AUTONOMOUS"
                        or has_delegated_panel_product()
                    )
                )
            elif required_action == "APPLY_CANDIDATE_SELECTION":
                applicable = (
                    action == "ADVANCE"
                    and mode != "evaluate"
                    and checkpoint == "POST_USER_GATE"
                    and isinstance(gate_receipt, dict)
                    and gate_receipt.get("gate") == "CANDIDATE_SELECTION"
                    and gate_receipt.get("action") == "SELECT"
                )
            elif required_action == "APPLY_RQ_CONFIRMATION":
                applicable = (
                    action == "ADVANCE"
                    and mode != "evaluate"
                    and checkpoint == "POST_USER_GATE"
                    and isinstance(gate_receipt, dict)
                    and gate_receipt.get("gate") == "RQ_CONFIRMATION"
                    and gate_receipt.get("action") == "CONFIRM"
                )
            elif required_action == "APPLY_RQ_REVISION":
                applicable = (
                    action == "ADVANCE"
                    and mode != "evaluate"
                    and checkpoint == "POST_USER_GATE"
                    and isinstance(gate_receipt, dict)
                    and gate_receipt.get("gate") == "RQ_CONFIRMATION"
                    and gate_receipt.get("action") == "REVISE"
                )
            elif required_action == "APPLY_EVALUATION_DECISION":
                applicable = (
                    action == "ADVANCE"
                    and mode == "evaluate"
                    and checkpoint == "POST_USER_GATE"
                    and isinstance(gate_receipt, dict)
                    and gate_receipt.get("gate") == "EVALUATION_DECISION"
                    and gate_receipt.get("action") in {"CONFIRM", "OVERRIDE"}
                )
            elif required_action == "APPLY_USER_REPAIR":
                applicable = (
                    action == "ADVANCE"
                    and from_status == "BLOCKED"
                    and isinstance(blocker_receipt, dict)
                    and blocker_receipt.get("action") == "REPAIR"
                )
            elif required_action in {
                "REPAIR_ARTIFACT_METADATA",
                "REPAIR_SESSION_STATE",
            }:
                applicable = (
                    action == "REPAIR_STATE" and checkpoint == "RECOVERY"
                )
            elif required_action == "RECORD_UNRESOLVED_BLOCKER":
                applicable = action == "BLOCK_SESSION"
            if not applicable:
                errors.append(
                    f"{location}.required_action {required_action!r} is not "
                    "applicable to this transition"
                )
        if not reason_codes:
            errors.append(f"{location}.reason_codes must not be empty")
        if "PERSIST_STATE" not in required_checks:
            errors.append(f"{location}.required_checks must include PERSIST_STATE")
        if dispatches:
            for required_check in ("VERIFY_ENVELOPES", "ENFORCE_BUDGET"):
                if required_check not in required_checks:
                    errors.append(
                        f"{location}.required_checks must include "
                        f"{required_check} when dispatches are present"
                    )
        if (
            checkpoint == "POST_USER_GATE"
            and "VERIFY_GATE_RECEIPT" not in required_checks
        ):
            errors.append(
                f"{location}: POST_USER_GATE requires VERIFY_GATE_RECEIPT"
            )
        if not nonempty_string(transition.get("recorded_at")):
            errors.append(f"{location}.recorded_at must be non-empty")

        if action == "HOLD_FOR_USER":
            expected_status = {
                "DIRECTION_SELECTION": "DIRECTION_GATE",
                "CANDIDATE_SELECTION": "USER_GATE",
                "RQ_CONFIRMATION": "RQ_REFINEMENT",
                "EVALUATION_DECISION": "DECISION_GATE",
            }.get(pending_gate if isinstance(pending_gate, str) else None)
            if expected_status is None or to_status != expected_status:
                errors.append(
                    f"{location}: HOLD_FOR_USER has an incompatible gate/status"
                )
            if dispatches:
                errors.append(f"{location}: HOLD_FOR_USER must not dispatch roles")
            if "RUN_SESSION_VALIDATOR" not in required_checks:
                errors.append(
                    f"{location}: HOLD_FOR_USER requires RUN_SESSION_VALIDATOR"
                )
            if pending_gate == "DIRECTION_SELECTION":
                if mode != "discover":
                    errors.append(
                        f"{location}: DIRECTION_SELECTION gate is valid only "
                        "in discover mode"
                    )
                if state.get("interaction_mode") != "GUIDED":
                    errors.append(
                        f"{location}: DIRECTION_SELECTION gate requires GUIDED "
                        "interaction mode"
                    )
            if pending_gate == "RQ_CONFIRMATION":
                selected_candidate_id = state.get("selected_candidate_id")
                latest_rq_packet = None
                unresolved_rq_packets: list[str] = []
                if nonempty_string(selected_candidate_id):
                    (
                        _latest_dispatched_rq,
                        latest_rq_packet,
                        unresolved_rq_packets,
                    ) = historical_rq_resolution(
                        prior_dispatches_before_batch,
                        historical_completed_ids,
                        historical_failed_ids,
                        selected_candidate_id,
                    )
                if unresolved_rq_packets:
                    errors.append(
                        f"{location}: RQ_CONFIRMATION cannot open while an RQ "
                        f"replacement is unresolved {unresolved_rq_packets}"
                    )
                if latest_rq_packet is None:
                    errors.append(
                        f"{location}: RQ_CONFIRMATION requires the latest "
                        "dispatched RQ_REFINEMENT/Research Question Architect "
                        "product to be completed"
                    )
        elif pending_gate is not None:
            errors.append(
                f"{location}: only HOLD_FOR_USER may set pending_user_gate"
            )

        if action == "ADVANCE":
            if (
                isinstance(to_status, str)
                and to_status in GATE_STATUS_REQUIREMENTS
            ):
                errors.append(
                    f"{location}: use HOLD_FOR_USER to enter a user gate"
                )
            if not dispatches and not required_actions:
                errors.append(
                    f"{location}: ADVANCE requires a dispatch or required action"
                )
        elif action == "REPAIR_STATE":
            if from_status != to_status:
                errors.append(
                    f"{location}: REPAIR_STATE must remain in the same status"
                )
            if dispatches or not required_actions:
                errors.append(
                    f"{location}: REPAIR_STATE requires deterministic actions "
                    "and no role dispatch"
                )
            unsupported_repair_actions = sorted(
                set(required_actions)
                - {"REPAIR_ARTIFACT_METADATA", "REPAIR_SESSION_STATE"}
            )
            if unsupported_repair_actions:
                errors.append(
                    f"{location}: REPAIR_STATE contains non-repair actions "
                    f"{unsupported_repair_actions}"
                )
        elif action == "RETRY_ROLE":
            if from_status != to_status:
                errors.append(
                    f"{location}: RETRY_ROLE must remain in the same status"
                )
            if len(dispatches) != 1:
                errors.append(
                    f"{location}: RETRY_ROLE requires exactly one dispatch"
                )
            if (
                not nonempty_string(retry_key)
                or retry_key not in rejected_packet_ids
            ):
                errors.append(
                    f"{location}.retry_key must reference a rejected packet"
                )
            else:
                retry_keys.append(retry_key)
                if retry_counts.get(retry_key) != 1:
                    errors.append(
                        f"{location}.retry_key must have retry_counts value 1"
                    )
                if retry_key in retry_dispatch_packet_ids:
                    errors.append(
                        f"{location}.retry_key references a prior retry packet; "
                        "retry chains are forbidden"
                    )
                original_dispatch = dispatches_by_packet_id.get(retry_key)
                retry_dispatch = (
                    dispatches[0]
                    if len(dispatches) == 1 and isinstance(dispatches[0], dict)
                    else None
                )
                if original_dispatch is None:
                    errors.append(
                        f"{location}.retry_key has no recorded original "
                        "controller dispatch"
                    )
                elif isinstance(retry_dispatch, dict):
                    if retry_dispatch.get("packet_id") == retry_key:
                        errors.append(
                            f"{location}: RETRY_ROLE must use a fresh packet_id"
                        )
                    for field in ("phase", "role", "candidate_id", "round"):
                        if retry_dispatch.get(field) != original_dispatch.get(field):
                            errors.append(
                                f"{location}: RETRY_ROLE dispatch {field} must "
                                "match the original dispatch"
                            )
                rejection = rejected_products.get(retry_key)
                if isinstance(rejection, dict) and isinstance(
                    original_dispatch, dict
                ):
                    for field in ("role", "candidate_id", "round"):
                        if rejection.get(field) != original_dispatch.get(field):
                            errors.append(
                                f"{location}: rejected packet {field} does not "
                                "match its original dispatch"
                            )
                if isinstance(retry_dispatch, dict) and nonempty_string(
                    retry_dispatch.get("packet_id")
                ):
                    retry_dispatch_packet_ids.add(retry_dispatch["packet_id"])
        elif action == "BLOCK_SESSION":
            if to_status != "BLOCKED" or dispatches or not blocking_reasons:
                errors.append(
                    f"{location}: BLOCK_SESSION requires BLOCKED, no dispatch, "
                    "and blocking reasons"
                )
            if from_status == "BLOCKED":
                errors.append(
                    f"{location}: a BLOCKED session cannot append another "
                    "BLOCK_SESSION transition"
                )
        elif action == "COMPLETE":
            if (
                to_status != "COMPLETE"
                or dispatches
                or blocking_reasons
                or pending_gate is not None
            ):
                errors.append(
                    f"{location}: COMPLETE requires a clean COMPLETE target"
                )
            if "RUN_SESSION_VALIDATOR" not in required_checks:
                errors.append(
                    f"{location}: COMPLETE requires RUN_SESSION_VALIDATOR"
                )
            if required_actions:
                errors.append(
                    f"{location}: COMPLETE requires required_actions to be empty"
                )

        if action != "RETRY_ROLE" and retry_key is not None:
            errors.append(f"{location}: retry_key is only valid for RETRY_ROLE")
        if action != "BLOCK_SESSION" and blocking_reasons:
            errors.append(
                f"{location}: blocking_reasons are only valid for BLOCK_SESSION"
            )

        if (
            checkpoint == "POST_USER_GATE"
            and isinstance(gate_receipt, dict)
            and gate_receipt.get("gate") == "RQ_CONFIRMATION"
        ):
            selected_candidate_id = state.get("selected_candidate_id")
            predecessor = transitions[index - 2] if index >= 2 else None
            predecessor_revision = (
                predecessor.get("revision")
                if isinstance(predecessor, dict)
                else None
            )
            hold_snapshot = (
                archived_snapshots_by_revision.get(predecessor_revision)
                if is_int(predecessor_revision)
                else None
            )
            hold_completed_ids = {
                value
                for value in (
                    hold_snapshot.get("completed_packet_ids", [])
                    if isinstance(hold_snapshot, dict)
                    and isinstance(
                        hold_snapshot.get("completed_packet_ids"),
                        list,
                    )
                    else []
                )
                if isinstance(value, str)
            }
            hold_failed_ids = {
                failed.get("packet_id")
                for failed in (
                    hold_snapshot.get("failed_packets", [])
                    if isinstance(hold_snapshot, dict)
                    and isinstance(hold_snapshot.get("failed_packets"), list)
                    else []
                )
                if isinstance(failed, dict)
                and isinstance(failed.get("packet_id"), str)
            }
            if not isinstance(hold_snapshot, dict):
                hold_completed_ids = historical_completed_ids
                hold_failed_ids = historical_failed_ids
            confirmed_packet_id = None
            unresolved_rq_packets: list[str] = []
            if nonempty_string(selected_candidate_id):
                (
                    _latest_dispatched_rq,
                    confirmed_packet_id,
                    unresolved_rq_packets,
                ) = historical_rq_resolution(
                    prior_dispatches_before_batch,
                    hold_completed_ids,
                    hold_failed_ids,
                    selected_candidate_id,
                )
            if unresolved_rq_packets:
                errors.append(
                    f"{location}: RQ confirmation cannot consume a receipt while "
                    f"RQ packets were unresolved at HOLD {unresolved_rq_packets}"
                )
            if gate_receipt.get("action") == "CONFIRM":
                if gate_receipt.get("values") != [
                    selected_candidate_id,
                    confirmed_packet_id,
                ]:
                    errors.append(
                        f"{location}: RQ_CONFIRMATION/CONFIRM values must bind "
                        "the selected candidate and latest accepted RQ packet"
                    )
                if (
                    action != "ADVANCE"
                    or to_status != "RQ_REFINEMENT"
                    or dispatches
                    or required_actions != ["APPLY_RQ_CONFIRMATION"]
                ):
                    errors.append(
                        f"{location}: RQ_CONFIRMATION/CONFIRM requires one "
                        "no-dispatch POST_USER_GATE ADVANCE with exactly "
                        "APPLY_RQ_CONFIRMATION"
                    )
            elif gate_receipt.get("action") == "REVISE":
                rq_dispatches = [
                    dispatch
                    for dispatch in dispatches
                    if isinstance(dispatch, dict)
                    and dispatch.get("phase") == "RQ_REFINEMENT"
                    and dispatch.get("role") == "Research Question Architect"
                ]
                if (
                    action != "ADVANCE"
                    or to_status != "RQ_REFINEMENT"
                    or len(dispatches) != 1
                    or len(rq_dispatches) != 1
                    or required_actions != ["APPLY_RQ_REVISION"]
                ):
                    errors.append(
                        f"{location}: RQ_CONFIRMATION/REVISE requires exactly "
                        "APPLY_RQ_REVISION and one replacement Research Question "
                        "Architect dispatch"
                    )

        product = control_products.get(
            packet_id if isinstance(packet_id, str) else None
        )
        if product is None:
            errors.append(
                f"{location}.packet_id has no accepted CONTROL work product"
            )
        else:
            if product.get("control_revision") != observed_revision:
                errors.append(
                    f"{location}: CONTROL product control_revision does not "
                    "match observed_revision"
                )
            if product.get("state_digest") != digest:
                errors.append(
                    f"{location}: CONTROL product state_digest does not match "
                    "observed_state_digest"
                )
            if product.get("control_input_digest") != control_input_digest:
                errors.append(
                    f"{location}: CONTROL product control_input_digest does not "
                    "match the transition"
                )

    for transition_index, transition in enumerate(transitions):
        if (
            not isinstance(transition, dict)
            or transition.get("required_actions")
            != ["APPLY_RQ_CONFIRMATION"]
        ):
            continue
        if transition.get("dispatches"):
            errors.append(
                "mainline_control: APPLY_RQ_CONFIRMATION transition must not "
                "dispatch roles"
            )
        if transition_index + 1 >= len(transitions):
            continue
        successor = transitions[transition_index + 1]
        if not (
            isinstance(successor, dict)
            and successor.get("action") == "COMPLETE"
            and successor.get("checkpoint") == "PRE_COMPLETE"
            and successor.get("to_status") == "COMPLETE"
        ):
            errors.append(
                "mainline_control: the transition after "
                "APPLY_RQ_CONFIRMATION must be PRE_COMPLETE/COMPLETE"
            )

    duplicate_transition_packets = duplicate_values(transition_packet_ids)
    if duplicate_transition_packets:
        errors.append(
            "mainline_control.transition_log contains duplicate packet IDs "
            f"{duplicate_transition_packets}"
        )
    duplicate_dispatch_packets = duplicate_values(dispatch_packet_ids)
    if duplicate_dispatch_packets:
        errors.append(
            "mainline_control.transition_log reuses dispatch packet IDs "
            f"{duplicate_dispatch_packets}"
        )
    reused_control_ids = set(dispatch_packet_ids) & set(transition_packet_ids)
    if reused_control_ids:
        errors.append(
            "mainline_control dispatch packet IDs must differ from CONTROL "
            f"packet IDs {sorted(reused_control_ids)}"
        )
    accepted_research_packet_ids = {
        product.get("packet_id")
        for product in accepted_products
        if product.get("phase") != "CONTROL"
        and nonempty_string(product.get("packet_id"))
    }
    rejected_research_packet_ids = {
        packet_id
        for packet_id, rejection in rejected_products.items()
        if not isinstance(rejection.get("role"), str)
        or rejection.get("role")
        not in {"Mainline Workflow Controller", "Deterministic Mainline Fallback"}
    }
    for request_index, request in enumerate(lane_search_requests):
        location = (
            f"mainline_control.lane_search_requests[{request_index}]"
        )
        source_packet_id = request.get("source_packet_id")
        safe_source_packet_id = (
            source_packet_id if isinstance(source_packet_id, str) else None
        )
        source_dispatch = dispatches_by_packet_id.get(safe_source_packet_id)
        if (
            safe_source_packet_id not in accepted_research_packet_ids
            or not isinstance(source_dispatch, dict)
        ):
            errors.append(
                f"{location}.source_packet_id must name an accepted committed "
                "dispatch"
            )
            continue
        expected_source = {
            "phase": request.get("phase"),
            "role": "Devil's Advocate",
            "candidate_id": request.get("candidate_id"),
            "round": request.get("round"),
        }
        if any(
            source_dispatch.get(field) != expected
            for field, expected in expected_source.items()
        ):
            errors.append(
                f"{location}.source_packet_id must name the accepted same-lane "
                "Devil's Advocate packet"
            )
    for product in accepted_products:
        packet_id = product.get("packet_id")
        if product.get("phase") == "CONTROL" or not nonempty_string(packet_id):
            continue
        original_dispatch = dispatches_by_packet_id.get(packet_id)
        if not isinstance(original_dispatch, dict):
            continue
        for field in ("phase", "role", "candidate_id", "round"):
            if product.get(field) != original_dispatch.get(field):
                errors.append(
                    f"accepted work product {packet_id!r} field {field} does "
                    "not match its controller dispatch"
                )
    for packet_id, rejection in rejected_products.items():
        if packet_id not in rejected_research_packet_ids:
            continue
        original_dispatch = dispatches_by_packet_id.get(packet_id)
        if not isinstance(original_dispatch, dict):
            continue
        for field in ("role", "candidate_id", "round"):
            if rejection.get(field) != original_dispatch.get(field):
                errors.append(
                    f"rejected work product {packet_id!r} field {field} does "
                    "not match its controller dispatch"
                )
    accepted_rejected_overlap = (
        accepted_research_packet_ids & rejected_research_packet_ids
    )
    if accepted_rejected_overlap:
        errors.append(
            "research packet IDs cannot be both accepted and rejected "
            f"{sorted(accepted_rejected_overlap)}"
        )
    orphan_resolved_packets = (
        accepted_research_packet_ids | rejected_research_packet_ids
    ) - set(dispatch_packet_ids)
    if orphan_resolved_packets:
        errors.append(
            "accepted or rejected research packets must originate from a "
            "committed controller dispatch "
            f"{sorted(orphan_resolved_packets)}"
        )
    duplicate_retry_keys = duplicate_values(retry_keys)
    if duplicate_retry_keys:
        errors.append(
            "mainline_control retries the same rejected packet more than once "
            f"{duplicate_retry_keys}"
        )
    if set(retry_counts) != set(retry_keys):
        errors.append(
            "mainline_control.retry_counts must exactly match committed "
            "RETRY_ROLE retry keys"
        )

    transition_packet_set = set(transition_packet_ids)
    control_packet_set = set(control_products)
    if transition_packet_set != control_packet_set:
        errors.append(
            "mainline_control transition packets and accepted CONTROL packets "
            "must match one-to-one"
        )

    last = transitions[-1]
    if not isinstance(last, dict):
        # The per-transition loop above already reported the malformed entry.
        return
    if control.get("last_checkpoint") != last.get("checkpoint"):
        errors.append(
            "mainline_control.last_checkpoint must match the last transition"
        )
    if control.get("pending_user_gate") != last.get("pending_user_gate"):
        errors.append(
            "mainline_control.pending_user_gate must match the last transition"
        )
    if control.get("last_controller_packet_id") != last.get("packet_id"):
        errors.append(
            "mainline_control.last_controller_packet_id must match the last "
            "transition"
        )
    if state.get("status") != last.get("to_status"):
        errors.append(
            "session-state.json: status must match the last control transition"
        )

    last_packet_id = last.get("packet_id")
    last_product = control_products.get(
        last_packet_id if isinstance(last_packet_id, str) else None
    )
    expected_last_role = (
        "Mainline Workflow Controller"
        if controller_status == "ACTIVE"
        else "Deterministic Mainline Fallback"
    )
    if isinstance(last_product, dict) and last_product.get("role") != expected_last_role:
        errors.append(
            "mainline_control.controller_status does not match the last "
            "CONTROL role"
        )

    status = state.get("status")
    expected_gate = GATE_STATUS_REQUIREMENTS.get(
        status if isinstance(status, str) else None
    )
    if expected_gate is not None and (
        last.get("action") != "HOLD_FOR_USER"
        or last.get("pending_user_gate") != expected_gate
    ):
        errors.append(
            f"mainline_control: {status} requires HOLD_FOR_USER with "
            f"{expected_gate}"
        )
    if status == "COMPLETE" and last.get("action") != "COMPLETE":
        errors.append(
            "mainline_control: COMPLETE status requires a COMPLETE directive"
        )
    if status == "BLOCKED" and last.get("action") != "BLOCK_SESSION":
        errors.append(
            "mainline_control: BLOCKED status requires a BLOCK_SESSION directive"
        )


def validate_gate_receipts(state: dict[str, Any], errors: list[str]) -> None:
    if state.get("schema_version") != "1.3":
        return

    receipts = state.get("gate_receipts")
    if not isinstance(receipts, list):
        errors.append("session-state.json: gate_receipts must be an array")
        return

    control = state.get("mainline_control")
    transitions = (
        control.get("transition_log")
        if isinstance(control, dict)
        and isinstance(control.get("transition_log"), list)
        else []
    )
    transitions_by_revision = {
        transition.get("revision"): transition
        for transition in transitions
        if isinstance(transition, dict) and is_int(transition.get("revision"))
    }
    fields = (
        "receipt_id",
        "gate",
        "action",
        "values",
        "based_on_revision",
        "received_at",
    )
    receipt_ids: list[str] = []
    parsed: list[dict[str, Any]] = []

    for index, receipt in enumerate(receipts):
        location = f"gate_receipts[{index}]"
        if not require_keys(receipt, fields, location, errors):
            continue
        receipt_id = receipt.get("receipt_id")
        gate = receipt.get("gate")
        action = receipt.get("action")
        based_on_revision = receipt.get("based_on_revision")
        if not nonempty_string(receipt_id) or not SAFE_ID.fullmatch(receipt_id):
            errors.append(f"{location}.receipt_id is invalid")
        else:
            receipt_ids.append(receipt_id)
        if (
            not isinstance(gate, str)
            or gate not in GATE_RECEIPT_ACTIONS
        ):
            errors.append(
                f"{location}.gate must be one of "
                f"{sorted(GATE_RECEIPT_ACTIONS)}"
            )
        elif (
            not isinstance(action, str)
            or action not in GATE_RECEIPT_ACTIONS[gate]
        ):
            errors.append(
                f"{location}.action must be one of "
                f"{sorted(GATE_RECEIPT_ACTIONS[gate])}"
            )
        values = validate_string_array(
            receipt.get("values"), f"{location}.values", errors
        )
        if not is_int(based_on_revision) or based_on_revision < 1:
            errors.append(
                f"{location}.based_on_revision must be a positive integer"
            )
        else:
            held = transitions_by_revision.get(based_on_revision)
            matching_transition = (
                isinstance(held, dict)
                and (
                    (
                        gate == "BLOCKER_DECISION"
                        and held.get("action") == "BLOCK_SESSION"
                        and held.get("to_status") == "BLOCKED"
                    )
                    or (
                        gate != "BLOCKER_DECISION"
                        and held.get("action") == "HOLD_FOR_USER"
                        and held.get("pending_user_gate") == gate
                    )
                )
            )
            if not matching_transition:
                errors.append(
                    f"{location}.based_on_revision must reference a matching "
                    "user boundary transition"
                )
            elif gate == "BLOCKER_DECISION" and held.get("from_status") == "BLOCKED":
                errors.append(
                    f"{location}.based_on_revision must reference the "
                    "BLOCK_SESSION transition that began the blocking episode"
                )
        if not nonempty_string(receipt.get("received_at")):
            errors.append(f"{location}.received_at must be non-empty")

        if gate == "DIRECTION_SELECTION" and action == "SELECT":
            if not 1 <= len(values) <= 2:
                errors.append(
                    f"{location}.values must contain one or two direction IDs"
                )
        elif gate == "CANDIDATE_SELECTION" and action == "SELECT":
            if len(values) != 1:
                errors.append(
                    f"{location}.values must contain one candidate ID"
                )
        elif gate == "RQ_CONFIRMATION" and action == "CONFIRM":
            selected_candidate_id = state.get("selected_candidate_id")
            accepted_packet_ids = {
                product.get("packet_id")
                for product in state.get("accepted_work_products", [])
                if isinstance(product, dict)
                and product.get("phase") != "CONTROL"
                and nonempty_string(product.get("packet_id"))
            }
            confirmed_packet_id = next(
                (
                    dispatch.get("packet_id")
                    for prior in reversed(transitions)
                    if isinstance(prior, dict)
                    and is_int(prior.get("revision"))
                    and is_int(based_on_revision)
                    and prior.get("revision") < based_on_revision
                    and isinstance(prior.get("dispatches"), list)
                    for dispatch in reversed(prior["dispatches"])
                    if isinstance(dispatch, dict)
                    and dispatch.get("packet_id") in accepted_packet_ids
                    and dispatch.get("phase") == "RQ_REFINEMENT"
                    and dispatch.get("role") == "Research Question Architect"
                    and dispatch.get("candidate_id") == selected_candidate_id
                    and dispatch.get("round") is None
                ),
                None,
            )
            if values != [selected_candidate_id, confirmed_packet_id]:
                errors.append(
                    f"{location}.values must contain the selected candidate ID "
                    "and the exact accepted RQ packet shown to the user"
                )
        elif gate == "EVALUATION_DECISION" and action in {"CONFIRM", "OVERRIDE"}:
            if len(values) != 1 or values[0] not in EVALUATION_DECISIONS:
                errors.append(
                    f"{location}.values must contain one evaluation decision"
                )
        elif gate == "BLOCKER_DECISION" and action == "REPAIR":
            held = transitions_by_revision.get(based_on_revision)
            resume_status = (
                held.get("from_status") if isinstance(held, dict) else None
            )
            if values != [resume_status]:
                errors.append(
                    f"{location}.values must contain the blocked transition's "
                    "from_status"
                )
        elif values:
            errors.append(f"{location}.values must be empty for action {action!r}")

        if isinstance(receipt, dict):
            parsed.append(receipt)

    duplicates = duplicate_values(receipt_ids)
    if duplicates:
        errors.append(
            f"session-state.json: duplicate gate receipt IDs {duplicates}"
        )
    receipt_keys = [
        (receipt.get("gate"), receipt.get("based_on_revision"))
        for receipt in parsed
    ]
    duplicate_receipts = duplicate_values(receipt_keys)
    if duplicate_receipts:
        errors.append(
            "session-state.json: multiple receipts reference the same gate "
            f"transition {duplicate_receipts}"
        )

    receipts_by_boundary = {
        (receipt.get("gate"), receipt.get("based_on_revision")): receipt
        for receipt in parsed
        if isinstance(receipt.get("gate"), str)
        and receipt.get("gate") in PENDING_USER_GATES
        and is_int(receipt.get("based_on_revision"))
    }
    for index, held in enumerate(transitions[:-1]):
        if (
            not isinstance(held, dict)
            or held.get("action") != "HOLD_FOR_USER"
            or not isinstance(held.get("pending_user_gate"), str)
            or held.get("pending_user_gate") not in PENDING_USER_GATES
        ):
            continue
        successor = transitions[index + 1]
        if not isinstance(successor, dict):
            continue
        if successor.get("action") == "HOLD_FOR_USER":
            errors.append(
                f"mainline_control: unresolved {held['pending_user_gate']} gate "
                "must not append another HOLD_FOR_USER"
            )
            continue
        if successor.get("action") == "BLOCK_SESSION":
            continue
        gate = held["pending_user_gate"]
        receipt = receipts_by_boundary.get((gate, held.get("revision")))
        if not isinstance(receipt, dict):
            errors.append(
                f"gate_receipts: transition after {gate} revision "
                f"{held.get('revision')!r} requires a direct user receipt"
            )
            continue
        allowed_targets = RECEIPT_TARGETS.get(
            (gate, receipt.get("action")),
            set(),
        )
        if successor.get("to_status") not in allowed_targets:
            errors.append(
                f"gate_receipts: {gate}/{receipt.get('action')} does not permit "
                f"target status {successor.get('to_status')!r}"
            )
        if successor.get("checkpoint") != "POST_USER_GATE":
            errors.append(
                f"mainline_control: leaving {gate} requires checkpoint "
                "POST_USER_GATE"
            )

    blocker_receipts = {
        receipt.get("based_on_revision"): receipt
        for receipt in parsed
        if receipt.get("gate") == "BLOCKER_DECISION"
        and is_int(receipt.get("based_on_revision"))
    }
    active_block: dict[str, Any] | None = None
    active_block_resume_gate: str | None = None
    for transition_index, transition in enumerate(transitions):
        if not isinstance(transition, dict):
            continue
        if (
            transition.get("action") == "BLOCK_SESSION"
            and transition.get("to_status") == "BLOCKED"
            and transition.get("from_status") != "BLOCKED"
        ):
            active_block = transition
            resume_status = transition.get("from_status")
            active_block_resume_gate = GATE_STATUS_REQUIREMENTS.get(resume_status)
            if active_block_resume_gate is None and transition_index >= 1:
                predecessor = transitions[transition_index - 1]
                if (
                    isinstance(predecessor, dict)
                    and predecessor.get("action") == "HOLD_FOR_USER"
                    and predecessor.get("to_status") == resume_status
                    and isinstance(
                        predecessor.get("pending_user_gate"),
                        str,
                    )
                    and predecessor.get("pending_user_gate") in PENDING_USER_GATES
                ):
                    active_block_resume_gate = predecessor.get(
                        "pending_user_gate"
                    )
            continue
        if (
            transition.get("from_status") == "BLOCKED"
            and transition.get("to_status") != "BLOCKED"
        ):
            block_revision = (
                active_block.get("revision")
                if isinstance(active_block, dict)
                else None
            )
            receipt = blocker_receipts.get(block_revision)
            resume_status = (
                active_block.get("from_status")
                if isinstance(active_block, dict)
                else None
            )
            if (
                not isinstance(receipt, dict)
                or receipt.get("action") != "REPAIR"
                or receipt.get("values") != [resume_status]
            ):
                errors.append(
                    "gate_receipts: leaving BLOCKED requires a matching "
                    "BLOCKER_DECISION/REPAIR receipt"
                )
            correct_resume_action = (
                transition.get("action") == "ADVANCE"
                if active_block_resume_gate is None
                else (
                    transition.get("action") == "HOLD_FOR_USER"
                    and transition.get("pending_user_gate")
                    == active_block_resume_gate
                )
            )
            if (
                not correct_resume_action
                or transition.get("to_status") != resume_status
                or transition.get("checkpoint") not in {"RECOVERY", "RESUME"}
            ):
                errors.append(
                    "mainline_control: leaving BLOCKED must restore the status "
                    "and any user gate that began the blocking episode at "
                    "RECOVERY or RESUME"
                )
            active_block = None
            active_block_resume_gate = None

    def latest_receipt(gate: str) -> dict[str, Any] | None:
        matches = [
            receipt
            for receipt in parsed
            if receipt.get("gate") == gate
            and is_int(receipt.get("based_on_revision"))
        ]
        return (
            max(matches, key=lambda receipt: receipt["based_on_revision"])
            if matches
            else None
        )

    selection = state.get("direction_selection")
    selected_directions = state.get("selected_macro_direction_ids")
    if isinstance(selection, dict) and isinstance(selected_directions, list):
        selected_by = selection.get("selected_by")
        direction_receipt = latest_receipt("DIRECTION_SELECTION")
        if selected_by == "USER":
            selected_values = [
                value for value in selected_directions if nonempty_string(value)
            ]
            receipt_values = (
                [
                    value
                    for value in direction_receipt.get("values", [])
                    if nonempty_string(value)
                ]
                if isinstance(direction_receipt, dict)
                and isinstance(direction_receipt.get("values"), list)
                else []
            )
            if (
                not isinstance(direction_receipt, dict)
                or direction_receipt.get("action") != "SELECT"
                or sorted(receipt_values) != sorted(selected_values)
            ):
                errors.append(
                    "gate_receipts: USER direction selection requires a matching "
                    "SELECT receipt"
                )
        elif selected_by == "PANEL_DELEGATED":
            if (
                not isinstance(direction_receipt, dict)
                or direction_receipt.get("action") != "DELEGATE"
            ):
                errors.append(
                    "gate_receipts: PANEL_DELEGATED direction selection requires "
                    "a DELEGATE receipt"
                )

    selected_candidate = state.get("selected_candidate_id")
    if nonempty_string(selected_candidate):
        candidate_receipt = latest_receipt("CANDIDATE_SELECTION")
        if (
            not isinstance(candidate_receipt, dict)
            or candidate_receipt.get("action") != "SELECT"
            or candidate_receipt.get("values") != [selected_candidate]
        ):
            errors.append(
                "gate_receipts: selected_candidate_id requires a matching "
                "candidate SELECT receipt"
            )

    if state.get("mode") != "evaluate" and state.get("status") == "COMPLETE":
        rq_receipt = latest_receipt("RQ_CONFIRMATION")
        confirmed_packet_id = (
            rq_receipt.get("values", [None, None])[1]
            if isinstance(rq_receipt, dict)
            and isinstance(rq_receipt.get("values"), list)
            and len(rq_receipt.get("values")) == 2
            else None
        )
        accepted_rq_packet = any(
            isinstance(product, dict)
            and product.get("packet_id") == confirmed_packet_id
            and product.get("phase") == "RQ_REFINEMENT"
            and product.get("role") == "Research Question Architect"
            and product.get("candidate_id") == selected_candidate
            for product in state.get("accepted_work_products", [])
        )
        if (
            not isinstance(rq_receipt, dict)
            or rq_receipt.get("action") != "CONFIRM"
            or not isinstance(rq_receipt.get("values"), list)
            or len(rq_receipt.get("values")) != 2
            or rq_receipt.get("values", [None])[0] != selected_candidate
            or not accepted_rq_packet
        ):
            errors.append(
                "gate_receipts: discovery COMPLETE requires an RQ CONFIRM receipt "
                "bound to the selected candidate and accepted RQ packet"
            )

    if state.get("mode") == "evaluate" and state.get("status") in {
        "NEXT_EXPERIMENT",
        "COMPLETE",
    }:
        evaluation_receipt = latest_receipt("EVALUATION_DECISION")
        decision = state.get("evaluation_decision")
        verdict = decision.get("verdict") if isinstance(decision, dict) else None
        if (
            not isinstance(evaluation_receipt, dict)
            or evaluation_receipt.get("action") not in {"CONFIRM", "OVERRIDE"}
            or evaluation_receipt.get("values") != [verdict]
        ):
            errors.append(
                "gate_receipts: evaluation progression requires a matching "
                "decision receipt"
            )


def validate_confidence_values(
    value: Any,
    location: str,
    errors: list[str],
) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            child_location = f"{location}.{key}" if location else key
            if key == "confidence" and child not in CONFIDENCE_LEVELS:
                errors.append(
                    f"{child_location} must be ordinal low, medium, or high"
                )
            validate_confidence_values(child, child_location, errors)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            validate_confidence_values(child, f"{location}[{index}]", errors)


def validate_state(session_dir: Path, state: Any, errors: list[str]) -> None:
    top_level = (
        "schema_version",
        "session_id",
        "mode",
        "interaction_mode",
        "execution_mode",
        "project_root",
        "project_snapshot",
        "status",
        "min_rounds",
        "default_rounds",
        "max_rounds",
        "macro_directions",
        "selected_macro_direction_ids",
        "direction_selection",
        "generated_candidate_ids",
        "initial_debate_candidate_ids",
        "user_gate_candidate_ids",
        "selected_candidate_id",
        "candidates",
        "source_ledger",
        "search_budget",
        "accepted_work_products",
        "rejected_work_products",
        "user_required",
        "updated_at",
    )
    if not require_keys(state, top_level, "session-state.json", errors):
        return

    schema_version = state.get("schema_version")
    if schema_version not in {"1.1", "1.2", "1.3"}:
        errors.append(
            "session-state.json: schema_version must be 1.1, 1.2, or 1.3"
        )
    session_id = state.get("session_id")
    if not nonempty_string(session_id) or not SAFE_ID.fullmatch(session_id):
        errors.append("session-state.json: session_id is invalid")
        session_id = ""
    elif session_dir.name != session_id:
        errors.append(
            f"session-state.json: session_id {session_id!r} must match "
            f"directory name {session_dir.name!r}"
        )

    mode = state.get("mode")
    if mode not in {"discover", "refine", "rq-only", "evaluate"}:
        errors.append(
            "session-state.json: mode must be discover, refine, rq-only, or evaluate"
        )
    if mode == "evaluate" and schema_version not in {"1.2", "1.3"}:
        errors.append(
            "session-state.json: evaluate mode requires schema_version 1.2 or 1.3"
        )
    if schema_version == "1.3":
        require_keys(
            state,
            ("mainline_control", "gate_receipts"),
            "session-state.json",
            errors,
        )
    if mode == "evaluate":
        require_keys(
            state,
            (
                "evaluation_target",
                "experiment_inventory",
                "claim_evidence_matrix",
                "evaluation_rounds",
                "evaluation_decision",
                "next_experiment",
            ),
            "session-state.json",
            errors,
        )
    interaction_mode = state.get("interaction_mode")
    if (
        not isinstance(interaction_mode, str)
        or interaction_mode not in INTERACTION_MODES
    ):
        errors.append(
            f"session-state.json: interaction_mode must be one of "
            f"{sorted(INTERACTION_MODES)}"
        )
    execution_mode = state.get("execution_mode")
    if (
        not isinstance(execution_mode, str)
        or execution_mode not in EXECUTION_MODES
    ):
        errors.append(
            f"session-state.json: execution_mode must be one of "
            f"{sorted(EXECUTION_MODES)}"
        )
    project_root = state.get("project_root")
    if not nonempty_string(project_root) or not Path(project_root).is_absolute():
        errors.append("session-state.json: project_root must be an absolute path")
    if not nonempty_string(state.get("project_snapshot")):
        errors.append("session-state.json: project_snapshot must be non-empty")

    status = state.get("status")
    if not isinstance(status, str) or status not in SESSION_STATUSES:
        errors.append(
            f"session-state.json: status must be one of {sorted(SESSION_STATUSES)}"
        )
        status = ""
    elif mode == "evaluate" and status not in EVALUATION_STATUSES:
        errors.append(
            "session-state.json: evaluate mode must use an evaluation status"
        )
    elif mode != "evaluate" and status not in DISCOVERY_STATUSES:
        errors.append(
            "session-state.json: discover/refine/rq-only mode must use a discovery status"
        )

    for key, expected in (
        ("min_rounds", 3),
        ("default_rounds", 4),
        ("max_rounds", 6),
    ):
        if not is_int(state.get(key)) or state.get(key) != expected:
            errors.append(
                f"session-state.json: {key} must equal the integer {expected}"
            )

    if not isinstance(state.get("user_required"), list):
        errors.append("session-state.json: user_required must be an array")
    elif not all(nonempty_string(value) for value in state.get("user_required")):
        errors.append(
            "session-state.json: user_required must contain non-empty string codes"
        )
    if not nonempty_string(state.get("updated_at")):
        errors.append("session-state.json: updated_at is required")

    validate_macro_directions(state, errors)
    validate_candidates(state, errors)
    validate_evaluation_state(state, errors)
    validate_source_ledger(state, errors)
    validate_search_budget(state, errors)
    validate_accepted_work_products(state, errors)
    validate_rejections(state, errors)
    validate_mainline_control(state, errors, session_dir)
    validate_gate_receipts(state, errors)
    validate_confidence_values(state, "", errors)
    if session_id and status:
        validate_artifacts(session_dir, session_id, status, mode, errors)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate a hotspot-to-rq research-direction session."
    )
    parser.add_argument(
        "session_directory",
        type=Path,
        help="Path to reports/research-direction/<session-id>",
    )
    args = parser.parse_args()
    session_dir = args.session_directory.expanduser().resolve()
    errors: list[str] = []

    if not session_dir.is_dir():
        print(f"Session validation failed: directory not found: {session_dir}")
        return 1

    state_path = session_dir / "session-state.json"
    if not state_path.is_file():
        print(f"Session validation failed: missing {state_path}")
        return 1
    try:
        raw_state = state_path.read_bytes()
    except OSError as exc:
        print(f"Session validation failed: cannot parse {state_path}: {exc}")
        return 1
    parse_errors: list[str] = []
    state = parse_strict_json_bytes(raw_state, "session-state.json", parse_errors)
    if parse_errors or not isinstance(state, dict):
        detail = parse_errors[0] if parse_errors else "top-level value must be an object"
        print(f"Session validation failed: cannot parse {state_path}: {detail}")
        return 1

    validate_state(session_dir, state, errors)
    if errors:
        print(f"Session validation failed with {len(errors)} error(s):")
        for error in errors:
            print(f"- {error}")
        return 1

    if state["mode"] == "evaluate":
        print(
            "Session validation passed: "
            f"{state['session_id']} "
            f"({state['status']}, {len(state['experiment_inventory'])} experiments, "
            f"{len(state['evaluation_rounds'])} evaluation rounds, "
            f"{len(state['source_ledger'])} sources)"
        )
    else:
        print(
            "Session validation passed: "
            f"{state['session_id']} "
            f"({state['status']}, {len(state['macro_directions'])} macro directions, "
            f"{len(state['candidates'])} candidates, "
            f"{len(state['source_ledger'])} sources)"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
