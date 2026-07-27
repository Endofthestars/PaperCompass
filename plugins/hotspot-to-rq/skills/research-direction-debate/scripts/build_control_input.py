#!/usr/bin/env python3
"""Build the canonical control-input snapshot for a Mainline Workflow Controller call.

Reads <session-dir>/session-state.json and emits the exact control-input JSON
the validators recompute, deriving every recomputable field through the same
projection functions validate_controller_decision.py uses (imported, never
reimplemented, so the snapshot cannot drift from validator expectations).

Only fields that genuinely cannot be derived from session state are taken
from flags: artifact_readiness (--readiness), latest_validation
(--validation-result / --validation-error-code), budget_flags (--budget-flag),
and unresolved_blockers (--unresolved-blocker). At POST_USER_GATE the
user_event is auto-projected from the receipt that answered the pending gate;
--receipt-id overrides the selection.

Byte format matches the archived control-inputs/<packet>.json contract:
UTF-8, json.dumps(..., ensure_ascii=False, indent=2) plus a trailing newline,
keys in the canonical order. By default the JSON bytes go to stdout and the
SHA-256 digest of those exact bytes goes to stderr; --out and --packet-id
write the same bytes to files instead.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import sys
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


controller = _load_module(
    "hotspot_validate_controller_decision",
    "validate_controller_decision.py",
)
capsules = _load_module(
    "hotspot_context_capsule_for_control_input",
    "build_context_capsule.py",
)

READINESS_VALUES = {"READY", "NOT_READY", "STALE", "UNRESOLVED"}
VALIDATION_RESULTS = {"PASS", "FAIL", "NOT_RUN"}


class BuildError(ValueError):
    """Raised when the snapshot cannot be derived from the session state."""


def _gate_receipts(state: dict[str, Any]) -> list[dict[str, Any]]:
    receipts = state.get("gate_receipts")
    if not isinstance(receipts, list):
        return []
    return [receipt for receipt in receipts if isinstance(receipt, dict)]


def _receipt_event(receipt: dict[str, Any]) -> dict[str, Any]:
    values = receipt.get("values")
    return {
        "kind": receipt.get("gate"),
        "receipt_id": receipt.get("receipt_id"),
        "selected_ids": list(values) if isinstance(values, list) else [],
    }


def derive_user_event(
    state: dict[str, Any],
    checkpoint: str,
    receipt_id: str | None,
) -> dict[str, Any]:
    receipts = _gate_receipts(state)
    if receipt_id is not None:
        matches = [
            receipt
            for receipt in receipts
            if receipt.get("receipt_id") == receipt_id
        ]
        if len(matches) != 1:
            raise BuildError(
                f"--receipt-id {receipt_id!r} must match exactly one "
                f"gate_receipts entry; found {len(matches)}"
            )
        return _receipt_event(matches[0])
    if checkpoint != "POST_USER_GATE":
        return {"kind": "NONE", "receipt_id": None, "selected_ids": []}

    control = state.get("mainline_control")
    log = (
        control.get("transition_log")
        if isinstance(control, dict)
        and isinstance(control.get("transition_log"), list)
        else []
    )
    predecessor = log[-1] if log else None
    gate = (
        predecessor.get("pending_user_gate")
        if isinstance(predecessor, dict)
        and predecessor.get("action") == "HOLD_FOR_USER"
        else None
    )
    if gate is None:
        raise BuildError(
            "POST_USER_GATE requires the latest committed transition to be a "
            "HOLD_FOR_USER with a pending gate; pass --receipt-id to select "
            "the consumed receipt explicitly"
        )
    matches = [
        receipt
        for receipt in receipts
        if receipt.get("gate") == gate
        and receipt.get("based_on_revision") == predecessor.get("revision")
    ]
    if len(matches) != 1:
        raise BuildError(
            f"POST_USER_GATE expects exactly one {gate} receipt with "
            f"based_on_revision {predecessor.get('revision')!r}; found "
            f"{len(matches)}; pass --receipt-id to disambiguate"
        )
    return _receipt_event(matches[0])


def build_snapshot(
    state: dict[str, Any],
    state_digest: str,
    checkpoint: str,
    *,
    artifact_readiness: dict[str, str] | None = None,
    validation_result: str = "PASS",
    validation_error_codes: list[str] | None = None,
    budget_flags: list[str] | None = None,
    unresolved_blockers: list[str] | None = None,
    receipt_id: str | None = None,
) -> dict[str, Any]:
    """Derive the canonical control-input snapshot for *checkpoint*."""
    if checkpoint not in controller.CONTROL_CHECKPOINTS:
        raise BuildError(
            f"checkpoint must be one of "
            f"{sorted(controller.CONTROL_CHECKPOINTS)}"
        )
    validation_error_codes = list(validation_error_codes or [])
    if validation_result not in VALIDATION_RESULTS:
        raise BuildError(
            f"validation result must be one of {sorted(VALIDATION_RESULTS)}"
        )
    if validation_result == "FAIL" and not validation_error_codes:
        raise BuildError(
            "latest_validation FAIL requires at least one "
            "--validation-error-code"
        )

    collect_errors: list[str] = []
    accepted, rejected = controller.collect_work_products(state, collect_errors)
    if collect_errors:
        raise BuildError(
            "session-state.json work products are invalid: "
            + "; ".join(collect_errors)
        )

    control = state.get("mainline_control")
    revision = control.get("revision") if isinstance(control, dict) else None
    if not controller.is_int(revision) or revision < 0:
        raise BuildError(
            "session-state.json.mainline_control.revision must be a "
            "non-negative integer"
        )
    if revision == 0 and checkpoint != "SESSION_INIT":
        raise BuildError("Control revision 0 requires checkpoint SESSION_INIT")
    if revision != 0 and checkpoint == "SESSION_INIT":
        raise BuildError("SESSION_INIT is valid only at control revision 0")

    snapshot = {
        "control_revision": revision,
        "state_digest": state_digest,
        "observed_status": state.get("status"),
        "mode": state.get("mode"),
        "interaction_mode": state.get("interaction_mode"),
        "checkpoint": checkpoint,
        "completed_packet_ids": controller.expected_completed_packet_ids(
            accepted
        ),
        "failed_packets": controller.expected_failed_packets(state, rejected),
        "active_lanes": controller.expected_active_lanes(state, accepted),
        "accepted_verdicts": controller.expected_accepted_verdicts(state),
        "artifact_readiness": dict(artifact_readiness or {}),
        "latest_validation": {
            "result": validation_result,
            "error_codes": validation_error_codes,
        },
        "budget_flags": list(budget_flags or []),
        "unresolved_blockers": list(unresolved_blockers or []),
        "user_event": derive_user_event(state, checkpoint, receipt_id),
        "allowed_target_statuses": controller.legal_target_statuses(state),
    }
    if state.get("schema_version") == "1.4":
        transport_profile = state.get("transport_profile")
        if (
            not isinstance(transport_profile, str)
            or transport_profile not in {"CLAUDE", "CODEX"}
        ):
            raise BuildError(
                "schema_version 1.4 requires transport_profile CLAUDE or CODEX"
            )
        snapshot["transport_profile"] = transport_profile
    return snapshot


def serialize_snapshot(snapshot: dict[str, Any]) -> bytes:
    """Serialize with the exact byte format the digest/copy contract assumes."""
    return (
        json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n"
    ).encode("utf-8")


def _parse_readiness(pairs: list[str]) -> dict[str, str]:
    readiness: dict[str, str] = {}
    for pair in pairs:
        code, separator, value = pair.partition("=")
        if not separator or not controller.CODE.fullmatch(code):
            raise BuildError(
                f"--readiness expects UPPERCASE_CODE=STATUS, got {pair!r}"
            )
        if value not in READINESS_VALUES:
            raise BuildError(
                f"--readiness status must be one of {sorted(READINESS_VALUES)}, "
                f"got {value!r}"
            )
        readiness[code] = value
    return readiness


def _require_codes(values: list[str], flag: str) -> list[str]:
    for value in values:
        if not controller.CODE.fullmatch(value):
            raise BuildError(f"{flag} must be an UPPERCASE_CODE, got {value!r}")
    return values


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Assemble the canonical control-input.json snapshot for the next "
            "Mainline Workflow Controller call from session-state.json, using "
            "the validators' own projection functions."
        )
    )
    parser.add_argument(
        "session_dir",
        type=Path,
        help="session directory containing session-state.json",
    )
    parser.add_argument(
        "--checkpoint",
        required=True,
        choices=sorted(controller.CONTROL_CHECKPOINTS),
        help="checkpoint the controller is being invoked at",
    )
    parser.add_argument(
        "--packet-id",
        help=(
            "CONTROL packet id the controller will emit; writes the snapshot "
            "bytes to <session-dir>/control-inputs/<packet-id>.json and to "
            "<session-dir>/control-input.json"
        ),
    )
    parser.add_argument(
        "--out",
        type=Path,
        help="write the snapshot bytes to this path instead of stdout",
    )
    parser.add_argument(
        "--digest-only",
        action="store_true",
        help="print only the SHA-256 digest of the snapshot bytes to stdout",
    )
    parser.add_argument(
        "--readiness",
        action="append",
        default=[],
        metavar="CODE=STATUS",
        help=(
            "artifact readiness entry (repeatable), e.g. "
            "--readiness CANDIDATE_DIRECTIONS=READY; statuses: "
            "READY, NOT_READY, STALE, UNRESOLVED"
        ),
    )
    parser.add_argument(
        "--validation-result",
        default="PASS",
        choices=sorted(VALIDATION_RESULTS),
        help="latest_validation.result (default: PASS)",
    )
    parser.add_argument(
        "--validation-error-code",
        action="append",
        default=[],
        metavar="CODE",
        help="latest_validation.error_codes entry (repeatable)",
    )
    parser.add_argument(
        "--budget-flag",
        action="append",
        default=[],
        metavar="CODE",
        help="budget_flags entry (repeatable)",
    )
    parser.add_argument(
        "--unresolved-blocker",
        action="append",
        default=[],
        metavar="CODE",
        help="unresolved_blockers entry (repeatable)",
    )
    parser.add_argument(
        "--receipt-id",
        help=(
            "gate receipt to project into user_event (defaults to NONE, or to "
            "the receipt answering the pending gate at POST_USER_GATE)"
        ),
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    state_path = args.session_dir / "session-state.json"
    try:
        state_raw = state_path.read_bytes()
    except OSError as exc:
        print(f"ERROR: cannot read {state_path}: {exc}", file=sys.stderr)
        return 1

    parse_errors: list[str] = []
    state = controller.parse_json_bytes(
        state_raw, "session-state.json", parse_errors
    )
    if parse_errors or not isinstance(state, dict):
        for error in parse_errors or ["session-state.json must be an object"]:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1

    try:
        if args.packet_id is not None and not controller.SAFE_ID.fullmatch(
            args.packet_id
        ):
            raise BuildError(f"--packet-id {args.packet_id!r} is not a safe id")
        snapshot = build_snapshot(
            state,
            hashlib.sha256(state_raw).hexdigest(),
            args.checkpoint,
            artifact_readiness=_parse_readiness(args.readiness),
            validation_result=args.validation_result,
            validation_error_codes=_require_codes(
                args.validation_error_code, "--validation-error-code"
            ),
            budget_flags=_require_codes(args.budget_flag, "--budget-flag"),
            unresolved_blockers=_require_codes(
                args.unresolved_blocker, "--unresolved-blocker"
            ),
            receipt_id=args.receipt_id,
        )
    except BuildError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    raw = serialize_snapshot(snapshot)
    digest = hashlib.sha256(raw).hexdigest()

    if args.digest_only:
        print(digest)
        return 0

    written: list[Path] = []
    try:
        if args.out is not None:
            args.out.write_bytes(raw)
            written.append(args.out)
        if args.packet_id is not None:
            archive_path = capsules.write_session_file(
                args.session_dir,
                f"control-inputs/{args.packet_id}.json",
                raw,
                immutable=True,
            )
            written.append(archive_path)
            live_path = capsules.write_session_file(
                args.session_dir,
                "control-input.json",
                raw,
                immutable=False,
            )
            written.append(live_path)
    except (OSError, capsules.CapsuleError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    if not written:
        sys.stdout.buffer.write(raw)
        sys.stdout.buffer.flush()

    for path in written:
        print(f"wrote {path}", file=sys.stderr)
    print(digest, file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
