from __future__ import annotations

import contextlib
import hashlib
import importlib.util
import io
import json
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from test_mainline_control import (  # noqa: E402
    VALIDATOR_PATH,
    control_state,
    controller_validator,
    research_product,
    transition,
    validator,
)

BUILDER_PATH = VALIDATOR_PATH.with_name("build_control_input.py")
BUILDER_SPEC = importlib.util.spec_from_file_location(
    "hotspot_build_control_input", BUILDER_PATH
)
assert BUILDER_SPEC is not None and BUILDER_SPEC.loader is not None
builder = importlib.util.module_from_spec(BUILDER_SPEC)
BUILDER_SPEC.loader.exec_module(builder)

DIGEST = "a" * 64


def screening_dispatch() -> dict:
    return {
        "packet_id": "SCR-01",
        "phase": "SCREENING",
        "role": "Panel Judge",
        "candidate_id": None,
        "round": None,
        "depends_on_packet_ids": [],
    }


def mentor_dispatch() -> dict:
    return {
        "packet_id": "C01-R1-MENTOR",
        "phase": "DEBATE",
        "role": "Socratic Mentor",
        "candidate_id": "C01",
        "round": 1,
        "depends_on_packet_ids": ["SCR-01"],
    }


def debate_candidate() -> dict:
    return {
        "candidate_id": "C01",
        "origin": "USER",
        "status": "ACTIVE",
        "gate_ready": False,
        "rounds_completed": 0,
        "rounds": [],
    }


def phase_boundary_state(transitions: list[dict], status: str) -> dict:
    state = control_state(
        status=status,
        transitions=transitions,
        products=[research_product("SCR-01", "SCREENING", "Panel Judge")],
    )
    state.update(
        {
            "max_rounds": 6,
            "initial_debate_candidate_ids": ["C01"],
            "candidates": [debate_candidate()],
        }
    )
    return state


def role_boundary_state(transitions: list[dict]) -> dict:
    state = control_state(
        status="DEBATING",
        transitions=transitions,
        products=[
            research_product("SCR-01", "SCREENING", "Panel Judge"),
            research_product(
                "C01-R1-MENTOR", "DEBATE", "Socratic Mentor", "C01", 1
            ),
        ],
    )
    state.update(
        {
            "max_rounds": 6,
            "initial_debate_candidate_ids": ["C01"],
            "candidates": [debate_candidate()],
        }
    )
    return state


def screening_transition() -> dict:
    return transition(
        revision=1,
        packet_id="CTRL-0001",
        checkpoint="PHASE_BOUNDARY",
        from_status="CANDIDATE_GENERATION",
        to_status="CANDIDATE_GENERATION",
        dispatches=[screening_dispatch()],
        required_actions=[],
    )


def mentor_transition(control_input_digest: str = "c" * 64) -> dict:
    return transition(
        revision=2,
        packet_id="CTRL-0002",
        digest=DIGEST,
        control_input_digest=control_input_digest,
        checkpoint="PHASE_BOUNDARY",
        from_status="CANDIDATE_GENERATION",
        to_status="DEBATING",
        dispatches=[mentor_dispatch()],
        required_actions=[],
    )


