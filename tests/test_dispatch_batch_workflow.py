"""Functional tests for workflows/dispatch-batch.js.

Regression background: a live run failed three consecutive workflow launches
because the workflow runtime delivered ``args`` as a JSON-encoded string while
the script assumed an object, and a later batch reported success while
silently carrying null results for transport-failed agents. These tests
execute the real script body under a stubbed runtime (see
``dispatch_batch_harness.js``) and pin the hardened behavior.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
WORKFLOW = REPO_ROOT / "plugins" / "hotspot-to-rq" / "workflows" / "dispatch-batch.js"
HARNESS = REPO_ROOT / "tests" / "dispatch_batch_harness.js"


def make_dispatch(packet_id: str, role: str = "Evidence Researcher", **overrides):
    dispatch = {
        "packet_id": packet_id,
        "phase": "DEBATE",
        "role": role,
        "candidate_id": "C01",
        "round": 1,
        "envelope": {"packet_id": packet_id, "session_id": "S"},
        "role_instructions": "follow the contract",
        "inline_payload": None,
        "allowed_artifact_paths": [],
        "search_budget": None,
    }
    dispatch.update(overrides)
    return dispatch


def envelopes_for(*dispatches):
    return {d["packet_id"]: d["envelope"] for d in dispatches}


@unittest.skipIf(shutil.which("node") is None, "node is not installed")
class DispatchBatchWorkflowTests(unittest.TestCase):
    def run_workflow(self, scenario: dict) -> dict:
        completed = subprocess.run(
            ["node", str(HARNESS), str(WORKFLOW), json.dumps(scenario)],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(0, completed.returncode, completed.stderr)
        return json.loads(completed.stdout)

    def test_accepts_args_delivered_as_a_json_encoded_string(self) -> None:
        dispatch = make_dispatch("C01-R1-EVIDENCE")
        outcome = self.run_workflow(
            {
                "args": {"dispatches": [dispatch]},
                "stringifyArgs": True,
                "envelopes": envelopes_for(dispatch),
            }
        )
        self.assertIsNone(outcome["error"])
        packets = outcome["result"]["packets"]
        self.assertEqual(["C01-R1-EVIDENCE"], [p["packet_id"] for p in packets])
        self.assertTrue(packets[0]["echo_ok"])
        self.assertEqual(0, outcome["result"]["failed_count"])

    def test_accepts_args_delivered_as_an_object(self) -> None:
        dispatch = make_dispatch("C01-R1-EVIDENCE")
        outcome = self.run_workflow(
            {
                "args": {"dispatches": [dispatch]},
                "stringifyArgs": False,
                "envelopes": envelopes_for(dispatch),
            }
        )
        self.assertIsNone(outcome["error"])
        self.assertEqual(1, len(outcome["result"]["packets"]))

    def test_missing_dispatches_error_names_the_received_type(self) -> None:
        outcome = self.run_workflow({"args": {}, "stringifyArgs": False})
        self.assertIn("non-empty array", outcome["error"])
        self.assertIn("object", outcome["error"])

    def test_one_failing_agent_does_not_sink_the_batch(self) -> None:
        healthy = make_dispatch("C02-R1-DEVIL", role="Devil's Advocate")
        doomed = make_dispatch("C03-R1-DEVIL", role="Devil's Advocate")
        outcome = self.run_workflow(
            {
                "args": {"dispatches": [healthy, doomed]},
                "agents": {"C03-R1-DEVIL": ["throw", "throw"]},
                "envelopes": envelopes_for(healthy, doomed),
            }
        )
        self.assertIsNone(outcome["error"])
        packets = {p["packet_id"]: p for p in outcome["result"]["packets"]}
        self.assertTrue(packets["C02-R1-DEVIL"]["echo_ok"])
        self.assertIsNone(packets["C03-R1-DEVIL"]["result"])
        self.assertIn("Overloaded", packets["C03-R1-DEVIL"]["error"])
        self.assertEqual(1, outcome["result"]["failed_count"])
        self.assertTrue(any("stay PENDING" in note for note in outcome["notes"]))

    def test_transient_failure_is_retried_once_and_recovers(self) -> None:
        dispatch = make_dispatch("C01-R1-EVIDENCE")
        outcome = self.run_workflow(
            {
                "args": {"dispatches": [dispatch]},
                "agents": {"C01-R1-EVIDENCE": ["throw", "ok"]},
                "envelopes": envelopes_for(dispatch),
            }
        )
        self.assertIsNone(outcome["error"])
        packet = outcome["result"]["packets"][0]
        self.assertIsNotNone(packet["result"])
        self.assertIsNone(packet["error"])
        self.assertEqual(0, outcome["result"]["failed_count"])
        self.assertEqual(2, len(outcome["calls"]))

    def test_guards_reject_control_phase_and_duplicate_packet_ids(self) -> None:
        control = make_dispatch("CTRL-0001", phase="CONTROL")
        first = make_dispatch("C01-R1-EVIDENCE")
        duplicate = make_dispatch("C01-R1-EVIDENCE")
        outcome = self.run_workflow(
            {
                "args": {"dispatches": [control, first, duplicate]},
                "envelopes": envelopes_for(first),
            }
        )
        self.assertIsNone(outcome["error"])
        rejected = {r["packet_id"]: r for r in outcome["result"]["rejected"]}
        self.assertEqual("CONTROL_ROLE_NOT_BATCHABLE", rejected["CTRL-0001"]["reason"])
        self.assertEqual("CONTROL_SCOPE_VIOLATION", rejected["CTRL-0001"]["reason_code"])
        self.assertEqual("DUPLICATE_PACKET_ID", rejected["C01-R1-EVIDENCE"]["reason"])
        self.assertEqual(1, len(outcome["result"]["packets"]))

    def test_typographic_apostrophe_role_still_gets_the_devil_schema(self) -> None:
        dispatch = make_dispatch("C01-R1-DEVIL", role="Devil’s Advocate")
        outcome = self.run_workflow(
            {
                "args": {"dispatches": [dispatch]},
                "envelopes": envelopes_for(dispatch),
            }
        )
        self.assertIsNone(outcome["error"])
        packet = outcome["result"]["packets"][0]
        self.assertEqual("Devil's Advocate", packet["role"])
        self.assertIn("strongest_form", outcome["calls"][0]["schemaRequired"])

    def test_ledger_row_schema_enforces_the_validator_enums(self) -> None:
        source = WORKFLOW.read_text(encoding="utf-8")
        for value in (
            "'peer-reviewed'",
            "'official-doc'",
            "'CLAIM_SUPPORTED_BY_SOURCE'",
            "'CONTRADICTED'",
        ):
            self.assertIn(value, source)


if __name__ == "__main__":
    unittest.main()
