from __future__ import annotations

import hashlib
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
VALIDATOR_PATH = (
    ROOT
    / "plugins"
    / "hotspot-to-rq"
    / "skills"
    / "research-direction-debate"
    / "scripts"
    / "validate_session.py"
)
SPEC = importlib.util.spec_from_file_location("hotspot_validate_session", VALIDATOR_PATH)
assert SPEC is not None and SPEC.loader is not None
validator = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(validator)

CONTROLLER_VALIDATOR_PATH = VALIDATOR_PATH.with_name(
    "validate_controller_decision.py"
)
CONTROLLER_SPEC = importlib.util.spec_from_file_location(
    "hotspot_validate_controller_decision", CONTROLLER_VALIDATOR_PATH
)
assert CONTROLLER_SPEC is not None and CONTROLLER_SPEC.loader is not None
controller_validator = importlib.util.module_from_spec(CONTROLLER_SPEC)
CONTROLLER_SPEC.loader.exec_module(controller_validator)


def control_product(
    packet_id: str = "CTRL-0001",
    observed_revision: int = 0,
    digest: str = "a" * 64,
    control_input_digest: str = "c" * 64,
    role: str = "Mainline Workflow Controller",
) -> dict:
    product = {
        "packet_id": packet_id,
        "phase": "CONTROL",
        "role": role,
        "session_id": "session-1",
        "project_root": "/tmp/project",
        "project_snapshot": "snapshot-1",
        "candidate_id": None,
        "round": None,
        "control_revision": observed_revision,
        "state_digest": digest,
        "control_input_digest": control_input_digest,
        "context_fingerprint": "",
    }
    product["context_fingerprint"] = validator.expected_context_fingerprint(product)
    return product


def research_product(
    packet_id: str,
    phase: str,
    role: str,
    candidate_id: str | None = None,
    round_number: int | None = None,
) -> dict:
    product = {
        "packet_id": packet_id,
        "phase": phase,
        "role": role,
        "session_id": "session-1",
        "project_root": "/tmp/project",
        "project_snapshot": "snapshot-1",
        "candidate_id": candidate_id,
        "round": round_number,
        "context_fingerprint": "",
    }
    product["context_fingerprint"] = validator.expected_context_fingerprint(product)
    return product


def transition(
    *,
    revision: int = 1,
    packet_id: str = "CTRL-0001",
    digest: str = "a" * 64,
    control_input_digest: str = "c" * 64,
    checkpoint: str = "SESSION_INIT",
    from_status: str = "SCANNING",
    action: str = "ADVANCE",
    to_status: str = "SCANNING",
    pending_user_gate: str | None = None,
    dispatches: list | None = None,
    required_actions: list[str] | None = None,
    required_checks: list[str] | None = None,
    blocking_reasons: list[str] | None = None,
    retry_key: str | None = None,
) -> dict:
    return {
        "revision": revision,
        "observed_revision": revision - 1,
        "packet_id": packet_id,
        "observed_state_digest": digest,
        "control_input_digest": control_input_digest,
        "control_input_path": f"control-inputs/{packet_id}.json",
        "checkpoint": checkpoint,
        "from_status": from_status,
        "action": action,
        "to_status": to_status,
        "pending_user_gate": pending_user_gate,
        "dispatches": [] if dispatches is None else dispatches,
        "required_actions": (
            ["BUILD_PROJECT_EVIDENCE_PACK"]
            if required_actions is None
            else required_actions
        ),
        "required_checks": (
            ["PERSIST_STATE"] if required_checks is None else required_checks
        ),
        "reason_codes": ["TEST_TRANSITION"],
        "blocking_reasons": (
            [] if blocking_reasons is None else blocking_reasons
        ),
        "retry_key": retry_key,
        "recorded_at": "2026-07-25T12:00:00+08:00",
    }


def control_state(
    *,
    status: str = "SCANNING",
    transitions: list[dict] | None = None,
    products: list[dict] | None = None,
) -> dict:
    transitions = [transition()] if transitions is None else transitions
    products = [control_product()] if products is None else products
    last = transitions[-1] if transitions else None
    return {
        "schema_version": "1.3",
        "session_id": "session-1",
        "mode": "discover",
        "interaction_mode": "GUIDED",
        "project_root": "/tmp/project",
        "project_snapshot": "snapshot-1",
        "status": status,
        "candidates": [],
        "accepted_work_products": products,
        "rejected_work_products": [],
        "gate_receipts": [],
        "mainline_control": {
            "controller_id": "MAINLINE",
            "controller_status": "ACTIVE",
            "revision": len(transitions),
            "last_checkpoint": last["checkpoint"] if last else None,
            "pending_user_gate": last["pending_user_gate"] if last else None,
            "last_controller_packet_id": last["packet_id"] if last else None,
            "retry_counts": {},
            "lane_search_requests": [],
            "transition_log": transitions,
        },
    }