def write_state(directory: Path, state: dict) -> tuple[Path, str]:
    state_path = directory / "session-state.json"
    state_path.write_text(
        json.dumps(state, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return state_path, hashlib.sha256(state_path.read_bytes()).hexdigest()


def writer_side_errors(snapshot: dict, state: dict, digest: str) -> list[str]:
    accepted, rejected = controller_validator.collect_work_products(state, [])
    errors: list[str] = []
    controller_validator.validate_control_input(
        json.loads(json.dumps(snapshot)),
        state,
        digest,
        state["mainline_control"]["revision"],
        accepted,
        rejected,
        errors,
    )
    return errors


class BuildControlInputTests(unittest.TestCase):
    def test_cli_rejects_unhashable_transport_profile_without_crashing(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            state = control_state(transitions=[], products=[])
            state.update(
                {
                    "schema_version": "1.4",
                    "transport_profile": {},
                }
            )
            write_state(directory, state)
            stderr = io.StringIO()
            with contextlib.redirect_stderr(stderr):
                exit_code = builder.main(
                    [
                        str(directory),
                        "--checkpoint",
                        "SESSION_INIT",
                    ]
                )
            self.assertEqual(1, exit_code)
            self.assertIn("transport_profile CLAUDE or CODEX", stderr.getvalue())

    def test_packet_archive_is_immutable_and_cannot_be_rewritten(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            state = control_state(transitions=[], products=[])
            state.update(
                {
                    "schema_version": "1.4",
                    "transport_profile": "CODEX",
                }
            )
            state_path, _digest = write_state(directory, state)
            command = [
                str(directory),
                "--checkpoint",
                "SESSION_INIT",
                "--packet-id",
                "CTRL-0001",
            ]
            stderr = io.StringIO()
            with contextlib.redirect_stderr(stderr):
                self.assertEqual(0, builder.main(command))
            archive = directory / "control-inputs" / "CTRL-0001.json"
            original = archive.read_bytes()
            self.assertEqual(0o400, stat.S_IMODE(archive.stat().st_mode))

            state["updated_at"] = "2026-07-27T12:34:56+08:00"
            state_path.write_text(
                json.dumps(state, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            second_stderr = io.StringIO()
            with contextlib.redirect_stderr(second_stderr):
                exit_code = builder.main(command)
            self.assertEqual(1, exit_code)
            self.assertIn(
                "refusing to overwrite immutable",
                second_stderr.getvalue(),
            )
            self.assertEqual(original, archive.read_bytes())
            self.assertEqual(0o400, stat.S_IMODE(archive.stat().st_mode))

    def test_session_init_snapshot_passes_full_controller_validation(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            state = control_state(transitions=[], products=[])
            state["max_rounds"] = 6
            state_path, digest = write_state(directory, state)
            control_input_path = directory / "control-input.json"
            with contextlib.redirect_stderr(io.StringIO()):
                exit_code = builder.main(
                    [
                        str(directory),
                        "--checkpoint",
                        "SESSION_INIT",
                        "--out",
                        str(control_input_path),
                    ]
                )
            self.assertEqual(0, exit_code)
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
                "control_input_digest": hashlib.sha256(
                    control_input_path.read_bytes()
                ).hexdigest(),
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
            output_path.write_text(
                json.dumps(output, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            errors, _state_raw = controller_validator.validate(
                state_path, output_path
            )
            self.assertEqual([], errors)

    def test_phase_boundary_snapshot_passes_writer_and_archive_checks(
        self,
    ) -> None:
        build_state = phase_boundary_state(
            [screening_transition()], "CANDIDATE_GENERATION"
        )
        snapshot = builder.build_snapshot(
            build_state,
            DIGEST,
            "PHASE_BOUNDARY",
            artifact_readiness={"CANDIDATE_DIRECTIONS": "READY"},
        )
        self.assertEqual([], writer_side_errors(snapshot, build_state, DIGEST))

        raw = builder.serialize_snapshot(snapshot)
        current = mentor_transition(
            control_input_digest=hashlib.sha256(raw).hexdigest()
        )
        archived_state = phase_boundary_state(
            [screening_transition(), current], "DEBATING"
        )
        errors: list[str] = []
        validator.validate_control_input_snapshot(
            json.loads(raw.decode("utf-8")),
            current,
            archived_state,
            "snapshot",
            errors,
        )
        self.assertEqual([], errors)

    def test_role_boundary_snapshot_passes_writer_and_archive_checks(
        self,
    ) -> None:
        build_state = role_boundary_state(
            [screening_transition(), mentor_transition()]
        )
        snapshot = builder.build_snapshot(
            build_state,
            DIGEST,
            "ROLE_BOUNDARY",
            artifact_readiness={"CANDIDATE_DIRECTIONS": "READY"},
        )
        lane = snapshot["active_lanes"][0]
        self.assertEqual("Evidence Researcher", lane["next_role"])
        self.assertEqual(["C01-R1-MENTOR"], lane["dependency_packet_ids"])
        self.assertEqual([], writer_side_errors(snapshot, build_state, DIGEST))

        raw = builder.serialize_snapshot(snapshot)
        current = transition(
            revision=3,
            packet_id="CTRL-0003",
            digest=DIGEST,
            control_input_digest=hashlib.sha256(raw).hexdigest(),
            checkpoint="ROLE_BOUNDARY",
            from_status="DEBATING",
            to_status="DEBATING",
            dispatches=[
                {
                    "packet_id": "C01-R1-EVIDENCE",
                    "phase": "DEBATE",
                    "role": "Evidence Researcher",
                    "candidate_id": "C01",
                    "round": 1,
                    "depends_on_packet_ids": ["C01-R1-MENTOR"],
                }
            ],
            required_actions=[],
        )
        archived_state = role_boundary_state(
            [screening_transition(), mentor_transition(), current]
        )
        errors: list[str] = []
        validator.validate_control_input_snapshot(
            json.loads(raw.decode("utf-8")),
            current,
            archived_state,
            "snapshot",
            errors,
        )
        self.assertEqual([], errors)

    def test_post_user_gate_projects_the_consumed_receipt(self) -> None:
        hold = transition(
            revision=1,
            packet_id="CTRL-0001",
            digest=DIGEST,
            checkpoint="PRE_USER_GATE",
            from_status="SCANNING",
            action="HOLD_FOR_USER",
            to_status="DIRECTION_GATE",
            pending_user_gate="DIRECTION_SELECTION",
            required_actions=[],
        )
        state = control_state(
            status="DIRECTION_GATE",
            transitions=[hold],
            products=[],
        )
        state["gate_receipts"] = [
            {
                "receipt_id": "REC-1",
                "gate": "DIRECTION_SELECTION",
                "action": "SELECT",
                "based_on_revision": 1,
                "values": ["MD-01"],
            }
        ]
        snapshot = builder.build_snapshot(state, DIGEST, "POST_USER_GATE")
        self.assertEqual(
            {
                "kind": "DIRECTION_SELECTION",
                "receipt_id": "REC-1",
                "selected_ids": ["MD-01"],
            },
            snapshot["user_event"],
        )
        self.assertEqual([], writer_side_errors(snapshot, state, DIGEST))

    def test_cli_bytes_are_stable_and_digest_matches(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            write_state(
                directory,
                role_boundary_state(
                    [screening_transition(), mentor_transition()]
                ),
            )
            command = [
                sys.executable,
                "-B",
                str(BUILDER_PATH),
                str(directory),
                "--checkpoint",
                "ROLE_BOUNDARY",
                "--readiness",
                "CANDIDATE_DIRECTIONS=READY",
            ]
            first = subprocess.run(command, capture_output=True, check=True)
            second = subprocess.run(command, capture_output=True, check=True)
            self.assertEqual(first.stdout, second.stdout)
            self.assertTrue(first.stdout.endswith(b"}\n"))
            digest = hashlib.sha256(first.stdout).hexdigest()
            self.assertEqual(
                digest,
                first.stderr.decode("utf-8").strip().splitlines()[-1],
            )
            self.assertEqual(
                sorted(controller_validator.CONTROL_INPUT_KEYS),
                sorted(json.loads(first.stdout.decode("utf-8"))),
            )

            digest_only = subprocess.run(
                command + ["--digest-only"], capture_output=True, check=True
            )
            self.assertEqual(
                digest, digest_only.stdout.decode("utf-8").strip()
            )

            archive = subprocess.run(
                command + ["--packet-id", "CTRL-0003"],
                capture_output=True,
                check=True,
            )
            self.assertEqual(0, archive.returncode)
            archived_bytes = (
                directory / "control-inputs" / "CTRL-0003.json"
            ).read_bytes()
            live_bytes = (directory / "control-input.json").read_bytes()
            self.assertEqual(first.stdout, archived_bytes)
            self.assertEqual(first.stdout, live_bytes)
            self.assertEqual(
                0o400,
                stat.S_IMODE(
                    (
                        directory
                        / "control-inputs"
                        / "CTRL-0003.json"
                    ).stat().st_mode
                ),
            )

    def test_checkpoint_revision_guard_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            write_state(directory, control_state(transitions=[], products=[]))
            result = subprocess.run(
                [
                    sys.executable,
                    "-B",
                    str(BUILDER_PATH),
                    str(directory),
                    "--checkpoint",
                    "ROLE_BOUNDARY",
                ],
                capture_output=True,
            )
            self.assertEqual(1, result.returncode)
            self.assertIn(b"SESSION_INIT", result.stderr)
            self.assertEqual(b"", result.stdout)


if __name__ == "__main__":
    unittest.main()
