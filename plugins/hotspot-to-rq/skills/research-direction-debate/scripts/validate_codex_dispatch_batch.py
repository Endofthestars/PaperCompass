#!/usr/bin/env python3
"""Verify that every controller role dispatch has a final persisted Codex packet.

Run this after validate_controller_decision.py and all build_codex_dispatch.py
calls, but before committing the controller transition. This closes the gap
between a valid logical directive and transport packets that can be retried
byte-for-byte after interruption.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import sys
import tempfile
from pathlib import Path
from typing import Any


_SCRIPTS_DIR = Path(__file__).resolve().parent


def _load_module(name: str, filename: str) -> Any:
    spec = importlib.util.spec_from_file_location(name, _SCRIPTS_DIR / filename)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load {filename} from {_SCRIPTS_DIR}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


dispatch_builder = _load_module(
    "hotspot_build_codex_dispatch_for_batch",
    "build_codex_dispatch.py",
)
capsules = dispatch_builder.capsules
controller_validator = _load_module(
    "hotspot_validate_controller_decision_for_codex_batch",
    "validate_controller_decision.py",
)

BATCH_MANIFEST_SCHEMA_VERSION = "codex-dispatch-batch-1"
MANIFEST_KEYS = {
    "schema_version",
    "controller_packet_id",
    "checkpoint",
    "controller_inputs",
    "dispatches",
}
INPUT_LABELS = {
    "session-state.json",
    "control-input.json",
    "controller-output.json",
}
INPUT_SUFFIXES = {
    "session-state.json": "session-state.json",
    "control-input.json": "control-input.json",
    "controller-output.json": "controller-output.json",
}
FILE_RECORD_KEYS = {"path", "sha256"}
DISPATCH_RECORD_KEYS = {
    "packet_id",
    "phase",
    "role",
    "candidate_id",
    "round",
    "packet_path",
    "packet_sha256",
    "capsule_path",
    "capsule_sha256",
}
READY_RECEIPT_SCHEMA_VERSION = "codex-dispatch-batch-ready-1"
READY_RECEIPT_KEYS = {
    "schema_version",
    "controller_packet_id",
    "manifest_sha256",
}


class BatchError(ValueError):
    """Raised when a controller batch is not ready for state commit."""


def list_or_empty(value: Any) -> list[Any]:
    """Treat malformed state collections as empty after full validation reports them."""
    return value if isinstance(value, list) else []


def sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def serialize_manifest(value: dict[str, Any]) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def live_snapshot_errors(
    session_root: Any,
    snapshot_paths: dict[str, str],
    snapshots: dict[str, bytes],
) -> list[str]:
    errors: list[str] = []
    try:
        for label, relative_path in snapshot_paths.items():
            current, _relative = capsules.read_session_artifact(
                session_root,
                relative_path,
            )
            if current != snapshots[label]:
                errors.append(
                    f"{label} changed while the Codex dispatch batch was validated"
                )
    except (capsules.CapsuleError, OSError) as error:
        errors.append(str(error))
    return errors


def validate_batch_manifest(
    session_dir: Any,
    controller_packet_id: str,
    packet_id: str | None = None,
) -> list[str]:
    try:
        capsules.validate_safe_id(controller_packet_id, "controller_packet_id")
        with capsules.session_scope(session_dir) as root:
            errors = validate_committed_controller_transition(
                root,
                controller_packet_id,
                packet_id,
            )
            capture_errors, captured_packets = capture_ready_manifest_packets(
                root,
                controller_packet_id,
            )
            errors.extend(capture_errors)
            if packet_id is not None and packet_id not in captured_packets:
                errors.append("target packet is absent from the ready batch manifest")
            errors.extend(
                validate_committed_controller_transition(
                    root,
                    controller_packet_id,
                    packet_id,
                    check_manifest_membership=False,
                )
            )
            return errors
    except (
        BatchError,
        dispatch_builder.DispatchError,
        capsules.CapsuleError,
        OSError,
    ) as error:
        return [str(error)]


def validate_ready_receipt(
    session_root: Any,
    controller_packet_id: str,
) -> list[str]:
    errors, _captured_packets = capture_ready_manifest_packets(
        session_root,
        controller_packet_id,
    )
    return errors


def validate_recorded_batch(
    session_dir: Any,
    controller_packet_id: str,
    expected_state: dict[str, Any],
) -> list[str]:
    """Validate one committed non-empty CODEX batch without recursive session validation."""
    try:
        capsules.validate_safe_id(
            controller_packet_id,
            "controller_packet_id",
        )
        with capsules.session_scope(session_dir) as root:
            state_raw, state_relative = capsules.read_session_artifact(
                root,
                "session-state.json",
            )
            current_state = dispatch_builder.strict_json(
                state_raw,
                state_relative,
            )
            if current_state != expected_state:
                return [
                    "current session-state.json does not match the state being "
                    "validated"
                ]
            if not isinstance(current_state, dict):
                return ["current session-state.json must be an object"]
            dispatch_builder.require_codex_transport_profile(current_state)

            errors = validate_committed_controller_transition(
                root,
                controller_packet_id,
                None,
                run_session_validation=False,
            )
            capture_errors, _captured_packets = capture_ready_manifest_packets(
                root,
                controller_packet_id,
            )
            errors.extend(capture_errors)
            errors.extend(
                validate_committed_controller_transition(
                    root,
                    controller_packet_id,
                    None,
                    check_manifest_membership=False,
                    run_session_validation=False,
                )
            )
            final_state_raw, final_state_relative = (
                capsules.read_session_artifact(
                    root,
                    "session-state.json",
                )
            )
            final_state = dispatch_builder.strict_json(
                final_state_raw,
                final_state_relative,
            )
            if final_state != expected_state:
                errors.append(
                    "session-state.json changed while the committed Codex "
                    "batch was validated"
                )
            return errors
    except (
        BatchError,
        dispatch_builder.DispatchError,
        capsules.CapsuleError,
        OSError,
    ) as error:
        return [str(error)]


def capture_ready_manifest_packets(
    session_root: Any,
    controller_packet_id: str,
) -> tuple[list[str], dict[str, bytes]]:
    """Validate a ready batch and retain the exact packet bytes from that pass."""
    errors: list[str] = []
    manifest_relative = (
        f"control-inputs/dispatch-batches/{controller_packet_id}.json"
    )
    ready_relative = (
        f"control-inputs/dispatch-batches/{controller_packet_id}.ready.json"
    )
    ready_raw, _relative = capsules.read_immutable_session_artifact(
        session_root,
        ready_relative,
    )
    ready = dispatch_builder.require_exact_keys(
        dispatch_builder.strict_json(ready_raw, ready_relative),
        READY_RECEIPT_KEYS,
        "dispatch batch ready receipt",
    )
    if ready["schema_version"] != READY_RECEIPT_SCHEMA_VERSION:
        errors.append("dispatch batch ready receipt schema_version is unsupported")
    if ready["controller_packet_id"] != controller_packet_id:
        errors.append("dispatch batch ready receipt id does not match")
    manifest_raw, _manifest_relative = capsules.read_immutable_session_artifact(
        session_root,
        manifest_relative,
    )
    if ready["manifest_sha256"] != sha256(manifest_raw):
        errors.append("dispatch batch ready receipt manifest digest does not match")
    captured_packets: dict[str, bytes] = {}
    errors.extend(
        _validate_batch_manifest(
            session_root,
            controller_packet_id,
            manifest_raw=manifest_raw,
            captured_packets=captured_packets,
        )
    )
    return errors, captured_packets


def validate_committed_controller_transition(
    session_root: Any,
    controller_packet_id: str,
    packet_id: str | None,
    *,
    check_manifest_membership: bool = True,
    run_session_validation: bool = True,
) -> list[str]:
    errors: list[str] = []
    state_raw, _state_relative = capsules.read_session_artifact(
        session_root,
        "session-state.json",
    )
    state = dispatch_builder.strict_json(state_raw, "session-state.json")
    if not isinstance(state, dict):
        return ["current session-state.json must be an object"]
    try:
        dispatch_builder.require_codex_transport_profile(state)
    except dispatch_builder.DispatchError as error:
        return [str(error)]
    if run_session_validation:
        session_errors: list[str] = []
        dispatch_builder.session_validator.validate_state(
            session_root.path,
            state,
            session_errors,
        )
        errors.extend(
            "current session validation failed: " + error
            for error in session_errors
        )

    archived_output_relative = (
        "control-inputs/dispatch-batch-inputs/"
        f"{controller_packet_id}.controller-output.json"
    )
    archived_output_raw, _relative = capsules.read_immutable_session_artifact(
        session_root,
        archived_output_relative,
    )
    archived_output = dispatch_builder.strict_json(
        archived_output_raw,
        archived_output_relative,
    )
    if not isinstance(archived_output, dict):
        return errors + ["archived controller output must be an object"]
    archived_envelope = archived_output.get("envelope")
    directive = archived_output.get("control_directive")
    if not isinstance(archived_envelope, dict) or not isinstance(directive, dict):
        return errors + ["archived controller output is malformed"]

    control = state.get("mainline_control")
    transitions = (
        control.get("transition_log")
        if isinstance(control, dict)
        and isinstance(control.get("transition_log"), list)
        else []
    )
    matches = [
        transition
        for transition in transitions
        if isinstance(transition, dict)
        and transition.get("packet_id") == controller_packet_id
    ]
    if len(matches) != 1:
        errors.append(
            "current session must contain exactly one committed controller transition"
        )
    else:
        transition = matches[0]
        bindings = {
            "observed_revision": "observed_revision",
            "observed_state_digest": "observed_state_digest",
            "observed_status": "from_status",
            "checkpoint": "checkpoint",
            "action": "action",
            "target_status": "to_status",
            "pending_user_gate": "pending_user_gate",
            "dispatches": "dispatches",
            "required_actions": "required_actions",
            "required_checks": "required_checks",
            "reason_codes": "reason_codes",
            "blocking_reasons": "blocking_reasons",
            "retry_key": "retry_key",
        }
        for directive_field, transition_field in bindings.items():
            if directive.get(directive_field) != transition.get(transition_field):
                errors.append(
                    "committed controller transition does not match archived "
                    f"directive field {directive_field}"
                )
    control_products = [
        product
        for product in list_or_empty(state.get("accepted_work_products"))
        if isinstance(product, dict)
        and product.get("phase") == "CONTROL"
        and product.get("packet_id") == controller_packet_id
    ]
    if len(control_products) != 1:
        errors.append(
            "current session must contain the accepted CONTROL work product"
        )
    else:
        product = control_products[0]
        for field in (
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
        ):
            if product.get(field) != archived_envelope.get(field):
                errors.append(
                    f"accepted CONTROL work product does not match {field}"
                )

    if packet_id is not None:
        try:
            capsules.validate_safe_id(packet_id, "packet_id")
        except capsules.CapsuleError as error:
            errors.append(str(error))
            return errors
        if check_manifest_membership:
            manifest_relative = (
                f"control-inputs/dispatch-batches/{controller_packet_id}.json"
            )
            manifest_raw, _manifest_relative = (
                capsules.read_immutable_session_artifact(
                    session_root,
                    manifest_relative,
                )
            )
            manifest = dispatch_builder.strict_json(
                manifest_raw,
                manifest_relative,
            )
            manifest_ids: set[str] = set()
            try:
                checked_manifest = dispatch_builder.require_exact_keys(
                    manifest,
                    MANIFEST_KEYS,
                    "dispatch batch manifest",
                )
            except dispatch_builder.DispatchError as error:
                errors.append(str(error))
            else:
                dispatch_records = checked_manifest["dispatches"]
                if not isinstance(dispatch_records, list):
                    errors.append(
                        "dispatch batch manifest dispatches must be an array"
                    )
                else:
                    for index, record_value in enumerate(dispatch_records):
                        record_location = (
                            f"dispatch batch manifest dispatches[{index}]"
                        )
                        try:
                            record = dispatch_builder.require_exact_keys(
                                record_value,
                                DISPATCH_RECORD_KEYS,
                                record_location,
                            )
                            manifest_packet_id = capsules.validate_safe_id(
                                record["packet_id"],
                                f"{record_location}.packet_id",
                            )
                        except (
                            dispatch_builder.DispatchError,
                            capsules.CapsuleError,
                        ) as error:
                            errors.append(str(error))
                            continue
                        manifest_ids.add(manifest_packet_id)
            if packet_id not in manifest_ids:
                errors.append(
                    "target packet is not part of the committed batch manifest"
                )
        resolved_ids: set[str] = set()
        for field in ("accepted_work_products", "rejected_work_products"):
            for index, product in enumerate(list_or_empty(state.get(field))):
                if not isinstance(product, dict):
                    continue
                resolved_packet_id = product.get("packet_id")
                try:
                    capsules.validate_safe_id(
                        resolved_packet_id,
                        f"{field}[{index}].packet_id",
                    )
                except capsules.CapsuleError as error:
                    errors.append(str(error))
                    continue
                resolved_ids.add(resolved_packet_id)
        if packet_id in resolved_ids:
            errors.append("target packet is already accepted or rejected")
    return errors


def load_committed_packet_bytes(
    session_dir: Any,
    controller_packet_id: str,
    packet_id: str,
) -> bytes:
    capsules.validate_safe_id(controller_packet_id, "controller_packet_id")
    capsules.validate_safe_id(packet_id, "packet_id")
    with capsules.session_scope(session_dir) as root:
        errors = validate_committed_controller_transition(
            root,
            controller_packet_id,
            packet_id,
        )
        capture_errors, captured_packets = capture_ready_manifest_packets(
            root,
            controller_packet_id,
        )
        errors.extend(capture_errors)
        if packet_id not in captured_packets:
            errors.append("target packet is absent from the ready batch manifest")
        errors.extend(
            validate_committed_controller_transition(
                root,
                controller_packet_id,
                packet_id,
                check_manifest_membership=False,
            )
        )
        if errors:
            raise BatchError("; ".join(errors))
        return captured_packets[packet_id]


def load_recorded_packet_bytes(
    session_dir: Any,
    controller_packet_id: str,
    packet_id: str,
    expected_state: dict[str, Any],
) -> bytes:
    """Capture an accepted packet through the canonical committed-batch proof.

    This variant is called from the full session validator after a role result
    has been accepted. It intentionally permits a resolved target and skips
    recursively invoking that same full validator, while still rechecking the
    committed CONTROL transition on both sides of the ready/manifest/packet
    capture.
    """
    capsules.validate_safe_id(controller_packet_id, "controller_packet_id")
    capsules.validate_safe_id(packet_id, "packet_id")
    with capsules.session_scope(session_dir) as root:
        state_raw, state_relative = capsules.read_session_artifact(
            root,
            "session-state.json",
        )
        current_state = dispatch_builder.strict_json(state_raw, state_relative)
        if current_state != expected_state:
            raise BatchError(
                "current session-state.json does not match the state being validated"
            )
        if not isinstance(current_state, dict):
            raise BatchError("current session-state.json must be an object")
        dispatch_builder.require_codex_transport_profile(current_state)

        errors = validate_committed_controller_transition(
            root,
            controller_packet_id,
            None,
            run_session_validation=False,
        )
        capture_errors, captured_packets = capture_ready_manifest_packets(
            root,
            controller_packet_id,
        )
        errors.extend(capture_errors)
        if packet_id not in captured_packets:
            errors.append("target packet is absent from the ready batch manifest")
        errors.extend(
            validate_committed_controller_transition(
                root,
                controller_packet_id,
                None,
                check_manifest_membership=False,
                run_session_validation=False,
            )
        )
        if errors:
            raise BatchError("; ".join(errors))
        return captured_packets[packet_id]


def _validate_batch_manifest(
    session_root: Any,
    controller_packet_id: str,
    *,
    manifest_raw: bytes | None = None,
    captured_packets: dict[str, bytes] | None = None,
) -> list[str]:
    errors: list[str] = []
    manifest_relative = (
        f"control-inputs/dispatch-batches/{controller_packet_id}.json"
    )
    if manifest_raw is None:
        raw, _relative = capsules.read_immutable_session_artifact(
            session_root,
            manifest_relative,
        )
    else:
        raw = manifest_raw
    manifest = dispatch_builder.require_exact_keys(
        dispatch_builder.strict_json(raw, manifest_relative),
        MANIFEST_KEYS,
        "dispatch batch manifest",
    )
    if manifest["schema_version"] != BATCH_MANIFEST_SCHEMA_VERSION:
        errors.append("dispatch batch manifest schema_version is unsupported")
    if manifest["controller_packet_id"] != controller_packet_id:
        errors.append("dispatch batch manifest id does not match its filename")
    try:
        capsules.validate_checkpoint(manifest["checkpoint"])
    except capsules.CapsuleError as error:
        errors.append(str(error))

    controller_inputs = dispatch_builder.require_exact_keys(
        manifest["controller_inputs"],
        INPUT_LABELS,
        "dispatch batch manifest controller_inputs",
    )
    archived_raw: dict[str, bytes] = {}
    for label, record_value in controller_inputs.items():
        record = dispatch_builder.require_exact_keys(
            record_value,
            FILE_RECORD_KEYS,
            f"dispatch batch manifest controller_inputs[{label!r}]",
        )
        path = record["path"]
        expected_path = (
            "control-inputs/dispatch-batch-inputs/"
            f"{controller_packet_id}.{INPUT_SUFFIXES[label]}"
        )
        if path != expected_path:
            errors.append(f"dispatch batch manifest {label} path is invalid")
            continue
        try:
            source_raw, _source_relative = capsules.read_immutable_session_artifact(
                session_root,
                path,
            )
        except capsules.CapsuleError as error:
            errors.append(f"dispatch batch manifest {label}: {error}")
            continue
        if record["sha256"] != sha256(source_raw):
            errors.append(f"dispatch batch manifest {label} digest does not match")
        archived_raw[label] = source_raw

    logical_dispatches: list[Any] = []
    archived_state: dict[str, Any] | None = None
    if set(archived_raw) == INPUT_LABELS:
        parsed_state = dispatch_builder.strict_json(
            archived_raw["session-state.json"],
            "archived session-state.json",
        )
        if isinstance(parsed_state, dict):
            archived_state = parsed_state
            try:
                dispatch_builder.require_codex_transport_profile(
                    archived_state,
                    "archived session-state.json",
                )
            except dispatch_builder.DispatchError as error:
                errors.append(str(error))
        else:
            errors.append("archived session state must be an object")
        with tempfile.TemporaryDirectory(
            prefix="codex-dispatch-manifest-"
        ) as temporary:
            stable = Path(temporary)
            state_path = stable / "session-state.json"
            control_input_path = stable / "control-input.json"
            output_path = stable / "controller-output.json"
            state_path.write_bytes(archived_raw["session-state.json"])
            control_input_path.write_bytes(archived_raw["control-input.json"])
            output_path.write_bytes(archived_raw["controller-output.json"])
            controller_errors, validated_state_raw = controller_validator.validate(
                state_path,
                output_path,
                control_input_path,
            )
        errors.extend(
            "dispatch batch manifest controller input validation failed: " + error
            for error in controller_errors
        )
        if validated_state_raw != archived_raw["session-state.json"]:
            errors.append(
                "dispatch batch manifest controller state snapshot is not bound"
            )
        try:
            archived_output = dispatch_builder.strict_json(
                archived_raw["controller-output.json"],
                "archived controller-output.json",
            )
        except dispatch_builder.DispatchError as error:
            errors.append(str(error))
        else:
            if not isinstance(archived_output, dict):
                errors.append("archived controller output must be an object")
            else:
                archived_envelope = archived_output.get("envelope")
                archived_directive = archived_output.get("control_directive")
                if (
                    not isinstance(archived_envelope, dict)
                    or archived_envelope.get("packet_id")
                    != controller_packet_id
                ):
                    errors.append(
                        "archived controller output does not match manifest id"
                    )
                if not isinstance(archived_directive, dict):
                    errors.append(
                        "archived controller output directive must be an object"
                    )
                else:
                    if archived_directive.get("checkpoint") != manifest["checkpoint"]:
                        errors.append(
                            "archived controller checkpoint does not match manifest"
                        )
                    value = archived_directive.get("dispatches")
                    if isinstance(value, list):
                        logical_dispatches = value
                    else:
                        errors.append(
                            "archived controller dispatches must be an array"
                        )

    dispatch_records = manifest["dispatches"]
    if not isinstance(dispatch_records, list):
        return errors + ["dispatch batch manifest dispatches must be an array"]
    seen: set[str] = set()
    manifest_coordinates: list[tuple[Any, ...]] = []
    for index, record_value in enumerate(dispatch_records):
        location = f"dispatch batch manifest dispatches[{index}]"
        record = dispatch_builder.require_exact_keys(
            record_value,
            DISPATCH_RECORD_KEYS,
            location,
        )
        packet_id = record["packet_id"]
        try:
            capsules.validate_safe_id(packet_id, f"{location}.packet_id")
        except capsules.CapsuleError as error:
            errors.append(str(error))
            continue
        if packet_id in seen:
            errors.append(f"{location}.packet_id is duplicated")
            continue
        seen.add(packet_id)
        manifest_coordinates.append(
            tuple(
                record[field]
                for field in ("packet_id", "phase", "role", "candidate_id", "round")
            )
        )
        expected_packet_path = f"control-inputs/dispatches/{packet_id}.json"
        expected_capsule_path = f"context-capsules/{packet_id}.json"
        if record["packet_path"] != expected_packet_path:
            errors.append(f"{location}.packet_path is invalid")
        if record["capsule_path"] != expected_capsule_path:
            errors.append(f"{location}.capsule_path is invalid")
        try:
            packet, packet_raw = dispatch_builder.validate_persisted_packet(
                session_root,
                packet_id,
            )
            capsule_raw, _capsule_relative = capsules.read_immutable_session_artifact(
                session_root,
                expected_capsule_path,
            )
        except (
            dispatch_builder.DispatchError,
            capsules.CapsuleError,
            OSError,
        ) as error:
            errors.append(f"{location}: {error}")
            continue
        if record["packet_sha256"] != sha256(packet_raw):
            errors.append(f"{location}.packet_sha256 does not match")
        if record["capsule_sha256"] != sha256(capsule_raw):
            errors.append(f"{location}.capsule_sha256 does not match")
        envelope = packet["envelope"]
        for field in ("phase", "role", "candidate_id", "round"):
            if record[field] != envelope[field]:
                errors.append(f"{location}.{field} does not match packet")
        if packet["context_capsule"]["checkpoint"] != manifest["checkpoint"]:
            errors.append(f"{location} capsule checkpoint does not match manifest")
        if archived_state is not None:
            try:
                dispatch_builder.validate_authorized_search_budget(
                    packet["search_budget"],
                    envelope["role"],
                    envelope,
                    archived_state,
                    f"{location}.search_budget",
                )
            except dispatch_builder.DispatchError as error:
                errors.append(str(error))
        if captured_packets is not None:
            captured_packets[packet_id] = packet_raw
    logical_coordinates = [
        tuple(
            logical.get(field)
            for field in ("packet_id", "phase", "role", "candidate_id", "round")
        )
        for logical in logical_dispatches
        if isinstance(logical, dict)
    ]
    if manifest_coordinates != logical_coordinates:
        errors.append(
            "dispatch batch manifest records do not match archived controller dispatches"
        )
    return errors


def validate_batch(
    session_dir: Path,
    controller_output_relative_path: str,
    control_input_relative_path: str = "control-input.json",
) -> list[str]:
    try:
        with capsules.session_scope(session_dir) as root:
            return _validate_batch(
                root,
                controller_output_relative_path,
                control_input_relative_path,
            )
    except (
        BatchError,
        dispatch_builder.DispatchError,
        capsules.CapsuleError,
        OSError,
    ) as error:
        return [str(error)]


def _validate_batch(
    session_root: Any,
    controller_output_relative_path: str,
    control_input_relative_path: str,
) -> list[str]:
    errors: list[str] = []
    snapshot_paths = {
        "session-state.json": "session-state.json",
        "control-input.json": control_input_relative_path,
        "controller-output.json": controller_output_relative_path,
    }
    snapshots: dict[str, bytes] = {}
    try:
        for label, relative_path in snapshot_paths.items():
            raw, _relative = capsules.read_session_artifact(
                session_root,
                relative_path,
            )
            snapshots[label] = raw
    except (
        dispatch_builder.DispatchError,
        capsules.CapsuleError,
        OSError,
    ) as error:
        return [str(error)]

    with tempfile.TemporaryDirectory(prefix="codex-dispatch-gate-") as temporary:
        stable = Path(temporary)
        state_path = stable / "session-state.json"
        control_input_path = stable / "control-input.json"
        output_path = stable / "controller-output.json"
        state_path.write_bytes(snapshots["session-state.json"])
        control_input_path.write_bytes(snapshots["control-input.json"])
        output_path.write_bytes(snapshots["controller-output.json"])
        controller_errors, validated_state_raw = controller_validator.validate(
            state_path,
            output_path,
            control_input_path,
        )
    if controller_errors:
        return [
            "controller directive validation failed: " + error
            for error in controller_errors
        ]
    if validated_state_raw != snapshots["session-state.json"]:
        return ["controller validator did not bind the snapshotted session state"]
    try:
        snapshotted_state = dispatch_builder.strict_json(
            snapshots["session-state.json"],
            "session-state.json",
        )
        if not isinstance(snapshotted_state, dict):
            return ["session-state.json must be an object"]
        dispatch_builder.require_codex_transport_profile(snapshotted_state)
    except dispatch_builder.DispatchError as error:
        return [str(error)]

    try:
        output = dispatch_builder.strict_json(
            snapshots["controller-output.json"],
            "controller-output.json",
        )
    except dispatch_builder.DispatchError as error:
        return [str(error)]
    if not isinstance(output, dict):
        return ["controller output must be an object"]
    directive = output.get("control_directive")
    if not isinstance(directive, dict):
        return ["controller output control_directive must be an object"]
    dispatches = directive.get("dispatches")
    if not isinstance(dispatches, list):
        return ["controller output dispatches must be an array"]
    checkpoint = directive.get("checkpoint")
    if not isinstance(checkpoint, str):
        return ["controller output checkpoint must be a string"]

    seen: set[str] = set()
    records: list[dict[str, Any]] = []
    for index, logical in enumerate(dispatches):
        location = f"control_directive.dispatches[{index}]"
        if not isinstance(logical, dict):
            errors.append(f"{location} must be an object")
            continue
        packet_id = logical.get("packet_id")
        if not isinstance(packet_id, str) or not packet_id:
            errors.append(f"{location}.packet_id must be non-empty")
            continue
        if packet_id in seen:
            errors.append(f"{location}.packet_id is duplicated")
            continue
        seen.add(packet_id)
        if logical.get("phase") == "CONTROL":
            errors.append(f"{location} must not dispatch CONTROL")
            continue
        try:
            packet, _packet_raw = dispatch_builder.validate_persisted_packet(
                session_root,
                packet_id,
            )
        except (
            dispatch_builder.DispatchError,
            capsules.CapsuleError,
            OSError,
        ) as error:
            errors.append(f"{location}: {error}")
            continue
        envelope = packet["envelope"]
        for field in ("phase", "role", "candidate_id", "round"):
            if envelope.get(field) != logical.get(field):
                errors.append(
                    f"{location}.{field} does not match persisted packet"
                )
        if packet["context_capsule"]["checkpoint"] != checkpoint:
            errors.append(
                f"{location} capsule checkpoint does not match controller directive"
            )
        capsule_relative = f"context-capsules/{packet_id}.json"
        capsule_raw, _capsule_relative = capsules.read_session_artifact(
            session_root,
            capsule_relative,
        )
        records.append(
            {
                "packet_id": packet_id,
                "phase": envelope["phase"],
                "role": envelope["role"],
                "candidate_id": envelope["candidate_id"],
                "round": envelope["round"],
                "packet_path": (
                    f"control-inputs/dispatches/{packet_id}.json"
                ),
                "packet_sha256": sha256(_packet_raw),
                "capsule_path": capsule_relative,
                "capsule_sha256": sha256(capsule_raw),
            }
        )

    errors.extend(
        live_snapshot_errors(session_root, snapshot_paths, snapshots)
    )
    if errors:
        return errors

    envelope = output.get("envelope")
    if not isinstance(envelope, dict):
        return ["controller output envelope must be an object"]
    controller_packet_id = envelope.get("packet_id")
    try:
        capsules.validate_safe_id(
            controller_packet_id,
            "controller output envelope packet_id",
        )
    except capsules.CapsuleError as error:
        return [str(error)]

    archived_inputs: dict[str, dict[str, str]] = {}
    for label, suffix in INPUT_SUFFIXES.items():
        relative = (
            "control-inputs/dispatch-batch-inputs/"
            f"{controller_packet_id}.{suffix}"
        )
        capsules.write_session_file(
            session_root,
            relative,
            snapshots[label],
            immutable=True,
        )
        archived_inputs[label] = {
            "path": relative,
            "sha256": sha256(snapshots[label]),
        }
    manifest = {
        "schema_version": BATCH_MANIFEST_SCHEMA_VERSION,
        "controller_packet_id": controller_packet_id,
        "checkpoint": checkpoint,
        "controller_inputs": archived_inputs,
        "dispatches": records,
    }
    manifest_raw = serialize_manifest(manifest)
    capsules.write_session_file(
        session_root,
        f"control-inputs/dispatch-batches/{controller_packet_id}.json",
        manifest_raw,
        immutable=True,
    )
    errors.extend(
        _validate_batch_manifest(session_root, controller_packet_id)
    )
    errors.extend(
        live_snapshot_errors(session_root, snapshot_paths, snapshots)
    )
    if errors:
        return errors
    ready = {
        "schema_version": READY_RECEIPT_SCHEMA_VERSION,
        "controller_packet_id": controller_packet_id,
        "manifest_sha256": sha256(manifest_raw),
    }
    capsules.write_session_file(
        session_root,
        f"control-inputs/dispatch-batches/{controller_packet_id}.ready.json",
        serialize_manifest(ready),
        immutable=True,
    )
    return errors


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Verify persisted Codex role packets for one validated controller "
            "output before committing its state transition."
        )
    )
    parser.add_argument("session_dir", type=Path)
    parser.add_argument(
        "controller_output",
        nargs="?",
        help="session-relative controller-output JSON path",
    )
    parser.add_argument(
        "--verify-manifest",
        metavar="CONTROLLER_PACKET_ID",
        help=(
            "verify one committed batch manifest and its exact packet/capsule "
            "bytes before initial dispatch or retry"
        ),
    )
    parser.add_argument(
        "--packet-id",
        help=(
            "target unresolved role packet; required with --verify-manifest"
        ),
    )
    parser.add_argument(
        "--emit-packet",
        action="store_true",
        help=(
            "emit the exact manifest-validated target packet bytes to stdout"
        ),
    )
    parser.add_argument(
        "--control-input",
        default="control-input.json",
        help=(
            "session-relative authoritative control-input path "
            "(default: control-input.json)"
        ),
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.verify_manifest:
        if args.controller_output is not None:
            print(
                "ERROR: controller_output is not used with --verify-manifest",
                file=sys.stderr,
            )
            return 2
        if not args.packet_id:
            print(
                "ERROR: --packet-id is required with --verify-manifest",
                file=sys.stderr,
            )
            return 2
        if args.emit_packet:
            try:
                raw = load_committed_packet_bytes(
                    args.session_dir,
                    args.verify_manifest,
                    args.packet_id,
                )
            except (
                BatchError,
                dispatch_builder.DispatchError,
                capsules.CapsuleError,
                OSError,
            ) as error:
                print(f"ERROR: {error}", file=sys.stderr)
                return 2
            sys.stdout.buffer.write(raw)
            return 0
        errors = validate_batch_manifest(
            args.session_dir,
            args.verify_manifest,
            args.packet_id,
        )
    else:
        if args.packet_id or args.emit_packet:
            print(
                "ERROR: --packet-id/--emit-packet require --verify-manifest",
                file=sys.stderr,
            )
            return 2
        if args.controller_output is None:
            print(
                "ERROR: controller_output is required before state commit",
                file=sys.stderr,
            )
            return 2
        errors = validate_batch(
            args.session_dir,
            args.controller_output,
            args.control_input,
        )
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 2
    if args.verify_manifest:
        print("Codex dispatch batch manifest and exact packet bytes are valid.")
    else:
        print("Codex dispatch batch is ready for state commit.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