def write_controller_fixture(
    state_path: Path,
    output_path: Path,
    output: dict,
) -> None:
    state = json.loads(state_path.read_text(encoding="utf-8"))
    state_digest = hashlib.sha256(state_path.read_bytes()).hexdigest()
    accepted = [
        product
        for product in state.get("accepted_work_products", [])
        if isinstance(product, dict) and product.get("phase") != "CONTROL"
    ]
    accepted_by_id = {
        product["packet_id"]: product
        for product in accepted
        if isinstance(product.get("packet_id"), str)
    }
    rejected = [
        product
        for product in state.get("rejected_work_products", [])
        if isinstance(product, dict)
        and product.get("role")
        not in {"Mainline Workflow Controller", "Deterministic Mainline Fallback"}
    ]
    retry_counts = state.get("mainline_control", {}).get("retry_counts", {})
    receipts = [
        receipt
        for receipt in state.get("gate_receipts", [])
        if isinstance(receipt, dict)
    ]
    latest_receipt = receipts[-1] if receipts else None
    transitions = state.get("mainline_control", {}).get("transition_log", [])
    blockers = []
    if transitions and isinstance(transitions[-1], dict):
        blockers = transitions[-1].get("blocking_reasons", [])
    accepted_verdicts = []
    for candidate in state.get("candidates", []):
        if not isinstance(candidate, dict):
            continue
        for round_record in candidate.get("rounds", []):
            if isinstance(round_record, dict):
                accepted_verdicts.append(
                    {
                        "candidate_id": candidate.get("candidate_id"),
                        "round": round_record.get("round"),
                        "verdict": round_record.get("verdict"),
                    }
                )
    for round_record in state.get("evaluation_rounds", []):
        if isinstance(round_record, dict):
            accepted_verdicts.append(
                {
                    "candidate_id": None,
                    "round": round_record.get("round"),
                    "verdict": round_record.get("verdict"),
                }
            )

    directive = output["control_directive"]
    control_input = {
        "control_revision": state["mainline_control"]["revision"],
        "state_digest": state_digest,
        "observed_status": state["status"],
        "mode": state["mode"],
        "interaction_mode": state.get("interaction_mode", "GUIDED"),
        "checkpoint": directive["checkpoint"],
        "completed_packet_ids": [
            product["packet_id"] for product in accepted
        ],
        "failed_packets": [
            {
                "packet_id": product["packet_id"],
                "role": product["role"],
                "phase": next(
                    (
                        dispatch.get("phase")
                        for transition_item in transitions
                        if isinstance(transition_item, dict)
                        for dispatch in transition_item.get("dispatches", [])
                        if isinstance(dispatch, dict)
                        and dispatch.get("packet_id") == product["packet_id"]
                    ),
                    None,
                ),
                "candidate_id": product.get("candidate_id"),
                "round": product.get("round"),
                "reason_code": product["reason_code"],
                "retry_count": retry_counts.get(product["packet_id"], 0),
            }
            for product in rejected
        ],
        "active_lanes": controller_validator.expected_active_lanes(
            state,
            accepted_by_id,
        ),
        "accepted_verdicts": accepted_verdicts,
        "artifact_readiness": {
            "PROJECT_EVIDENCE_PACK": (
                "READY"
                if state["mainline_control"]["revision"] > 0
                else "NOT_READY"
            )
        },
        "latest_validation": {"result": "NOT_RUN", "error_codes": []},
        "budget_flags": [],
        "unresolved_blockers": blockers,
        "user_event": {
            "kind": (
                latest_receipt.get("gate")
                if isinstance(latest_receipt, dict)
                else "NONE"
            ),
            "receipt_id": (
                latest_receipt.get("receipt_id")
                if isinstance(latest_receipt, dict)
                else None
            ),
            "selected_ids": (
                latest_receipt.get("values", [])
                if isinstance(latest_receipt, dict)
                else []
            ),
        },
        "allowed_target_statuses": [directive["target_status"]],
    }
    control_input_path = output_path.with_name("control-input.json")
    control_input_path.write_text(
        json.dumps(control_input, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    output["envelope"]["control_input_digest"] = hashlib.sha256(
        control_input_path.read_bytes()
    ).hexdigest()
    output["envelope"]["context_fingerprint"] = (
        controller_validator.expected_context_fingerprint(output["envelope"])
    )
    output_path.write_text(
        json.dumps(output, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


class MainlineControlTests(unittest.TestCase):
    def assert_control_valid(self, state: dict) -> None:
        errors: list[str] = []
        validator.validate_accepted_work_products(state, errors)
        validator.validate_mainline_control(state, errors)
        self.assertEqual([], errors)

    def test_schema_13_bootstrap_is_valid_only_at_initial_state(self) -> None:
        state = control_state(transitions=[], products=[])
        self.assert_control_valid(state)

        state["status"] = "DEBATING"
        errors: list[str] = []
        validator.validate_mainline_control(state, errors)
        self.assertTrue(any("bootstrap status" in error for error in errors))

    def test_valid_committed_direction_gate_hold(self) -> None:
        held = transition(
            revision=2,
            packet_id="CTRL-0002",
            digest="b" * 64,
            checkpoint="PRE_USER_GATE",
            action="HOLD_FOR_USER",
            to_status="DIRECTION_GATE",
            pending_user_gate="DIRECTION_SELECTION",
            required_actions=[],
            required_checks=["PERSIST_STATE", "RUN_SESSION_VALIDATOR"],
        )
        state = control_state(
            status="DIRECTION_GATE",
            transitions=[transition(), held],
            products=[
                control_product(),
                control_product(
                    packet_id="CTRL-0002",
                    observed_revision=1,
                    digest="b" * 64,
                ),
            ],
        )
        self.assert_control_valid(state)

    def test_control_product_binds_observed_revision(self) -> None:
        product = control_product(observed_revision=1)
        state = control_state(products=[product])
        errors: list[str] = []
        validator.validate_accepted_work_products(state, errors)
        validator.validate_mainline_control(state, errors)
        self.assertTrue(
            any("control_revision does not match" in error for error in errors)
        )

    def test_float_revision_is_rejected(self) -> None:
        bad = transition()
        bad["revision"] = 1.0
        state = control_state(transitions=[bad])
        state["mainline_control"]["revision"] = 1.0
        errors: list[str] = []
        validator.validate_mainline_control(state, errors)
        self.assertTrue(any("revision" in error and "integer" in error for error in errors))

    def test_transition_and_control_packets_are_bijective(self) -> None:
        state = control_state()
        state["accepted_work_products"].append(
            control_product("CTRL-ORPHAN", observed_revision=0, digest="b" * 64)
        )
        errors: list[str] = []
        validator.validate_accepted_work_products(state, errors)
        validator.validate_mainline_control(state, errors)
        self.assertTrue(any("one-to-one" in error for error in errors))

    def test_gate_status_requires_matching_hold(self) -> None:
        bad = transition(to_status="DIRECTION_GATE")
        state = control_state(status="DIRECTION_GATE", transitions=[bad])
        errors: list[str] = []
        validator.validate_mainline_control(state, errors)
        self.assertTrue(any("HOLD_FOR_USER" in error for error in errors))

    def test_retry_is_single_shot(self) -> None:
        dispatch = {
            "packet_id": "RETRY-1",
            "phase": "HOTSPOT",
            "role": "Hotspot Analyst",
            "candidate_id": None,
            "round": None,
            "depends_on_packet_ids": [],
        }
        first = transition(
            action="RETRY_ROLE",
            dispatches=[dispatch],
            required_actions=[],
            retry_key="FAILED-1",
        )
        second = transition(
            revision=2,
            packet_id="CTRL-0002",
            digest="b" * 64,
            checkpoint="RECOVERY",
            action="RETRY_ROLE",
            dispatches=[
                {
                    **dispatch,
                    "packet_id": "RETRY-2",
                }
            ],
            required_actions=[],
            retry_key="FAILED-1",
        )
        state = control_state(
            transitions=[first, second],
            products=[
                control_product(),
                control_product("CTRL-0002", observed_revision=1, digest="b" * 64),
            ],
        )
        state["mainline_control"]["retry_counts"] = {"FAILED-1": 1}
        state["rejected_work_products"] = [
            {
                "role": "Hotspot Analyst",
                "packet_id": "FAILED-1",
                "candidate_id": None,
                "round": None,
                "reason_code": "ROLE_CONTRACT_VIOLATION",
                "reason": "bad output",
            }
        ]
        errors: list[str] = []
        validator.validate_mainline_control(state, errors)
        self.assertTrue(any("more than once" in error for error in errors))

    def test_valid_retry_preserves_original_logical_dispatch(self) -> None:
        failed_dispatch = {
            "packet_id": "FAILED-1",
            "phase": "DIRECTION_MAPPING",
            "role": "Macro Direction Mapper",
            "candidate_id": None,
            "round": None,
            "depends_on_packet_ids": [],
        }
        retry_dispatch = {
            **failed_dispatch,
            "packet_id": "RETRY-1",
        }
        initial = transition()
        first = transition(
            revision=2,
            packet_id="CTRL-0002",
            digest="b" * 64,
            checkpoint="PHASE_BOUNDARY",
            dispatches=[failed_dispatch],
            required_actions=[],
            required_checks=[
                "PERSIST_STATE",
                "VERIFY_ENVELOPES",
                "ENFORCE_BUDGET",
            ],
        )
        second = transition(
            revision=3,
            packet_id="CTRL-0003",
            digest="d" * 64,
            checkpoint="RECOVERY",
            action="RETRY_ROLE",
            dispatches=[retry_dispatch],
            required_actions=[],
            required_checks=[
                "PERSIST_STATE",
                "VERIFY_ENVELOPES",
                "ENFORCE_BUDGET",
            ],
            retry_key="FAILED-1",
        )
        state = control_state(
            transitions=[initial, first, second],
            products=[
                control_product(),
                control_product(
                    "CTRL-0002",
                    observed_revision=1,
                    digest="b" * 64,
                ),
                control_product(
                    "CTRL-0003",
                    observed_revision=2,
                    digest="d" * 64,
                ),
            ],
        )
        state["mainline_control"]["retry_counts"] = {"FAILED-1": 1}
        state["rejected_work_products"] = [
            {
                "role": "Macro Direction Mapper",
                "packet_id": "FAILED-1",
                "candidate_id": None,
                "round": None,
                "reason_code": "ROLE_CONTRACT_VIOLATION",
                "reason": "bad output",
            }
        ]
        errors: list[str] = []
        validator.validate_accepted_work_products(state, errors)
        validator.validate_mainline_control(state, errors)
        self.assertEqual([], errors)

    def test_full_validator_rejects_inapplicable_required_action(self) -> None:
        second = transition(
            revision=2,
            packet_id="CTRL-0002",
            digest="b" * 64,
            checkpoint="PHASE_BOUNDARY",
            required_actions=["APPLY_EVALUATION_DECISION"],
        )
        state = control_state(
            transitions=[transition(), second],
            products=[
                control_product(),
                control_product(
                    "CTRL-0002",
                    observed_revision=1,
                    digest="b" * 64,
                ),
            ],
        )
        errors: list[str] = []
        validator.validate_mainline_control(state, errors)
        self.assertTrue(any("not applicable" in error for error in errors))

    def test_full_validator_requires_immutable_control_input_snapshot(self) -> None:
        state = control_state()
        with tempfile.TemporaryDirectory() as temporary:
            errors: list[str] = []
            validator.validate_mainline_control(
                state,
                errors,
                Path(temporary),
            )
        self.assertTrue(
            any("control_input_path cannot be read" in error for error in errors)
        )

    def test_full_validator_accepts_matching_control_input_snapshot(self) -> None:
        snapshot = {
            "control_revision": 0,
            "state_digest": "a" * 64,
            "observed_status": "SCANNING",
            "mode": "discover",
            "interaction_mode": "GUIDED",
            "checkpoint": "SESSION_INIT",
            "completed_packet_ids": [],
            "failed_packets": [],
            "active_lanes": [],
            "accepted_verdicts": [],
            "artifact_readiness": {"PROJECT_EVIDENCE_PACK": "NOT_READY"},
            "latest_validation": {"result": "NOT_RUN", "error_codes": []},
            "budget_flags": [],
            "unresolved_blockers": [],
            "user_event": {
                "kind": "NONE",
                "receipt_id": None,
                "selected_ids": [],
            },
            "allowed_target_statuses": ["SCANNING"],
        }
        snapshot_raw = (
            json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n"
        ).encode()
        snapshot_digest = hashlib.sha256(snapshot_raw).hexdigest()
        committed = transition(control_input_digest=snapshot_digest)
        product = control_product(control_input_digest=snapshot_digest)
        state = control_state(transitions=[committed], products=[product])

        with tempfile.TemporaryDirectory() as temporary:
            session_dir = Path(temporary)
            snapshot_path = session_dir / "control-inputs" / "CTRL-0001.json"
            snapshot_path.parent.mkdir()
            snapshot_path.write_bytes(snapshot_raw)
            errors: list[str] = []
            validator.validate_accepted_work_products(state, errors)
            validator.validate_mainline_control(state, errors, session_dir)
        self.assertEqual([], errors)

    def test_full_validator_rejects_symlinked_control_input_archive(self) -> None:
        snapshot = {
            "control_revision": 0,
            "state_digest": "a" * 64,
            "observed_status": "SCANNING",
            "mode": "discover",
            "interaction_mode": "GUIDED",
            "checkpoint": "SESSION_INIT",
            "completed_packet_ids": [],
            "failed_packets": [],
            "active_lanes": [],
            "accepted_verdicts": [],
            "artifact_readiness": {"PROJECT_EVIDENCE_PACK": "NOT_READY"},
            "latest_validation": {"result": "NOT_RUN", "error_codes": []},
            "budget_flags": [],
            "unresolved_blockers": [],
            "user_event": {
                "kind": "NONE",
                "receipt_id": None,
                "selected_ids": [],
            },
            "allowed_target_statuses": ["SCANNING"],
        }
        snapshot_raw = (
            json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n"
        ).encode()
        snapshot_digest = hashlib.sha256(snapshot_raw).hexdigest()
        state = control_state(
            transitions=[transition(control_input_digest=snapshot_digest)],
            products=[control_product(control_input_digest=snapshot_digest)],
        )
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            session_dir = root / "session"
            external_dir = root / "external"
            session_dir.mkdir()
            external_dir.mkdir()
            (external_dir / "CTRL-0001.json").write_bytes(snapshot_raw)
            (session_dir / "control-inputs").symlink_to(
                external_dir,
                target_is_directory=True,
            )
            errors: list[str] = []
            validator.validate_mainline_control(state, errors, session_dir)
        self.assertTrue(
            any("must not be a symlink" in error for error in errors)
        )

    def test_archived_control_input_rejects_duplicate_json_keys(self) -> None:
        errors: list[str] = []
        parsed = validator.parse_strict_json_bytes(
            b'{"control_revision":0,"control_revision":1}',
            "snapshot",
            errors,
        )
        self.assertIsNone(parsed)
        self.assertTrue(any("duplicate object key" in error for error in errors))

    def test_archived_snapshot_malformed_nested_types_report_errors(self) -> None:
        malformed = {
            "control_revision": 0,
            "state_digest": "a" * 64,
            "observed_status": [],
            "mode": {},
            "interaction_mode": [],
            "checkpoint": {},
            "completed_packet_ids": [{}],
            "failed_packets": [
                {
                    "packet_id": [],
                    "phase": {},
                    "role": [],
                    "candidate_id": {},
                    "round": [],
                    "reason_code": {},
                    "retry_count": [],
                }
            ],
            "active_lanes": [
                {
                    "phase": "DEBATE",
                    "candidate_id": {},
                    "round": 1,
                    "last_resolved_role": [],
                    "next_role": {},
                    "dependency_packet_ids": [{}],
                    "search_required": [],
                    "lane_revision": 0,
                }
            ],
            "accepted_verdicts": [
                {"candidate_id": {}, "round": 1, "verdict": {}}
            ],
            "artifact_readiness": {"PROJECT_EVIDENCE_PACK": []},
            "latest_validation": {"result": [], "error_codes": [{}]},
            "budget_flags": [{}],
            "unresolved_blockers": [{}],
            "user_event": {
                "kind": [],
                "receipt_id": {},
                "selected_ids": [{}],
            },
            "allowed_target_statuses": [{}],
        }
        malformed_transition = transition(
            action="BLOCK_SESSION",
            to_status="BLOCKED",
            dispatches=[
                {
                    "packet_id": "BAD-DISPATCH",
                    "phase": "DEBATE",
                    "role": "Socratic Mentor",
                    "candidate_id": {},
                    "round": 1,
                    "depends_on_packet_ids": [{}],
                }
            ],
            required_actions=[],
            blocking_reasons=[{}],
        )
        errors: list[str] = []
        validator.validate_control_input_snapshot(
            malformed,
            malformed_transition,
            control_state(),
            "snapshot",
            errors,
        )
        self.assertTrue(errors)

    def test_archived_snapshot_coalesces_every_ready_lane(self) -> None:
        mentor_c1 = {
            "packet_id": "C01-R1-MENTOR",
            "phase": "DEBATE",
            "role": "Socratic Mentor",
            "candidate_id": "C01",
            "round": 1,
            "depends_on_packet_ids": [],
        }
        current = transition(
            revision=2,
            packet_id="CTRL-0002",
            checkpoint="PHASE_BOUNDARY",
            from_status="DEBATING",
            to_status="DEBATING",
            dispatches=[mentor_c1],
            required_actions=[],
            required_checks=[
                "PERSIST_STATE",
                "VERIFY_ENVELOPES",
                "ENFORCE_BUDGET",
            ],
        )
        state = control_state(
            status="DEBATING",
            transitions=[transition(), current],
            products=[],
        )
        state.update(
            {
                "max_rounds": 6,
                "initial_debate_candidate_ids": ["C01", "C02"],
                "candidates": [
                    {"candidate_id": "C01", "rounds": []},
                    {"candidate_id": "C02", "rounds": []},
                ],
            }
        )
        snapshot = {
            "control_revision": 1,
            "state_digest": "a" * 64,
            "observed_status": "DEBATING",
            "mode": "discover",
            "interaction_mode": "GUIDED",
            "checkpoint": "PHASE_BOUNDARY",
            "completed_packet_ids": [],
            "failed_packets": [],
            "active_lanes": [
                {
                    "phase": "DEBATE",
                    "candidate_id": candidate_id,
                    "round": 1,
                    "last_resolved_role": None,
                    "next_role": "Socratic Mentor",
                    "dependency_packet_ids": [],
                    "search_required": False,
                    "lane_revision": 1,
                }
                for candidate_id in ("C01", "C02")
            ],
            "accepted_verdicts": [],
            "artifact_readiness": {"CANDIDATE_DIRECTIONS": "READY"},
            "latest_validation": {"result": "NOT_RUN", "error_codes": []},
            "budget_flags": [],
            "unresolved_blockers": [],
            "user_event": {
                "kind": "NONE",
                "receipt_id": None,
                "selected_ids": [],
            },
            "allowed_target_statuses": ["DEBATING"],
        }
        errors: list[str] = []
        validator.validate_control_input_snapshot(
            snapshot,
            current,
            state,
            "snapshot",
            errors,
        )
        self.assertTrue(
            any("coalesce every ready archived lane" in error for error in errors)
        )

    def test_archived_snapshot_cannot_forge_waiting_lane(self) -> None:
        mentor_c1 = {
            "packet_id": "C01-R1-MENTOR",
            "phase": "DEBATE",
            "role": "Socratic Mentor",
            "candidate_id": "C01",
            "round": 1,
            "depends_on_packet_ids": [],
        }
        current = transition(
            revision=2,
            packet_id="CTRL-0002",
            checkpoint="PHASE_BOUNDARY",
            from_status="DEBATING",
            to_status="DEBATING",
            dispatches=[mentor_c1],
            required_actions=[],
            required_checks=[
                "PERSIST_STATE",
                "VERIFY_ENVELOPES",
                "ENFORCE_BUDGET",
            ],
        )
        state = control_state(
            status="DEBATING",
            transitions=[transition(), current],
            products=[],
        )
        state.update(
            {
                "max_rounds": 6,
                "initial_debate_candidate_ids": ["C01", "C02"],
                "candidates": [
                    {"candidate_id": "C01"},
                    {"candidate_id": "C02"},
                ],
            }
        )
        snapshot = {
            "control_revision": 1,
            "state_digest": "a" * 64,
            "observed_status": "DEBATING",
            "mode": "discover",
            "interaction_mode": "GUIDED",
            "checkpoint": "PHASE_BOUNDARY",
            "completed_packet_ids": [],
            "failed_packets": [],
            "active_lanes": [
                {
                    "phase": "DEBATE",
                    "candidate_id": "C01",
                    "round": 1,
                    "last_resolved_role": None,
                    "next_role": "Socratic Mentor",
                    "dependency_packet_ids": [],
                    "search_required": False,
                    "lane_revision": 1,
                },
                {
                    "phase": "DEBATE",
                    "candidate_id": "C02",
                    "round": 1,
                    "last_resolved_role": None,
                    "next_role": "WAIT_FOR_RESULT",
                    "dependency_packet_ids": [],
                    "search_required": False,
                    "lane_revision": 1,
                },
            ],
            "accepted_verdicts": [],
            "artifact_readiness": {"CANDIDATE_DIRECTIONS": "READY"},
            "latest_validation": {"result": "NOT_RUN", "error_codes": []},
            "budget_flags": [],
            "unresolved_blockers": [],
            "user_event": {
                "kind": "NONE",
                "receipt_id": None,
                "selected_ids": [],
            },
            "allowed_target_statuses": ["DEBATING"],
        }
        errors: list[str] = []
        validator.validate_control_input_snapshot(
            snapshot,
            current,
            state,
            "snapshot",
            errors,
        )
        self.assertTrue(
            any("historical projection" in error for error in errors)
        )

    def test_role_boundary_defers_next_round_mentor_lane(self) -> None:
        control_input = {
            "active_lanes": [
                {
                    "phase": "DEBATE",
                    "candidate_id": "C01",
                    "round": 2,
                    "next_role": "Socratic Mentor",
                    "dependency_packet_ids": ["C01-R1-JUDGE"],
                },
                {
                    "phase": "DEBATE",
                    "candidate_id": "C02",
                    "round": 1,
                    "next_role": "Panel Judge",
                    "dependency_packet_ids": [
                        "C02-MENTOR",
                        "C02-EVIDENCE",
                        "C02-DEVIL",
                    ],
                },
            ]
        }
        next_round_mentor = {
            "packet_id": "C01-R2-MENTOR",
            "phase": "DEBATE",
            "role": "Socratic Mentor",
            "candidate_id": "C01",
            "round": 2,
            "depends_on_packet_ids": ["C01-R1-JUDGE"],
        }
        current_round_judge = {
            "packet_id": "C02-R1-JUDGE",
            "phase": "DEBATE",
            "role": "Panel Judge",
            "candidate_id": "C02",
            "round": 1,
            "depends_on_packet_ids": [
                "C02-MENTOR",
                "C02-EVIDENCE",
                "C02-DEVIL",
            ],
        }
        valid_errors: list[str] = []
        controller_validator.validate_lane_dispatches(
            [current_round_judge],
            control_input,
            "ADVANCE",
            "DEBATING",
            "ROLE_BOUNDARY",
            valid_errors,
        )
        self.assertEqual([], valid_errors)

        invalid_errors: list[str] = []
        controller_validator.validate_lane_dispatches(
            [next_round_mentor, current_round_judge],
            control_input,
            "ADVANCE",
            "DEBATING",
            "ROLE_BOUNDARY",
            invalid_errors,
        )
        self.assertTrue(
            any("not eligible" in error for error in invalid_errors)
        )

    def test_archived_rq_hold_rejects_late_outcome(self) -> None:
        rq_dispatch = {
            "packet_id": "RQ-LATE",
            "phase": "RQ_REFINEMENT",
            "role": "Research Question Architect",
            "candidate_id": "C01",
            "round": None,
            "depends_on_packet_ids": [],
        }
        first = transition(
            dispatches=[rq_dispatch],
            required_actions=[],
        )
        hold = transition(
            revision=2,
            packet_id="CTRL-0002",
            checkpoint="PRE_USER_GATE",
            from_status="RQ_REFINEMENT",
            action="HOLD_FOR_USER",
            to_status="RQ_REFINEMENT",
            pending_user_gate="RQ_CONFIRMATION",
            required_actions=[],
            required_checks=["PERSIST_STATE", "RUN_SESSION_VALIDATOR"],
        )
        state = control_state(
            status="RQ_REFINEMENT",
            transitions=[first, hold],
            products=[
                research_product(
                    "RQ-LATE",
                    "RQ_REFINEMENT",
                    "Research Question Architect",
                    "C01",
                )
            ],
        )
        state.update(
            {
                "selected_candidate_id": "C01",
                "candidates": [{"candidate_id": "C01"}],
                "gate_receipts": [
                    {
                        "receipt_id": "RQ-RECEIPT",
                        "gate": "RQ_CONFIRMATION",
                        "action": "CONFIRM",
                        "values": ["C01", "RQ-LATE"],
                        "based_on_revision": 2,
                        "received_at": "2026-07-25T12:30:00+08:00",
                    }
                ],
            }
        )
        snapshot = {
            "control_revision": 1,
            "state_digest": "a" * 64,
            "observed_status": "RQ_REFINEMENT",
            "mode": "discover",
            "interaction_mode": "GUIDED",
            "checkpoint": "PRE_USER_GATE",
            "completed_packet_ids": [],
            "failed_packets": [],
            "active_lanes": [],
            "accepted_verdicts": [],
            "artifact_readiness": {"DECISION_PACKET": "READY"},
            "latest_validation": {"result": "PASS", "error_codes": []},
            "budget_flags": [],
            "unresolved_blockers": [],
            "user_event": {
                "kind": "NONE",
                "receipt_id": None,
                "selected_ids": [],
            },
            "allowed_target_statuses": ["RQ_REFINEMENT"],
        }
        errors: list[str] = []
        validator.validate_control_input_snapshot(
            snapshot,
            hold,
            state,
            "snapshot",
            errors,
        )
        self.assertTrue(any("unresolved" in error for error in errors))
        self.assertTrue(
            any("archived completed_packet_ids" in error for error in errors)
        )

    def test_archived_snapshot_requires_completed_dependencies(self) -> None:
        mapping = {
            "packet_id": "MAP-1",
            "phase": "DIRECTION_MAPPING",
            "role": "Macro Direction Mapper",
            "candidate_id": None,
            "round": None,
            "depends_on_packet_ids": [],
        }
        first = transition(dispatches=[mapping], required_actions=[])
        hotspot = {
            "packet_id": "HOTSPOT-1",
            "phase": "HOTSPOT",
            "role": "Hotspot Analyst",
            "candidate_id": None,
            "round": None,
            "depends_on_packet_ids": ["MAP-1"],
        }
        current = transition(
            revision=2,
            packet_id="CTRL-0002",
            checkpoint="PHASE_BOUNDARY",
            to_status="CANDIDATE_GENERATION",
            dispatches=[hotspot],
            required_actions=[],
            required_checks=[
                "PERSIST_STATE",
                "VERIFY_ENVELOPES",
                "ENFORCE_BUDGET",
            ],
        )
        state = control_state(
            status="CANDIDATE_GENERATION",
            transitions=[first, current],
            products=[research_product("MAP-1", "DIRECTION_MAPPING", "Macro Direction Mapper")],
        )
        snapshot = {
            "control_revision": 1,
            "state_digest": "a" * 64,
            "observed_status": "SCANNING",
            "mode": "discover",
            "interaction_mode": "GUIDED",
            "checkpoint": "PHASE_BOUNDARY",
            "completed_packet_ids": [],
            "failed_packets": [],
            "active_lanes": [],
            "accepted_verdicts": [],
            "artifact_readiness": {
                "PROJECT_EVIDENCE_PACK": "READY",
                "DIRECTION_MAP": "READY",
            },
            "latest_validation": {"result": "NOT_RUN", "error_codes": []},
            "budget_flags": [],
            "unresolved_blockers": [],
            "user_event": {
                "kind": "NONE",
                "receipt_id": None,
                "selected_ids": [],
            },
            "allowed_target_statuses": ["CANDIDATE_GENERATION"],
        }
        errors: list[str] = []
        validator.validate_control_input_snapshot(
            snapshot,
            current,
            state,
            "snapshot",
            errors,
        )
        self.assertTrue(
            any("absent from completed_packet_ids" in error for error in errors)
        )
        snapshot["allowed_target_statuses"] = ["SCANNING"]
        errors = []
        validator.validate_control_input_snapshot(
            snapshot,
            current,
            state,
            "snapshot",
            errors,
        )
        self.assertTrue(
            any("must contain the transition target" in error for error in errors)
        )

    def test_judge_cannot_skip_requested_search_and_evidence_revision(self) -> None:
        prior_dispatches = {
            packet_id: dispatch
            for packet_id, role, dependencies in (
                ("MENTOR-1", "Socratic Mentor", []),
                ("EVIDENCE-1", "Evidence Researcher", ["MENTOR-1"]),
                ("DEVIL-1", "Devil's Advocate", ["EVIDENCE-1"]),
            )
            for dispatch in [
                {
                    "packet_id": packet_id,
                    "phase": "DEBATE",
                    "role": role,
                    "candidate_id": "C01",
                    "round": 1,
                    "depends_on_packet_ids": dependencies,
                }
            ]
        }
        state = {
            "interaction_mode": "GUIDED",
            "initial_debate_candidate_ids": ["C01"],
            "candidates": [
                {
                    "candidate_id": "C01",
                    "origin": "GENERATED",
                    "status": "ACTIVE",
                }
            ],
            "mainline_control": {
                "lane_search_requests": [
                    {
                        "phase": "DEBATE",
                        "candidate_id": "C01",
                        "round": 1,
                        "source_packet_id": "DEVIL-1",
                        "reason_codes": ["PIVOTAL_CLAIM_UNVERIFIED"],
                    }
                ]
            },
        }
        judge = {
            "packet_id": "JUDGE-1",
            "phase": "DEBATE",
            "role": "Panel Judge",
            "candidate_id": "C01",
            "round": 1,
            "depends_on_packet_ids": ["MENTOR-1", "EVIDENCE-1", "DEVIL-1"],
        }
        errors: list[str] = []
        validator.validate_committed_dispatch_prerequisites(
            judge,
            state,
            set(prior_dispatches),
            prior_dispatches,
            judge["depends_on_packet_ids"],
            "judge",
            errors,
        )
        self.assertTrue(
            any("before the same-round search is accepted" in error for error in errors)
        )

    def test_active_lane_projection_drives_search_revision_sequence(self) -> None:
        screening = {
            "packet_id": "SCREEN-1",
            "phase": "SCREENING",
            "role": "Panel Judge",
            "candidate_id": None,
            "round": None,
            "depends_on_packet_ids": [],
        }
        mentor = {
            "packet_id": "MENTOR-1",
            "phase": "DEBATE",
            "role": "Socratic Mentor",
            "candidate_id": "C01",
            "round": 1,
            "depends_on_packet_ids": ["SCREEN-1"],
        }
        evidence = {
            "packet_id": "EVIDENCE-1",
            "phase": "DEBATE",
            "role": "Evidence Researcher",
            "candidate_id": "C01",
            "round": 1,
            "depends_on_packet_ids": ["MENTOR-1"],
        }
        challenge = {
            "packet_id": "DEVIL-1",
            "phase": "DEBATE",
            "role": "Devil's Advocate",
            "candidate_id": "C01",
            "round": 1,
            "depends_on_packet_ids": ["EVIDENCE-1"],
        }
        dispatches = [screening, mentor, evidence, challenge]
        transitions = [transition()]
        for revision, dispatch in enumerate(dispatches, start=2):
            transitions.append(
                transition(
                    revision=revision,
                    packet_id=f"CTRL-000{revision}",
                    digest=chr(96 + revision) * 64,
                    checkpoint="ROLE_BOUNDARY",
                    from_status="DEBATING",
                    to_status="DEBATING",
                    dispatches=[dispatch],
                    required_actions=[],
                    required_checks=[
                        "PERSIST_STATE",
                        "VERIFY_ENVELOPES",
                        "ENFORCE_BUDGET",
                    ],
                )
            )
        accepted = {
            dispatch["packet_id"]: research_product(
                dispatch["packet_id"],
                dispatch["phase"],
                dispatch["role"],
                dispatch["candidate_id"],
                dispatch["round"],
            )
            for dispatch in dispatches
        }
        state = control_state(status="DEBATING", transitions=transitions, products=[])
        state.update(
            {
                "max_rounds": 6,
                "initial_debate_candidate_ids": ["C01"],
                "candidates": [
                    {
                        "candidate_id": "C01",
                        "origin": "GENERATED",
                        "status": "ACTIVE",
                        "gate_ready": False,
                        "rounds_completed": 0,
                    }
                ],
            }
        )
        state["mainline_control"]["lane_search_requests"] = [
            {
                "phase": "DEBATE",
                "candidate_id": "C01",
                "round": 1,
                "source_packet_id": "DEVIL-1",
                "reason_codes": ["PIVOTAL_CLAIM_UNVERIFIED"],
            }
        ]

        lane = controller_validator.expected_active_lanes(state, accepted)[0]
        self.assertEqual("Search and Verification Specialist", lane["next_role"])
        self.assertEqual(["DEVIL-1"], lane["dependency_packet_ids"])

        search = {
            "packet_id": "SEARCH-1",
            "phase": "DEBATE",
            "role": "Search and Verification Specialist",
            "candidate_id": "C01",
            "round": 1,
            "depends_on_packet_ids": ["DEVIL-1"],
        }
        state["mainline_control"]["transition_log"].append(
            transition(
                revision=6,
                packet_id="CTRL-0006",
                digest="f" * 64,
                checkpoint="ROLE_BOUNDARY",
                from_status="DEBATING",
                to_status="DEBATING",
                dispatches=[search],
                required_actions=[],
                required_checks=[
                    "PERSIST_STATE",
                    "VERIFY_ENVELOPES",
                    "ENFORCE_BUDGET",
                ],
            )
        )
        state["mainline_control"]["revision"] = 6
        accepted["SEARCH-1"] = research_product(
            "SEARCH-1",
            "DEBATE",
            "Search and Verification Specialist",
            "C01",
            1,
        )
        lane = controller_validator.expected_active_lanes(state, accepted)[0]
        self.assertEqual("Evidence Researcher", lane["next_role"])
        self.assertEqual(
            ["MENTOR-1", "EVIDENCE-1", "SEARCH-1"],
            lane["dependency_packet_ids"],
        )

        revised = {
            "packet_id": "EVIDENCE-2",
            "phase": "DEBATE",
            "role": "Evidence Researcher",
            "candidate_id": "C01",
            "round": 1,
            "depends_on_packet_ids": [
                "MENTOR-1",
                "EVIDENCE-1",
                "SEARCH-1",
            ],
        }
        state["mainline_control"]["transition_log"].append(
            transition(
                revision=7,
                packet_id="CTRL-0007",
                digest="g" * 64,
                checkpoint="ROLE_BOUNDARY",
                from_status="DEBATING",
                to_status="DEBATING",
                dispatches=[revised],
                required_actions=[],
                required_checks=[
                    "PERSIST_STATE",
                    "VERIFY_ENVELOPES",
                    "ENFORCE_BUDGET",
                ],
            )
        )
        state["mainline_control"]["revision"] = 7
        accepted["EVIDENCE-2"] = research_product(
            "EVIDENCE-2",
            "DEBATE",
            "Evidence Researcher",
            "C01",
            1,
        )
        lane = controller_validator.expected_active_lanes(state, accepted)[0]
        self.assertEqual("Panel Judge", lane["next_role"])
        self.assertEqual(
            ["MENTOR-1", "EVIDENCE-2", "DEVIL-1", "SEARCH-1"],
            lane["dependency_packet_ids"],
        )

    def test_partial_lane_projection_survives_missing_earlier_roles(self) -> None:
        # Regression: a lane whose accepted packets lacked the Mentor (or the
        # Mentor and Evidence Researcher) crashed the live projection with an
        # IndexError instead of producing a validation result.
        evidence = {
            "packet_id": "EVIDENCE-1",
            "phase": "DEBATE",
            "role": "Evidence Researcher",
            "candidate_id": "C01",
            "round": 1,
            "depends_on_packet_ids": [],
        }
        search = {
            "packet_id": "SEARCH-1",
            "phase": "DEBATE",
            "role": "Search and Verification Specialist",
            "candidate_id": "C01",
            "round": 1,
            "depends_on_packet_ids": ["EVIDENCE-1"],
        }
        transitions = [transition()]
        for revision, dispatch in enumerate((evidence, search), start=2):
            transitions.append(
                transition(
                    revision=revision,
                    packet_id=f"CTRL-000{revision}",
                    digest=chr(96 + revision) * 64,
                    checkpoint="ROLE_BOUNDARY",
                    from_status="DEBATING",
                    to_status="DEBATING",
                    dispatches=[dispatch],
                    required_actions=[],
                    required_checks=[
                        "PERSIST_STATE",
                        "VERIFY_ENVELOPES",
                        "ENFORCE_BUDGET",
                    ],
                )
            )
        accepted = {
            dispatch["packet_id"]: research_product(
                dispatch["packet_id"],
                dispatch["phase"],
                dispatch["role"],
                dispatch["candidate_id"],
                dispatch["round"],
            )
            for dispatch in (evidence, search)
        }
        state = control_state(status="DEBATING", transitions=transitions, products=[])
        state.update(
            {
                "max_rounds": 6,
                "initial_debate_candidate_ids": ["C01"],
                "candidates": [
                    {
                        "candidate_id": "C01",
                        "origin": "GENERATED",
                        "status": "ACTIVE",
                        "gate_ready": False,
                        "rounds_completed": 0,
                    }
                ],
            }
        )

        lane = controller_validator.expected_active_lanes(state, accepted)[0]
        self.assertEqual("Evidence Researcher", lane["next_role"])
        self.assertEqual(["EVIDENCE-1", "SEARCH-1"], lane["dependency_packet_ids"])

        challenge = {
            "packet_id": "DEVIL-1",
            "phase": "DEBATE",
            "role": "Devil's Advocate",
            "candidate_id": "C01",
            "round": 1,
            "depends_on_packet_ids": [],
        }
        judge_transitions = [
            transition(),
            transition(
                revision=2,
                packet_id="CTRL-0002",
                digest="b" * 64,
                checkpoint="ROLE_BOUNDARY",
                from_status="DEBATING",
                to_status="DEBATING",
                dispatches=[challenge],
                required_actions=[],
                required_checks=[
                    "PERSIST_STATE",
                    "VERIFY_ENVELOPES",
                    "ENFORCE_BUDGET",
                ],
            ),
        ]
        judge_state = control_state(
            status="DEBATING", transitions=judge_transitions, products=[]
        )
        judge_state.update(
            {
                "max_rounds": 6,
                "initial_debate_candidate_ids": ["C01"],
                "candidates": [
                    {
                        "candidate_id": "C01",
                        "origin": "GENERATED",
                        "status": "ACTIVE",
                        "gate_ready": False,
                        "rounds_completed": 0,
                    }
                ],
            }
        )
        judge_accepted = {
            "DEVIL-1": research_product(
                "DEVIL-1", "DEBATE", "Devil's Advocate", "C01", 1
            )
        }

        lane = controller_validator.expected_active_lanes(
            judge_state, judge_accepted
        )[0]
        self.assertEqual("Panel Judge", lane["next_role"])
        self.assertEqual(["DEVIL-1"], lane["dependency_packet_ids"])

    def test_malformed_final_transition_reports_instead_of_crashing(self) -> None:
        # Regression: a non-object tail entry in transition_log raised an
        # AttributeError in the last-transition consistency block.
        state = control_state()
        state["mainline_control"]["transition_log"].append("not-a-transition")
        state["mainline_control"]["revision"] = 2
        errors: list[str] = []
        validator.validate_mainline_control(state, errors)
        self.assertTrue(errors)

    def test_converged_evaluation_has_no_spurious_next_round_lane(self) -> None:
        state = control_state()
        state.update(
            {
                "mode": "evaluate",
                "status": "EVALUATION_DEBATE",
                "max_rounds": 6,
                "evaluation_rounds": [
                    {"round": 1, "verdict": "CONTINUE"},
                    {"round": 2, "verdict": "CONTINUE"},
                    {"round": 3, "verdict": "CONVERGED"},
                ],
            }
        )
        self.assertEqual(
            [],
            controller_validator.expected_active_lanes(state, {}),
        )

    def test_selected_candidate_requires_user_receipt(self) -> None:
        state = control_state()
        state["selected_candidate_id"] = "C01"
        errors: list[str] = []
        validator.validate_gate_receipts(state, errors)
        self.assertTrue(
            any("selected_candidate_id requires" in error for error in errors)
        )

    def test_leaving_blocked_requires_typed_repair_receipt(self) -> None:
        blocked = transition(
            checkpoint="RECOVERY",
            action="BLOCK_SESSION",
            to_status="BLOCKED",
            required_actions=[],
            blocking_reasons=["CRITICAL_VALIDITY_FLAW"],
        )
        resumed = transition(
            revision=2,
            packet_id="CTRL-0002",
            digest="b" * 64,
            checkpoint="RESUME",
            from_status="BLOCKED",
            action="ADVANCE",
            to_status="SCANNING",
            required_actions=["APPLY_USER_REPAIR"],
        )
        state = control_state(
            status="SCANNING",
            transitions=[blocked, resumed],
            products=[
                control_product(),
                control_product("CTRL-0002", observed_revision=1, digest="b" * 64),
            ],
        )

        errors: list[str] = []
        validator.validate_gate_receipts(state, errors)
        self.assertTrue(
            any("leaving BLOCKED requires" in error for error in errors)
        )

        state["gate_receipts"] = [
            {
                "receipt_id": "GATE-BLOCKER-0001",
                "gate": "BLOCKER_DECISION",
                "action": "REPAIR",
                "values": ["SCANNING"],
                "based_on_revision": 1,
                "received_at": "2026-07-25T12:30:00+08:00",
            }
        ]
        errors = []
        validator.validate_gate_receipts(state, errors)
        self.assertEqual([], errors)

    def test_blocked_session_cannot_reblock_or_rebase_stop_receipt(self) -> None:
        blocked = transition(
            checkpoint="RECOVERY",
            action="BLOCK_SESSION",
            to_status="BLOCKED",
            required_actions=[],
            blocking_reasons=["CRITICAL_VALIDITY_FLAW"],
        )
        reblocked = transition(
            revision=2,
            packet_id="CTRL-0002",
            digest="b" * 64,
            checkpoint="RECOVERY",
            from_status="BLOCKED",
            action="BLOCK_SESSION",
            to_status="BLOCKED",
            required_actions=[],
            blocking_reasons=["CRITICAL_VALIDITY_FLAW"],
        )
        state = control_state(
            status="BLOCKED",
            transitions=[blocked, reblocked],
            products=[
                control_product(),
                control_product("CTRL-0002", observed_revision=1, digest="b" * 64),
            ],
        )
        state["gate_receipts"] = [
            {
                "receipt_id": "GATE-BLOCKER-0001",
                "gate": "BLOCKER_DECISION",
                "action": "STOP",
                "values": [],
                "based_on_revision": 2,
                "received_at": "2026-07-25T12:30:00+08:00",
            }
        ]

        errors: list[str] = []
        validator.validate_mainline_control(state, errors)
        validator.validate_gate_receipts(state, errors)
        self.assertTrue(
            any("cannot append another BLOCK_SESSION" in error for error in errors)
        )
        self.assertTrue(
            any("began the blocking episode" in error for error in errors)
        )


class StrictIntegerRegressionTests(unittest.TestCase):
    def test_evidence_intake_can_record_explicit_missing_target_fields(self) -> None:
        state = {
            "mode": "evaluate",
            "status": "EVIDENCE_INTAKE",
            "evaluation_target": {
                "direction": "",
                "primary_claim": "",
                "study_type": "",
                "constraints": [],
            },
            "experiment_inventory": [],
            "claim_evidence_matrix": [],
            "evaluation_rounds": [],
            "evaluation_decision": None,
            "next_experiment": None,
            "min_rounds": 3,
            "max_rounds": 6,
            "user_required": [
                "EVALUATION_DIRECTION",
                "PRIMARY_CLAIM",
                "STUDY_TYPE",
            ],
        }
        errors: list[str] = []
        validator.validate_evaluation_state(state, errors)
        self.assertEqual([], errors)

        state["user_required"].remove("PRIMARY_CLAIM")
        errors = []
        validator.validate_evaluation_state(state, errors)
        self.assertTrue(
            any("PRIMARY_CLAIM" in error for error in errors)
        )

    def test_round_configuration_rejects_json_float(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            session_dir = Path(temporary) / "session-1"
            session_dir.mkdir()
            state = {
                "schema_version": "1.3",
                "session_id": "session-1",
                "mode": "discover",
                "interaction_mode": "GUIDED",
                "execution_mode": "MULTI_AGENT",
                "project_root": str(session_dir),
                "project_snapshot": "snapshot-1",
                "status": "SCANNING",
                "min_rounds": 3.0,
                "default_rounds": 4,
                "max_rounds": 6,
                "macro_directions": [],
                "selected_macro_direction_ids": [],
                "direction_selection": None,
                "generated_candidate_ids": [],
                "initial_debate_candidate_ids": [],
                "user_gate_candidate_ids": [],
                "selected_candidate_id": None,
                "candidates": [],
                "source_ledger": [],
                "search_budget": {"profile": "standard", "large_downloads": []},
                "accepted_work_products": [],
                "rejected_work_products": [],
                "mainline_control": {
                    "controller_id": "MAINLINE",
                    "controller_status": "ACTIVE",
                    "revision": 0,
                    "last_checkpoint": None,
                    "pending_user_gate": None,
                    "last_controller_packet_id": None,
                    "retry_counts": {},
                    "lane_search_requests": [],
                    "transition_log": [],
                },
                "gate_receipts": [],
                "user_required": [],
                "updated_at": "2026-07-25T12:00:00+08:00",
            }
            for artifact in validator.BASE_ARTIFACTS:
                (session_dir / artifact).write_text(
                    "---\n"
                    "session_id: session-1\n"
                    f"artifact: {artifact}\n"
                    "status: SCANNING\n"
                    "updated_at: 2026-07-25T12:00:00+08:00\n"
                    "---\n",
                    encoding="utf-8",
                )
            state["min_rounds"] = 3
            valid_errors: list[str] = []
            validator.validate_state(session_dir, state, valid_errors)
            self.assertEqual([], valid_errors)

            state["min_rounds"] = 3.0
            errors: list[str] = []
            validator.validate_state(session_dir, state, errors)
            self.assertTrue(
                any("min_rounds must equal the integer 3" in error for error in errors)
            )


class StrictnessRegressionTests(unittest.TestCase):
    def test_require_keys_reports_missing_keys_via_return_value(self) -> None:
        errors: list[str] = []
        self.assertFalse(
            validator.require_keys({"a": 1}, ("a", "b"), "loc", errors)
        )
        self.assertEqual(["loc.b is required"], errors)

        errors = []
        self.assertTrue(validator.require_keys({"a": 1}, ("a",), "loc", errors))
        self.assertEqual([], errors)

    def test_stored_retry_count_must_be_exactly_one(self) -> None:
        # An explicit 0 entry passed the controller validator while the
        # session validator rejected it; both now require exactly 1.
        state = control_state()
        state["mainline_control"]["retry_counts"] = {"PACKET-1": 0}
        errors: list[str] = []
        controller_validator.validate_mainline_state(state, errors)
        self.assertTrue(any("must be integer 1" in error for error in errors))

    def test_state_parsing_rejects_duplicates_nonfinite_and_non_utf8(self) -> None:
        cases = {
            "duplicate keys": b'{"a": 1, "a": 2}',
            "non-finite": b'{"a": NaN}',
            "utf-16": '{"a": 1}'.encode("utf-16"),
            "utf-8 bom": b'\xef\xbb\xbf{"a": 1}',
        }
        for label, raw in cases.items():
            with self.subTest(case=label):
                errors: list[str] = []
                self.assertIsNone(
                    validator.parse_strict_json_bytes(raw, "state", errors)
                )
                self.assertTrue(errors)

    def test_delegated_panel_selection_check_does_not_crash(self) -> None:
        # Regression: has_delegated_panel_product() once hit a stray
        # `return not missing` (NameError) on its success path, so a fully
        # matched user-delegated direction selection crashed the validator.
        judge = {
            "packet_id": "DIRSEL-1",
            "phase": "DIRECTION_SELECTION",
            "role": "Panel Judge",
            "candidate_id": None,
            "round": None,
            "depends_on_packet_ids": [],
        }
        transitions = [
            transition(),
            transition(
                revision=2,
                packet_id="CTRL-0002",
                digest="b" * 64,
                checkpoint="PRE_USER_GATE",
                from_status="SCANNING",
                action="HOLD_FOR_USER",
                to_status="DIRECTION_GATE",
                pending_user_gate="DIRECTION_SELECTION",
                required_actions=[],
                required_checks=["PERSIST_STATE", "RUN_SESSION_VALIDATOR"],
            ),
            transition(
                revision=3,
                packet_id="CTRL-0003",
                digest="c" * 64,
                checkpoint="POST_USER_GATE",
                from_status="DIRECTION_GATE",
                to_status="SCANNING",
                dispatches=[judge],
                required_actions=[],
                required_checks=[
                    "PERSIST_STATE",
                    "VERIFY_ENVELOPES",
                    "ENFORCE_BUDGET",
                    "VERIFY_GATE_RECEIPT",
                ],
            ),
            transition(
                revision=4,
                packet_id="CTRL-0004",
                digest="d" * 64,
                checkpoint="PHASE_BOUNDARY",
                from_status="SCANNING",
                to_status="CANDIDATE_GENERATION",
                required_actions=["APPLY_PANEL_DIRECTION_SELECTION"],
                required_checks=["PERSIST_STATE"],
            ),
        ]
        products = [
            research_product(
                "DIRSEL-1", "DIRECTION_SELECTION", "Panel Judge", None, None
            )
        ]
        state = control_state(
            status="CANDIDATE_GENERATION",
            transitions=transitions,
            products=products,
        )
        state["gate_receipts"] = [
            {
                "receipt_id": "GATE-DIRECTION-0001",
                "gate": "DIRECTION_SELECTION",
                "action": "DELEGATE",
                "values": [],
                "based_on_revision": 2,
                "received_at": "2026-07-25T12:10:00+08:00",
            }
        ]
        errors: list[str] = []
        validator.validate_mainline_control(state, errors)

    def test_cli_rejects_a_duplicate_key_state_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            session_dir = Path(tmp) / "20260726-000000"
            session_dir.mkdir()
            (session_dir / "session-state.json").write_bytes(b'{"a": 1, "a": 2}')
            result = subprocess.run(
                [sys.executable, "-B", str(VALIDATOR_PATH), str(session_dir)],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(1, result.returncode)
            self.assertIn("cannot parse", result.stdout)


class ControllerDecisionTests(unittest.TestCase):
    def make_files(self, directory: Path) -> tuple[Path, Path, dict]:
        state = {
            "schema_version": "1.3",
            "session_id": "session-1",
            "mode": "discover",
            "interaction_mode": "GUIDED",
            "project_root": "/tmp/project",
            "project_snapshot": "snapshot-1",
            "status": "SCANNING",
            "max_rounds": 6,
            "candidates": [],
            "accepted_work_products": [],
            "rejected_work_products": [],
            "gate_receipts": [],
            "mainline_control": {
                "controller_id": "MAINLINE",
                "controller_status": "ACTIVE",
                "revision": 0,
                "last_checkpoint": None,
                "pending_user_gate": None,
                "last_controller_packet_id": None,
                "retry_counts": {},
                "lane_search_requests": [],
                "transition_log": [],
            },
        }
        state_path = directory / "session-state.json"
        state_path.write_text(
            json.dumps(state, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        digest = hashlib.sha256(state_path.read_bytes()).hexdigest()
        envelope = {
            "schema_version": "1.0",
            "session_id": "session-1",
            "project_root": "/tmp/project",
            "project_snapshot": "snapshot-1",
            "phase": "CONTROL",
            "role": "Mainline Workflow Controller",
            "candidate_id": None,
            "round": None,
            "packet_id": "CTRL-0001",
            "control_revision": 0,
            "state_digest": digest,
            "control_input_digest": "0" * 64,
            "context_fingerprint": "",
            "allowed_artifacts": [],
        }
        envelope["context_fingerprint"] = (
            controller_validator.expected_context_fingerprint(envelope)
        )
        output = {
            "envelope": envelope,
            "control_directive": {
                "observed_revision": 0,
                "observed_state_digest": digest,
                "observed_status": "SCANNING",
                "checkpoint": "SESSION_INIT",
                "action": "ADVANCE",
                "target_status": "SCANNING",
                "pending_user_gate": None,
                "dispatches": [],
                "required_actions": ["BUILD_PROJECT_EVIDENCE_PACK"],
                "required_checks": ["PERSIST_STATE"],
                "reason_codes": ["SESSION_INITIALIZED"],
                "blocking_reasons": [],
                "retry_key": None,
            },
        }
        output_path = directory / "controller-output.json"
        write_controller_fixture(state_path, output_path, output)
        return state_path, output_path, output

    def test_valid_bootstrap_decision(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            state_path, output_path, _output = self.make_files(Path(temporary))
            errors, _state_raw = controller_validator.validate(
                state_path, output_path
            )
            self.assertEqual([], errors)

    def test_live_control_input_malformed_failed_packet_reports_errors(self) -> None:
        state = control_state(transitions=[], products=[])
        control_input = {
            "control_revision": 0,
            "state_digest": "a" * 64,
            "observed_status": "SCANNING",
            "mode": "discover",
            "interaction_mode": "GUIDED",
            "checkpoint": [],
            "completed_packet_ids": [],
            "failed_packets": [
                {
                    "packet_id": [],
                    "phase": {},
                    "role": [],
                    "candidate_id": {},
                    "round": [],
                    "reason_code": {},
                    "retry_count": [],
                }
            ],
            "active_lanes": [
                {
                    "phase": {},
                    "candidate_id": {},
                    "round": [],
                    "last_resolved_role": [],
                    "next_role": {},
                    "dependency_packet_ids": [{}],
                    "search_required": [],
                    "lane_revision": [],
                }
            ],
            "accepted_verdicts": [
                {"candidate_id": {}, "round": [], "verdict": {}}
            ],
            "artifact_readiness": {"PROJECT_EVIDENCE_PACK": []},
            "latest_validation": {"result": [], "error_codes": [{}]},
            "budget_flags": [],
            "unresolved_blockers": [],
            "user_event": {
                "kind": [],
                "receipt_id": {},
                "selected_ids": [{}],
            },
            "allowed_target_statuses": ["SCANNING"],
        }
        errors: list[str] = []
        controller_validator.validate_control_input(
            control_input,
            state,
            "a" * 64,
            0,
            {},
            {},
            errors,
        )
        self.assertTrue(errors)

    def test_malformed_dispatch_coordinates_fail_closed(self) -> None:
        base_dispatch = {
            "packet_id": "BAD-COORDINATE",
            "phase": "DEBATE",
            "role": "Socratic Mentor",
            "candidate_id": "C01",
            "round": 1,
            "depends_on_packet_ids": [],
        }
        state = control_state(transitions=[], products=[])
        state.update(
            {
                "mode": "discover",
                "status": "DEBATING",
                "max_rounds": 6,
                "candidates": [{"candidate_id": "C01"}],
            }
        )
        for field in ("phase", "role", "candidate_id", "round"):
            for malformed in ([], {}):
                dispatch = {**base_dispatch, field: malformed}
                live_errors: list[str] = []
                controller_validator.validate_dispatches(
                    [dispatch],
                    state,
                    None,
                    "ADVANCE",
                    None,
                    "DEBATING",
                    "ROLE_BOUNDARY",
                    [],
                    {},
                    {},
                    live_errors,
                )
                self.assertTrue(live_errors)

                full_errors: list[str] = []
                validator.validate_control_dispatch(
                    dispatch,
                    "dispatch",
                    {"C01"},
                    set(),
                    full_errors,
                )
                self.assertTrue(full_errors)

    def test_rq_confirmation_waits_for_latest_replacement(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            state_path, output_path, output = self.make_files(Path(temporary))
            state = json.loads(state_path.read_text(encoding="utf-8"))
            rq_1 = {
                "packet_id": "RQ-1",
                "phase": "RQ_REFINEMENT",
                "role": "Research Question Architect",
                "candidate_id": "C01",
                "round": None,
                "depends_on_packet_ids": [],
            }
            rq_2 = {
                **rq_1,
                "packet_id": "RQ-2",
                "depends_on_packet_ids": ["RQ-1"],
            }
            first = transition(
                checkpoint="PHASE_BOUNDARY",
                from_status="RQ_REFINEMENT",
                to_status="RQ_REFINEMENT",
                dispatches=[rq_1],
                required_actions=[],
                required_checks=[
                    "PERSIST_STATE",
                    "VERIFY_ENVELOPES",
                    "ENFORCE_BUDGET",
                ],
            )
            second = transition(
                revision=2,
                packet_id="CTRL-0002",
                checkpoint="POST_USER_GATE",
                from_status="RQ_REFINEMENT",
                to_status="RQ_REFINEMENT",
                dispatches=[rq_2],
                required_actions=["APPLY_RQ_REVISION"],
                required_checks=[
                    "PERSIST_STATE",
                    "VERIFY_GATE_RECEIPT",
                    "VERIFY_ENVELOPES",
                    "ENFORCE_BUDGET",
                ],
            )
            state.update(
                {
                    "status": "RQ_REFINEMENT",
                    "selected_candidate_id": "C01",
                    "candidates": [{"candidate_id": "C01"}],
                    "accepted_work_products": [
                        research_product(
                            "RQ-1",
                            "RQ_REFINEMENT",
                            "Research Question Architect",
                            "C01",
                        )
                    ],
                }
            )
            state["mainline_control"].update(
                {
                    "revision": 2,
                    "last_checkpoint": "POST_USER_GATE",
                    "pending_user_gate": None,
                    "last_controller_packet_id": "CTRL-0002",
                    "transition_log": [first, second],
                }
            )
            state_path.write_text(
                json.dumps(state, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            digest = hashlib.sha256(state_path.read_bytes()).hexdigest()
            output["envelope"].update(
                {
                    "packet_id": "CTRL-0003",
                    "control_revision": 2,
                    "state_digest": digest,
                }
            )
            output["envelope"]["context_fingerprint"] = (
                controller_validator.expected_context_fingerprint(
                    output["envelope"]
                )
            )
            output["control_directive"].update(
                {
                    "observed_revision": 2,
                    "observed_state_digest": digest,
                    "observed_status": "RQ_REFINEMENT",
                    "checkpoint": "PRE_USER_GATE",
                    "action": "HOLD_FOR_USER",
                    "target_status": "RQ_REFINEMENT",
                    "pending_user_gate": "RQ_CONFIRMATION",
                    "dispatches": [],
                    "required_actions": [],
                    "required_checks": [
                        "PERSIST_STATE",
                        "RUN_SESSION_VALIDATOR",
                    ],
                    "reason_codes": ["RQ_CONFIRMATION_READY"],
                }
            )
            write_controller_fixture(state_path, output_path, output)
            errors, _state_raw = controller_validator.validate(
                state_path,
                output_path,
            )
            self.assertTrue(
                any("unresolved" in error for error in errors)
            )

    def test_rq_confirmation_binds_version_then_only_allows_complete(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            state_path, output_path, output = self.make_files(Path(temporary))
            state = json.loads(state_path.read_text(encoding="utf-8"))
            rq_dispatch = {
                "packet_id": "RQ-1",
                "phase": "RQ_REFINEMENT",
                "role": "Research Question Architect",
                "candidate_id": "C01",
                "round": None,
                "depends_on_packet_ids": [],
            }
            rq_transition = transition(
                checkpoint="PHASE_BOUNDARY",
                from_status="RQ_REFINEMENT",
                to_status="RQ_REFINEMENT",
                dispatches=[rq_dispatch],
                required_actions=[],
                required_checks=[
                    "PERSIST_STATE",
                    "VERIFY_ENVELOPES",
                    "ENFORCE_BUDGET",
                ],
            )
            hold = transition(
                revision=2,
                packet_id="CTRL-0002",
                checkpoint="PRE_USER_GATE",
                from_status="RQ_REFINEMENT",
                action="HOLD_FOR_USER",
                to_status="RQ_REFINEMENT",
                pending_user_gate="RQ_CONFIRMATION",
                required_actions=[],
                required_checks=["PERSIST_STATE", "RUN_SESSION_VALIDATOR"],
            )
            state.update(
                {
                    "status": "RQ_REFINEMENT",
                    "selected_candidate_id": "C01",
                    "candidates": [{"candidate_id": "C01"}],
                    "accepted_work_products": [
                        research_product(
                            "RQ-1",
                            "RQ_REFINEMENT",
                            "Research Question Architect",
                            "C01",
                        )
                    ],
                    "gate_receipts": [
                        {
                            "receipt_id": "GATE-RQ-1",
                            "gate": "RQ_CONFIRMATION",
                            "action": "CONFIRM",
                            "values": ["C01", "RQ-1"],
                            "based_on_revision": 2,
                            "received_at": "2026-07-25T12:30:00+08:00",
                        }
                    ],
                }
            )
            state["mainline_control"].update(
                {
                    "revision": 2,
                    "last_checkpoint": "PRE_USER_GATE",
                    "pending_user_gate": "RQ_CONFIRMATION",
                    "last_controller_packet_id": "CTRL-0002",
                    "transition_log": [rq_transition, hold],
                }
            )
            state_path.write_text(
                json.dumps(state, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            digest = hashlib.sha256(state_path.read_bytes()).hexdigest()
            output["envelope"].update(
                {
                    "packet_id": "CTRL-0003",
                    "control_revision": 2,
                    "state_digest": digest,
                }
            )
            output["envelope"]["context_fingerprint"] = (
                controller_validator.expected_context_fingerprint(
                    output["envelope"]
                )
            )
            output["control_directive"].update(
                {
                    "observed_revision": 2,
                    "observed_state_digest": digest,
                    "observed_status": "RQ_REFINEMENT",
                    "checkpoint": "POST_USER_GATE",
                    "action": "ADVANCE",
                    "target_status": "RQ_REFINEMENT",
                    "dispatches": [],
                    "required_actions": ["APPLY_RQ_CONFIRMATION"],
                    "required_checks": [
                        "PERSIST_STATE",
                        "VERIFY_GATE_RECEIPT",
                    ],
                    "reason_codes": ["RQ_CONFIRMATION_APPLIED"],
                }
            )
            write_controller_fixture(state_path, output_path, output)
            errors, _state_raw = controller_validator.validate(
                state_path,
                output_path,
            )
            self.assertEqual([], errors)

            acknowledgement = transition(
                revision=3,
                packet_id="CTRL-0003",
                checkpoint="POST_USER_GATE",
                from_status="RQ_REFINEMENT",
                to_status="RQ_REFINEMENT",
                required_actions=["APPLY_RQ_CONFIRMATION"],
                required_checks=["PERSIST_STATE", "VERIFY_GATE_RECEIPT"],
            )
            state["mainline_control"].update(
                {
                    "revision": 3,
                    "last_checkpoint": "POST_USER_GATE",
                    "pending_user_gate": None,
                    "last_controller_packet_id": "CTRL-0003",
                    "transition_log": [rq_transition, hold, acknowledgement],
                }
            )
            state_path.write_text(
                json.dumps(state, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            digest = hashlib.sha256(state_path.read_bytes()).hexdigest()
            output["envelope"].update(
                {
                    "packet_id": "CTRL-0004",
                    "control_revision": 3,
                    "state_digest": digest,
                }
            )
            output["envelope"]["context_fingerprint"] = (
                controller_validator.expected_context_fingerprint(
                    output["envelope"]
                )
            )
            output["control_directive"].update(
                {
                    "observed_revision": 3,
                    "observed_state_digest": digest,
                    "checkpoint": "PRE_COMPLETE",
                    "action": "COMPLETE",
                    "target_status": "COMPLETE",
                    "dispatches": [],
                    "required_actions": [],
                    "required_checks": [
                        "PERSIST_STATE",
                        "RUN_SESSION_VALIDATOR",
                    ],
                    "reason_codes": ["RQ_CONFIRMED_COMPLETE"],
                }
            )
            write_controller_fixture(state_path, output_path, output)
            errors, _state_raw = controller_validator.validate(
                state_path,
                output_path,
            )
            self.assertEqual([], errors)

            output["control_directive"].update(
                {
                    "checkpoint": "PHASE_BOUNDARY",
                    "action": "ADVANCE",
                    "target_status": "RQ_REFINEMENT",
                    "dispatches": [
                        {
                            **rq_dispatch,
                            "packet_id": "RQ-2",
                            "depends_on_packet_ids": ["RQ-1"],
                        }
                    ],
                    "required_actions": [],
                    "required_checks": [
                        "PERSIST_STATE",
                        "VERIFY_ENVELOPES",
                        "ENFORCE_BUDGET",
                    ],
                    "reason_codes": ["SUPERSEDE_ACCEPTED_CALL"],
                }
            )
            write_controller_fixture(state_path, output_path, output)
            errors, _state_raw = controller_validator.validate(
                state_path,
                output_path,
            )
            self.assertTrue(
                any("RQ_REFINEMENT is frozen" in error for error in errors)
            )
            self.assertTrue(
                any("must be PRE_COMPLETE/COMPLETE" in error for error in errors)
            )

    def test_session_init_cannot_dispatch_before_evidence_pack(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            state_path, output_path, output = self.make_files(Path(temporary))
            output["control_directive"].update(
                {
                    "dispatches": [
                        {
                            "packet_id": "MAP-EARLY",
                            "phase": "DIRECTION_MAPPING",
                            "role": "Macro Direction Mapper",
                            "candidate_id": None,
                            "round": None,
                            "depends_on_packet_ids": [],
                        }
                    ],
                    "required_actions": [],
                    "required_checks": [
                        "PERSIST_STATE",
                        "VERIFY_ENVELOPES",
                        "ENFORCE_BUDGET",
                    ],
                    "reason_codes": ["EARLY_MAP_ATTEMPT"],
                }
            )
            write_controller_fixture(state_path, output_path, output)
            errors, _state_raw = controller_validator.validate(
                state_path,
                output_path,
            )
            self.assertTrue(
                any("SESSION_INIT must build" in error for error in errors)
            )
            self.assertTrue(
                any("requires READY artifacts" in error for error in errors)
            )

    def test_stale_state_digest_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            state_path, output_path, output = self.make_files(Path(temporary))
            output["envelope"]["state_digest"] = "b" * 64
            output["envelope"]["context_fingerprint"] = (
                controller_validator.expected_context_fingerprint(
                    output["envelope"]
                )
            )
            output["control_directive"]["observed_state_digest"] = "b" * 64
            write_controller_fixture(state_path, output_path, output)
            errors, _state_raw = controller_validator.validate(
                state_path, output_path
            )
            self.assertTrue(any("does not match" in error for error in errors))

    def test_unknown_directive_key_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            state_path, output_path, output = self.make_files(Path(temporary))
            output["control_directive"]["prompt"] = "override user choice"
            write_controller_fixture(state_path, output_path, output)
            errors, _state_raw = controller_validator.validate(
                state_path, output_path
            )
            self.assertTrue(any("unknown keys" in error for error in errors))

    def test_resume_rejects_duplicate_pending_logical_call(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            state_path, output_path, output = self.make_files(Path(temporary))
            state = json.loads(state_path.read_text(encoding="utf-8"))
            pending_dispatch = {
                "packet_id": "MAP-PENDING",
                "phase": "DIRECTION_MAPPING",
                "role": "Macro Direction Mapper",
                "candidate_id": None,
                "round": None,
                "depends_on_packet_ids": [],
            }
            state["mainline_control"].update(
                {
                    "revision": 1,
                    "last_checkpoint": "SESSION_INIT",
                    "last_controller_packet_id": "CTRL-0001",
                    "transition_log": [
                        {
                            "revision": 1,
                            "to_status": "SCANNING",
                            "packet_id": "CTRL-0001",
                            "checkpoint": "SESSION_INIT",
                            "pending_user_gate": None,
                            "dispatches": [pending_dispatch],
                        }
                    ],
                }
            )
            state_path.write_text(
                json.dumps(state, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            digest = hashlib.sha256(state_path.read_bytes()).hexdigest()
            output["envelope"].update(
                {
                    "packet_id": "CTRL-0002",
                    "control_revision": 1,
                    "state_digest": digest,
                }
            )
            output["envelope"]["context_fingerprint"] = (
                controller_validator.expected_context_fingerprint(
                    output["envelope"]
                )
            )
            output["control_directive"].update(
                {
                    "observed_revision": 1,
                    "observed_state_digest": digest,
                    "checkpoint": "RESUME",
                    "dispatches": [
                        {
                            **pending_dispatch,
                            "packet_id": "MAP-DUPLICATE",
                        }
                    ],
                    "required_actions": [],
                    "required_checks": [
                        "PERSIST_STATE",
                        "VERIFY_ENVELOPES",
                        "ENFORCE_BUDGET",
                    ],
                }
            )
            write_controller_fixture(state_path, output_path, output)
            errors, _state_raw = controller_validator.validate(
                state_path, output_path
            )
            self.assertTrue(
                any("unresolved prior dispatch" in error for error in errors)
            )

    def test_rejected_dispatch_requires_one_non_chained_retry(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            state_path, output_path, output = self.make_files(Path(temporary))
            state = json.loads(state_path.read_text(encoding="utf-8"))
            failed_dispatch = {
                "packet_id": "FAILED-1",
                "phase": "DIRECTION_MAPPING",
                "role": "Macro Direction Mapper",
                "candidate_id": None,
                "round": None,
                "depends_on_packet_ids": [],
            }
            state["rejected_work_products"] = [
                {
                    "role": "Macro Direction Mapper",
                    "packet_id": "FAILED-1",
                    "candidate_id": None,
                    "round": None,
                    "reason_code": "ROLE_CONTRACT_VIOLATION",
                    "reason": "bad output",
                }
            ]
            state["mainline_control"].update(
                {
                    "revision": 1,
                    "last_checkpoint": "SESSION_INIT",
                    "last_controller_packet_id": "CTRL-0001",
                    "transition_log": [
                        transition(
                            dispatches=[failed_dispatch],
                            required_actions=[],
                            required_checks=[
                                "PERSIST_STATE",
                                "VERIFY_ENVELOPES",
                                "ENFORCE_BUDGET",
                            ],
                        )
                    ],
                }
            )
            state_path.write_text(
                json.dumps(state, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            digest = hashlib.sha256(state_path.read_bytes()).hexdigest()
            retry_dispatch = {
                **failed_dispatch,
                "packet_id": "RETRY-1",
            }
            output["envelope"].update(
                {
                    "packet_id": "CTRL-0002",
                    "control_revision": 1,
                    "state_digest": digest,
                }
            )
            output["envelope"]["context_fingerprint"] = (
                controller_validator.expected_context_fingerprint(
                    output["envelope"]
                )
            )
            output["control_directive"].update(
                {
                    "observed_revision": 1,
                    "observed_state_digest": digest,
                    "checkpoint": "RECOVERY",
                    "dispatches": [retry_dispatch],
                    "required_actions": [],
                    "required_checks": [
                        "PERSIST_STATE",
                        "VERIFY_ENVELOPES",
                        "ENFORCE_BUDGET",
                    ],
                    "reason_codes": ["RETRY_REQUIRED"],
                }
            )
            write_controller_fixture(state_path, output_path, output)

            errors, _state_raw = controller_validator.validate(
                state_path, output_path
            )
            self.assertTrue(
                any("outside its one RETRY_ROLE" in error for error in errors)
            )

            output["control_directive"].update(
                {
                    "action": "RETRY_ROLE",
                    "retry_key": "FAILED-1",
                }
            )
            write_controller_fixture(state_path, output_path, output)
            errors, _state_raw = controller_validator.validate(
                state_path, output_path
            )
            self.assertEqual([], errors)

            state["rejected_work_products"].append(
                {
                    "role": "Macro Direction Mapper",
                    "packet_id": "RETRY-1",
                    "candidate_id": None,
                    "round": None,
                    "reason_code": "ROLE_CONTRACT_VIOLATION",
                    "reason": "retry also failed",
                }
            )
            state["mainline_control"].update(
                {
                    "revision": 2,
                    "last_checkpoint": "RECOVERY",
                    "last_controller_packet_id": "CTRL-0002",
                    "retry_counts": {"FAILED-1": 1},
                    "transition_log": [
                        state["mainline_control"]["transition_log"][0],
                        transition(
                            revision=2,
                            packet_id="CTRL-0002",
                            digest="b" * 64,
                            checkpoint="RECOVERY",
                            action="RETRY_ROLE",
                            dispatches=[retry_dispatch],
                            required_actions=[],
                            required_checks=[
                                "PERSIST_STATE",
                                "VERIFY_ENVELOPES",
                                "ENFORCE_BUDGET",
                            ],
                            retry_key="FAILED-1",
                        ),
                    ],
                }
            )
            state_path.write_text(
                json.dumps(state, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            digest = hashlib.sha256(state_path.read_bytes()).hexdigest()
            output["envelope"].update(
                {
                    "packet_id": "CTRL-0003",
                    "control_revision": 2,
                    "state_digest": digest,
                }
            )
            output["envelope"]["context_fingerprint"] = (
                controller_validator.expected_context_fingerprint(
                    output["envelope"]
                )
            )
            output["control_directive"].update(
                {
                    "observed_revision": 2,
                    "observed_state_digest": digest,
                    "dispatches": [{**retry_dispatch, "packet_id": "RETRY-2"}],
                    "retry_key": "RETRY-1",
                    "reason_codes": ["INVALID_RETRY_CHAIN"],
                }
            )
            write_controller_fixture(state_path, output_path, output)
            errors, _state_raw = controller_validator.validate(
                state_path, output_path
            )
            self.assertTrue(
                any("retry chains are forbidden" in error for error in errors)
            )

    def test_blocked_session_cannot_advance_without_repair_receipt(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            state_path, output_path, output = self.make_files(Path(temporary))
            state = json.loads(state_path.read_text(encoding="utf-8"))
            state.update({"status": "BLOCKED"})
            state["mainline_control"].update(
                {
                    "revision": 1,
                    "last_checkpoint": "RECOVERY",
                    "last_controller_packet_id": "CTRL-0001",
                    "transition_log": [
                        transition(
                            checkpoint="RECOVERY",
                            action="BLOCK_SESSION",
                            to_status="BLOCKED",
                            required_actions=[],
                            blocking_reasons=["CRITICAL_VALIDITY_FLAW"],
                        )
                    ],
                }
            )
            state_path.write_text(
                json.dumps(state, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            digest = hashlib.sha256(state_path.read_bytes()).hexdigest()
            output["envelope"].update(
                {
                    "packet_id": "CTRL-0002",
                    "control_revision": 1,
                    "state_digest": digest,
                }
            )
            output["envelope"]["context_fingerprint"] = (
                controller_validator.expected_context_fingerprint(
                    output["envelope"]
                )
            )
            output["control_directive"].update(
                {
                    "observed_revision": 1,
                    "observed_state_digest": digest,
                    "observed_status": "BLOCKED",
                    "checkpoint": "RESUME",
                    "action": "ADVANCE",
                    "target_status": "SCANNING",
                    "required_actions": ["APPLY_USER_REPAIR"],
                    "reason_codes": ["USER_REPAIR_ACCEPTED"],
                }
            )
            write_controller_fixture(state_path, output_path, output)

            errors, _state_raw = controller_validator.validate(
                state_path, output_path
            )
            self.assertTrue(
                any("requires a direct BLOCKER_DECISION receipt" in error for error in errors)
            )

            state["gate_receipts"] = [
                {
                    "receipt_id": "GATE-BLOCKER-0001",
                    "gate": "BLOCKER_DECISION",
                    "action": "REPAIR",
                    "values": ["SCANNING"],
                    "based_on_revision": 1,
                    "received_at": "2026-07-25T12:30:00+08:00",
                }
            ]
            state_path.write_text(
                json.dumps(state, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            digest = hashlib.sha256(state_path.read_bytes()).hexdigest()
            output["envelope"]["state_digest"] = digest
            output["envelope"]["context_fingerprint"] = (
                controller_validator.expected_context_fingerprint(
                    output["envelope"]
                )
            )
            output["control_directive"]["observed_state_digest"] = digest
            write_controller_fixture(state_path, output_path, output)
            errors, _state_raw = controller_validator.validate(
                state_path, output_path
            )
            self.assertEqual([], errors)

    def test_blocker_stop_receipt_cannot_resume_session(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            state_path, output_path, output = self.make_files(Path(temporary))
            state = json.loads(state_path.read_text(encoding="utf-8"))
            state.update({"status": "BLOCKED"})
            state["gate_receipts"] = [
                {
                    "receipt_id": "GATE-BLOCKER-0001",
                    "gate": "BLOCKER_DECISION",
                    "action": "STOP",
                    "values": [],
                    "based_on_revision": 1,
                    "received_at": "2026-07-25T12:30:00+08:00",
                }
            ]
            state["mainline_control"].update(
                {
                    "revision": 1,
                    "last_checkpoint": "RECOVERY",
                    "last_controller_packet_id": "CTRL-0001",
                    "transition_log": [
                        transition(
                            checkpoint="RECOVERY",
                            action="BLOCK_SESSION",
                            to_status="BLOCKED",
                            required_actions=[],
                            blocking_reasons=["CRITICAL_VALIDITY_FLAW"],
                        )
                    ],
                }
            )
            state_path.write_text(
                json.dumps(state, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            digest = hashlib.sha256(state_path.read_bytes()).hexdigest()
            output["envelope"].update(
                {
                    "packet_id": "CTRL-0002",
                    "control_revision": 1,
                    "state_digest": digest,
                }
            )
            output["envelope"]["context_fingerprint"] = (
                controller_validator.expected_context_fingerprint(
                    output["envelope"]
                )
            )
            output["control_directive"].update(
                {
                    "observed_revision": 1,
                    "observed_state_digest": digest,
                    "observed_status": "BLOCKED",
                    "checkpoint": "RESUME",
                    "action": "ADVANCE",
                    "target_status": "SCANNING",
                    "required_actions": ["APPLY_USER_REPAIR"],
                    "reason_codes": ["INVALID_RESUME_ATTEMPT"],
                }
            )
            write_controller_fixture(state_path, output_path, output)
            errors, _state_raw = controller_validator.validate(
                state_path, output_path
            )
            self.assertTrue(
                any("STOP keeps the session BLOCKED" in error for error in errors)
            )

            output["control_directive"].update(
                {
                    "action": "BLOCK_SESSION",
                    "target_status": "BLOCKED",
                    "required_actions": [],
                    "blocking_reasons": ["CRITICAL_VALIDITY_FLAW"],
                    "reason_codes": ["INVALID_REBLOCK_ATTEMPT"],
                }
            )
            write_controller_fixture(state_path, output_path, output)
            errors, _state_raw = controller_validator.validate(
                state_path, output_path
            )
            self.assertTrue(
                any("cannot append another BLOCK_SESSION" in error for error in errors)
            )


class RoleBoundaryResolvedWindowTests(unittest.TestCase):
    """ROLE_BOUNDARY must see resolved work committed since the previous
    boundary checkpoint, not only in the single latest committed batch.

    Incident regression: a single-dispatch RECOVERY retry batch for one
    failing lane (C03) must not mask the resolved Devil's Advocate packets
    of the sibling lanes (C02/C04) committed at the preceding
    ROLE_BOUNDARY batch.
    """

    CANDIDATES = ("C02", "C03", "C04")

    @staticmethod
    def lane_dispatch(
        role: str,
        candidate: str,
        packet_id: str,
        depends: list[str] | None = None,
    ) -> dict:
        return {
            "packet_id": packet_id,
            "phase": "DEBATE",
            "role": role,
            "candidate_id": candidate,
            "round": 1,
            "depends_on_packet_ids": [] if depends is None else depends,
        }

    @classmethod
    def debate_state(cls, *, include_recovery: bool, resolve_devils: bool) -> dict:
        mentors = [
            cls.lane_dispatch(
                "Socratic Mentor", candidate, f"{candidate}-R1-MENTOR"
            )
            for candidate in cls.CANDIDATES
        ]
        devils = [
            cls.lane_dispatch(
                "Devil's Advocate",
                candidate,
                f"{candidate}-R1-DEVIL",
                depends=[f"{candidate}-R1-MENTOR"],
            )
            for candidate in cls.CANDIDATES
        ]
        transitions = [
            transition(required_actions=[]),
            transition(
                revision=2,
                packet_id="CTRL-0002",
                checkpoint="PHASE_BOUNDARY",
                from_status="SCANNING",
                to_status="CANDIDATE_GENERATION",
                required_actions=[],
            ),
            transition(
                revision=3,
                packet_id="CTRL-0003",
                checkpoint="PHASE_BOUNDARY",
                from_status="CANDIDATE_GENERATION",
                to_status="DEBATING",
                dispatches=mentors,
                required_actions=[],
            ),
            transition(
                revision=4,
                packet_id="CTRL-0004",
                checkpoint="ROLE_BOUNDARY",
                from_status="DEBATING",
                to_status="DEBATING",
                dispatches=devils,
                required_actions=[],
            ),
        ]
        if include_recovery:
            transitions.append(
                transition(
                    revision=5,
                    packet_id="CTRL-0005",
                    checkpoint="RECOVERY",
                    from_status="DEBATING",
                    to_status="DEBATING",
                    action="RETRY_ROLE",
                    dispatches=[
                        {**devils[1], "packet_id": "C03-R1-DEVIL-RT"}
                    ],
                    required_actions=[],
                    retry_key="C03-R1-DEVIL",
                )
            )
        products = [
            control_product(
                packet_id=item["packet_id"],
                observed_revision=item["revision"] - 1,
            )
            for item in transitions
        ]
        products.extend(
            research_product(
                f"{candidate}-R1-MENTOR",
                "DEBATE",
                "Socratic Mentor",
                candidate,
                1,
            )
            for candidate in cls.CANDIDATES
        )
        if resolve_devils:
            products.extend(
                research_product(
                    f"{candidate}-R1-DEVIL",
                    "DEBATE",
                    "Devil's Advocate",
                    candidate,
                    1,
                )
                for candidate in ("C02", "C04")
            )
        state = control_state(
            status="DEBATING",
            transitions=transitions,
            products=products,
        )
        state["max_rounds"] = 6
        state["candidates"] = [
            {"candidate_id": candidate} for candidate in cls.CANDIDATES
        ]
        if include_recovery:
            state["rejected_work_products"] = [
                {
                    "role": "Devil's Advocate",
                    "packet_id": "C03-R1-DEVIL",
                    "candidate_id": "C03",
                    "round": 1,
                    "reason_code": "ROLE_CONTRACT_VIOLATION",
                    "reason": "transport failure",
                }
            ]
            state["mainline_control"]["retry_counts"] = {"C03-R1-DEVIL": 1}
        return state

    @classmethod
    def role_boundary_snapshot(cls, current: dict, state: dict) -> dict:
        completed = [
            product["packet_id"]
            for product in state["accepted_work_products"]
            if product.get("phase") != "CONTROL"
        ]
        failed = [
            {
                "packet_id": product["packet_id"],
                "phase": "DEBATE",
                "role": product["role"],
                "candidate_id": product["candidate_id"],
                "round": product["round"],
                "reason_code": product["reason_code"],
                "retry_count": 1,
            }
            for product in state["rejected_work_products"]
        ]
        return {
            "control_revision": current["observed_revision"],
            "state_digest": current["observed_state_digest"],
            "observed_status": current["from_status"],
            "mode": "discover",
            "interaction_mode": "GUIDED",
            "checkpoint": "ROLE_BOUNDARY",
            "completed_packet_ids": completed,
            "failed_packets": failed,
            "active_lanes": [],
            "accepted_verdicts": [],
            "artifact_readiness": {"PROJECT_EVIDENCE_PACK": "READY"},
            "latest_validation": {"result": "PASS", "error_codes": []},
            "budget_flags": [],
            "unresolved_blockers": [],
            "user_event": {
                "kind": "NONE",
                "receipt_id": None,
                "selected_ids": [],
            },
            "allowed_target_statuses": ["DEBATING"],
        }

    def next_role_boundary(self, state: dict) -> dict:
        revision = state["mainline_control"]["revision"] + 1
        return transition(
            revision=revision,
            packet_id=f"CTRL-{revision:04d}",
            checkpoint="ROLE_BOUNDARY",
            from_status="DEBATING",
            to_status="DEBATING",
            required_actions=[],
        )

    def run_decision_validator(self, state: dict) -> list[str]:
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            state_path = directory / "session-state.json"
            state_path.write_text(
                json.dumps(state, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            digest = hashlib.sha256(state_path.read_bytes()).hexdigest()
            revision = state["mainline_control"]["revision"]
            envelope = {
                "schema_version": "1.0",
                "session_id": "session-1",
                "project_root": "/tmp/project",
                "project_snapshot": "snapshot-1",
                "phase": "CONTROL",
                "role": "Mainline Workflow Controller",
                "candidate_id": None,
                "round": None,
                "packet_id": f"CTRL-{revision + 1:04d}",
                "control_revision": revision,
                "state_digest": digest,
                "control_input_digest": "0" * 64,
                "context_fingerprint": "",
                "allowed_artifacts": [],
            }
            output = {
                "envelope": envelope,
                "control_directive": {
                    "observed_revision": revision,
                    "observed_state_digest": digest,
                    "observed_status": "DEBATING",
                    "checkpoint": "ROLE_BOUNDARY",
                    "action": "ADVANCE",
                    "target_status": "DEBATING",
                    "pending_user_gate": None,
                    "dispatches": [],
                    "required_actions": [],
                    "required_checks": ["PERSIST_STATE"],
                    "reason_codes": ["ROLE_BATCH_READY"],
                    "blocking_reasons": [],
                    "retry_key": None,
                },
            }
            output_path = directory / "controller-output.json"
            write_controller_fixture(state_path, output_path, output)
            errors, _state_raw = controller_validator.validate(
                state_path, output_path
            )
            return errors

    def test_decision_role_boundary_sees_resolved_work_behind_pending_retry(
        self,
    ) -> None:
        state = self.debate_state(include_recovery=True, resolve_devils=True)
        errors = self.run_decision_validator(state)
        self.assertFalse(
            [error for error in errors if "ROLE_BOUNDARY requires" in error],
            errors,
        )

    def test_decision_role_boundary_rejects_nothing_resolved_since_boundary(
        self,
    ) -> None:
        state = self.debate_state(include_recovery=False, resolve_devils=False)
        errors = self.run_decision_validator(state)
        self.assertTrue(
            any(
                "ROLE_BOUNDARY requires at least one resolved dispatch "
                "committed since the previous boundary checkpoint" in error
                for error in errors
            ),
            errors,
        )

    def test_session_log_role_boundary_sees_resolved_work_behind_pending_retry(
        self,
    ) -> None:
        state = self.debate_state(include_recovery=True, resolve_devils=True)
        current = self.next_role_boundary(state)
        state["mainline_control"]["transition_log"].append(current)
        state["mainline_control"]["revision"] = current["revision"]
        state["mainline_control"]["last_checkpoint"] = "ROLE_BOUNDARY"
        state["mainline_control"]["last_controller_packet_id"] = current[
            "packet_id"
        ]
        state["accepted_work_products"].append(
            control_product(
                packet_id=current["packet_id"],
                observed_revision=current["revision"] - 1,
            )
        )
        log_errors: list[str] = []
        validator.validate_mainline_control(state, log_errors)
        self.assertFalse(
            [error for error in log_errors if "ROLE_BOUNDARY requires" in error],
            log_errors,
        )

        snapshot_errors: list[str] = []
        validator.validate_control_input_snapshot(
            self.role_boundary_snapshot(current, state),
            current,
            state,
            "snapshot",
            snapshot_errors,
        )
        self.assertFalse(
            [
                error
                for error in snapshot_errors
                if "ROLE_BOUNDARY requires" in error
            ],
            snapshot_errors,
        )

    def test_session_log_role_boundary_rejects_nothing_resolved_since_boundary(
        self,
    ) -> None:
        state = self.debate_state(include_recovery=False, resolve_devils=False)
        current = self.next_role_boundary(state)
        state["mainline_control"]["transition_log"].append(current)
        state["mainline_control"]["revision"] = current["revision"]
        state["mainline_control"]["last_checkpoint"] = "ROLE_BOUNDARY"
        state["mainline_control"]["last_controller_packet_id"] = current[
            "packet_id"
        ]
        state["accepted_work_products"].append(
            control_product(
                packet_id=current["packet_id"],
                observed_revision=current["revision"] - 1,
            )
        )
        log_errors: list[str] = []
        validator.validate_mainline_control(state, log_errors)
        self.assertTrue(
            any(
                "ROLE_BOUNDARY requires a resolved dispatch committed since "
                "the previous boundary checkpoint" in error
                for error in log_errors
            ),
            log_errors,
        )

        snapshot_errors: list[str] = []
        validator.validate_control_input_snapshot(
            self.role_boundary_snapshot(current, state),
            current,
            state,
            "snapshot",
            snapshot_errors,
        )
        self.assertTrue(
            any(
                "ROLE_BOUNDARY requires at least one packet dispatched since "
                "the previous boundary checkpoint" in error
                for error in snapshot_errors
            ),
            snapshot_errors,
        )


if __name__ == "__main__":
    unittest.main()
