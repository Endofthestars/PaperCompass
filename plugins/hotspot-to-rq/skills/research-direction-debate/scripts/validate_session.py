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
CORE_ROUND_ROLES = {
    "Socratic Mentor",
    "Evidence Researcher",
    "Devil's Advocate",
    "Panel Judge",
}
SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
HEADER = re.compile(
    r"\A---[ \t]*\r?\n(?P<body>.*?)\r?\n---[ \t]*(?:\r?\n|\Z)",
    re.DOTALL,
)
TEN_MIB = 10 * 1024 * 1024


def is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def nonempty_string(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def duplicate_values(values: list[Any]) -> list[Any]:
    seen: set[Any] = set()
    duplicates: list[Any] = []
    for value in values:
        if value in seen and value not in duplicates:
            duplicates.append(value)
        seen.add(value)
    return duplicates


def require_keys(
    value: Any,
    keys: tuple[str, ...],
    location: str,
    errors: list[str],
) -> bool:
    if not isinstance(value, dict):
        errors.append(f"{location} must be an object")
        return False
    for key in keys:
        if key not in value:
            errors.append(f"{location}.{key} is required")
    return True


def parse_markdown_header(path: Path, errors: list[str]) -> dict[str, str] | None:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
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
            if round_record.get("round") != round_index:
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
            last_verdict = rounds[-1].get("verdict") if rounds else None
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
            if isinstance(parent_rounds, list) and parent_rounds
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
        audit = candidate.get("identification_audit")
        if audit is None:
            errors.append(
                f"candidate {candidate_id!r}: identification_audit is required"
            )

    selected = state.get("selected_candidate_id")
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
        for key in ("direction", "primary_claim", "study_type"):
            if not nonempty_string(target.get(key)):
                errors.append(f"evaluation_target.{key} must be non-empty")
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
        if round_record.get("round") != index:
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
        if rejection.get("reason_code") not in REJECTION_CODES:
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
        if phase not in PHASE_ROLES:
            errors.append(f"{location}.phase must be one of {sorted(PHASE_ROLES)}")
        elif role not in PHASE_ROLES[phase]:
            errors.append(
                f"{location}.role {role!r} is not allowed in phase {phase!r}"
            )
        if not nonempty_string(role):
            errors.append(f"{location}.role must be non-empty")

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

        if phase in {
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
        elif phase in {"IDENTIFICATION", "RQ_REFINEMENT"}:
            if candidate_id is None or round_number is not None:
                errors.append(
                    f"{location}: {phase} requires candidate_id and a null round"
                )

        if not isinstance(fingerprint, str) or not re.fullmatch(
            r"[0-9a-f]{64}", fingerprint
        ):
            errors.append(
                f"{location}.context_fingerprint must be a lowercase SHA-256 digest"
            )
        elif fingerprint != expected_context_fingerprint(product):
            errors.append(
                f"{location}.context_fingerprint does not match its identity fields"
            )

        if phase in PHASE_ROLES and isinstance(role, str):
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
    if schema_version not in {"1.1", "1.2"}:
        errors.append("session-state.json: schema_version must be 1.1 or 1.2")
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
    if mode == "evaluate" and schema_version != "1.2":
        errors.append("session-state.json: evaluate mode requires schema_version 1.2")
    if state.get("interaction_mode") not in INTERACTION_MODES:
        errors.append(
            f"session-state.json: interaction_mode must be one of "
            f"{sorted(INTERACTION_MODES)}"
        )
    if state.get("execution_mode") not in EXECUTION_MODES:
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
    if status not in SESSION_STATUSES:
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
        if state.get(key) != expected:
            errors.append(f"session-state.json: {key} must equal {expected}")

    if not isinstance(state.get("user_required"), list):
        errors.append("session-state.json: user_required must be an array")
    if not nonempty_string(state.get("updated_at")):
        errors.append("session-state.json: updated_at is required")

    validate_macro_directions(state, errors)
    validate_candidates(state, errors)
    validate_evaluation_state(state, errors)
    validate_source_ledger(state, errors)
    validate_search_budget(state, errors)
    validate_accepted_work_products(state, errors)
    validate_rejections(state, errors)
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
        state = json.loads(state_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        print(f"Session validation failed: cannot parse {state_path}: {exc}")
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
