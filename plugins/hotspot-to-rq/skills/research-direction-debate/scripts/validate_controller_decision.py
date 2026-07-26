#!/usr/bin/env python3
"""Validate one Mainline Workflow Controller directive against live session state."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any


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
DISCOVERY_PHASES = {
    "DIRECTION_MAPPING",
    "DIRECTION_SELECTION",
    "HOTSPOT",
    "SCREENING",
    "DEBATE",
    "IDENTIFICATION",
    "FINAL_SELECTION",
    "RQ_REFINEMENT",
}
EVALUATION_PHASES = {
    "EVIDENCE_INTAKE",
    "RESULT_VALIDATION",
    "EXTERNAL_POSITIONING",
    "EVALUATION_DEBATE",
    "EVALUATION_DECISION",
    "NEXT_EXPERIMENT",
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
NULL_COORDINATE_PHASES = {
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
CANDIDATE_ONLY_PHASES = {"IDENTIFICATION", "RQ_REFINEMENT"}
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
PENDING_USER_GATES = {
    "DIRECTION_SELECTION",
    "CANDIDATE_SELECTION",
    "RQ_CONFIRMATION",
    "EVALUATION_DECISION",
}
GATE_TARGETS = {
    "DIRECTION_SELECTION": "DIRECTION_GATE",
    "CANDIDATE_SELECTION": "USER_GATE",
    "RQ_CONFIRMATION": "RQ_REFINEMENT",
    "EVALUATION_DECISION": "DECISION_GATE",
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
ENVELOPE_KEYS = {
    "schema_version",
    "session_id",
    "project_root",
    "project_snapshot",
    "phase",
    "role",
    "candidate_id",
    "round",
    "packet_id",
    "control_revision",
    "state_digest",
    "control_input_digest",
    "context_fingerprint",
    "allowed_artifacts",
}
CONTROL_INPUT_KEYS = {
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
DIRECTIVE_KEYS = {
    "observed_revision",
    "observed_state_digest",
    "observed_status",
    "checkpoint",
    "action",
    "target_status",
    "pending_user_gate",
    "dispatches",
    "required_actions",
    "required_checks",
    "reason_codes",
    "blocking_reasons",
    "retry_key",
}
DISPATCH_KEYS = {
    "packet_id",
    "phase",
    "role",
    "candidate_id",
    "round",
    "depends_on_packet_ids",
}
SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
CODE = re.compile(r"^[A-Z][A-Z0-9_]*$")
SHA256 = re.compile(r"^[0-9a-f]{64}$")


class StrictJSONError(ValueError):
    """Raised when JSON violates the strict parsing contract."""


def is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def nonempty_string(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def key_component(value: Any) -> Any:
    if value is None or isinstance(value, str) or is_int(value):
        return value
    return f"<INVALID_{type(value).__name__.upper()}>"


def strict_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise StrictJSONError(f"duplicate object key {key!r}")
        result[key] = value
    return result


def reject_nonfinite(value: str) -> Any:
    raise StrictJSONError(f"non-finite number {value!r} is not valid strict JSON")


def parse_json_bytes(raw: bytes, label: str, errors: list[str]) -> Any | None:
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        errors.append(f"{label}: file is not valid UTF-8: {exc}")
        return None
    try:
        return json.loads(
            text,
            object_pairs_hook=strict_object,
            parse_constant=reject_nonfinite,
        )
    except (json.JSONDecodeError, StrictJSONError) as exc:
        errors.append(f"{label}: invalid strict JSON: {exc}")
        return None


def read_file(path: Path, label: str, errors: list[str]) -> bytes | None:
    try:
        return path.read_bytes()
    except OSError as exc:
        errors.append(f"{label}: cannot read {path}: {exc}")
        return None


def require_exact_keys(
    value: Any,
    expected: set[str],
    location: str,
    errors: list[str],
) -> bool:
    if not isinstance(value, dict):
        errors.append(f"{location} must be an object")
        return False
    actual = set(value)
    missing = sorted(expected - actual)
    unknown = sorted(actual - expected)
    if missing:
        errors.append(f"{location}: missing keys {missing}")
    if unknown:
        errors.append(f"{location}: unknown keys {unknown}")
    return not missing and not unknown


def require_keys(
    value: Any,
    expected: tuple[str, ...],
    location: str,
    errors: list[str],
) -> bool:
    if not isinstance(value, dict):
        errors.append(f"{location} must be an object")
        return False
    missing = [key for key in expected if key not in value]
    if missing:
        errors.append(f"{location}: missing keys {missing}")
    return not missing


def validate_string_list(
    value: Any,
    location: str,
    errors: list[str],
    *,
    code_values: bool = False,
) -> list[str]:
    if not isinstance(value, list):
        errors.append(f"{location} must be an array")
        return []
    valid: list[str] = []
    seen: set[str] = set()
    for index, item in enumerate(value):
        item_location = f"{location}[{index}]"
        if not nonempty_string(item):
            errors.append(f"{item_location} must be a non-empty string")
            continue
        if code_values and not CODE.fullmatch(item):
            errors.append(f"{item_location} must be an uppercase reason/action code")
            continue
        if item in seen:
            errors.append(f"{location} contains duplicate value {item!r}")
            continue
        seen.add(item)
        valid.append(item)
    return valid


def validate_lane_search_requests(
    value: Any,
    location: str,
    errors: list[str],
) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        errors.append(f"{location} must be an array")
        return []
    requests: list[dict[str, Any]] = []
    keys: set[tuple[Any, ...]] = set()
    for index, request in enumerate(value):
        item_location = f"{location}[{index}]"
        if not require_exact_keys(
            request,
            {
                "phase",
                "candidate_id",
                "round",
                "source_packet_id",
                "reason_codes",
            },
            item_location,
            errors,
        ):
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
        reason_codes = validate_string_list(
            request.get("reason_codes"),
            f"{item_location}.reason_codes",
            errors,
            code_values=True,
        )
        if not reason_codes:
            errors.append(f"{item_location}.reason_codes must not be empty")
        key = tuple(
            key_component(component)
            for component in (phase, candidate_id, round_number)
        )
        if key in keys:
            errors.append(f"{location} contains duplicate lane request {key!r}")
        keys.add(key)
        requests.append(request)
    return requests


def collect_work_products(
    state: dict[str, Any],
    errors: list[str],
) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    collections: list[tuple[str, dict[str, dict[str, Any]]]] = [
        ("accepted_work_products", {}),
        ("rejected_work_products", {}),
    ]
    for field, target in collections:
        records = state.get(field)
        if not isinstance(records, list):
            errors.append(f"session-state.json.{field} must be an array")
            continue
        for index, record in enumerate(records):
            location = f"session-state.json.{field}[{index}]"
            if not isinstance(record, dict):
                errors.append(f"{location} must be an object")
                continue
            packet_id = record.get("packet_id")
            if not nonempty_string(packet_id) or not SAFE_ID.fullmatch(packet_id):
                errors.append(f"{location}.packet_id is invalid")
                continue
            if packet_id in target:
                errors.append(f"{field} contains duplicate packet_id {packet_id!r}")
                continue
            target[packet_id] = record
    accepted = collections[0][1]
    rejected = collections[1][1]
    overlap = sorted(set(accepted) & set(rejected))
    if overlap:
        errors.append(
            "session-state.json: packet IDs cannot be both accepted and rejected: "
            f"{overlap}"
        )
    return accepted, rejected


def validate_mainline_state(
    state: dict[str, Any],
    errors: list[str],
) -> tuple[int | None, dict[str, int], str | None]:
    control = state.get("mainline_control")
    required = (
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
    if not require_keys(control, required, "session-state.json.mainline_control", errors):
        return None, {}, None
    assert isinstance(control, dict)

    if control.get("controller_id") != "MAINLINE":
        errors.append(
            "session-state.json.mainline_control.controller_id must be 'MAINLINE'"
        )
    if control.get("controller_status") != "ACTIVE":
        errors.append(
            "session-state.json.mainline_control.controller_status must be ACTIVE "
            "for an agent controller decision"
        )

    revision = control.get("revision")
    if not is_int(revision) or revision < 0:
        errors.append(
            "session-state.json.mainline_control.revision must be a non-negative integer"
        )
        revision_value: int | None = None
    else:
        revision_value = revision

    pending_gate = control.get("pending_user_gate")
    if pending_gate is not None and (
        not isinstance(pending_gate, str)
        or pending_gate not in PENDING_USER_GATES
    ):
        errors.append(
            "session-state.json.mainline_control.pending_user_gate must be null or "
            f"one of {sorted(PENDING_USER_GATES)}"
        )
        pending_value: str | None = None
    else:
        pending_value = pending_gate

    retry_counts_value = control.get("retry_counts")
    retry_counts: dict[str, int] = {}
    if not isinstance(retry_counts_value, dict):
        errors.append(
            "session-state.json.mainline_control.retry_counts must be an object"
        )
    else:
        for key, count in retry_counts_value.items():
            location = f"session-state.json.mainline_control.retry_counts[{key!r}]"
            if not nonempty_string(key) or not SAFE_ID.fullmatch(key):
                errors.append(f"{location}: retry key is invalid")
            if not is_int(count) or count not in {0, 1}:
                errors.append(f"{location} must be integer 0 or 1")
                continue
            retry_counts[key] = count

    validate_lane_search_requests(
        control.get("lane_search_requests"),
        "session-state.json.mainline_control.lane_search_requests",
        errors,
    )

    transition_log = control.get("transition_log")
    if not isinstance(transition_log, list):
        errors.append(
            "session-state.json.mainline_control.transition_log must be an array"
        )
    elif revision_value is not None:
        if len(transition_log) != revision_value:
            errors.append(
                "session-state.json.mainline_control.revision must equal the "
                "transition_log length"
            )
        if revision_value == 0:
            if control.get("last_checkpoint") is not None:
                errors.append(
                    "session-state.json.mainline_control.last_checkpoint must be "
                    "null at revision 0"
                )
            if control.get("last_controller_packet_id") is not None:
                errors.append(
                    "session-state.json.mainline_control.last_controller_packet_id "
                    "must be null at revision 0"
                )
            if pending_gate is not None:
                errors.append(
                    "session-state.json.mainline_control.pending_user_gate must be "
                    "null at revision 0"
                )
        elif transition_log and isinstance(transition_log[-1], dict):
            last = transition_log[-1]
            if last.get("revision") != revision_value:
                errors.append(
                    "session-state.json.mainline_control last transition revision "
                    "does not match the top-level control revision"
                )
            if last.get("to_status") != state.get("status"):
                errors.append(
                    "session-state.json.status does not match the last control "
                    "transition to_status"
                )
            if last.get("packet_id") != control.get("last_controller_packet_id"):
                errors.append(
                    "session-state.json.mainline_control.last_controller_packet_id "
                    "does not match the last transition"
                )
            if last.get("checkpoint") != control.get("last_checkpoint"):
                errors.append(
                    "session-state.json.mainline_control.last_checkpoint does not "
                    "match the last transition"
                )
            if last.get("pending_user_gate") != pending_gate:
                errors.append(
                    "session-state.json.mainline_control.pending_user_gate does not "
                    "match the last transition"
                )

    status = state.get("status")
    if pending_value is not None and GATE_TARGETS[pending_value] != status:
        errors.append(
            "session-state.json.mainline_control.pending_user_gate is incompatible "
            f"with current status {status!r}"
        )

    return revision_value, retry_counts, pending_value


def expected_context_fingerprint(envelope: dict[str, Any]) -> str:
    identity = {
        key: envelope.get(key)
        for key in (
            "session_id",
            "project_root",
            "project_snapshot",
            "phase",
            "role",
            "candidate_id",
            "round",
            "packet_id",
            "control_revision",
            "state_digest",
            "control_input_digest",
        )
    }
    compact = json.dumps(
        identity,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    return hashlib.sha256(compact.encode("utf-8")).hexdigest()


def validate_envelope(
    envelope: Any,
    state: dict[str, Any],
    state_digest: str,
    control_input_digest: str,
    revision: int | None,
    used_packet_ids: set[str],
    errors: list[str],
) -> str | None:
    if not require_exact_keys(
        envelope, ENVELOPE_KEYS, "controller-output.json.envelope", errors
    ):
        if not isinstance(envelope, dict):
            return None
    assert isinstance(envelope, dict)

    expected_identity = {
        "schema_version": "1.0",
        "session_id": state.get("session_id"),
        "project_root": state.get("project_root"),
        "project_snapshot": state.get("project_snapshot"),
        "phase": "CONTROL",
        "role": "Mainline Workflow Controller",
        "candidate_id": None,
        "round": None,
    }
    for field, expected in expected_identity.items():
        if envelope.get(field) != expected:
            errors.append(
                f"controller-output.json.envelope.{field} must equal {expected!r}"
            )

    packet_id = envelope.get("packet_id")
    if not nonempty_string(packet_id) or not SAFE_ID.fullmatch(packet_id):
        errors.append("controller-output.json.envelope.packet_id is invalid")
        packet_value: str | None = None
    else:
        packet_value = packet_id
        if packet_id in used_packet_ids:
            errors.append(
                "controller-output.json.envelope.packet_id already exists in "
                f"session state: {packet_id!r}"
            )

    control_revision = envelope.get("control_revision")
    if not is_int(control_revision) or control_revision < 0:
        errors.append(
            "controller-output.json.envelope.control_revision must be a "
            "non-negative integer"
        )
    elif revision is not None and control_revision != revision:
        errors.append(
            "controller-output.json.envelope.control_revision does not match "
            "the current mainline revision"
        )

    digest = envelope.get("state_digest")
    if not isinstance(digest, str) or not SHA256.fullmatch(digest):
        errors.append(
            "controller-output.json.envelope.state_digest must be a lowercase "
            "SHA-256 digest"
        )
    elif digest != state_digest:
        errors.append(
            "controller-output.json.envelope.state_digest does not match the "
            "current session-state.json bytes"
        )
    input_digest = envelope.get("control_input_digest")
    if not isinstance(input_digest, str) or not SHA256.fullmatch(input_digest):
        errors.append(
            "controller-output.json.envelope.control_input_digest must be a "
            "lowercase SHA-256 digest"
        )
    elif input_digest != control_input_digest:
        errors.append(
            "controller-output.json.envelope.control_input_digest does not "
            "match the authoritative control-input.json bytes"
        )

    fingerprint = envelope.get("context_fingerprint")
    if not isinstance(fingerprint, str) or not SHA256.fullmatch(fingerprint):
        errors.append(
            "controller-output.json.envelope.context_fingerprint must be a "
            "lowercase SHA-256 digest"
        )
    elif fingerprint != expected_context_fingerprint(envelope):
        errors.append(
            "controller-output.json.envelope.context_fingerprint does not match "
            "the CONTROL identity fields"
        )

    allowed_artifacts = envelope.get("allowed_artifacts")
    artifacts = validate_string_list(
        allowed_artifacts,
        "controller-output.json.envelope.allowed_artifacts",
        errors,
    )
    if artifacts:
        errors.append(
            "controller-output.json.envelope.allowed_artifacts must be empty; "
            "the controller receives only the compact control_input"
        )

    return packet_value


def candidate_ids_from_state(state: dict[str, Any]) -> set[str]:
    candidates = state.get("candidates")
    if not isinstance(candidates, list):
        return set()
    return {
        candidate["candidate_id"]
        for candidate in candidates
        if isinstance(candidate, dict)
        and nonempty_string(candidate.get("candidate_id"))
    }


def logical_dispatch_key(value: dict[str, Any]) -> tuple[Any, ...]:
    return tuple(
        key_component(value.get(field))
        for field in ("phase", "role", "candidate_id", "round")
    )


def prior_dispatches_by_id(state: dict[str, Any]) -> dict[str, dict[str, Any]]:
    control = state.get("mainline_control")
    transitions = (
        control.get("transition_log")
        if isinstance(control, dict)
        and isinstance(control.get("transition_log"), list)
        else []
    )
    dispatched: dict[str, dict[str, Any]] = {}
    for transition in transitions:
        dispatches = (
            transition.get("dispatches")
            if isinstance(transition, dict)
            and isinstance(transition.get("dispatches"), list)
            else []
        )
        for dispatch in dispatches:
            if (
                isinstance(dispatch, dict)
                and nonempty_string(dispatch.get("packet_id"))
            ):
                dispatched[dispatch["packet_id"]] = dispatch
    return dispatched


def prior_retry_dispatch_ids(state: dict[str, Any]) -> set[str]:
    control = state.get("mainline_control")
    transitions = (
        control.get("transition_log")
        if isinstance(control, dict)
        and isinstance(control.get("transition_log"), list)
        else []
    )
    return {
        dispatch["packet_id"]
        for transition in transitions
        if isinstance(transition, dict)
        and transition.get("action") == "RETRY_ROLE"
        and isinstance(transition.get("dispatches"), list)
        for dispatch in transition["dispatches"]
        if isinstance(dispatch, dict)
        and nonempty_string(dispatch.get("packet_id"))
    }


def validate_resolved_dispatch_bindings(
    state: dict[str, Any],
    accepted: dict[str, dict[str, Any]],
    rejected: dict[str, dict[str, Any]],
    errors: list[str],
) -> None:
    dispatched = prior_dispatches_by_id(state)
    control = state.get("mainline_control")
    transitions = (
        control.get("transition_log")
        if isinstance(control, dict)
        and isinstance(control.get("transition_log"), list)
        else []
    )
    for packet_id, product in accepted.items():
        if product.get("phase") == "CONTROL":
            continue
        original = dispatched.get(packet_id)
        if original is None:
            errors.append(
                f"accepted packet {packet_id!r} has no committed controller "
                "dispatch"
            )
            continue
        for field in ("phase", "role", "candidate_id", "round"):
            if product.get(field) != original.get(field):
                errors.append(
                    f"accepted packet {packet_id!r} field {field} does not "
                    "match its controller dispatch"
                )

    for packet_id, rejection in rejected.items():
        if rejection.get("role") in {
            "Mainline Workflow Controller",
            "Deterministic Mainline Fallback",
        }:
            continue
        original = dispatched.get(packet_id)
        if original is None:
            errors.append(
                f"rejected packet {packet_id!r} has no committed controller "
                "dispatch"
            )
            continue
        for field in ("role", "candidate_id", "round"):
            if rejection.get(field) != original.get(field):
                errors.append(
                    f"rejected packet {packet_id!r} field {field} does not "
                    "match its controller dispatch"
                )


def validate_lane_search_bindings(
    state: dict[str, Any],
    accepted: dict[str, dict[str, Any]],
    errors: list[str],
) -> None:
    control = state.get("mainline_control")
    requests = (
        control.get("lane_search_requests")
        if isinstance(control, dict)
        and isinstance(control.get("lane_search_requests"), list)
        else []
    )
    dispatched = prior_dispatches_by_id(state)
    for index, request in enumerate(requests):
        if not isinstance(request, dict):
            continue
        location = f"session-state.json.mainline_control.lane_search_requests[{index}]"
        source_packet_id = request.get("source_packet_id")
        safe_source_packet_id = (
            source_packet_id if isinstance(source_packet_id, str) else None
        )
        source = dispatched.get(safe_source_packet_id)
        if (
            safe_source_packet_id not in accepted
            or not isinstance(source, dict)
        ):
            errors.append(
                f"{location}.source_packet_id must name an accepted committed "
                "dispatch"
            )
            continue
        expected = {
            "phase": request.get("phase"),
            "role": "Devil's Advocate",
            "candidate_id": request.get("candidate_id"),
            "round": request.get("round"),
        }
        if any(source.get(field) != value for field, value in expected.items()):
            errors.append(
                f"{location}.source_packet_id must name the accepted same-lane "
                "Devil's Advocate packet"
            )


def latest_accepted_dispatch_id(
    state: dict[str, Any],
    accepted: dict[str, dict[str, Any]],
    **coordinates: Any,
) -> str | None:
    dispatched = list(prior_dispatches_by_id(state).items())
    for packet_id, dispatch in reversed(dispatched):
        if packet_id in accepted and all(
            dispatch.get(field) == value
            for field, value in coordinates.items()
        ):
            return packet_id
    return None


def rq_dispatch_resolution(
    state: dict[str, Any],
    accepted: dict[str, dict[str, Any]],
    rejected: dict[str, dict[str, Any]],
    candidate_id: str,
) -> tuple[str | None, str | None, list[str]]:
    """Return latest RQ dispatch, latest iff accepted, and unresolved RQ packets."""
    matching = [
        packet_id
        for packet_id, dispatch in prior_dispatches_by_id(state).items()
        if dispatch.get("phase") == "RQ_REFINEMENT"
        and dispatch.get("role") == "Research Question Architect"
        and dispatch.get("candidate_id") == candidate_id
        and dispatch.get("round") is None
    ]
    latest = matching[-1] if matching else None
    unresolved = [
        packet_id
        for packet_id in matching
        if packet_id not in accepted and packet_id not in rejected
    ]
    latest_accepted = latest if latest in accepted else None
    return latest, latest_accepted, unresolved


def validate_dispatch_prerequisites(
    dispatch: dict[str, Any],
    state: dict[str, Any],
    accepted: dict[str, dict[str, Any]],
    dependencies: list[str],
    location: str,
    errors: list[str],
) -> None:
    phase = dispatch.get("phase")
    role = dispatch.get("role")
    candidate_id = dispatch.get("candidate_id")
    round_number = dispatch.get("round")
    if not isinstance(phase, str) or not isinstance(role, str):
        return

    def require(label: str, **coordinates: Any) -> str | None:
        packet_id = latest_accepted_dispatch_id(state, accepted, **coordinates)
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
        if (
            state.get("interaction_mode") == "GUIDED"
            and not has_current_direction_delegate_receipt(state)
        ):
            errors.append(
                f"{location} requires AUTONOMOUS interaction mode or a current "
                "DIRECTION_SELECTION/DELEGATE receipt"
            )
        return
    if phase == "HOTSPOT":
        selected = state.get("selected_macro_direction_ids")
        if not isinstance(selected, list) or not selected:
            errors.append(
                f"{location} requires at least one selected macro direction"
            )
        direction_choice = latest_accepted_dispatch_id(
            state,
            accepted,
            phase="DIRECTION_SELECTION",
        )
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
                    and candidate.get("status") == "DOWNGRADED"
                )
                if not eligible_lane:
                    errors.append(
                        f"{location} requires an initially selected or eligible "
                        "derived debate candidate"
                    )
                if (
                    not isinstance(candidate, dict)
                    or candidate.get("status") not in {"ACTIVE", "DOWNGRADED"}
                ):
                    errors.append(
                        f"{location} requires candidate status ACTIVE or DOWNGRADED"
                    )
            if is_int(round_number) and round_number > 1:
                require(
                    "previous-round Judge",
                    phase=phase,
                    role="Panel Judge",
                    candidate_id=candidate_id,
                    round=round_number - 1,
                )
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
                require(
                    "external positioning",
                    phase="EXTERNAL_POSITIONING",
                )
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
            search_packet = latest_accepted_dispatch_id(
                state,
                accepted,
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
                    for packet_id, prior in prior_dispatches_by_id(state).items()
                    if packet_id in accepted
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
        rounds = candidate.get("rounds") if isinstance(candidate, dict) else None
        rounds_completed = (
            candidate.get("rounds_completed")
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
        packet_id = latest_accepted_dispatch_id(
            state,
            accepted,
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
        rounds = state.get("evaluation_rounds")
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
        if not has_completion_receipt(
            state,
            "EVALUATION_DECISION",
            {"CONFIRM", "OVERRIDE"},
        ):
            errors.append(
                f"{location} requires an EVALUATION_DECISION user receipt"
            )


def prior_dispatch_keys(
    state: dict[str, Any],
    accepted: dict[str, dict[str, Any]],
    rejected: dict[str, dict[str, Any]],
) -> tuple[
    set[tuple[Any, ...]],
    set[tuple[Any, ...]],
    dict[tuple[Any, ...], set[str]],
    dict[tuple[Any, ...], str],
]:
    resolved_ids = set(accepted) | set(rejected)
    pending: set[tuple[Any, ...]] = set()
    rejected_keys: dict[tuple[Any, ...], set[str]] = {}
    accepted_repeat_keys: dict[tuple[Any, ...], str] = {}
    control = state.get("mainline_control")
    transitions = (
        control.get("transition_log")
        if isinstance(control, dict)
        and isinstance(control.get("transition_log"), list)
        else []
    )
    for transition in transitions:
        dispatches = (
            transition.get("dispatches")
            if isinstance(transition, dict)
            and isinstance(transition.get("dispatches"), list)
            else []
        )
        for dispatch in dispatches:
            if not (
                isinstance(dispatch, dict)
                and nonempty_string(dispatch.get("packet_id"))
            ):
                continue
            packet_id = dispatch["packet_id"]
            dispatch_key = logical_dispatch_key(dispatch)
            if packet_id in rejected:
                rejected_keys.setdefault(dispatch_key, set()).add(packet_id)
            elif packet_id in accepted and (
                not isinstance(dispatch.get("phase"), str)
                or dispatch.get("phase")
                not in {"DEBATE", "EVALUATION_DEBATE"}
                or dispatch.get("role") == "Evidence Researcher"
            ):
                accepted_repeat_keys[dispatch_key] = packet_id
            elif packet_id not in resolved_ids:
                pending.add(dispatch_key)

    completed_round_calls = {
        logical_dispatch_key(product)
        for product in accepted.values()
        if isinstance(product.get("phase"), str)
        and product.get("phase") in {"DEBATE", "EVALUATION_DEBATE"}
        and product.get("role") != "Evidence Researcher"
    }
    return (
        pending,
        completed_round_calls,
        rejected_keys,
        accepted_repeat_keys,
    )


def validate_dispatches(
    value: Any,
    state: dict[str, Any],
    controller_packet_id: str | None,
    action: Any,
    retry_key: Any,
    target_status: Any,
    checkpoint: Any,
    directive_reason_codes: Any,
    accepted: dict[str, dict[str, Any]],
    rejected: dict[str, dict[str, Any]],
    errors: list[str],
) -> list[dict[str, Any]]:
    location = "controller-output.json.control_directive.dispatches"
    if not isinstance(value, list):
        errors.append(f"{location} must be an array")
        return []

    mode = state.get("mode")
    allowed_phases = EVALUATION_PHASES if mode == "evaluate" else DISCOVERY_PHASES
    status_phase_map = (
        EVALUATION_DISPATCH_PHASES_BY_STATUS
        if mode == "evaluate"
        else DISCOVERY_DISPATCH_PHASES_BY_STATUS
    )
    status_phases = (
        status_phase_map.get(target_status, set())
        if isinstance(target_status, str)
        else set()
    )
    candidates = candidate_ids_from_state(state)
    existing_ids = set(accepted) | set(rejected)
    existing_ids.update(prior_dispatches_by_id(state))
    if controller_packet_id is not None:
        existing_ids.add(controller_packet_id)
    max_rounds = state.get("max_rounds")
    max_rounds_value = max_rounds if is_int(max_rounds) and max_rounds >= 1 else None
    retry_key_value = retry_key if isinstance(retry_key, str) else None
    dispatch_ids: set[str] = set()
    schedule_keys: set[tuple[Any, ...]] = set()
    (
        pending_keys,
        completed_round_keys,
        rejected_keys,
        accepted_repeat_keys,
    ) = prior_dispatch_keys(state, accepted, rejected)
    valid: list[dict[str, Any]] = []
    control = state.get("mainline_control")
    prior_transitions = (
        control.get("transition_log")
        if isinstance(control, dict)
        and isinstance(control.get("transition_log"), list)
        else []
    )
    rq_confirmation_applied = any(
        isinstance(transition, dict)
        and transition.get("required_actions") == ["APPLY_RQ_CONFIRMATION"]
        for transition in prior_transitions
    )

    for index, dispatch in enumerate(value):
        item_location = f"{location}[{index}]"
        if not require_exact_keys(dispatch, DISPATCH_KEYS, item_location, errors):
            if not isinstance(dispatch, dict):
                continue
        assert isinstance(dispatch, dict)

        packet_id = dispatch.get("packet_id")
        if not nonempty_string(packet_id) or not SAFE_ID.fullmatch(packet_id):
            errors.append(f"{item_location}.packet_id is invalid")
        else:
            if packet_id in dispatch_ids:
                errors.append(
                    f"{location} contains duplicate packet_id {packet_id!r}"
                )
            if packet_id in existing_ids:
                errors.append(
                    f"{item_location}.packet_id is not fresh: {packet_id!r}"
                )
            dispatch_ids.add(packet_id)

        phase = dispatch.get("phase")
        role = dispatch.get("role")
        if not isinstance(phase, str) or phase not in PHASE_ROLES:
            errors.append(
                f"{item_location}.phase must be one of {sorted(PHASE_ROLES)}"
            )
        else:
            if phase not in allowed_phases:
                errors.append(
                    f"{item_location}.phase {phase!r} is not valid in mode {mode!r}"
                )
            if phase not in status_phases:
                errors.append(
                    f"{item_location}.phase {phase!r} is not schedulable while "
                    f"targeting status {target_status!r}"
                )
            if not isinstance(role, str) or role not in PHASE_ROLES[phase]:
                errors.append(
                    f"{item_location}.role {role!r} is not allowed in phase "
                    f"{phase!r}"
                )
        if phase == "RQ_REFINEMENT" and rq_confirmation_applied:
            errors.append(
                f"{item_location}: RQ_REFINEMENT is frozen after the user-confirmed "
                "version has been applied"
            )
        if not nonempty_string(role):
            errors.append(f"{item_location}.role must be non-empty")
        if (
            phase == "DIRECTION_SELECTION"
            and state.get("interaction_mode") == "GUIDED"
            and checkpoint != "POST_USER_GATE"
        ):
            errors.append(
                f"{item_location}: GUIDED direction delegation is schedulable "
                "only at POST_USER_GATE"
            )
        if phase == "EVIDENCE_INTAKE":
            evaluation_target = state.get("evaluation_target")
            missing_target_fields = [
                field
                for field in ("direction", "primary_claim", "study_type")
                if not isinstance(evaluation_target, dict)
                or not nonempty_string(evaluation_target.get(field))
            ]
            if missing_target_fields:
                errors.append(
                    f"{item_location}: EVIDENCE_INTAKE cannot dispatch the "
                    "Experiment Auditor until target fields are resolved "
                    f"{missing_target_fields}"
                )

        candidate_id = dispatch.get("candidate_id")
        round_number = dispatch.get("round")
        if isinstance(phase, str) and phase in NULL_COORDINATE_PHASES:
            if candidate_id is not None or round_number is not None:
                errors.append(
                    f"{item_location}: {phase} requires null candidate_id and round"
                )
        elif phase == "DEBATE":
            if not nonempty_string(candidate_id):
                errors.append(
                    f"{item_location}: DEBATE requires a candidate_id"
                )
            elif candidate_id not in candidates:
                errors.append(
                    f"{item_location}.candidate_id {candidate_id!r} does not exist"
                )
            if not is_int(round_number) or round_number < 1:
                errors.append(
                    f"{item_location}: DEBATE requires a positive integer round"
                )
        elif phase == "EVALUATION_DEBATE":
            if candidate_id is not None:
                errors.append(
                    f"{item_location}: EVALUATION_DEBATE requires null candidate_id"
                )
            if not is_int(round_number) or round_number < 1:
                errors.append(
                    f"{item_location}: EVALUATION_DEBATE requires a positive "
                    "integer round"
                )
        elif isinstance(phase, str) and phase in CANDIDATE_ONLY_PHASES:
            if not nonempty_string(candidate_id):
                errors.append(
                    f"{item_location}: {phase} requires a candidate_id"
                )
            elif candidate_id not in candidates:
                errors.append(
                    f"{item_location}.candidate_id {candidate_id!r} does not exist"
                )
            if round_number is not None:
                errors.append(f"{item_location}: {phase} requires a null round")

        if (
            is_int(round_number)
            and max_rounds_value is not None
            and round_number > max_rounds_value
        ):
            errors.append(
                f"{item_location}.round exceeds session-state.json.max_rounds"
            )

        dependencies = validate_string_list(
            dispatch.get("depends_on_packet_ids"),
            f"{item_location}.depends_on_packet_ids",
            errors,
        )
        for dependency in dependencies:
            if not SAFE_ID.fullmatch(dependency):
                errors.append(
                    f"{item_location}.depends_on_packet_ids contains invalid "
                    f"packet ID {dependency!r}"
                )
            elif dependency not in accepted:
                errors.append(
                    f"{item_location}: dependency {dependency!r} is not an "
                    "already accepted work product"
                )
            if dependency == packet_id:
                errors.append(f"{item_location} cannot depend on its own packet")
        prior_dispatch_ids = set(prior_dispatches_by_id(state))
        unknown_dispatch_dependencies = sorted(
            set(dependencies) - prior_dispatch_ids
        )
        if unknown_dispatch_dependencies:
            errors.append(
                f"{item_location}.depends_on_packet_ids must reference prior "
                "controller dispatches "
                f"{unknown_dispatch_dependencies}"
            )
        validate_dispatch_prerequisites(
            dispatch,
            state,
            accepted,
            dependencies,
            item_location,
            errors,
        )

        schedule_key = tuple(
            key_component(component)
            for component in (phase, role, candidate_id, round_number)
        )
        if schedule_key in schedule_keys:
            errors.append(
                f"{location} contains a duplicate logical dispatch at index {index}"
            )
        if schedule_key in pending_keys:
            errors.append(
                f"{item_location} duplicates an unresolved prior dispatch"
            )
        if schedule_key in completed_round_keys:
            errors.append(
                f"{item_location} repeats an accepted debate-round role call"
            )
        rejected_packets = rejected_keys.get(schedule_key, set())
        if rejected_packets and not (
            action == "RETRY_ROLE" and retry_key_value in rejected_packets
        ):
            errors.append(
                f"{item_location} repeats a rejected logical dispatch outside "
                "its one RETRY_ROLE action"
            )
        superseded_packet = accepted_repeat_keys.get(schedule_key)
        if superseded_packet is not None:
            if (
                not isinstance(directive_reason_codes, list)
                or "SUPERSEDE_ACCEPTED_CALL" not in directive_reason_codes
            ):
                errors.append(
                    f"{item_location} repeats an accepted call "
                    "without reason code SUPERSEDE_ACCEPTED_CALL"
                )
            if superseded_packet not in dependencies:
                errors.append(
                    f"{item_location} must depend on the latest accepted packet "
                    f"it supersedes: {superseded_packet!r}"
                )
            if (
                phase in {"DEBATE", "EVALUATION_DEBATE"}
                and role == "Evidence Researcher"
            ):
                accepted_evidence_count = sum(
                    1
                    for product in accepted.values()
                    if logical_dispatch_key(product) == schedule_key
                )
                if accepted_evidence_count >= 2:
                    errors.append(
                        f"{item_location} exceeds the one permitted revised "
                        "Evidence Researcher answer"
                    )
                search_packet = latest_accepted_dispatch_id(
                    state,
                    accepted,
                    phase=phase,
                    role="Search and Verification Specialist",
                    candidate_id=candidate_id,
                    round=round_number,
                )
                if search_packet is None:
                    errors.append(
                        f"{item_location} may supersede Evidence only after an "
                        "accepted same-round search"
                    )
                elif search_packet not in dependencies:
                    errors.append(
                        f"{item_location}.depends_on_packet_ids must include "
                        f"same-round search packet {search_packet!r}"
                    )
        schedule_keys.add(schedule_key)
        valid.append(dispatch)

    return valid


def matching_gate_receipt(
    state: dict[str, Any],
    gate: str,
    revision: int,
    errors: list[str],
) -> dict[str, Any] | None:
    receipts = state.get("gate_receipts")
    if not isinstance(receipts, list):
        errors.append("session-state.json.gate_receipts must be an array")
        return None
    matches: list[dict[str, Any]] = []
    for index, receipt in enumerate(receipts):
        if not isinstance(receipt, dict):
            continue
        if receipt.get("gate") == gate and receipt.get("based_on_revision") == revision:
            location = f"session-state.json.gate_receipts[{index}]"
            action = receipt.get("action")
            if action not in GATE_RECEIPT_ACTIONS[gate]:
                errors.append(
                    f"{location}.action must be one of "
                    f"{sorted(GATE_RECEIPT_ACTIONS[gate])}"
                )
                continue
            if not nonempty_string(receipt.get("receipt_id")):
                errors.append(f"{location}.receipt_id must be non-empty")
            if not isinstance(receipt.get("values"), list):
                errors.append(f"{location}.values must be an array")
            if not nonempty_string(receipt.get("received_at")):
                errors.append(f"{location}.received_at must be non-empty")
            matches.append(receipt)
    if not matches:
        errors.append(
            f"session-state.json.gate_receipts requires a direct {gate} receipt "
            f"based on control revision {revision}"
        )
        return None
    if len(matches) > 1:
        errors.append(
            f"session-state.json.gate_receipts has multiple {gate} receipts "
            f"based on control revision {revision}"
        )
        return None
    return matches[0]


def blocking_entry_transition(state: dict[str, Any]) -> dict[str, Any] | None:
    control = state.get("mainline_control")
    transitions = (
        control.get("transition_log")
        if isinstance(control, dict)
        and isinstance(control.get("transition_log"), list)
        else []
    )
    for transition in reversed(transitions):
        if (
            isinstance(transition, dict)
            and transition.get("action") == "BLOCK_SESSION"
            and transition.get("to_status") == "BLOCKED"
            and transition.get("from_status") != "BLOCKED"
        ):
            return transition
    return None


def blocking_resume_gate(
    state: dict[str, Any],
    blocked_at: dict[str, Any],
) -> str | None:
    resume_status = blocked_at.get("from_status")
    for gate, target_status in GATE_TARGETS.items():
        if gate != "RQ_CONFIRMATION" and target_status == resume_status:
            return gate

    revision = blocked_at.get("revision")
    control = state.get("mainline_control")
    transitions = (
        control.get("transition_log")
        if isinstance(control, dict)
        and isinstance(control.get("transition_log"), list)
        else []
    )
    if is_int(revision) and revision >= 2 and len(transitions) >= revision - 1:
        predecessor = transitions[revision - 2]
        if (
            isinstance(predecessor, dict)
            and predecessor.get("action") == "HOLD_FOR_USER"
            and predecessor.get("to_status") == resume_status
            and isinstance(predecessor.get("pending_user_gate"), str)
            and predecessor.get("pending_user_gate") in PENDING_USER_GATES
        ):
            return predecessor["pending_user_gate"]
    return None


def has_completion_receipt(
    state: dict[str, Any],
    gate: str,
    allowed_actions: set[str],
) -> bool:
    receipts = state.get("gate_receipts")
    if not isinstance(receipts, list):
        return False
    return any(
        isinstance(receipt, dict)
        and receipt.get("gate") == gate
        and isinstance(receipt.get("action"), str)
        and receipt.get("action") in allowed_actions
        and is_int(receipt.get("based_on_revision"))
        for receipt in receipts
    )


def has_current_direction_delegate_receipt(state: dict[str, Any]) -> bool:
    control = state.get("mainline_control")
    revision = (
        control.get("revision")
        if isinstance(control, dict)
        else None
    )
    receipts = state.get("gate_receipts")
    if not is_int(revision) or not isinstance(receipts, list):
        return False
    return any(
        isinstance(receipt, dict)
        and receipt.get("gate") == "DIRECTION_SELECTION"
        and receipt.get("action") == "DELEGATE"
        and receipt.get("based_on_revision") == revision
        for receipt in receipts
    )


def has_delegated_direction_selection_product(
    state: dict[str, Any],
    accepted: dict[str, dict[str, Any]],
) -> bool:
    control = state.get("mainline_control")
    transitions = (
        control.get("transition_log")
        if isinstance(control, dict)
        and isinstance(control.get("transition_log"), list)
        else []
    )
    receipts = state.get("gate_receipts")
    if not isinstance(receipts, list):
        return False
    for index, transition in enumerate(transitions):
        if (
            not isinstance(transition, dict)
            or transition.get("checkpoint") != "POST_USER_GATE"
            or not isinstance(transition.get("dispatches"), list)
            or index == 0
        ):
            continue
        predecessor = transitions[index - 1]
        if (
            not isinstance(predecessor, dict)
            or predecessor.get("action") != "HOLD_FOR_USER"
            or predecessor.get("pending_user_gate") != "DIRECTION_SELECTION"
        ):
            continue
        has_delegate_receipt = any(
            isinstance(receipt, dict)
            and receipt.get("gate") == "DIRECTION_SELECTION"
            and receipt.get("action") == "DELEGATE"
            and receipt.get("based_on_revision") == predecessor.get("revision")
            for receipt in receipts
        )
        if not has_delegate_receipt:
            continue
        if any(
            isinstance(dispatch, dict)
            and dispatch.get("phase") == "DIRECTION_SELECTION"
            and dispatch.get("packet_id") in accepted
            for dispatch in transition["dispatches"]
        ):
            return True
    return False


def validate_retry(
    retry_key: Any,
    dispatches: list[dict[str, Any]],
    state: dict[str, Any],
    rejected: dict[str, dict[str, Any]],
    retry_counts: dict[str, int],
    errors: list[str],
) -> None:
    location = "controller-output.json.control_directive"
    if not nonempty_string(retry_key) or not SAFE_ID.fullmatch(retry_key):
        errors.append(f"{location}.retry_key must name a valid rejected packet")
        return
    rejection = rejected.get(retry_key)
    if rejection is None:
        errors.append(
            f"{location}.retry_key {retry_key!r} is not a recorded rejected packet"
        )
        return
    if retry_counts.get(retry_key, 0) != 0:
        errors.append(
            f"{location}.retry_key {retry_key!r} has already used its one retry"
        )
    if retry_key in prior_retry_dispatch_ids(state):
        errors.append(
            f"{location}.retry_key {retry_key!r} is itself a retry packet; "
            "retry chains are forbidden"
        )
    original_dispatch = prior_dispatches_by_id(state).get(retry_key)
    if original_dispatch is None:
        errors.append(
            f"{location}.retry_key {retry_key!r} has no recorded original "
            "controller dispatch"
        )
    if len(dispatches) != 1:
        return
    dispatch = dispatches[0]
    if dispatch.get("packet_id") == retry_key:
        errors.append("RETRY_ROLE must use a fresh packet_id")
    for field in ("role", "candidate_id", "round"):
        if dispatch.get(field) != rejection.get(field):
            errors.append(
                f"RETRY_ROLE dispatch {field} does not match rejected packet "
                f"{retry_key!r}"
            )
    if isinstance(original_dispatch, dict):
        for field in ("phase", "role", "candidate_id", "round"):
            if dispatch.get(field) != original_dispatch.get(field):
                errors.append(
                    f"RETRY_ROLE dispatch {field} does not match the original "
                    f"dispatch for {retry_key!r}"
                )
    if "phase" in rejection and dispatch.get("phase") != rejection.get("phase"):
        errors.append(
            f"RETRY_ROLE dispatch phase does not match rejected packet {retry_key!r}"
        )


def validate_completion(
    state: dict[str, Any],
    required_actions: list[str],
    errors: list[str],
) -> None:
    mode = state.get("mode")
    if required_actions:
        errors.append("COMPLETE requires required_actions to be empty")
    if mode == "evaluate":
        if not isinstance(state.get("evaluation_decision"), dict):
            errors.append(
                "COMPLETE in evaluate mode requires an evaluation_decision object"
            )
        if not isinstance(state.get("next_experiment"), dict):
            errors.append(
                "COMPLETE in evaluate mode requires a next_experiment object"
            )
        if not has_completion_receipt(
            state,
            "EVALUATION_DECISION",
            {"CONFIRM", "OVERRIDE"},
        ):
            errors.append(
                "COMPLETE in evaluate mode requires a recorded "
                "EVALUATION_DECISION receipt"
            )
    else:
        selected_candidate_id = state.get("selected_candidate_id")
        if not nonempty_string(selected_candidate_id):
            errors.append(
                "COMPLETE in discovery/refine/RQ mode requires selected_candidate_id"
            )
        receipts = state.get("gate_receipts")
        rq_receipts = [
            receipt
            for receipt in receipts
            if isinstance(receipts, list)
            and isinstance(receipt, dict)
            and receipt.get("gate") == "RQ_CONFIRMATION"
            and receipt.get("action") == "CONFIRM"
        ] if isinstance(receipts, list) else []
        rq_receipt = rq_receipts[-1] if rq_receipts else None
        values = (
            rq_receipt.get("values")
            if isinstance(rq_receipt, dict)
            and isinstance(rq_receipt.get("values"), list)
            else []
        )
        confirmed_packet_id = values[1] if len(values) == 2 else None
        accepted_products = state.get("accepted_work_products")
        accepted_by_id = {
            product.get("packet_id"): product
            for product in accepted_products
            if isinstance(accepted_products, list)
            and isinstance(product, dict)
            and nonempty_string(product.get("packet_id"))
        } if isinstance(accepted_products, list) else {}
        rejected_products = state.get("rejected_work_products")
        rejected_by_id = {
            product.get("packet_id"): product
            for product in rejected_products
            if isinstance(rejected_products, list)
            and isinstance(product, dict)
            and nonempty_string(product.get("packet_id"))
        } if isinstance(rejected_products, list) else {}
        latest_rq_packet = None
        unresolved_rq_packets: list[str] = []
        if nonempty_string(selected_candidate_id):
            (
                _latest_dispatched_rq,
                latest_rq_packet,
                unresolved_rq_packets,
            ) = rq_dispatch_resolution(
                state,
                accepted_by_id,
                rejected_by_id,
                selected_candidate_id,
            )
        bound_product = any(
            isinstance(product, dict)
            and product.get("packet_id") == confirmed_packet_id
            and product.get("phase") == "RQ_REFINEMENT"
            and product.get("role") == "Research Question Architect"
            and product.get("candidate_id") == selected_candidate_id
            for product in accepted_products
        ) if isinstance(accepted_products, list) else False
        if (
            not isinstance(rq_receipt, dict)
            or values != [selected_candidate_id, confirmed_packet_id]
            or not nonempty_string(confirmed_packet_id)
            or not bound_product
            or confirmed_packet_id != latest_rq_packet
            or unresolved_rq_packets
        ):
            errors.append(
                "COMPLETE requires an RQ_CONFIRMATION/CONFIRM receipt bound to "
                "the selected candidate and latest resolved accepted RQ packet"
            )


def expected_active_lanes(
    state: dict[str, Any],
    accepted: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    status = state.get("status")
    if not isinstance(status, str):
        return []
    lane_coordinates: list[tuple[str, Any, int]] = []
    if status in {"EXTERNAL_POSITIONING", "EVALUATION_DEBATE"}:
        rounds = state.get("evaluation_rounds")
        last_verdict = (
            rounds[-1].get("verdict")
            if isinstance(rounds, list)
            and rounds
            and isinstance(rounds[-1], dict)
            else None
        )
        if last_verdict == "CONVERGED":
            return []
        next_round = len(rounds) + 1 if isinstance(rounds, list) else 1
        max_rounds = state.get("max_rounds")
        if is_int(max_rounds) and next_round > max_rounds:
            return []
        lane_coordinates.append(("EVALUATION_DEBATE", None, next_round))
    elif status not in {"CANDIDATE_GENERATION", "DEBATING"}:
        return []
    else:
        initial = state.get("initial_debate_candidate_ids")
        initial_ids = set(initial) if isinstance(initial, list) else set()
        max_rounds = state.get("max_rounds")
        for candidate in state.get("candidates", []):
            if not isinstance(candidate, dict):
                continue
            candidate_id = candidate.get("candidate_id")
            candidate_status = candidate.get("status")
            eligible = candidate_id in initial_ids or (
                candidate.get("origin") == "DERIVED"
                and candidate_status == "DOWNGRADED"
            )
            rounds_completed = candidate.get("rounds_completed")
            if (
                not eligible
                or not isinstance(candidate_status, str)
                or candidate_status not in {"ACTIVE", "DOWNGRADED"}
                or candidate.get("gate_ready") is True
                or not is_int(rounds_completed)
            ):
                continue
            next_round = rounds_completed + 1
            if is_int(max_rounds) and next_round > max_rounds:
                continue
            lane_coordinates.append(("DEBATE", candidate_id, next_round))

    control = state.get("mainline_control")
    revision = control.get("revision") if isinstance(control, dict) else None
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
    }
    dispatched = prior_dispatches_by_id(state)
    rejected = {
        product.get("packet_id")
        for product in state.get("rejected_work_products", [])
        if isinstance(product, dict)
        and nonempty_string(product.get("packet_id"))
    }
    resolved = set(accepted) | rejected
    lanes: list[dict[str, Any]] = []
    for phase, candidate_id, round_number in lane_coordinates:
        lane_dispatches = [
            (packet_id, dispatch)
            for packet_id, dispatch in dispatched.items()
            if dispatch.get("phase") == phase
            and dispatch.get("candidate_id") == candidate_id
            and dispatch.get("round") == round_number
        ]
        accepted_lane = [
            (packet_id, dispatch)
            for packet_id, dispatch in lane_dispatches
            if packet_id in accepted
        ]
        pending_lane = [
            packet_id
            for packet_id, _dispatch in lane_dispatches
            if packet_id not in resolved
        ]
        by_role: dict[str, list[str]] = {}
        for packet_id, dispatch in accepted_lane:
            role = dispatch.get("role")
            if nonempty_string(role):
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
            dependencies = [mentor[-1], evidence[-1], search[-1]]
        elif challenge and search_required and not search:
            next_role = "Search and Verification Specialist"
            dependencies = [challenge[-1]]
        elif challenge:
            next_role = "Panel Judge"
            dependencies = [mentor[-1], evidence[-1], challenge[-1]]
            if search:
                dependencies.append(search[-1])
        elif evidence:
            next_role = "Devil's Advocate"
            dependencies = [evidence[-1]]
        elif mentor:
            next_role = "Evidence Researcher"
            dependencies = [mentor[-1]]
        else:
            next_role = "Socratic Mentor"
            if round_number > 1:
                previous_judge = latest_accepted_dispatch_id(
                    state,
                    accepted,
                    phase=phase,
                    role="Panel Judge",
                    candidate_id=candidate_id,
                    round=round_number - 1,
                )
                if previous_judge is not None:
                    dependencies = [previous_judge]
            elif phase == "DEBATE":
                screening = latest_accepted_dispatch_id(
                    state,
                    accepted,
                    phase="SCREENING",
                )
                if screening is not None:
                    dependencies = [screening]
            else:
                positioning = latest_accepted_dispatch_id(
                    state,
                    accepted,
                    phase="EXTERNAL_POSITIONING",
                )
                if positioning is not None:
                    dependencies = [positioning]

        lanes.append(
            {
                "phase": phase,
                "candidate_id": candidate_id,
                "round": round_number,
                "last_resolved_role": (
                    accepted_lane[-1][1].get("role") if accepted_lane else None
                ),
                "next_role": next_role,
                "dependency_packet_ids": dependencies,
                "search_required": search_required,
                "lane_revision": revision,
            }
        )
    return lanes


def validate_lane_dispatches(
    dispatches: list[dict[str, Any]],
    control_input: dict[str, Any],
    action: Any,
    target_status: Any,
    checkpoint: Any,
    errors: list[str],
) -> None:
    lanes_value = control_input.get("active_lanes")
    lanes = (
        [lane for lane in lanes_value if isinstance(lane, dict)]
        if isinstance(lanes_value, list)
        else []
    )
    by_key = {
        tuple(
            key_component(component)
            for component in (
                lane.get("phase"),
                lane.get("candidate_id"),
                lane.get("round"),
            )
        ): lane
        for lane in lanes
    }
    dispatched_lane_keys: set[tuple[Any, ...]] = set()
    for index, dispatch in enumerate(dispatches):
        dispatch_phase = dispatch.get("phase")
        if (
            not isinstance(dispatch_phase, str)
            or dispatch_phase not in {"DEBATE", "EVALUATION_DEBATE"}
        ):
            continue
        key = tuple(
            key_component(component)
            for component in (
                dispatch.get("phase"),
                dispatch.get("candidate_id"),
                dispatch.get("round"),
            )
        )
        lane = by_key.get(key)
        location = f"controller-output.json.control_directive.dispatches[{index}]"
        if lane is None:
            errors.append(
                f"{location} has no matching authoritative active_lanes entry"
            )
            continue
        dispatched_lane_keys.add(key)
        if dispatch.get("role") != lane.get("next_role"):
            errors.append(
                f"{location}.role must equal authoritative next_role "
                f"{lane.get('next_role')!r}"
            )
        dependencies = dispatch.get("depends_on_packet_ids")
        required_dependencies = lane.get("dependency_packet_ids")
        if isinstance(dependencies, list) and isinstance(
            required_dependencies, list
        ):
            dependency_ids = {
                dependency
                for dependency in dependencies
                if isinstance(dependency, str)
            }
            required_dependency_ids = {
                dependency
                for dependency in required_dependencies
                if isinstance(dependency, str)
            }
            missing = sorted(required_dependency_ids - dependency_ids)
            if missing:
                errors.append(
                    f"{location}.depends_on_packet_ids omits authoritative "
                    f"lane dependencies {missing}"
                )

    if (
        action == "ADVANCE"
        and target_status in {"DEBATING", "EVALUATION_DEBATE"}
        and checkpoint in {
            "PHASE_BOUNDARY",
            "ROLE_BOUNDARY",
            "ROUND_BOUNDARY",
            "RESUME",
        }
    ):
        if checkpoint == "ROUND_BOUNDARY":
            ready_lane_keys = {
                key
                for key, lane in by_key.items()
                if lane.get("next_role") == "Socratic Mentor"
            }
        else:
            ready_lane_keys = {
                key
                for key, lane in by_key.items()
                if lane.get("next_role")
                not in {"WAIT_FOR_RESULT", "COMMIT_ROUND"}
                and not (
                    checkpoint == "ROLE_BOUNDARY"
                    and lane.get("next_role") == "Socratic Mentor"
                    and is_int(lane.get("round"))
                    and lane.get("round") > 1
                )
            }
        missing_lanes = sorted(
            ready_lane_keys - dispatched_lane_keys,
            key=lambda key: repr(key),
        )
        ineligible_lanes = sorted(
            dispatched_lane_keys - ready_lane_keys,
            key=lambda key: repr(key),
        )
        if missing_lanes:
            errors.append(
                "ADVANCE in a debate status must coalesce every ready "
                f"authoritative lane; missing {missing_lanes}"
            )
        if ineligible_lanes:
            errors.append(
                f"{checkpoint} dispatched lanes that are not eligible at this "
                f"barrier: {ineligible_lanes}"
            )
        if checkpoint == "ROUND_BOUNDARY":
            incomplete_lanes = [
                key
                for key, lane in by_key.items()
                if lane.get("next_role") != "Socratic Mentor"
            ]
            if incomplete_lanes:
                errors.append(
                    "ROUND_BOUNDARY requires every continuing lane to be ready "
                    f"for its next Mentor; incomplete {incomplete_lanes}"
                )


def validate_control_input(
    value: Any,
    state: dict[str, Any],
    state_digest: str,
    revision: int | None,
    accepted: dict[str, dict[str, Any]],
    rejected: dict[str, dict[str, Any]],
    errors: list[str],
) -> dict[str, Any]:
    location = "control-input.json"
    if not require_exact_keys(value, CONTROL_INPUT_KEYS, location, errors):
        if not isinstance(value, dict):
            return {}
    assert isinstance(value, dict)

    expected_scalars = {
        "control_revision": revision,
        "state_digest": state_digest,
        "observed_status": state.get("status"),
        "mode": state.get("mode"),
        "interaction_mode": state.get("interaction_mode"),
    }
    for field, expected in expected_scalars.items():
        if value.get(field) != expected:
            errors.append(f"{location}.{field} must equal {expected!r}")

    checkpoint = value.get("checkpoint")
    if not isinstance(checkpoint, str) or checkpoint not in CONTROL_CHECKPOINTS:
        errors.append(
            f"{location}.checkpoint must be one of "
            f"{sorted(CONTROL_CHECKPOINTS)}"
        )

    completed = validate_string_list(
        value.get("completed_packet_ids"),
        f"{location}.completed_packet_ids",
        errors,
    )
    expected_completed = {
        packet_id
        for packet_id, product in accepted.items()
        if product.get("phase") != "CONTROL"
    }
    if set(completed) != expected_completed:
        errors.append(
            f"{location}.completed_packet_ids must exactly match accepted "
            "research packets"
        )

    failed_value = value.get("failed_packets")
    failed_ids: set[str] = set()
    failed_reason_codes: set[str] = set()
    if not isinstance(failed_value, list):
        errors.append(f"{location}.failed_packets must be an array")
    else:
        for index, failed in enumerate(failed_value):
            failed_location = f"{location}.failed_packets[{index}]"
            if not require_exact_keys(
                failed,
                {
                    "packet_id",
                    "phase",
                    "role",
                    "candidate_id",
                    "round",
                    "reason_code",
                    "retry_count",
                },
                failed_location,
                errors,
            ):
                continue
            assert isinstance(failed, dict)
            packet_id = failed.get("packet_id")
            if not nonempty_string(packet_id) or not SAFE_ID.fullmatch(packet_id):
                errors.append(f"{failed_location}.packet_id is invalid")
                valid_packet_id = None
            else:
                failed_ids.add(packet_id)
                valid_packet_id = packet_id
            rejection = rejected.get(valid_packet_id)
            original_dispatch = prior_dispatches_by_id(state).get(valid_packet_id)
            if (
                not isinstance(original_dispatch, dict)
                or failed.get("phase") != original_dispatch.get("phase")
            ):
                errors.append(
                    f"{failed_location}.phase does not match the committed "
                    "dispatch"
                )
            for field in ("role", "candidate_id", "round", "reason_code"):
                if not isinstance(rejection, dict) or failed.get(field) != rejection.get(
                    field
                ):
                    errors.append(
                        f"{failed_location}.{field} does not match session state"
                    )
            reason_code = failed.get("reason_code")
            if nonempty_string(reason_code):
                failed_reason_codes.add(reason_code)
            retry_count = failed.get("retry_count")
            control = state.get("mainline_control")
            counts = (
                control.get("retry_counts")
                if isinstance(control, dict)
                and isinstance(control.get("retry_counts"), dict)
                else {}
            )
            if retry_count != counts.get(valid_packet_id, 0):
                errors.append(
                    f"{failed_location}.retry_count does not match session state"
                )
    expected_failed = {
        packet_id
        for packet_id, rejection in rejected.items()
        if rejection.get("role")
        not in {"Mainline Workflow Controller", "Deterministic Mainline Fallback"}
    }
    if failed_ids != expected_failed:
        errors.append(
            f"{location}.failed_packets must exactly match rejected research "
            "packets"
        )

    active_lanes = value.get("active_lanes")
    if not isinstance(active_lanes, list):
        errors.append(f"{location}.active_lanes must be an array")
    else:
        for index, lane in enumerate(active_lanes):
            lane_location = f"{location}.active_lanes[{index}]"
            if not require_exact_keys(
                lane,
                {
                    "phase",
                    "candidate_id",
                    "round",
                    "last_resolved_role",
                    "next_role",
                    "dependency_packet_ids",
                    "search_required",
                    "lane_revision",
                },
                lane_location,
                errors,
            ):
                continue
            assert isinstance(lane, dict)
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
                errors.append(
                    f"{lane_location}.round must be a positive integer"
                )
            if lane.get("last_resolved_role") is not None and not nonempty_string(
                lane.get("last_resolved_role")
            ):
                errors.append(
                    f"{lane_location}.last_resolved_role must be a string or null"
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
            validate_string_list(
                lane.get("dependency_packet_ids"),
                f"{lane_location}.dependency_packet_ids",
                errors,
            )
            if not isinstance(lane.get("search_required"), bool):
                errors.append(f"{lane_location}.search_required must be boolean")
            if not is_int(lane.get("lane_revision")):
                errors.append(f"{lane_location}.lane_revision must be integer")
        if active_lanes != expected_active_lanes(state, accepted):
            errors.append(
                f"{location}.active_lanes must exactly match eligible persisted "
                "debate lanes"
            )

    accepted_verdicts = value.get("accepted_verdicts")
    if not isinstance(accepted_verdicts, list):
        errors.append(f"{location}.accepted_verdicts must be an array")
    else:
        for index, verdict in enumerate(accepted_verdicts):
            verdict_location = f"{location}.accepted_verdicts[{index}]"
            if not require_exact_keys(
                verdict,
                {"candidate_id", "round", "verdict"},
                verdict_location,
                errors,
            ):
                continue
            assert isinstance(verdict, dict)
            if verdict.get("candidate_id") is not None and not nonempty_string(
                verdict.get("candidate_id")
            ):
                errors.append(
                    f"{verdict_location}.candidate_id must be a string or null"
                )
            if not is_int(verdict.get("round")) or verdict.get("round") < 1:
                errors.append(f"{verdict_location}.round must be positive integer")
            verdict_value = verdict.get("verdict")
            if not isinstance(verdict_value, str) or verdict_value not in {
                "CONTINUE",
                "SEARCH",
                "REVISE",
                "DOWNGRADE",
                "DEFER",
                "ELIMINATE",
                "USER_GATE",
                "CONVERGED",
            }:
                errors.append(f"{verdict_location}.verdict is invalid")

        expected_verdicts: list[dict[str, Any]] = []
        for candidate in state.get("candidates", []):
            if not isinstance(candidate, dict):
                continue
            for round_record in candidate.get("rounds", []):
                if isinstance(round_record, dict):
                    expected_verdicts.append(
                        {
                            "candidate_id": candidate.get("candidate_id"),
                            "round": round_record.get("round"),
                            "verdict": round_record.get("verdict"),
                        }
                    )
        for round_record in state.get("evaluation_rounds", []):
            if isinstance(round_record, dict):
                expected_verdicts.append(
                    {
                        "candidate_id": None,
                        "round": round_record.get("round"),
                        "verdict": round_record.get("verdict"),
                    }
                )
        if accepted_verdicts != expected_verdicts:
            errors.append(
                f"{location}.accepted_verdicts must exactly match persisted "
                "candidate and evaluation round verdicts"
            )

    readiness = value.get("artifact_readiness")
    if not isinstance(readiness, dict):
        errors.append(f"{location}.artifact_readiness must be an object")
    else:
        for artifact, readiness_value in readiness.items():
            if not nonempty_string(artifact) or not CODE.fullmatch(artifact):
                errors.append(
                    f"{location}.artifact_readiness key {artifact!r} is invalid"
                )
            if not isinstance(readiness_value, str) or readiness_value not in {
                "READY",
                "NOT_READY",
                "STALE",
                "UNRESOLVED",
            }:
                errors.append(
                    f"{location}.artifact_readiness[{artifact!r}] has an "
                    "invalid value"
                )

    latest_validation = value.get("latest_validation")
    validation_error_codes: list[str] = []
    if require_exact_keys(
        latest_validation,
        {"result", "error_codes"},
        f"{location}.latest_validation",
        errors,
    ):
        assert isinstance(latest_validation, dict)
        validation_result = latest_validation.get("result")
        if (
            not isinstance(validation_result, str)
            or validation_result not in {"PASS", "FAIL", "NOT_RUN"}
        ):
            errors.append(
                f"{location}.latest_validation.result must be PASS, FAIL, or "
                "NOT_RUN"
            )
        validation_error_codes = validate_string_list(
            latest_validation.get("error_codes"),
            f"{location}.latest_validation.error_codes",
            errors,
            code_values=True,
        )
        if (
            latest_validation.get("result") == "FAIL"
            and not validation_error_codes
        ):
            errors.append(
                f"{location}.latest_validation FAIL requires error_codes"
            )

    budget_flags = validate_string_list(
        value.get("budget_flags"),
        f"{location}.budget_flags",
        errors,
        code_values=True,
    )
    blockers = validate_string_list(
        value.get("unresolved_blockers"),
        f"{location}.unresolved_blockers",
        errors,
        code_values=True,
    )

    user_event = value.get("user_event")
    if require_exact_keys(
        user_event,
        {"kind", "receipt_id", "selected_ids"},
        f"{location}.user_event",
        errors,
    ):
        assert isinstance(user_event, dict)
        event_kind = user_event.get("kind")
        if (
            not isinstance(event_kind, str)
            or event_kind not in {"NONE"} | set(GATE_RECEIPT_ACTIONS)
        ):
            errors.append(f"{location}.user_event.kind is invalid")
        selected_ids = validate_string_list(
            user_event.get("selected_ids"),
            f"{location}.user_event.selected_ids",
            errors,
        )
        receipt_id = user_event.get("receipt_id")
        if event_kind == "NONE":
            if receipt_id is not None or selected_ids:
                errors.append(
                    f"{location}.user_event NONE requires null receipt and no "
                    "selected IDs"
                )
        else:
            receipts = state.get("gate_receipts")
            matches = [
                receipt
                for receipt in receipts
                if isinstance(receipts, list)
                and isinstance(receipt, dict)
                and receipt.get("receipt_id") == receipt_id
                and receipt.get("gate") == event_kind
            ] if isinstance(receipts, list) else []
            if len(matches) != 1:
                errors.append(
                    f"{location}.user_event must name one matching gate receipt"
                )
            elif matches[0].get("values") != selected_ids:
                errors.append(
                    f"{location}.user_event.selected_ids must equal receipt values"
                )

    mode = state.get("mode")
    statuses = EVALUATION_STATUSES if mode == "evaluate" else DISCOVERY_STATUSES
    allowed_targets = validate_string_list(
        value.get("allowed_target_statuses"),
        f"{location}.allowed_target_statuses",
        errors,
    )
    observed_status = state.get("status")
    transitions = (
        EVALUATION_TRANSITIONS if mode == "evaluate" else DISCOVERY_TRANSITIONS
    )
    legal_targets = transitions.get(observed_status, set())
    if any(target not in statuses or target not in legal_targets for target in allowed_targets):
        errors.append(
            f"{location}.allowed_target_statuses contains an illegal transition"
        )
    if not allowed_targets:
        errors.append(f"{location}.allowed_target_statuses must not be empty")

    value["_validated_blocking_codes"] = sorted(
        set(budget_flags)
        | set(blockers)
        | set(validation_error_codes)
        | failed_reason_codes
    )
    return value


def validate_directive(
    directive: Any,
    state: dict[str, Any],
    state_digest: str,
    revision: int | None,
    pending_gate: str | None,
    retry_counts: dict[str, int],
    controller_packet_id: str | None,
    accepted: dict[str, dict[str, Any]],
    rejected: dict[str, dict[str, Any]],
    control_input: dict[str, Any],
    errors: list[str],
) -> None:
    location = "controller-output.json.control_directive"
    if not require_exact_keys(directive, DIRECTIVE_KEYS, location, errors):
        if not isinstance(directive, dict):
            return
    assert isinstance(directive, dict)

    observed_revision = directive.get("observed_revision")
    if not is_int(observed_revision) or observed_revision < 0:
        errors.append(f"{location}.observed_revision must be a non-negative integer")
    elif revision is not None and observed_revision != revision:
        errors.append(
            f"{location}.observed_revision does not match the current "
            "mainline revision"
        )

    observed_digest = directive.get("observed_state_digest")
    if not isinstance(observed_digest, str) or not SHA256.fullmatch(observed_digest):
        errors.append(
            f"{location}.observed_state_digest must be a lowercase SHA-256 digest"
        )
    elif observed_digest != state_digest:
        errors.append(
            f"{location}.observed_state_digest does not match the current "
            "session-state.json bytes"
        )

    observed_status = directive.get("observed_status")
    if observed_status != state.get("status"):
        errors.append(
            f"{location}.observed_status does not match session-state.json.status"
        )
    if not isinstance(observed_status, str):
        observed_status = None

    checkpoint = directive.get("checkpoint")
    if not isinstance(checkpoint, str) or checkpoint not in CONTROL_CHECKPOINTS:
        errors.append(
            f"{location}.checkpoint must be one of {sorted(CONTROL_CHECKPOINTS)}"
        )
    if not isinstance(checkpoint, str):
        checkpoint = None
    if control_input and checkpoint != control_input.get("checkpoint"):
        errors.append(
            f"{location}.checkpoint does not match authoritative control input"
        )
    if revision == 0 and checkpoint != "SESSION_INIT":
        errors.append("Control revision 0 requires checkpoint SESSION_INIT")
    if revision != 0 and checkpoint == "SESSION_INIT":
        errors.append("SESSION_INIT is valid only at control revision 0")
    if checkpoint == "RESUME" and revision == 0:
        errors.append("RESUME requires an existing schema-1.3 control history")

    action = directive.get("action")
    if not isinstance(action, str) or action not in CONTROL_ACTIONS:
        errors.append(f"{location}.action must be one of {sorted(CONTROL_ACTIONS)}")
    if not isinstance(action, str):
        action = None
    if checkpoint == "PRE_USER_GATE" and action != "HOLD_FOR_USER":
        errors.append("PRE_USER_GATE requires action HOLD_FOR_USER")
    if checkpoint == "PRE_COMPLETE" and action != "COMPLETE":
        errors.append("PRE_COMPLETE requires action COMPLETE")
    if action == "COMPLETE" and checkpoint != "PRE_COMPLETE":
        errors.append("COMPLETE requires checkpoint PRE_COMPLETE")
    if checkpoint == "ROUND_BOUNDARY" and observed_status not in {
        "DEBATING",
        "EVALUATION_DEBATE",
    }:
        errors.append(
            "ROUND_BOUNDARY is valid only in discovery or evaluation debate status"
        )
    if checkpoint == "ROLE_BOUNDARY" and observed_status not in {
        "DEBATING",
        "EVALUATION_DEBATE",
    }:
        errors.append(
            "ROLE_BOUNDARY is valid only in discovery or evaluation debate status"
        )

    mode = state.get("mode")
    target_status = directive.get("target_status")
    statuses = EVALUATION_STATUSES if mode == "evaluate" else DISCOVERY_STATUSES
    transitions = EVALUATION_TRANSITIONS if mode == "evaluate" else DISCOVERY_TRANSITIONS
    if not isinstance(target_status, str) or target_status not in statuses:
        errors.append(
            f"{location}.target_status {target_status!r} is not valid in mode "
            f"{mode!r}"
        )
    elif (
        isinstance(observed_status, str)
        and observed_status in transitions
        and target_status not in transitions[observed_status]
    ):
        errors.append(
            f"{location}: transition {observed_status!r} -> {target_status!r} "
            "is not legal"
        )
    if not isinstance(target_status, str):
        target_status = None
    if target_status == "BLOCKED" and action != "BLOCK_SESSION":
        errors.append("Only BLOCK_SESSION may target BLOCKED")
    if target_status == "COMPLETE" and action != "COMPLETE":
        errors.append("Only COMPLETE may target COMPLETE")
    if control_input and target_status not in control_input.get(
        "allowed_target_statuses", []
    ):
        errors.append(
            f"{location}.target_status is absent from authoritative "
            "allowed_target_statuses"
        )

    proposed_gate = directive.get("pending_user_gate")
    if proposed_gate is not None and (
        not isinstance(proposed_gate, str)
        or proposed_gate not in PENDING_USER_GATES
    ):
        errors.append(
            f"{location}.pending_user_gate must be null or one of "
            f"{sorted(PENDING_USER_GATES)}"
        )
    if not isinstance(proposed_gate, str):
        proposed_gate = None

    raw_retry_key = directive.get("retry_key")
    dispatches = validate_dispatches(
        directive.get("dispatches"),
        state,
        controller_packet_id,
        action,
        raw_retry_key,
        target_status,
        checkpoint,
        directive.get("reason_codes"),
        accepted,
        rejected,
        errors,
    )
    validate_lane_dispatches(
        dispatches,
        control_input,
        action,
        target_status,
        checkpoint,
        errors,
    )
    required_actions = validate_string_list(
        directive.get("required_actions"),
        f"{location}.required_actions",
        errors,
        code_values=True,
    )
    required_checks = validate_string_list(
        directive.get("required_checks"),
        f"{location}.required_checks",
        errors,
        code_values=True,
    )
    reason_codes = validate_string_list(
        directive.get("reason_codes"),
        f"{location}.reason_codes",
        errors,
        code_values=True,
    )
    blocking_reasons = validate_string_list(
        directive.get("blocking_reasons"),
        f"{location}.blocking_reasons",
        errors,
        code_values=True,
    )
    retry_key = raw_retry_key

    unknown_actions = sorted(set(required_actions) - CONTROL_REQUIRED_ACTIONS)
    if unknown_actions:
        errors.append(
            f"{location}.required_actions contains unsupported actions "
            f"{unknown_actions}"
        )
    unknown_checks = sorted(set(required_checks) - CONTROL_REQUIRED_CHECKS)
    if unknown_checks:
        errors.append(
            f"{location}.required_checks contains unsupported checks "
            f"{unknown_checks}"
        )

    readiness = control_input.get("artifact_readiness")
    readiness = readiness if isinstance(readiness, dict) else {}
    for dispatch in dispatches:
        dispatch_phase = dispatch.get("phase")
        phase_requirements = DISPATCH_ARTIFACT_REQUIREMENTS.get(
            dispatch_phase if isinstance(dispatch_phase, str) else None,
            set(),
        )
        not_ready = sorted(
            artifact
            for artifact in phase_requirements
            if readiness.get(artifact) != "READY"
        )
        if not_ready:
            errors.append(
                "controller-output.json.control_directive dispatch phase "
                f"{dispatch.get('phase')!r} requires READY artifacts {not_ready}"
            )

    if revision == 0:
        expected_init_action = (
            "BUILD_EVALUATION_INPUT_SNAPSHOT"
            if state.get("mode") == "evaluate"
            else "BUILD_PROJECT_EVIDENCE_PACK"
        )
        if required_actions != [expected_init_action]:
            errors.append(
                f"SESSION_INIT must require exactly {expected_init_action}"
            )
        if dispatches:
            errors.append(
                "SESSION_INIT must build the evidence pack before any role dispatch"
            )

    user_event = (
        control_input.get("user_event")
        if isinstance(control_input.get("user_event"), dict)
        else {}
    )
    receipt = None
    receipts = state.get("gate_receipts")
    if isinstance(receipts, list) and nonempty_string(user_event.get("receipt_id")):
        receipt = next(
            (
                candidate
                for candidate in receipts
                if isinstance(candidate, dict)
                and candidate.get("receipt_id") == user_event.get("receipt_id")
            ),
            None,
        )
    for required_action in required_actions:
        applicable = True
        if required_action == "BUILD_PROJECT_EVIDENCE_PACK":
            applicable = (
                state.get("mode") != "evaluate"
                and checkpoint == "SESSION_INIT"
                and action == "ADVANCE"
            )
        elif required_action == "BUILD_EVALUATION_INPUT_SNAPSHOT":
            applicable = (
                state.get("mode") == "evaluate"
                and checkpoint == "SESSION_INIT"
                and action == "ADVANCE"
            )
        elif required_action == "APPLY_USER_DIRECTION_SELECTION":
            applicable = (
                action == "ADVANCE"
                and state.get("mode") == "discover"
                and checkpoint == "POST_USER_GATE"
                and isinstance(receipt, dict)
                and receipt.get("gate") == "DIRECTION_SELECTION"
                and receipt.get("action") == "SELECT"
            )
        elif required_action == "APPLY_PANEL_DIRECTION_SELECTION":
            applicable = (
                action == "ADVANCE"
                and checkpoint in {"PHASE_BOUNDARY", "POST_USER_GATE"}
                and any(
                    product.get("phase") == "DIRECTION_SELECTION"
                    for product in accepted.values()
                )
                and (
                    state.get("interaction_mode") == "AUTONOMOUS"
                    or has_delegated_direction_selection_product(
                        state,
                        accepted,
                    )
                )
            )
        elif required_action == "APPLY_CANDIDATE_SELECTION":
            applicable = (
                action == "ADVANCE"
                and checkpoint == "POST_USER_GATE"
                and isinstance(receipt, dict)
                and receipt.get("gate") == "CANDIDATE_SELECTION"
                and receipt.get("action") == "SELECT"
            )
        elif required_action == "APPLY_RQ_CONFIRMATION":
            applicable = (
                action == "ADVANCE"
                and checkpoint == "POST_USER_GATE"
                and isinstance(receipt, dict)
                and receipt.get("gate") == "RQ_CONFIRMATION"
                and receipt.get("action") == "CONFIRM"
            )
        elif required_action == "APPLY_RQ_REVISION":
            applicable = (
                action == "ADVANCE"
                and checkpoint == "POST_USER_GATE"
                and isinstance(receipt, dict)
                and receipt.get("gate") == "RQ_CONFIRMATION"
                and receipt.get("action") == "REVISE"
            )
        elif required_action == "APPLY_EVALUATION_DECISION":
            applicable = (
                action == "ADVANCE"
                and checkpoint == "POST_USER_GATE"
                and isinstance(receipt, dict)
                and receipt.get("gate") == "EVALUATION_DECISION"
                and receipt.get("action") in {"CONFIRM", "OVERRIDE"}
            )
        elif required_action == "APPLY_USER_REPAIR":
            blocked_at = blocking_entry_transition(state)
            applicable = (
                action == "ADVANCE"
                and state.get("status") == "BLOCKED"
                and isinstance(blocked_at, dict)
                and isinstance(receipt, dict)
                and receipt.get("gate") == "BLOCKER_DECISION"
                and receipt.get("action") == "REPAIR"
                and receipt.get("based_on_revision") == blocked_at.get("revision")
            )
        elif required_action in {
            "REPAIR_ARTIFACT_METADATA",
            "REPAIR_SESSION_STATE",
        }:
            applicable = action == "REPAIR_STATE" and checkpoint == "RECOVERY"
        elif required_action == "RECORD_UNRESOLVED_BLOCKER":
            applicable = action == "BLOCK_SESSION"
        if not applicable:
            errors.append(
                f"{location}.required_action {required_action!r} is not "
                "applicable to this state, checkpoint, and receipt"
            )
    if not reason_codes:
        errors.append(f"{location}.reason_codes must contain at least one code")
    if "PERSIST_STATE" not in required_checks:
        errors.append(f"{location}.required_checks must include PERSIST_STATE")
    if dispatches:
        for check in ("VERIFY_ENVELOPES", "ENFORCE_BUDGET"):
            if check not in required_checks:
                errors.append(
                    f"{location}.required_checks must include {check} when "
                    "dispatches are scheduled"
                )
    if (
        checkpoint == "POST_USER_GATE"
        and "VERIFY_GATE_RECEIPT" not in required_checks
    ):
        errors.append("POST_USER_GATE requires VERIFY_GATE_RECEIPT")

    if action == "ADVANCE":
        if not dispatches and not required_actions:
            errors.append(
                "ADVANCE requires at least one dispatch or deterministic "
                "required_action"
            )
        if proposed_gate is not None:
            errors.append("ADVANCE requires pending_user_gate to be null")
        if retry_key is not None:
            errors.append("ADVANCE requires retry_key to be null")
        if blocking_reasons:
            errors.append("ADVANCE requires blocking_reasons to be empty")

    elif action == "HOLD_FOR_USER":
        if dispatches:
            errors.append("HOLD_FOR_USER must not schedule dispatches")
        if proposed_gate not in PENDING_USER_GATES:
            errors.append("HOLD_FOR_USER requires a pending_user_gate")
        elif target_status != GATE_TARGETS[proposed_gate]:
            errors.append(
                f"HOLD_FOR_USER gate {proposed_gate!r} requires target_status "
                f"{GATE_TARGETS[proposed_gate]!r}"
            )
        if proposed_gate == "EVALUATION_DECISION" and mode != "evaluate":
            errors.append("EVALUATION_DECISION gate is valid only in evaluate mode")
        if proposed_gate != "EVALUATION_DECISION" and mode == "evaluate":
            errors.append(
                f"{proposed_gate!r} is not a valid user gate in evaluate mode"
            )
        if proposed_gate == "DIRECTION_SELECTION" and mode != "discover":
            errors.append("DIRECTION_SELECTION gate is valid only in discover mode")
        if (
            proposed_gate == "DIRECTION_SELECTION"
            and state.get("interaction_mode") != "GUIDED"
        ):
            errors.append(
                "DIRECTION_SELECTION gate requires interaction_mode GUIDED"
            )
        if proposed_gate == "RQ_CONFIRMATION":
            selected_candidate_id = state.get("selected_candidate_id")
            latest_rq_packet = None
            unresolved_rq_packets: list[str] = []
            if nonempty_string(selected_candidate_id):
                (
                    _latest_dispatched_rq,
                    latest_rq_packet,
                    unresolved_rq_packets,
                ) = rq_dispatch_resolution(
                    state,
                    accepted,
                    rejected,
                    selected_candidate_id,
                )
            if unresolved_rq_packets:
                errors.append(
                    "RQ_CONFIRMATION cannot open while the latest RQ replacement "
                    f"is unresolved: {unresolved_rq_packets}"
                )
            if latest_rq_packet is None:
                errors.append(
                    "RQ_CONFIRMATION requires the latest dispatched "
                    "RQ_REFINEMENT/Research Question Architect product to be "
                    "accepted"
                )
        if retry_key is not None:
            errors.append("HOLD_FOR_USER requires retry_key to be null")
        if blocking_reasons:
            errors.append("HOLD_FOR_USER requires blocking_reasons to be empty")
        if "RUN_SESSION_VALIDATOR" not in required_checks:
            errors.append(
                "HOLD_FOR_USER requires RUN_SESSION_VALIDATOR in required_checks"
            )

    elif action == "REPAIR_STATE":
        if dispatches:
            errors.append("REPAIR_STATE must not schedule dispatches")
        if target_status != observed_status:
            errors.append("REPAIR_STATE must remain at the observed status")
        if not required_actions:
            errors.append("REPAIR_STATE requires at least one required_action")
        unsupported_repair_actions = sorted(
            set(required_actions)
            - {"REPAIR_ARTIFACT_METADATA", "REPAIR_SESSION_STATE"}
        )
        if unsupported_repair_actions:
            errors.append(
                "REPAIR_STATE contains non-repair actions "
                f"{unsupported_repair_actions}"
            )
        if proposed_gate is not None:
            errors.append("REPAIR_STATE requires pending_user_gate to be null")
        if retry_key is not None:
            errors.append("REPAIR_STATE requires retry_key to be null")
        if blocking_reasons:
            errors.append("REPAIR_STATE requires blocking_reasons to be empty")

    elif action == "RETRY_ROLE":
        if len(dispatches) != 1:
            errors.append("RETRY_ROLE must schedule exactly one dispatch")
        if target_status != observed_status:
            errors.append("RETRY_ROLE must remain at the observed status")
        if proposed_gate is not None:
            errors.append("RETRY_ROLE requires pending_user_gate to be null")
        if blocking_reasons:
            errors.append("RETRY_ROLE requires blocking_reasons to be empty")
        validate_retry(
            retry_key,
            dispatches,
            state,
            rejected,
            retry_counts,
            errors,
        )

    elif action == "BLOCK_SESSION":
        if dispatches:
            errors.append("BLOCK_SESSION must not schedule dispatches")
        if target_status != "BLOCKED":
            errors.append("BLOCK_SESSION requires target_status BLOCKED")
        if observed_status == "BLOCKED":
            errors.append(
                "A BLOCKED session cannot append another BLOCK_SESSION "
                "transition"
            )
        if proposed_gate is not None:
            errors.append("BLOCK_SESSION requires pending_user_gate to be null")
        if not blocking_reasons:
            errors.append(
                "BLOCK_SESSION requires at least one explicit blocking reason code"
            )
        authoritative_blockers = set(
            control_input.get("_validated_blocking_codes", [])
        )
        unsupported_blockers = sorted(
            set(blocking_reasons) - authoritative_blockers
        )
        if unsupported_blockers:
            errors.append(
                "BLOCK_SESSION blocking_reasons are absent from the "
                f"authoritative control input {unsupported_blockers}"
            )
        if retry_key is not None:
            errors.append("BLOCK_SESSION requires retry_key to be null")

    elif action == "COMPLETE":
        if dispatches:
            errors.append("COMPLETE must not schedule dispatches")
        if target_status != "COMPLETE":
            errors.append("COMPLETE requires target_status COMPLETE")
        if proposed_gate is not None:
            errors.append("COMPLETE requires pending_user_gate to be null")
        if blocking_reasons:
            errors.append("COMPLETE requires blocking_reasons to be empty")
        if retry_key is not None:
            errors.append("COMPLETE requires retry_key to be null")
        if "RUN_SESSION_VALIDATOR" not in required_checks:
            errors.append("COMPLETE requires RUN_SESSION_VALIDATOR")
        validate_completion(state, required_actions, errors)

    if pending_gate is not None:
        if action == "HOLD_FOR_USER":
            if proposed_gate != pending_gate:
                errors.append(
                    "HOLD_FOR_USER cannot replace an unresolved pending user gate"
                )
            errors.append(
                "An unresolved user gate must remain at its current revision; "
                "do not append another HOLD_FOR_USER"
            )
        elif action != "BLOCK_SESSION" and revision is not None:
            receipt = matching_gate_receipt(state, pending_gate, revision, errors)
            if receipt is not None:
                receipt_action = receipt.get("action")
                allowed_targets = RECEIPT_TARGETS.get(
                    (pending_gate, receipt_action),
                    set(),
                )
                if target_status not in allowed_targets:
                    errors.append(
                        f"{pending_gate}/{receipt_action} receipt does not permit "
                        f"target_status {target_status!r}"
                    )
                dispatch_phases = [
                    dispatch.get("phase") for dispatch in dispatches
                ]
                if pending_gate == "DIRECTION_SELECTION":
                    if (
                        receipt_action == "REVISE"
                        and dispatch_phases != ["DIRECTION_MAPPING"]
                    ):
                        errors.append(
                            "DIRECTION_SELECTION/REVISE requires exactly one "
                            "DIRECTION_MAPPING dispatch"
                        )
                    if (
                        receipt_action == "DELEGATE"
                        and dispatch_phases != ["DIRECTION_SELECTION"]
                    ):
                        errors.append(
                            "DIRECTION_SELECTION/DELEGATE requires exactly one "
                            "DIRECTION_SELECTION Panel Judge dispatch"
                        )
                    if (
                        receipt_action == "SELECT"
                        and "DIRECTION_SELECTION" in dispatch_phases
                    ):
                        errors.append(
                            "DIRECTION_SELECTION/SELECT must not dispatch a "
                            "Panel Judge to replace the user's choice"
                        )
                if pending_gate == "RQ_CONFIRMATION":
                    selected_candidate_id = state.get("selected_candidate_id")
                    confirmed_packet_id = None
                    unresolved_rq_packets: list[str] = []
                    if nonempty_string(selected_candidate_id):
                        (
                            _latest_dispatched_rq,
                            confirmed_packet_id,
                            unresolved_rq_packets,
                        ) = rq_dispatch_resolution(
                            state,
                            accepted,
                            rejected,
                            selected_candidate_id,
                        )
                    if unresolved_rq_packets:
                        errors.append(
                            "RQ_CONFIRMATION cannot consume a receipt while an "
                            f"RQ replacement is unresolved: {unresolved_rq_packets}"
                        )
                    if receipt_action == "CONFIRM":
                        expected_values = [
                            selected_candidate_id,
                            confirmed_packet_id,
                        ]
                        if receipt.get("values") != expected_values:
                            errors.append(
                                "RQ_CONFIRMATION/CONFIRM values must bind the "
                                "selected candidate and latest accepted RQ packet"
                            )
                        if (
                            action != "ADVANCE"
                            or target_status != "RQ_REFINEMENT"
                            or dispatches
                            or required_actions != ["APPLY_RQ_CONFIRMATION"]
                        ):
                            errors.append(
                                "RQ_CONFIRMATION/CONFIRM requires one no-dispatch "
                                "POST_USER_GATE ADVANCE with exactly "
                                "APPLY_RQ_CONFIRMATION"
                            )
                    elif receipt_action == "REVISE":
                        rq_dispatches = [
                            dispatch
                            for dispatch in dispatches
                            if dispatch.get("phase") == "RQ_REFINEMENT"
                            and dispatch.get("role")
                            == "Research Question Architect"
                        ]
                        if (
                            action != "ADVANCE"
                            or target_status != "RQ_REFINEMENT"
                            or len(dispatches) != 1
                            or len(rq_dispatches) != 1
                            or required_actions != ["APPLY_RQ_REVISION"]
                        ):
                            errors.append(
                                "RQ_CONFIRMATION/REVISE requires exactly "
                                "APPLY_RQ_REVISION and one replacement Research "
                                "Question Architect dispatch"
                            )
            if checkpoint != "POST_USER_GATE":
                errors.append(
                    "Leaving a pending user gate requires checkpoint "
                    "POST_USER_GATE"
                )
    elif checkpoint == "POST_USER_GATE":
        errors.append(
            "POST_USER_GATE requires an unresolved pending gate in the current "
            "state"
        )

    prior_transition_log_value = state.get("mainline_control")
    prior_transition_log = (
        prior_transition_log_value.get("transition_log")
        if isinstance(prior_transition_log_value, dict)
        and isinstance(prior_transition_log_value.get("transition_log"), list)
        else []
    )
    if (
        prior_transition_log
        and isinstance(prior_transition_log[-1], dict)
        and prior_transition_log[-1].get("required_actions")
        == ["APPLY_RQ_CONFIRMATION"]
        and not (
            action == "COMPLETE"
            and checkpoint == "PRE_COMPLETE"
            and target_status == "COMPLETE"
        )
    ):
        errors.append(
            "The transition after APPLY_RQ_CONFIRMATION must be "
            "PRE_COMPLETE/COMPLETE"
        )

    if checkpoint == "POST_USER_GATE" and user_event.get("kind") != pending_gate:
        errors.append(
            "POST_USER_GATE control input must carry the current gate receipt"
        )
    if checkpoint == "RECOVERY":
        latest_validation = control_input.get("latest_validation")
        has_recovery_event = bool(
            control_input.get("failed_packets")
            or control_input.get("budget_flags")
            or control_input.get("unresolved_blockers")
            or (
                isinstance(latest_validation, dict)
                and latest_validation.get("result") == "FAIL"
            )
            or observed_status == "BLOCKED"
        )
        if not has_recovery_event:
            errors.append(
                "RECOVERY requires a failure, budget flag, blocker, failed "
                "validation, or BLOCKED state in control input"
            )
    control = state.get("mainline_control")
    transitions_log = (
        control.get("transition_log")
        if isinstance(control, dict)
        and isinstance(control.get("transition_log"), list)
        else []
    )
    latest_dispatches = (
        transitions_log[-1].get("dispatches")
        if transitions_log
        and isinstance(transitions_log[-1], dict)
        and isinstance(transitions_log[-1].get("dispatches"), list)
        else []
    )
    resolved_packet_ids = set(accepted) | set(rejected)
    if checkpoint == "ROLE_BOUNDARY":
        if not latest_dispatches or not any(
            isinstance(dispatch, dict)
            and dispatch.get("packet_id") in resolved_packet_ids
            for dispatch in latest_dispatches
        ):
            errors.append(
                "ROLE_BOUNDARY requires at least one resolved dispatch from "
                "the latest committed controller batch"
            )
    if checkpoint == "ROUND_BOUNDARY":
        active_lanes = control_input.get("active_lanes")
        incomplete_lane_keys = [
            (
                lane.get("phase"),
                lane.get("candidate_id"),
                lane.get("round"),
            )
            for lane in active_lanes
            if isinstance(active_lanes, list)
            and isinstance(lane, dict)
            and lane.get("next_role") != "Socratic Mentor"
        ] if isinstance(active_lanes, list) else []
        if incomplete_lane_keys:
            errors.append(
                "ROUND_BOUNDARY requires every continuing active lane to be "
                f"ready for its next Mentor; incomplete {incomplete_lane_keys}"
            )
        latest_judge_ids = [
            dispatch.get("packet_id")
            for dispatch in latest_dispatches
            if isinstance(dispatch, dict)
            and dispatch.get("role") == "Panel Judge"
            and dispatch.get("phase") in {"DEBATE", "EVALUATION_DEBATE"}
        ]
        if (
            not latest_judge_ids
            or any(packet_id not in accepted for packet_id in latest_judge_ids)
        ):
            errors.append(
                "ROUND_BOUNDARY requires accepted Judge outputs from the "
                "latest committed controller batch"
            )
        unresolved_dispatch_ids = [
            dispatch.get("packet_id")
            for transition in transitions_log
            if isinstance(transition, dict)
            and isinstance(transition.get("dispatches"), list)
            for dispatch in transition["dispatches"]
            if isinstance(dispatch, dict)
            and dispatch.get("packet_id") not in resolved_packet_ids
        ]
        if unresolved_dispatch_ids:
            errors.append(
                "ROUND_BOUNDARY requires all committed research dispatches to "
                f"be resolved; pending {sorted(unresolved_dispatch_ids)}"
            )
        if not control_input.get("accepted_verdicts"):
            errors.append(
                "ROUND_BOUNDARY requires accepted_verdicts in control input"
            )

    if observed_status == "BLOCKED" and action != "BLOCK_SESSION":
        blocked_at = blocking_entry_transition(state)
        blocked_revision = (
            blocked_at.get("revision") if isinstance(blocked_at, dict) else None
        )
        if not is_int(blocked_revision):
            errors.append(
                "A BLOCKED session must retain the BLOCK_SESSION transition "
                "that began its current blocking episode"
            )
        else:
            receipt = matching_gate_receipt(
                state,
                "BLOCKER_DECISION",
                blocked_revision,
                errors,
            )
            if receipt is not None:
                receipt_action = receipt.get("action")
                resume_status = blocked_at.get("from_status")
                resume_gate = blocking_resume_gate(state, blocked_at)
                if receipt_action == "STOP":
                    errors.append(
                        "BLOCKER_DECISION/STOP keeps the session BLOCKED and "
                        "does not permit another controller transition"
                    )
                else:
                    if receipt.get("values") != [resume_status]:
                        errors.append(
                            "BLOCKER_DECISION/REPAIR values must contain the "
                            "status that entered the blocking episode"
                        )
                    if target_status != resume_status:
                        errors.append(
                            "BLOCKER_DECISION/REPAIR must resume the status "
                            "that entered the blocking episode"
                        )
                    if resume_gate is None:
                        if action != "ADVANCE":
                            errors.append(
                                "Leaving BLOCKED after BLOCKER_DECISION/REPAIR "
                                "requires action ADVANCE"
                            )
                    else:
                        if action != "HOLD_FOR_USER":
                            errors.append(
                                "Repairing a blocker that interrupted a user "
                                "gate must reopen it with HOLD_FOR_USER"
                            )
                        if proposed_gate != resume_gate:
                            errors.append(
                                "The reopened user gate does not match the gate "
                                "interrupted by BLOCK_SESSION"
                            )
                    if checkpoint not in {"RECOVERY", "RESUME"}:
                        errors.append(
                            "Leaving BLOCKED requires checkpoint RECOVERY or "
                            "RESUME"
                        )


def validate(
    state_path: Path,
    output_path: Path,
    control_input_path: Path | None = None,
) -> tuple[list[str], bytes | None]:
    errors: list[str] = []
    if control_input_path is None:
        control_input_path = output_path.with_name("control-input.json")
    state_raw = read_file(state_path, "session-state.json", errors)
    control_input_raw = read_file(
        control_input_path,
        "control-input.json",
        errors,
    )
    output_raw = read_file(output_path, "controller-output.json", errors)
    if state_raw is None or control_input_raw is None or output_raw is None:
        return errors, state_raw

    state_digest = hashlib.sha256(state_raw).hexdigest()
    control_input_digest = hashlib.sha256(control_input_raw).hexdigest()
    state_value = parse_json_bytes(state_raw, "session-state.json", errors)
    control_input_value = parse_json_bytes(
        control_input_raw,
        "control-input.json",
        errors,
    )
    output_value = parse_json_bytes(output_raw, "controller-output.json", errors)
    if not isinstance(state_value, dict):
        if state_value is not None:
            errors.append("session-state.json must contain a JSON object")
        return errors, state_raw
    state = state_value

    if state.get("schema_version") != "1.3":
        errors.append("session-state.json.schema_version must be exactly '1.3'")
    for field in ("session_id", "project_root", "project_snapshot"):
        if not nonempty_string(state.get(field)):
            errors.append(f"session-state.json.{field} must be a non-empty string")

    mode = state.get("mode")
    if (
        not isinstance(mode, str)
        or mode not in {"discover", "refine", "rq-only", "evaluate"}
    ):
        errors.append(
            "session-state.json.mode must be discover, refine, rq-only, or evaluate"
        )
    status = state.get("status")
    valid_statuses = EVALUATION_STATUSES if mode == "evaluate" else DISCOVERY_STATUSES
    if not isinstance(status, str) or status not in valid_statuses:
        errors.append(
            f"session-state.json.status {status!r} is not valid in mode {mode!r}"
        )

    accepted, rejected = collect_work_products(state, errors)
    revision, retry_counts, pending_gate = validate_mainline_state(state, errors)
    validate_resolved_dispatch_bindings(state, accepted, rejected, errors)
    validate_lane_search_bindings(state, accepted, errors)
    control_input = validate_control_input(
        control_input_value,
        state,
        state_digest,
        revision,
        accepted,
        rejected,
        errors,
    )

    if not require_exact_keys(
        output_value,
        {"envelope", "control_directive"},
        "controller-output.json",
        errors,
    ):
        if not isinstance(output_value, dict):
            return errors, state_raw
    assert isinstance(output_value, dict)

    controller_packet_id = validate_envelope(
        output_value.get("envelope"),
        state,
        state_digest,
        control_input_digest,
        revision,
        set(accepted) | set(rejected),
        errors,
    )
    validate_directive(
        output_value.get("control_directive"),
        state,
        state_digest,
        revision,
        pending_gate,
        retry_counts,
        controller_packet_id,
        accepted,
        rejected,
        control_input,
        errors,
    )

    try:
        final_state_raw = state_path.read_bytes()
    except OSError as exc:
        errors.append(
            f"session-state.json: cannot re-read file for stale-state check: {exc}"
        )
    else:
        if final_state_raw != state_raw:
            errors.append(
                "session-state.json changed while the controller decision was "
                "being validated"
            )
    try:
        final_control_input_raw = control_input_path.read_bytes()
    except OSError as exc:
        errors.append(
            f"control-input.json: cannot re-read file for stale-input check: {exc}"
        )
    else:
        if final_control_input_raw != control_input_raw:
            errors.append(
                "control-input.json changed while the controller decision was "
                "being validated"
            )

    return errors, state_raw


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Validate a strict Mainline Workflow Controller JSON directive "
            "against the exact current session-state.json bytes."
        )
    )
    parser.add_argument(
        "session_state",
        type=Path,
        help="path to the current schema-1.3 session-state.json",
    )
    parser.add_argument(
        "controller_output",
        type=Path,
        help="path to the controller's strict JSON output",
    )
    parser.add_argument(
        "--control-input",
        type=Path,
        help=(
            "path to the authoritative control input JSON; defaults to "
            "control-input.json beside controller_output"
        ),
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    errors, state_raw = validate(
        args.session_state,
        args.controller_output,
        args.control_input,
    )
    if errors:
        print(
            "FAIL: controller directive validation failed with "
            f"{len(errors)} error(s)"
        )
        for error in errors:
            print(f"- {error}")
        return 1

    revision_text = "unknown"
    session_text = "unknown"
    if state_raw is not None:
        state = parse_json_bytes(state_raw, "session-state.json", [])
        if isinstance(state, dict):
            session_text = str(state.get("session_id", "unknown"))
            control = state.get("mainline_control")
            if isinstance(control, dict):
                revision_text = str(control.get("revision", "unknown"))
    print(
        "PASS: controller directive is valid for "
        f"session {session_text!r} at revision {revision_text}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
