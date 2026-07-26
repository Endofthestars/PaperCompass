from __future__ import annotations

import hashlib
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
VENDOR_ROOT = (
    ROOT
    / "plugins"
    / "hotspot-to-rq"
    / "skills"
    / "research-direction-debate"
    / "vendor"
    / "academic-research-suite"
)


EXPECTED_SHA256 = {
    "LICENSE": "b3848009d12a173f549ef98d9ee486e64459e8eb5d9f895bff53782b4aa86d7c",
    "deep-research/WORKFLOW.md": "fe9573084c825fdba295479fbdb329d6fcfa4eb11c955bbbd65a31e8df620513",
    "deep-research/agents/bibliography_agent.md": "885ef79f7a37cc03e0fcb9c4a7deecb9bb9f9bbae5b98ce2c7c9e42804e76dea",
    "deep-research/agents/devils_advocate_agent.md": "f1affcd163b081ed10b6ba0c31e2029f0f821b43b8201ac0b25622aba211e682",
    "deep-research/agents/research_architect_agent.md": "438a7f09d669193c1256c5a36601787d64a03eecded4b65f3128e9ca27732a8c",
    "deep-research/agents/research_question_agent.md": "d5d8df51f7fbe54ddec08ba335346c1c49a5264a1a1b0cd1ef680c026092523e",
    "deep-research/agents/socratic_mentor_agent.md": "6d9218971f0787603f0453693af63b2f36c894e4655ccd365aa868bcbd8748c0",
    "deep-research/agents/source_verification_agent.md": "3ffecae526acdde6d28bb8d2a9f5a88f95c00f51338c8f4d4a724ced3f7777bf",
    "deep-research/agents/synthesis_agent.md": "4e7150d9f465346888ca36c3bdc1421916138c746a3c5bef447313fbeb195ce5",
    "experiment-agent/WORKFLOW.md": "3d3dee7e28b0ae3eba025afb311f11910d6107fabe6afe32ff91928c3028b118",
}


class ArsVendorBundleTests(unittest.TestCase):
    def test_vendor_bundle_is_complete_and_byte_pinned(self) -> None:
        for relative_path, expected_hash in EXPECTED_SHA256.items():
            with self.subTest(path=relative_path):
                path = VENDOR_ROOT / relative_path
                self.assertTrue(path.is_file(), f"missing vendored file: {path}")
                self.assertEqual(
                    expected_hash,
                    hashlib.sha256(path.read_bytes()).hexdigest(),
                )

    def test_vendor_provenance_records_source_and_license(self) -> None:
        provenance = (VENDOR_ROOT / "VENDOR.md").read_text(encoding="utf-8")
        self.assertIn("bbc0659272a511b422f6856cd6f44b6ccb2ac213", provenance)
        self.assertIn("9b063fa895eaf1f63ac99ac03f924f8d31aa8d26", provenance)
        self.assertIn("Attribution-NonCommercial 4.0", provenance)


if __name__ == "__main__":
    unittest.main()
