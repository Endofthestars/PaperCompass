from __future__ import annotations

import hashlib
import importlib.util
import json
import stat
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from fixture_builders import build_schema14_session, write_dispatch_draft


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = (
    ROOT
    / "plugins"
    / "hotspot-to-rq"
    / "skills"
    / "research-direction-debate"
    / "scripts"
)


def load_module(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / filename)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


dispatch_builder = load_module(
    "hotspot_build_codex_dispatch_test",
    "build_codex_dispatch.py",
)
batch_validator = load_module(
    "hotspot_validate_codex_dispatch_batch_test",
    "validate_codex_dispatch_batch.py",
)


def standard_search_budget() -> dict:
    return {
        "profile": "standard",
        "max_query_batches": 2,
        "max_queries_per_batch": 4,
        "max_new_sources": 8,
        "extension": {
            "approved": False,
            "approval_packet_id": None,
            "judge_reason": None,
            "extra_query_batches": 0,
            "extra_sources": 0,
        },
        "large_downloads": [],
    }


class CodexDispatchTests(unittest.TestCase):
    def write_draft(
        self,
        session: Path,
        *,
        packet_id: str,
        candidate_id: str | None,
        phase: str = "DEBATE",
        role: str = "Socratic Mentor",
        round_number: int | None = 1,
        role_instructions: str = "Ask one bounded Socratic question.",
        inline_payload: object | None = None,
        search_budget: dict | None = None,
    ) -> None:
        write_dispatch_draft(
            session,
            packet_id=packet_id,
            candidate_id=candidate_id,
            phase=phase,
            role=role,
            round_number=round_number,
            role_instructions=role_instructions,
            inline_payload=inline_payload,
            search_budget=search_budget,
        )

    def make_session(self, root: Path, packet_id: str = "C01-R1-MENTOR") -> Path:
        return build_schema14_session(
            root,
            packet_id=packet_id,
        )

    def build(
        self,
        session: Path,
        packet_id: str = "C01-R1-MENTOR",
        *,
        checkpoint: str = "ROLE_BOUNDARY",
        max_chars: int = 1_024,
    ):
        return dispatch_builder.build_dispatch(
            session,
            draft_relative_path=(
                f"control-inputs/dispatch-drafts/{packet_id}.json"
            ),
            checkpoint=checkpoint,
            artifacts=["project-evidence-pack.md"],
            max_chars=max_chars,
        )

    def write_controller_output(
        self,
        session: Path,
        *,
        packet_id: str = "C01-R1-MENTOR",
        role: str = "Socratic Mentor",
        checkpoint: str = "ROLE_BOUNDARY",
    ) -> None:
        output = {
            "envelope": {"packet_id": "CTRL-UNIT"},
            "control_directive": {
                "checkpoint": checkpoint,
                "dispatches": [
                    {
                        "packet_id": packet_id,
                        "phase": "DEBATE",
                        "role": role,
                        "candidate_id": "C01",
                        "round": 1,
                        "depends_on_packet_ids": [],
                    }
                ]
            }
        }
        (session / "controller-output.json").write_text(
            json.dumps(output, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    def validate_unit_batch(
        self,
        session: Path,
        controller_output: str = "controller-output.json",
    ) -> list[str]:
        state_raw = (session / "session-state.json").read_bytes()
        with mock.patch.object(
            batch_validator.controller_validator,
            "validate",
            return_value=([], state_raw),
        ):
            return batch_validator.validate_batch(session, controller_output)

    def write_valid_empty_controller_batch(self, session: Path) -> None:
        state = {
            "schema_version": "1.4",
            "transport_profile": "CODEX",
            "session_id": "session-1",
            "mode": "discover",
            "interaction_mode": "GUIDED",
            "project_root": str(session.parent.resolve()),
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
        state_path = session / "session-state.json"
        state_path.write_text(
            json.dumps(state, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        state_digest = hashlib.sha256(state_path.read_bytes()).hexdigest()
        control_input = {
            "control_revision": 0,
            "state_digest": state_digest,
            "observed_status": "SCANNING",
            "mode": "discover",
            "interaction_mode": "GUIDED",
            "transport_profile": "CODEX",
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
        control_input_path = session / "control-input.json"
        control_input_path.write_text(
            json.dumps(control_input, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        envelope = {
            "schema_version": "1.0",
            "session_id": "session-1",
            "project_root": str(session.parent.resolve()),
            "project_snapshot": "snapshot-1",
            "phase": "CONTROL",
            "role": "Mainline Workflow Controller",
            "candidate_id": None,
            "round": None,
            "packet_id": "CTRL-0001",
            "control_revision": 0,
            "state_digest": state_digest,
            "control_input_digest": hashlib.sha256(
                control_input_path.read_bytes()
            ).hexdigest(),
            "context_fingerprint": "",
            "allowed_artifacts": [],
        }
        envelope["context_fingerprint"] = (
            batch_validator.controller_validator.expected_context_fingerprint(
                envelope
            )
        )
        output = {
            "envelope": envelope,
            "control_directive": {
                "observed_revision": 0,
                "observed_state_digest": state_digest,
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
        (session / "controller-output.json").write_text(
            json.dumps(output, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    def write_valid_nonempty_controller_batch(self, session: Path) -> None:
        project_root = str(session.parent.resolve())
        historical_digest = "a" * 64
        historical_input = {
            "control_revision": 0,
            "state_digest": historical_digest,
            "observed_status": "SCANNING",
            "mode": "discover",
            "interaction_mode": "GUIDED",
            "transport_profile": "CODEX",
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
        historical_input_raw = (
            json.dumps(historical_input, ensure_ascii=False, indent=2) + "\n"
        ).encode("utf-8")
        historical_input_digest = hashlib.sha256(
            historical_input_raw
        ).hexdigest()
        historical_input_path = session / "control-inputs" / "CTRL-0001.json"
        historical_input_path.parent.mkdir(parents=True, exist_ok=True)
        historical_input_path.write_bytes(historical_input_raw)
        historical_input_path.chmod(0o400)
        historical_envelope = {
            "session_id": "session-1",
            "project_root": project_root,
            "project_snapshot": "snapshot-1",
            "phase": "CONTROL",
            "role": "Mainline Workflow Controller",
            "candidate_id": None,
            "round": None,
            "packet_id": "CTRL-0001",
            "control_revision": 0,
            "state_digest": historical_digest,
            "control_input_digest": historical_input_digest,
        }
        historical_product = {
            **historical_envelope,
            "context_fingerprint": (
                batch_validator.controller_validator.expected_context_fingerprint(
                    historical_envelope
                )
            ),
        }
        historical_transition = {
            "revision": 1,
            "observed_revision": 0,
            "packet_id": "CTRL-0001",
            "observed_state_digest": historical_digest,
            "control_input_digest": historical_input_digest,
            "control_input_path": "control-inputs/CTRL-0001.json",
            "checkpoint": "SESSION_INIT",
            "from_status": "SCANNING",
            "action": "ADVANCE",
            "to_status": "SCANNING",
            "pending_user_gate": None,
            "dispatches": [],
            "required_actions": ["BUILD_PROJECT_EVIDENCE_PACK"],
            "required_checks": ["PERSIST_STATE"],
            "reason_codes": ["SESSION_INITIALIZED"],
            "blocking_reasons": [],
            "retry_key": None,
            "recorded_at": "2026-07-27T12:00:00+08:00",
        }
        state = {
            "schema_version": "1.4",
            "session_id": "session-1",
            "mode": "discover",
            "interaction_mode": "GUIDED",
            "transport_profile": "CODEX",
            "execution_mode": "MULTI_AGENT",
            "project_root": project_root,
            "project_snapshot": "snapshot-1",
            "status": "SCANNING",
            "min_rounds": 3,
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
            "search_budget": {
                "profile": "standard",
                "large_downloads": [],
                "approved_extensions": [],
            },
            "accepted_work_products": [historical_product],
            "rejected_work_products": [],
            "gate_receipts": [],
            "user_required": [],
            "updated_at": "2026-07-27T12:00:00+08:00",
            "mainline_control": {
                "controller_id": "MAINLINE",
                "controller_status": "ACTIVE",
                "revision": 1,
                "last_checkpoint": "SESSION_INIT",
                "pending_user_gate": None,
                "last_controller_packet_id": "CTRL-0001",
                "retry_counts": {},
                "lane_search_requests": [],
                "transition_log": [historical_transition],
            },
        }
        for artifact in dispatch_builder.session_validator.BASE_ARTIFACTS:
            (session / artifact).write_text(
                "---\n"
                "session_id: session-1\n"
                f"artifact: {artifact}\n"
                "status: SCANNING\n"
                "updated_at: 2026-07-27T12:00:00+08:00\n"
                "---\n",
                encoding="utf-8",
            )
        state_path = session / "session-state.json"
        state_path.write_text(
            json.dumps(state, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        state_digest = hashlib.sha256(state_path.read_bytes()).hexdigest()
        control_input = {
            "control_revision": 1,
            "state_digest": state_digest,
            "observed_status": "SCANNING",
            "mode": "discover",
            "interaction_mode": "GUIDED",
            "transport_profile": "CODEX",
            "checkpoint": "PHASE_BOUNDARY",
            "completed_packet_ids": [],
            "failed_packets": [],
            "active_lanes": [],
            "accepted_verdicts": [],
            "artifact_readiness": {"PROJECT_EVIDENCE_PACK": "READY"},
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
        control_input_path = session / "control-input.json"
        control_input_path.write_text(
            json.dumps(control_input, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        envelope = {
            "schema_version": "1.0",
            "session_id": "session-1",
            "project_root": project_root,
            "project_snapshot": "snapshot-1",
            "phase": "CONTROL",
            "role": "Mainline Workflow Controller",
            "candidate_id": None,
            "round": None,
            "packet_id": "CTRL-0002",
            "control_revision": 1,
            "state_digest": state_digest,
            "control_input_digest": hashlib.sha256(
                control_input_path.read_bytes()
            ).hexdigest(),
            "context_fingerprint": "",
            "allowed_artifacts": [],
        }
        envelope["context_fingerprint"] = (
            batch_validator.controller_validator.expected_context_fingerprint(
                envelope
            )
        )
        output = {
            "envelope": envelope,
            "control_directive": {
                "observed_revision": 1,
                "observed_state_digest": state_digest,
                "observed_status": "SCANNING",
                "checkpoint": "PHASE_BOUNDARY",
                "action": "ADVANCE",
                "target_status": "SCANNING",
                "pending_user_gate": None,
                "dispatches": [
                    {
                        "packet_id": "MAP-001",
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
                "reason_codes": ["DIRECTION_MAPPING_READY"],
                "blocking_reasons": [],
                "retry_key": None,
            },
        }
        (session / "controller-output.json").write_text(
            json.dumps(output, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        self.write_draft(
            session,
            packet_id="MAP-001",
            candidate_id=None,
            phase="DIRECTION_MAPPING",
            role="Macro Direction Mapper",
            round_number=None,
            role_instructions="Map broad directions from the bounded evidence.",
            inline_payload={},
        )
        self.build(
            session,
            "MAP-001",
            checkpoint="PHASE_BOUNDARY",
        )

    def session_validation_errors(self, session: Path) -> list[str]:
        errors: list[str] = []
        state = json.loads(
            (session / "session-state.json").read_text(encoding="utf-8")
        )
        dispatch_builder.session_validator.validate_state(
            session,
            state,
            errors,
        )
        return errors

    def commit_current_controller_transition(self, session: Path) -> None:
        state_path = session / "session-state.json"
        state = json.loads(state_path.read_text(encoding="utf-8"))
        output = json.loads(
            (session / "controller-output.json").read_text(encoding="utf-8")
        )
        envelope = output["envelope"]
        directive = output["control_directive"]
        control_input_raw = (session / "control-input.json").read_bytes()
        archived_control_input = (
            session / "control-inputs" / f"{envelope['packet_id']}.json"
        )
        archived_control_input.write_bytes(control_input_raw)
        archived_control_input.chmod(0o400)
        transition = {
            "revision": 2,
            "observed_revision": directive["observed_revision"],
            "packet_id": envelope["packet_id"],
            "observed_state_digest": directive["observed_state_digest"],
            "control_input_digest": envelope["control_input_digest"],
            "control_input_path": (
                f"control-inputs/{envelope['packet_id']}.json"
            ),
            "checkpoint": directive["checkpoint"],
            "from_status": directive["observed_status"],
            "action": directive["action"],
            "to_status": directive["target_status"],
            "pending_user_gate": directive["pending_user_gate"],
            "dispatches": directive["dispatches"],
            "required_actions": directive["required_actions"],
            "required_checks": directive["required_checks"],
            "reason_codes": directive["reason_codes"],
            "blocking_reasons": directive["blocking_reasons"],
            "retry_key": directive["retry_key"],
            "recorded_at": "2026-07-27T12:01:00+08:00",
        }
        state["mainline_control"]["transition_log"].append(transition)
        state["mainline_control"]["revision"] = 2
        state["mainline_control"]["last_checkpoint"] = directive["checkpoint"]
        state["mainline_control"]["last_controller_packet_id"] = envelope[
            "packet_id"
        ]
        state["mainline_control"]["pending_user_gate"] = directive[
            "pending_user_gate"
        ]
        control_product = {
            field: envelope[field]
            for field in (
                "packet_id",
                "phase",
                "role",
                "session_id",
                "project_root",
                "project_snapshot",
                "candidate_id",
                "round",
                "control_revision",
                "state_digest",
                "control_input_digest",
                "context_fingerprint",
            )
        }
        state["accepted_work_products"].append(control_product)
        state["updated_at"] = "2026-07-27T12:01:00+08:00"
        state_path.write_text(
            json.dumps(state, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    def test_final_packet_allows_only_an_absolute_verified_capsule(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            session = self.make_session(Path(temporary))
            packet, raw, output = self.build(session)
            capsule_path = (
                session / "context-capsules" / "C01-R1-MENTOR.json"
            ).resolve()
            self.assertTrue(output.is_absolute())
            self.assertEqual(
                [str(capsule_path)],
                packet["envelope"]["allowed_artifacts"],
            )
            self.assertEqual(
                [str(capsule_path)],
                packet["allowed_artifact_paths"],
            )
            self.assertNotIn(
                str((session / "project-evidence-pack.md").resolve()),
                packet["allowed_artifact_paths"],
            )
            self.assertEqual(
                hashlib.sha256(capsule_path.read_bytes()).hexdigest(),
                packet["context_capsule"]["sha256"],
            )
            self.assertEqual(
                0,
                stat.S_IMODE(output.stat().st_mode) & 0o222,
            )
            self.assertEqual(
                0,
                stat.S_IMODE(capsule_path.stat().st_mode) & 0o222,
            )
            loaded, persisted_raw = dispatch_builder.validate_persisted_packet(
                session,
                "C01-R1-MENTOR",
            )
            self.assertEqual(packet, loaded)
            self.assertEqual(raw, persisted_raw)

    def test_codex_builder_and_batch_gate_reject_claude_profile(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            session = self.make_session(Path(temporary))
            state_path = session / "session-state.json"
            state = json.loads(state_path.read_text(encoding="utf-8"))
            state["transport_profile"] = "CLAUDE"
            state_path.write_text(
                json.dumps(state, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(
                dispatch_builder.DispatchError,
                "transport_profile CODEX",
            ):
                self.build(session)

        with tempfile.TemporaryDirectory() as temporary:
            session = self.make_session(Path(temporary))
            self.write_valid_empty_controller_batch(session)
            state_path = session / "session-state.json"
            state = json.loads(state_path.read_text(encoding="utf-8"))
            state["transport_profile"] = "CLAUDE"
            state_path.write_text(
                json.dumps(state, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            errors = self.validate_unit_batch(session)
            self.assertTrue(
                any("transport_profile CODEX" in error for error in errors),
                errors,
            )

    def test_batch_gate_requires_matching_persisted_packets(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            session = self.make_session(Path(temporary))
            self.build(session)
            self.write_controller_output(session)
            self.assertEqual(
                [],
                self.validate_unit_batch(session),
            )
            self.write_controller_output(session, role="Panel Judge")
            errors = self.validate_unit_batch(session)
            self.assertTrue(errors)
            self.assertIn("role does not match", errors[0])

    def test_retry_reads_identical_packet_and_rebuild_cannot_mutate_it(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            session = self.make_session(Path(temporary))
            _packet, committed_packet, _output = self.build(session)
            capsule_path = session / "context-capsules" / "C01-R1-MENTOR.json"
            committed_capsule = capsule_path.read_bytes()
            (session / "project-evidence-pack.md").write_text(
                "new evidence must use a new packet id\n",
                encoding="utf-8",
            )
            with self.assertRaises(dispatch_builder.capsules.CapsuleError):
                self.build(session)
            _loaded, retry_bytes = dispatch_builder.validate_persisted_packet(
                session,
                "C01-R1-MENTOR",
            )
            self.assertEqual(committed_packet, retry_bytes)
            self.assertEqual(committed_capsule, capsule_path.read_bytes())

    def test_batch_gate_fails_when_a_packet_is_missing(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            session = self.make_session(Path(temporary))
            self.write_controller_output(session)
            errors = self.validate_unit_batch(session)
            self.assertTrue(errors)
            self.assertTrue(
                "artifact is unavailable" in errors[0]
                or "immutable artifact" in errors[0],
                errors,
            )

    def test_multi_lane_batch_requires_and_accepts_every_final_packet(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            session = self.make_session(Path(temporary))
            self.write_draft(
                session,
                packet_id="C02-R1-MENTOR",
                candidate_id="C02",
            )
            self.build(session, "C01-R1-MENTOR")
            output = {
                "envelope": {"packet_id": "CTRL-UNIT-MULTI"},
                "control_directive": {
                    "checkpoint": "ROLE_BOUNDARY",
                    "dispatches": [
                        {
                            "packet_id": "C01-R1-MENTOR",
                            "phase": "DEBATE",
                            "role": "Socratic Mentor",
                            "candidate_id": "C01",
                            "round": 1,
                            "depends_on_packet_ids": [],
                        },
                        {
                            "packet_id": "C02-R1-MENTOR",
                            "phase": "DEBATE",
                            "role": "Socratic Mentor",
                            "candidate_id": "C02",
                            "round": 1,
                            "depends_on_packet_ids": [],
                        },
                    ]
                }
            }
            (session / "controller-output.json").write_text(
                json.dumps(output, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            errors = self.validate_unit_batch(session)
            self.assertTrue(errors)
            self.assertIn("C02-R1-MENTOR", errors[0])

            self.build(session, "C02-R1-MENTOR")
            self.assertEqual(
                [],
                self.validate_unit_batch(session),
            )

    def test_batch_gate_runs_full_controller_validation_on_stable_snapshots(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            session = self.make_session(Path(temporary))
            self.write_valid_empty_controller_batch(session)
            self.assertEqual(
                [],
                batch_validator.validate_batch(
                    session,
                    "controller-output.json",
                ),
            )

    def test_nonempty_batch_runs_real_controller_and_packet_validation(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            session = self.make_session(Path(temporary))
            self.write_valid_nonempty_controller_batch(session)
            self.assertEqual([], self.session_validation_errors(session))
            self.assertEqual(
                [],
                batch_validator.validate_batch(
                    session,
                    "controller-output.json",
                ),
            )
            precommit_errors = batch_validator.validate_batch_manifest(
                session,
                "CTRL-0002",
                "MAP-001",
            )
            self.assertTrue(precommit_errors)
            self.assertTrue(
                any("committed controller transition" in error for error in precommit_errors),
                precommit_errors,
            )
            self.commit_current_controller_transition(session)
            self.assertEqual([], self.session_validation_errors(session))
            self.assertEqual(
                [],
                batch_validator.validate_batch_manifest(
                    session,
                    "CTRL-0002",
                    "MAP-001",
                ),
            )
            persisted = (
                session / "control-inputs" / "dispatches" / "MAP-001.json"
            ).read_bytes()
            self.assertEqual(
                persisted,
                batch_validator.load_committed_packet_bytes(
                    session,
                    "CTRL-0002",
                    "MAP-001",
                ),
            )
            self.assertEqual(
                persisted,
                batch_validator.load_recorded_packet_bytes(
                    session,
                    "CTRL-0002",
                    "MAP-001",
                    json.loads(
                        (session / "session-state.json").read_text(
                            encoding="utf-8"
                        )
                    ),
                ),
            )
            original_commit_check = (
                batch_validator.validate_committed_controller_transition
            )
            mutated_after_commit_check = False

            def mutate_after_commit_check(
                session_root,
                controller_packet_id,
                packet_id,
                **kwargs,
            ):
                nonlocal mutated_after_commit_check
                errors = original_commit_check(
                    session_root,
                    controller_packet_id,
                    packet_id,
                    **kwargs,
                )
                if mutated_after_commit_check:
                    return errors
                mutated_after_commit_check = True
                packet_path = (
                    session
                    / "control-inputs"
                    / "dispatches"
                    / "MAP-001.json"
                )
                manifest_path = (
                    session
                    / "control-inputs"
                    / "dispatch-batches"
                    / "CTRL-0002.json"
                )
                packet = json.loads(packet_path.read_text(encoding="utf-8"))
                packet["role_instructions"] = (
                    "Adversarial replacement that must never become retry bytes."
                )
                replacement_packet_raw = (
                    json.dumps(packet, ensure_ascii=False, indent=2) + "\n"
                ).encode("utf-8")
                packet_path.chmod(0o600)
                packet_path.write_bytes(replacement_packet_raw)
                packet_path.chmod(0o400)

                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                manifest["dispatches"][0]["packet_sha256"] = hashlib.sha256(
                    replacement_packet_raw
                ).hexdigest()
                replacement_manifest_raw = (
                    json.dumps(manifest, ensure_ascii=False, indent=2) + "\n"
                ).encode("utf-8")
                manifest_path.chmod(0o600)
                manifest_path.write_bytes(replacement_manifest_raw)
                manifest_path.chmod(0o400)
                return errors

            with mock.patch.object(
                batch_validator,
                "validate_committed_controller_transition",
                side_effect=mutate_after_commit_check,
            ):
                with self.assertRaisesRegex(
                    batch_validator.BatchError,
                    "ready receipt manifest digest",
                ):
                    batch_validator.load_committed_packet_bytes(
                        session,
                        "CTRL-0002",
                        "MAP-001",
                    )

    def test_codex_guided_role_result_completes_a_committed_dispatch(
        self,
    ) -> None:
        """Exercise the real builder/validator path through role acceptance."""
        with tempfile.TemporaryDirectory() as temporary:
            session = self.make_session(Path(temporary))
            self.write_valid_nonempty_controller_batch(session)
            self.assertEqual(
                [],
                batch_validator.validate_batch(
                    session,
                    "controller-output.json",
                ),
            )
            self.commit_current_controller_transition(session)
            persisted_path = (
                session
                / "control-inputs"
                / "dispatches"
                / "MAP-001.json"
            )
            persisted = persisted_path.read_bytes()
            self.assertEqual(
                persisted,
                batch_validator.load_committed_packet_bytes(
                    session,
                    "CTRL-0002",
                    "MAP-001",
                ),
            )

            packet = json.loads(
                persisted_path.read_text(encoding="utf-8")
            )
            envelope = packet["envelope"]
            product = {
                field: envelope[field]
                for field in (
                    "packet_id",
                    "phase",
                    "role",
                    "session_id",
                    "project_root",
                    "project_snapshot",
                    "candidate_id",
                    "round",
                )
            }
            product["context_fingerprint"] = (
                dispatch_builder.session_validator.expected_context_fingerprint(
                    product
                )
            )
            state_path = session / "session-state.json"
            state = json.loads(state_path.read_text(encoding="utf-8"))
            state["accepted_work_products"].append(product)
            state_path.write_text(
                json.dumps(state, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )

            self.assertEqual([], self.session_validation_errors(session))
            with self.assertRaisesRegex(
                batch_validator.BatchError,
                "already accepted or rejected",
            ):
                batch_validator.load_committed_packet_bytes(
                    session,
                    "CTRL-0002",
                    "MAP-001",
                )
            self.assertEqual(persisted, persisted_path.read_bytes())

    def test_full_session_requires_a_committed_codex_batch_for_dispatches(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            session = self.make_session(Path(temporary))
            self.write_valid_nonempty_controller_batch(session)
            self.commit_current_controller_transition(session)
            manifest_path = (
                session
                / "control-inputs"
                / "dispatch-batches"
                / "CTRL-0002.json"
            )
            self.assertFalse(manifest_path.exists())
            errors = self.session_validation_errors(session)
            self.assertTrue(
                any(
                    "committed Codex batch is invalid" in error
                    for error in errors
                ),
                errors,
            )

    def test_schema_14_full_session_requires_immutable_control_snapshot(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            session = self.make_session(Path(temporary))
            self.write_valid_nonempty_controller_batch(session)
            self.assertEqual(
                [],
                batch_validator.validate_batch(
                    session,
                    "controller-output.json",
                ),
            )
            self.commit_current_controller_transition(session)
            snapshot = session / "control-inputs" / "CTRL-0002.json"
            snapshot.chmod(0o600)
            errors = self.session_validation_errors(session)
            self.assertTrue(
                any(
                    "immutable artifact permissions" in error
                    for error in errors
                ),
                errors,
            )

    def test_malformed_committed_manifest_reports_errors_without_crashing(
        self,
    ) -> None:
        mutations = (
            (
                "null-dispatches",
                lambda manifest: manifest.update({"dispatches": None}),
                "dispatches must be an array",
            ),
            (
                "object-packet-id",
                lambda manifest: manifest["dispatches"][0].update(
                    {"packet_id": {}}
                ),
                "packet_id is invalid",
            ),
        )
        for label, mutate, expected in mutations:
            with self.subTest(label=label), tempfile.TemporaryDirectory() as temporary:
                session = self.make_session(Path(temporary))
                self.write_valid_nonempty_controller_batch(session)
                self.assertEqual(
                    [],
                    batch_validator.validate_batch(
                        session,
                        "controller-output.json",
                    ),
                )
                self.commit_current_controller_transition(session)
                batch_dir = (
                    session / "control-inputs" / "dispatch-batches"
                )
                manifest_path = batch_dir / "CTRL-0002.json"
                ready_path = batch_dir / "CTRL-0002.ready.json"
                manifest = json.loads(
                    manifest_path.read_text(encoding="utf-8")
                )
                mutate(manifest)
                manifest_raw = batch_validator.serialize_manifest(manifest)
                manifest_path.chmod(0o600)
                manifest_path.write_bytes(manifest_raw)
                manifest_path.chmod(0o400)
                ready = json.loads(ready_path.read_text(encoding="utf-8"))
                ready["manifest_sha256"] = hashlib.sha256(
                    manifest_raw
                ).hexdigest()
                ready_path.chmod(0o600)
                ready_path.write_bytes(
                    batch_validator.serialize_manifest(ready)
                )
                ready_path.chmod(0o400)

                errors = batch_validator.validate_batch_manifest(
                    session,
                    "CTRL-0002",
                    "MAP-001",
                )
                self.assertTrue(
                    any(expected in error for error in errors),
                    errors,
                )

    def test_malformed_resolved_packet_id_reports_without_crashing(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            session = self.make_session(Path(temporary))
            self.write_valid_nonempty_controller_batch(session)
            self.assertEqual(
                [],
                batch_validator.validate_batch(
                    session,
                    "controller-output.json",
                ),
            )
            self.commit_current_controller_transition(session)
            state_path = session / "session-state.json"
            state = json.loads(state_path.read_text(encoding="utf-8"))
            state["accepted_work_products"].append({"packet_id": {}})
            state_path.write_text(
                json.dumps(state, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            errors = batch_validator.validate_batch_manifest(
                session,
                "CTRL-0002",
                "MAP-001",
            )
            self.assertTrue(
                any(
                    "accepted_work_products" in error
                    and "packet_id is invalid" in error
                    for error in errors
                ),
                errors,
            )

    def test_emit_rechecks_target_resolution_after_packet_capture(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            session = self.make_session(Path(temporary))
            self.write_valid_nonempty_controller_batch(session)
            self.assertEqual(
                [],
                batch_validator.validate_batch(
                    session,
                    "controller-output.json",
                ),
            )
            self.commit_current_controller_transition(session)
            original_capture = batch_validator.capture_ready_manifest_packets

            def accept_target_after_capture(session_root, controller_packet_id):
                result = original_capture(session_root, controller_packet_id)
                state_path = session / "session-state.json"
                state = json.loads(state_path.read_text(encoding="utf-8"))
                packet = json.loads(
                    (
                        session
                        / "control-inputs"
                        / "dispatches"
                        / "MAP-001.json"
                    ).read_text(encoding="utf-8")
                )
                envelope = packet["envelope"]
                state["accepted_work_products"].append(
                    {
                        field: envelope[field]
                        for field in (
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
                    }
                )
                state["updated_at"] = "2026-07-27T12:02:00+08:00"
                state_path.write_text(
                    json.dumps(state, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8",
                )
                self.assertEqual([], self.session_validation_errors(session))
                return result

            with mock.patch.object(
                batch_validator,
                "capture_ready_manifest_packets",
                side_effect=accept_target_after_capture,
            ):
                with self.assertRaisesRegex(
                    batch_validator.BatchError,
                    "already accepted or rejected",
                ):
                    batch_validator.load_committed_packet_bytes(
                        session,
                        "CTRL-0002",
                        "MAP-001",
                    )

    def test_full_session_reports_null_accepted_products_without_crashing(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            session = self.make_session(Path(temporary))
            self.write_valid_nonempty_controller_batch(session)
            state_path = session / "session-state.json"
            state = json.loads(state_path.read_text(encoding="utf-8"))
            state["accepted_work_products"] = None
            state_path.write_text(
                json.dumps(state, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            errors = self.session_validation_errors(session)
            self.assertTrue(
                any(
                    "accepted_work_products must be an array" in error
                    for error in errors
                ),
                errors,
            )

    def test_emit_rejects_an_unsafe_controller_packet_id_immediately(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            session = self.make_session(Path(temporary))
            with self.assertRaisesRegex(
                batch_validator.capsules.CapsuleError,
                "controller_packet_id is invalid",
            ):
                batch_validator.load_committed_packet_bytes(
                    session,
                    "unsafe/controller",
                    "MAP-001",
                )

    def test_batch_manifest_detects_packet_or_capsule_byte_mutation(self) -> None:
        for relative in (
            "control-inputs/dispatches/C01-R1-MENTOR.json",
            "context-capsules/C01-R1-MENTOR.json",
        ):
            with self.subTest(relative=relative), tempfile.TemporaryDirectory() as temporary:
                session = self.make_session(Path(temporary))
                self.build(session)
                self.write_controller_output(session)
                self.assertEqual([], self.validate_unit_batch(session))
                target = session / relative
                target.chmod(0o600)
                if "dispatches" in relative:
                    mutated = json.loads(target.read_text(encoding="utf-8"))
                    mutated["role_instructions"] = (
                        "Mutated instructions must not become retry bytes."
                    )
                    target.write_text(
                        json.dumps(mutated, ensure_ascii=False, indent=2) + "\n",
                        encoding="utf-8",
                    )
                else:
                    target.write_bytes(target.read_bytes() + b" ")
                errors = batch_validator.validate_batch_manifest(
                    session,
                    "CTRL-UNIT",
                )
                self.assertTrue(errors)
                self.assertTrue(
                    any(
                        "digest" in error
                        or "sha256" in error
                        or "invalid JSON" in error
                        or "permissions" in error
                        for error in errors
                    ),
                    errors,
                )

    def test_batch_gate_rejects_malformed_controller_output_before_packets(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            session = self.make_session(Path(temporary))
            self.write_controller_output(session)
            errors = batch_validator.validate_batch(
                session,
                "controller-output.json",
            )
            self.assertTrue(errors)
            self.assertTrue(
                all(
                    error.startswith("controller directive validation failed:")
                    for error in errors
                )
            )

    def test_batch_gate_rejects_checkpoint_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            session = self.make_session(Path(temporary))
            self.build(session, checkpoint="ROLE_BOUNDARY")
            self.write_controller_output(
                session,
                checkpoint="ROUND_BOUNDARY",
            )
            errors = self.validate_unit_batch(session)
            self.assertTrue(errors)
            self.assertIn("checkpoint does not match", errors[0])

    def test_batch_gate_detects_live_state_input_or_output_changes(self) -> None:
        for relative in (
            "session-state.json",
            "control-input.json",
            "controller-output.json",
        ):
            with self.subTest(relative=relative), tempfile.TemporaryDirectory() as temporary:
                session = self.make_session(Path(temporary))
                self.build(session)
                self.write_controller_output(session)
                state_raw = (session / "session-state.json").read_bytes()
                original = batch_validator.dispatch_builder.validate_persisted_packet

                def mutate_after_validation(
                    session_dir: Path,
                    packet_id: str,
                ):
                    result = original(session_dir, packet_id)
                    target = session / relative
                    target.write_bytes(target.read_bytes() + b"\n")
                    return result

                with (
                    mock.patch.object(
                        batch_validator.controller_validator,
                        "validate",
                        return_value=([], state_raw),
                    ),
                    mock.patch.object(
                        batch_validator.dispatch_builder,
                        "validate_persisted_packet",
                        side_effect=mutate_after_validation,
                    ),
                ):
                    errors = batch_validator.validate_batch(
                        session,
                        "controller-output.json",
                    )
                self.assertTrue(errors)
                self.assertTrue(
                    any("changed while" in error for error in errors),
                    errors,
                )

    def test_failed_final_gate_cannot_publish_a_ready_batch(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            session = self.make_session(Path(temporary))
            self.build(session)
            self.write_controller_output(session)
            state_raw = (session / "session-state.json").read_bytes()
            checks = 0

            def fail_last_check(*_args, **_kwargs):
                nonlocal checks
                checks += 1
                if checks == 2:
                    return [
                        "controller-output.json changed during final validation"
                    ]
                return []

            with (
                mock.patch.object(
                    batch_validator.controller_validator,
                    "validate",
                    return_value=([], state_raw),
                ),
                mock.patch.object(
                    batch_validator,
                    "live_snapshot_errors",
                    side_effect=fail_last_check,
                ),
            ):
                errors = batch_validator.validate_batch(
                    session,
                    "controller-output.json",
                )
            self.assertTrue(errors)
            self.assertFalse(
                (
                    session
                    / "control-inputs"
                    / "dispatch-batches"
                    / "CTRL-UNIT.ready.json"
                ).exists()
            )
            verify_errors = batch_validator.validate_batch_manifest(
                session,
                "CTRL-UNIT",
                "C01-R1-MENTOR",
            )
            self.assertTrue(verify_errors)
            self.assertTrue(
                any("ready" in error for error in verify_errors),
                verify_errors,
            )

    def test_search_budget_is_equally_strict_for_draft_and_persisted_packet(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            session = self.make_session(Path(temporary))
            packet_id = "SEARCH-001"
            self.write_draft(
                session,
                packet_id=packet_id,
                candidate_id=None,
                phase="EXTERNAL_POSITIONING",
                role="Search and Verification Specialist",
                round_number=None,
                search_budget=standard_search_budget(),
            )
            self.build(session, packet_id, checkpoint="PHASE_BOUNDARY")
            packet_path = (
                session / "control-inputs" / "dispatches" / f"{packet_id}.json"
            )
            mutated = json.loads(packet_path.read_text(encoding="utf-8"))
            mutated["search_budget"] = None
            packet_path.chmod(0o600)
            packet_path.write_text(
                json.dumps(mutated, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            packet_path.chmod(0o400)
            with self.assertRaisesRegex(
                dispatch_builder.DispatchError,
                "search_budget",
            ):
                dispatch_builder.validate_persisted_packet(session, packet_id)

        with tempfile.TemporaryDirectory() as temporary:
            session = self.make_session(Path(temporary))
            packet_id = "SEARCH-OVER-BUDGET"
            budget = standard_search_budget()
            budget["max_query_batches"] = 3
            self.write_draft(
                session,
                packet_id=packet_id,
                candidate_id=None,
                phase="EXTERNAL_POSITIONING",
                role="Search and Verification Specialist",
                round_number=None,
                search_budget=budget,
            )
            with self.assertRaisesRegex(
                dispatch_builder.DispatchError,
                "max_query_batches",
            ):
                self.build(session, packet_id, checkpoint="PHASE_BOUNDARY")

        with tempfile.TemporaryDirectory() as temporary:
            session = self.make_session(Path(temporary))
            packet_id = "SEARCH-ZERO-BUDGET"
            budget = standard_search_budget()
            budget["max_query_batches"] = 0
            self.write_draft(
                session,
                packet_id=packet_id,
                candidate_id=None,
                phase="EXTERNAL_POSITIONING",
                role="Search and Verification Specialist",
                round_number=None,
                search_budget=budget,
            )
            with self.assertRaisesRegex(
                dispatch_builder.DispatchError,
                "max_query_batches must equal 2",
            ):
                self.build(session, packet_id, checkpoint="PHASE_BOUNDARY")

    def test_search_usage_cannot_claim_an_extension_absent_from_its_packet(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            session = self.make_session(Path(temporary))
            packet_id = "C01-R1-SEARCH"
            self.write_draft(
                session,
                packet_id=packet_id,
                candidate_id="C01",
                phase="DEBATE",
                role="Search and Verification Specialist",
                round_number=1,
                search_budget=standard_search_budget(),
            )
            packet, packet_raw, _output = self.build(session, packet_id)
            controller_packet_id = "CTRL-SEARCH"
            manifest = {
                "schema_version": "codex-dispatch-batch-1",
                "controller_packet_id": controller_packet_id,
                "checkpoint": "ROLE_BOUNDARY",
                "controller_inputs": {},
                "dispatches": [
                    {
                        "packet_id": packet_id,
                        "phase": "DEBATE",
                        "role": "Search and Verification Specialist",
                        "candidate_id": "C01",
                        "round": 1,
                        "packet_path": (
                            f"control-inputs/dispatches/{packet_id}.json"
                        ),
                        "packet_sha256": hashlib.sha256(packet_raw).hexdigest(),
                        "capsule_path": f"context-capsules/{packet_id}.json",
                        "capsule_sha256": packet["context_capsule"]["sha256"],
                    }
                ],
            }
            manifest_raw = batch_validator.serialize_manifest(manifest)
            batch_directory = (
                session / "control-inputs" / "dispatch-batches"
            )
            batch_directory.mkdir(parents=True)
            manifest_path = batch_directory / f"{controller_packet_id}.json"
            manifest_path.write_bytes(manifest_raw)
            manifest_path.chmod(0o400)
            ready_path = (
                batch_directory / f"{controller_packet_id}.ready.json"
            )
            ready_path.write_bytes(
                batch_validator.serialize_manifest(
                    {
                        "schema_version": "codex-dispatch-batch-ready-1",
                        "controller_packet_id": controller_packet_id,
                        "manifest_sha256": hashlib.sha256(
                            manifest_raw
                        ).hexdigest(),
                    }
                )
            )
            ready_path.chmod(0o400)

            authorization = {
                "approval_packet_id": "C01-R1-JUDGE",
                "judge_reason": "One unresolved direct-prior conflict.",
                "extra_query_batches": 1,
                "extra_sources": 4,
            }
            state = {
                "schema_version": "1.4",
                "transport_profile": "CODEX",
                "session_id": "session-1",
                "project_root": str(Path(temporary).resolve()),
                "project_snapshot": "snapshot-1",
                "search_budget": {
                    "profile": "standard",
                    "large_downloads": [],
                    "approved_extensions": [authorization],
                },
                "accepted_work_products": [
                    {
                        "packet_id": "C01-R1-JUDGE",
                        "role": "Panel Judge",
                        "candidate_id": "C01",
                        "round": 1,
                    },
                    {
                        "packet_id": packet_id,
                        "phase": "DEBATE",
                        "role": "Search and Verification Specialist",
                        "candidate_id": "C01",
                        "round": 1,
                    },
                ],
                "mainline_control": {
                    "transition_log": [
                        {
                            "packet_id": controller_packet_id,
                            "dispatches": [
                                {
                                    "packet_id": packet_id,
                                    "role": (
                                        "Search and Verification Specialist"
                                    ),
                                    "candidate_id": "C01",
                                    "round": 1,
                                }
                            ],
                        }
                    ]
                },
            }
            usage = {
                "query_batches": 3,
                "queries": 12,
                "sources_inspected": 12,
                "search_packet_id": packet_id,
                "budget_extension": authorization,
            }
            errors: list[str] = []
            dispatch_builder.session_validator.validate_search_usage(
                usage,
                "candidates[0].rounds[0].search_usage",
                errors,
                state=state,
                session_dir=session,
                candidate_id="C01",
                round_number=1,
            )
            self.assertTrue(
                any("committed Codex transport is invalid" in error for error in errors),
                errors,
            )
            packet_path = (
                session
                / "control-inputs"
                / "dispatches"
                / f"{packet_id}.json"
            )
            granted_packet = json.loads(
                packet_path.read_text(encoding="utf-8")
            )
            granted_packet["search_budget"]["extension"] = {
                "approved": True,
                **authorization,
            }
            granted_packet_raw = (
                json.dumps(granted_packet, ensure_ascii=False, indent=2) + "\n"
            ).encode("utf-8")
            packet_path.chmod(0o600)
            packet_path.write_bytes(granted_packet_raw)
            packet_path.chmod(0o400)

            manifest["dispatches"][0]["packet_sha256"] = hashlib.sha256(
                granted_packet_raw
            ).hexdigest()
            granted_manifest_raw = batch_validator.serialize_manifest(manifest)
            manifest_path.chmod(0o600)
            manifest_path.write_bytes(granted_manifest_raw)
            manifest_path.chmod(0o400)
            ready_path.chmod(0o600)
            ready_path.write_bytes(
                batch_validator.serialize_manifest(
                    {
                        "schema_version": "codex-dispatch-batch-ready-1",
                        "controller_packet_id": controller_packet_id,
                        "manifest_sha256": hashlib.sha256(
                            granted_manifest_raw
                        ).hexdigest(),
                    }
                )
            )
            ready_path.chmod(0o400)
            granted_errors: list[str] = []
            canonical_batch = (
                dispatch_builder.session_validator.codex_batch_validator_module()
            )
            with mock.patch.object(
                canonical_batch,
                "load_recorded_packet_bytes",
                return_value=granted_packet_raw,
            ):
                dispatch_builder.session_validator.validate_search_usage(
                    usage,
                    "candidates[0].rounds[0].search_usage",
                    granted_errors,
                    state=state,
                    session_dir=session,
                    candidate_id="C01",
                    round_number=1,
                )
            self.assertEqual([], granted_errors)

    def test_claude_transport_profile_validates_its_persisted_search_grant(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            session = self.make_session(Path(temporary))
            search_packet_id = "C01-R1-SEARCH"
            authorization = {
                "approval_packet_id": "C01-R1-JUDGE",
                "judge_reason": "One unresolved direct-prior conflict.",
                "extra_query_batches": 1,
                "extra_sources": 4,
            }
            claude_transport = {
                "schema_version": "claude-dispatch-input-1",
                "envelope": {
                    "schema_version": "1.0",
                    "session_id": "session-1",
                    "project_root": str(Path(temporary).resolve()),
                    "project_snapshot": "snapshot-1",
                    "packet_id": search_packet_id,
                    "phase": "DEBATE",
                    "role": "Search and Verification Specialist",
                    "candidate_id": "C01",
                    "round": 1,
                    "context_fingerprint": "",
                    "allowed_artifacts": [],
                },
                "role_instructions": "Verify the unresolved direct prior.",
                "inline_payload": {},
                "allowed_artifact_paths": [],
                "search_budget": {
                    **standard_search_budget(),
                    "extension": {
                        "approved": True,
                        **authorization,
                    },
                },
            }
            claude_transport["envelope"]["context_fingerprint"] = (
                dispatch_builder.session_validator.expected_context_fingerprint(
                    claude_transport["envelope"]
                )
            )
            transport_path = (
                session
                / "control-inputs"
                / "dispatches"
                / f"{search_packet_id}.json"
            )
            transport_path.parent.mkdir(parents=True)
            transport_path.write_text(
                json.dumps(claude_transport, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            transport_path.chmod(0o400)
            transport_digest = hashlib.sha256(
                transport_path.read_bytes()
            ).hexdigest()
            state = {
                "schema_version": "1.4",
                "transport_profile": "CLAUDE",
                "session_id": "session-1",
                "project_root": str(Path(temporary).resolve()),
                "project_snapshot": "snapshot-1",
                "search_budget": {
                    "profile": "standard",
                    "large_downloads": [],
                    "approved_extensions": [authorization],
                },
                "accepted_work_products": [
                    {
                        "packet_id": "C01-R1-JUDGE",
                        "phase": "DEBATE",
                        "role": "Panel Judge",
                        "candidate_id": "C01",
                        "round": 1,
                    },
                    {
                        "packet_id": search_packet_id,
                        "phase": "DEBATE",
                        "role": "Search and Verification Specialist",
                        "candidate_id": "C01",
                        "round": 1,
                    },
                ],
                "mainline_control": {
                    "transition_log": [
                        {
                            "packet_id": "CTRL-CLAUDE",
                            "dispatches": [
                                {
                                    "packet_id": search_packet_id,
                                    "phase": "DEBATE",
                                    "role": (
                                        "Search and Verification Specialist"
                                    ),
                                    "candidate_id": "C01",
                                    "round": 1,
                                    "depends_on_packet_ids": [],
                                    "transport_path": (
                                        "control-inputs/dispatches/"
                                        f"{search_packet_id}.json"
                                    ),
                                    "transport_sha256": transport_digest,
                                }
                            ],
                        }
                    ]
                },
            }
            binding_errors: list[str] = []
            bound_dispatch = state["mainline_control"]["transition_log"][0][
                "dispatches"
            ][0]
            dispatch_builder.session_validator.validate_control_dispatch(
                bound_dispatch,
                "mainline_control.transition_log[0].dispatches[0]",
                {"C01"},
                set(),
                state,
                session,
                binding_errors,
            )
            self.assertEqual([], binding_errors)
            unauthorized_state = json.loads(
                json.dumps(state, ensure_ascii=False)
            )
            unauthorized_state["search_budget"]["approved_extensions"] = []
            unauthorized_errors: list[str] = []
            dispatch_builder.session_validator.validate_control_dispatch(
                unauthorized_state["mainline_control"]["transition_log"][0][
                    "dispatches"
                ][0],
                "mainline_control.transition_log[0].dispatches[0]",
                {"C01"},
                set(),
                unauthorized_state,
                session,
                unauthorized_errors,
            )
            self.assertTrue(
                any(
                    "no matching authoritative approval" in error
                    for error in unauthorized_errors
                ),
                unauthorized_errors,
            )
            errors: list[str] = []
            dispatch_builder.session_validator.validate_search_usage(
                {
                    "query_batches": 3,
                    "queries": 12,
                    "sources_inspected": 12,
                    "search_packet_id": search_packet_id,
                    "budget_extension": authorization,
                },
                "candidates[0].rounds[0].search_usage",
                errors,
                state=state,
                session_dir=session,
                candidate_id="C01",
                round_number=1,
            )
            self.assertEqual([], errors)

            foreign_transport = json.loads(
                transport_path.read_text(encoding="utf-8")
            )
            foreign_transport["envelope"]["session_id"] = "foreign-session"
            foreign_transport["envelope"]["context_fingerprint"] = (
                dispatch_builder.session_validator.expected_context_fingerprint(
                    foreign_transport["envelope"]
                )
            )
            transport_path.chmod(0o600)
            transport_path.write_text(
                json.dumps(
                    foreign_transport,
                    ensure_ascii=False,
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
            transport_path.chmod(0o400)
            bound_dispatch["transport_sha256"] = hashlib.sha256(
                transport_path.read_bytes()
            ).hexdigest()
            foreign_errors: list[str] = []
            dispatch_builder.session_validator.validate_search_usage(
                {
                    "query_batches": 3,
                    "queries": 12,
                    "sources_inspected": 12,
                    "search_packet_id": search_packet_id,
                    "budget_extension": authorization,
                },
                "candidates[0].rounds[0].search_usage",
                foreign_errors,
                state=state,
                session_dir=session,
                candidate_id="C01",
                round_number=1,
            )
            self.assertTrue(
                any("envelope.session_id must equal" in error for error in foreign_errors),
                foreign_errors,
            )

    def test_claude_large_downloads_obey_shape_uniqueness_and_source_quota(
        self,
    ) -> None:
        valid_download = {
            "url": "https://example.test/large-dataset",
            "size_bytes": dispatch_builder.TEN_MIB + 1,
            "necessity": "Required to verify the benchmark artifact.",
            "user_approved": True,
        }
        scenarios: list[tuple[str, list[dict], str]] = [
            (
                "duplicate",
                [valid_download, dict(valid_download)],
                "duplicated",
            ),
            (
                "over-quota",
                [
                    {
                        **valid_download,
                        "url": f"https://example.test/large-dataset-{index}",
                    }
                    for index in range(9)
                ],
                "source quota",
            ),
            (
                "not-large",
                [
                    {
                        **valid_download,
                        "url": "https://example.test/small-file",
                        "size_bytes": dispatch_builder.TEN_MIB,
                    }
                ],
                "only above 10 MiB",
            ),
        ]
        dispatch = {
            "packet_id": "C01-R1-SEARCH",
            "phase": "DEBATE",
            "role": "Search and Verification Specialist",
            "candidate_id": "C01",
            "round": 1,
            "depends_on_packet_ids": [],
            "transport_path": (
                "control-inputs/dispatches/C01-R1-SEARCH.json"
            ),
            "transport_sha256": "a" * 64,
        }
        for label, downloads, expected_error in scenarios:
            with self.subTest(label=label):
                envelope = {
                    "schema_version": "1.0",
                    "session_id": "session-1",
                    "project_root": "/tmp/project",
                    "project_snapshot": "snapshot-1",
                    "packet_id": "C01-R1-SEARCH",
                    "phase": "DEBATE",
                    "role": "Search and Verification Specialist",
                    "candidate_id": "C01",
                    "round": 1,
                    "context_fingerprint": "",
                    "allowed_artifacts": [],
                }
                envelope["context_fingerprint"] = (
                    dispatch_builder.session_validator
                    .expected_context_fingerprint(envelope)
                )
                packet = {
                    "schema_version": "claude-dispatch-input-1",
                    "envelope": envelope,
                    "role_instructions": "Verify the benchmark artifact.",
                    "inline_payload": {},
                    "allowed_artifact_paths": [],
                    "search_budget": {
                        **standard_search_budget(),
                        "large_downloads": downloads,
                    },
                }
                state = {
                    "session_id": "session-1",
                    "project_root": "/tmp/project",
                    "project_snapshot": "snapshot-1",
                    "search_budget": {
                        "profile": "standard",
                        "large_downloads": list(
                            {
                                download["url"]: download
                                for download in downloads
                            }.values()
                        ),
                        "approved_extensions": [],
                    },
                    "accepted_work_products": [],
                }
                errors: list[str] = []
                dispatch_builder.session_validator.validate_claude_dispatch_input(
                    (
                        json.dumps(packet, ensure_ascii=False, indent=2) + "\n"
                    ).encode("utf-8"),
                    dispatch,
                    state,
                    "claude-transport",
                    errors,
                )
                self.assertTrue(
                    any(expected_error in error for error in errors),
                    errors,
                )

    def test_search_large_downloads_are_unique_and_within_source_quota(
        self,
    ) -> None:
        valid_download = {
            "url": "https://example.test/large-dataset",
            "size_bytes": dispatch_builder.TEN_MIB + 1,
            "necessity": "Required to verify the benchmark artifact.",
            "user_approved": True,
        }
        invalid_budgets = []
        over_quota = standard_search_budget()
        over_quota["large_downloads"] = [
            {
                **valid_download,
                "url": f"https://example.test/large-dataset-{index}",
            }
            for index in range(9)
        ]
        invalid_budgets.append(("quota", over_quota, "source quota"))

        duplicated = standard_search_budget()
        duplicated["large_downloads"] = [valid_download, dict(valid_download)]
        invalid_budgets.append(("duplicate", duplicated, "duplicated"))

        not_large = standard_search_budget()
        not_large["large_downloads"] = [
            {
                **valid_download,
                "url": "https://example.test/small-file",
                "size_bytes": dispatch_builder.TEN_MIB,
            }
        ]
        invalid_budgets.append(("small", not_large, "only above 10 MiB"))

        for label, budget, message in invalid_budgets:
            with self.subTest(label=label), tempfile.TemporaryDirectory() as temporary:
                session = self.make_session(Path(temporary))
                packet_id = f"SEARCH-{label.upper()}"
                self.write_draft(
                    session,
                    packet_id=packet_id,
                    candidate_id=None,
                    phase="EXTERNAL_POSITIONING",
                    role="Search and Verification Specialist",
                    round_number=None,
                    search_budget=budget,
                )
                with self.assertRaisesRegex(
                    dispatch_builder.DispatchError,
                    message,
                ):
                    self.build(
                        session,
                        packet_id,
                        checkpoint="PHASE_BOUNDARY",
                    )

    def test_search_claimed_approval_must_exist_in_authoritative_state(
        self,
    ) -> None:
        approved_download = {
            "url": "https://example.test/approved-large-dataset",
            "size_bytes": dispatch_builder.TEN_MIB + 1,
            "necessity": "Required to verify the benchmark artifact.",
            "user_approved": True,
        }
        with tempfile.TemporaryDirectory() as temporary:
            session = self.make_session(Path(temporary))
            packet_id = "SEARCH-UNAUTHORIZED-DOWNLOAD"
            budget = standard_search_budget()
            budget["large_downloads"] = [approved_download]
            self.write_draft(
                session,
                packet_id=packet_id,
                candidate_id=None,
                phase="EXTERNAL_POSITIONING",
                role="Search and Verification Specialist",
                round_number=None,
                search_budget=budget,
            )
            with self.assertRaisesRegex(
                dispatch_builder.DispatchError,
                "authoritative session approval",
            ):
                self.build(session, packet_id, checkpoint="PHASE_BOUNDARY")
            state_path = session / "session-state.json"
            state = json.loads(state_path.read_text(encoding="utf-8"))
            state["search_budget"]["large_downloads"] = [approved_download]
            state_path.write_text(
                json.dumps(state, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            _packet, _raw, output = self.build(
                session,
                packet_id,
                checkpoint="PHASE_BOUNDARY",
            )
            self.assertTrue(output.exists())

        with tempfile.TemporaryDirectory() as temporary:
            session = self.make_session(Path(temporary))
            packet_id = "SEARCH-UNAUTHORIZED-EXTENSION"
            budget = standard_search_budget()
            budget["extension"] = {
                "approved": True,
                "approval_packet_id": "JUDGE-001",
                "judge_reason": "More evidence is needed.",
                "extra_query_batches": 1,
                "extra_sources": 4,
            }
            self.write_draft(
                session,
                packet_id=packet_id,
                candidate_id=None,
                phase="EXTERNAL_POSITIONING",
                role="Search and Verification Specialist",
                round_number=None,
                search_budget=budget,
            )
            with self.assertRaisesRegex(
                dispatch_builder.DispatchError,
                "authoritative state approval",
            ):
                self.build(session, packet_id, checkpoint="PHASE_BOUNDARY")
            malformed_state = {
                "search_budget": {
                    "profile": "standard",
                    "large_downloads": [],
                    "approved_extensions": [
                        {
                            "approval_packet_id": "JUDGE-001",
                            "judge_reason": "More evidence is needed.",
                            "extra_query_batches": 1,
                            "extra_sources": 4,
                        }
                    ],
                },
                "accepted_work_products": None,
            }
            with self.assertRaisesRegex(
                dispatch_builder.DispatchError,
                "accepted Panel Judge",
            ):
                dispatch_builder.validate_authorized_search_budget(
                    budget,
                    "Search and Verification Specialist",
                    {
                        "candidate_id": None,
                        "round": None,
                    },
                    malformed_state,
                    "draft.search_budget",
                )

    def test_complete_role_input_budget_covers_payload_and_unicode_capsule(
        self,
    ) -> None:
        oversized_inputs = (
            (
                "instructions",
                "Observed signal A\n",
                "x" * 190_000,
                {"candidate": "C01"},
                1_024,
            ),
            (
                "inline-payload",
                "Observed signal A\n",
                "bounded instructions",
                {"payload": "x" * 190_000},
                1_024,
            ),
            (
                "cjk-capsule",
                "汉" * 100_000,
                "bounded instructions",
                {"candidate": "C01"},
                100_000,
            ),
            (
                "emoji-capsule",
                "🧭" * 60_000,
                "bounded instructions",
                {"candidate": "C01"},
                60_000,
            ),
        )
        for (
            label,
            evidence,
            instructions,
            inline_payload,
            max_chars,
        ) in oversized_inputs:
            with self.subTest(label=label), tempfile.TemporaryDirectory() as temporary:
                session = self.make_session(Path(temporary))
                (session / "project-evidence-pack.md").write_text(
                    evidence,
                    encoding="utf-8",
                )
                self.write_draft(
                    session,
                    packet_id="C01-R1-MENTOR",
                    candidate_id="C01",
                    role_instructions=instructions,
                    inline_payload=inline_payload,
                )
                with self.assertRaisesRegex(
                    dispatch_builder.DispatchError,
                    "UTF-8 byte budget",
                ):
                    self.build(session, max_chars=max_chars)
                self.assertFalse(
                    (
                        session
                        / "context-capsules"
                        / "C01-R1-MENTOR.json"
                    ).exists()
                )
                self.assertFalse(
                    (
                        session
                        / "control-inputs"
                        / "dispatches"
                        / "C01-R1-MENTOR.json"
                    ).exists()
                )


class CodexPortDocumentationTests(unittest.TestCase):
    SKILL_ROOT = (
        ROOT
        / "plugins"
        / "hotspot-to-rq"
        / "skills"
        / "research-direction-debate"
    )

    def test_contract_is_mandatory_ordered_and_honest_about_tool_isolation(
        self,
    ) -> None:
        port = (self.SKILL_ROOT / "references" / "codex-port.md").read_text(
            encoding="utf-8"
        )
        skill = (self.SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
        readme = (ROOT / "README.md").read_text(encoding="utf-8")

        self.assertIn("MUST contain one bounded evidence", port)
        self.assertIn("MUST be the only entry", port)
        self.assertIn("before committing its transition", port)
        self.assertIn("Generic Codex tasks inherit", port)
        self.assertIn("not a technical tool whitelist", port)
        self.assertIn("192,000-byte conservative role-input cap", port)
        self.assertIn("runs the full", port)
        self.assertIn("--verify-manifest", port)
        self.assertIn("binding every\nraw packet and capsule SHA-256", port)
        self.assertNotIn("approximately a\n   40K-token", port)
        self.assertNotIn("receives no project\nor artifact path", port)
        self.assertNotIn("capsule is an optional", port)
        self.assertIn("build_codex_dispatch.py", skill)
        self.assertIn("validate_codex_dispatch_batch.py", skill)
        self.assertIn("模型级", readme)


if __name__ == "__main__":
    unittest.main()
