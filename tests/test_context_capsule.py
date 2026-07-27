from __future__ import annotations

import hashlib
import importlib.util
import json
import multiprocessing
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = (
    ROOT
    / "plugins"
    / "hotspot-to-rq"
    / "skills"
    / "research-direction-debate"
    / "scripts"
    / "build_context_capsule.py"
)
SPEC = importlib.util.spec_from_file_location("hotspot_context_capsule", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
capsule_builder = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(capsule_builder)


def concurrent_immutable_write(
    session: str,
    raw: bytes,
    barrier: object,
    results: object,
) -> None:
    original = capsule_builder._read_existing_at

    def synchronized_read(
        directory_fd: int,
        name: str,
        *,
        require_immutable: bool = False,
    ) -> bytes | None:
        existing = original(
            directory_fd,
            name,
            require_immutable=require_immutable,
        )
        if name == "race.json" and existing is None:
            barrier.wait(timeout=10)
        return existing

    capsule_builder._read_existing_at = synchronized_read
    try:
        capsule_builder.write_session_file(
            Path(session),
            "context-capsules/race.json",
            raw,
            immutable=True,
        )
    except capsule_builder.CapsuleError as error:
        results.put(("error", str(error)))
    else:
        results.put(("ok", raw))


class ContextCapsuleTests(unittest.TestCase):
    def write_session(self, directory: Path) -> Path:
        session = directory / "session-1"
        session.mkdir()
        (session / "project-evidence-pack.md").write_text(
            "Observed signal A\n", encoding="utf-8"
        )
        (session / "candidate-directions.md").write_text(
            "Candidate B\n", encoding="utf-8"
        )
        return session

    def test_writes_deterministic_integrity_labelled_capsule(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            session = self.write_session(Path(temporary))
            args = [
                str(session),
                "--packet-id",
                "C01-R1-MENTOR",
                "--checkpoint",
                "ROLE_BOUNDARY",
                "--artifact",
                "project-evidence-pack.md",
                "--artifact",
                "candidate-directions.md",
            ]
            self.assertEqual(0, capsule_builder.main(args))
            output = session / "context-capsules" / "C01-R1-MENTOR.json"
            first = output.read_bytes()
            self.assertEqual(0, capsule_builder.main(args))
            self.assertEqual(first, output.read_bytes())

            capsule = json.loads(first)
            self.assertEqual("codex-context-capsule-1", capsule["schema_version"])
            self.assertEqual("ROLE_BOUNDARY", capsule["checkpoint"])
            self.assertEqual(2, len(capsule["sources"]))
            self.assertLessEqual(
                capsule["excerpt_chars_total"],
                capsule["source_char_budget"],
            )
            first_source = capsule["sources"][0]
            self.assertEqual("project-evidence-pack.md", first_source["path"])
            self.assertEqual(
                hashlib.sha256(
                    (session / "project-evidence-pack.md").read_bytes()
                ).hexdigest(),
                first_source["sha256"],
            )
            self.assertFalse(first_source["truncated"])

    def test_many_sources_cannot_exceed_the_aggregate_budget(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            session = self.write_session(Path(temporary))
            artifacts = []
            for index in range(21):
                relative = f"evidence-{index:02d}.md"
                (session / relative).write_text(
                    f"START-{index}-" + "x" * 10_000 + f"-END-{index}",
                    encoding="utf-8",
                )
                artifacts.append(relative)
            capsule = capsule_builder.build_capsule(
                session,
                packet_id="C01-R1-EVIDENCE",
                checkpoint="ROLE_BOUNDARY",
                artifacts=artifacts,
                max_chars=1_024,
            )
            total = sum(source["excerpt_chars"] for source in capsule["sources"])
            self.assertEqual(capsule["excerpt_chars_total"], total)
            self.assertLessEqual(total, 1_024)
            self.assertTrue(all(source["truncated"] for source in capsule["sources"]))

    def test_rejects_a_component_budget_above_the_hard_cap(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            session = self.write_session(Path(temporary))
            with self.assertRaisesRegex(
                capsule_builder.CapsuleError,
                "must not exceed",
            ):
                capsule_builder.build_capsule(
                    session,
                    packet_id="C01-R1-MENTOR",
                    checkpoint="ROLE_BOUNDARY",
                    artifacts=["project-evidence-pack.md"],
                    max_chars=capsule_builder.DEFAULT_MAX_CHARS + 1,
                )

    def test_short_sources_return_unused_budget_to_long_sources(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            session = self.write_session(Path(temporary))
            (session / "short.md").write_text("x", encoding="utf-8")
            (session / "long.md").write_text("y" * 3_000, encoding="utf-8")
            capsule = capsule_builder.build_capsule(
                session,
                packet_id="C01-R1-EVIDENCE",
                checkpoint="ROLE_BOUNDARY",
                artifacts=["short.md", "long.md"],
                max_chars=1_024,
            )
            self.assertEqual(1_024, capsule["excerpt_chars_total"])
            self.assertEqual(1, capsule["sources"][0]["excerpt_chars"])
            self.assertEqual(1_023, capsule["sources"][1]["excerpt_chars"])
            self.assertFalse(capsule["sources"][0]["truncated"])
            self.assertTrue(capsule["sources"][1]["truncated"])

    def test_empty_sources_never_consume_water_filling_budget(self) -> None:
        limits = capsule_builder.allocate_excerpt_limits(
            [0] * 1_024 + [5_000],
            1_024,
        )
        self.assertEqual(0, sum(limits[:-1]))
        self.assertEqual(1_024, limits[-1])

    def test_truncates_a_source_without_losing_its_ends(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            session = self.write_session(Path(temporary))
            source = session / "project-evidence-pack.md"
            source.write_text("START-" + "x" * 2_000 + "-END", encoding="utf-8")
            capsule = capsule_builder.build_capsule(
                session,
                packet_id="C01-R1-EVIDENCE",
                checkpoint="ROLE_BOUNDARY",
                artifacts=["project-evidence-pack.md"],
                max_chars=1_024,
            )
            entry = capsule["sources"][0]
            self.assertTrue(entry["truncated"])
            self.assertLessEqual(entry["excerpt_chars"], 1_024)
            self.assertTrue(entry["text"].startswith("START-"))
            self.assertTrue(entry["text"].endswith("-END"))

    def test_rejects_paths_outside_the_session_or_through_symlinks(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            session = self.write_session(root)
            outside = root / "outside.md"
            outside.write_text("not session evidence", encoding="utf-8")
            with self.assertRaises(capsule_builder.CapsuleError):
                capsule_builder.build_capsule(
                    session,
                    packet_id="C01-R1-MENTOR",
                    checkpoint="ROLE_BOUNDARY",
                    artifacts=["../outside.md"],
                )

            link = session / "linked-evidence.md"
            try:
                link.symlink_to(outside)
            except OSError as error:
                self.skipTest(f"symlinks unavailable: {error}")
            with self.assertRaises(capsule_builder.CapsuleError):
                capsule_builder.build_capsule(
                    session,
                    packet_id="C01-R1-MENTOR",
                    checkpoint="ROLE_BOUNDARY",
                    artifacts=["linked-evidence.md"],
                )

    def test_dot_artifact_path_fails_cleanly(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            session = self.write_session(Path(temporary))
            result = capsule_builder.main(
                [
                    str(session),
                    "--packet-id",
                    "C01-R1-MENTOR",
                    "--checkpoint",
                    "ROLE_BOUNDARY",
                    "--artifact",
                    "./",
                ]
            )
            self.assertEqual(2, result)

    def test_refuses_a_symlinked_output_directory(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            session = self.write_session(root)
            outside = root / "outside"
            outside.mkdir()
            try:
                (session / "context-capsules").symlink_to(outside, target_is_directory=True)
            except OSError as error:
                self.skipTest(f"symlinks unavailable: {error}")
            result = capsule_builder.main(
                [
                    str(session),
                    "--packet-id",
                    "C01-R1-MENTOR",
                    "--checkpoint",
                    "ROLE_BOUNDARY",
                    "--artifact",
                    "project-evidence-pack.md",
                ]
            )
            self.assertEqual(2, result)
            self.assertFalse((outside / "C01-R1-MENTOR.json").exists())

    def test_packet_id_outputs_are_immutable(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            session = self.write_session(Path(temporary))
            args = [
                str(session),
                "--packet-id",
                "C01-R1-MENTOR",
                "--checkpoint",
                "ROLE_BOUNDARY",
                "--artifact",
                "project-evidence-pack.md",
            ]
            self.assertEqual(0, capsule_builder.main(args))
            output = session / "context-capsules" / "C01-R1-MENTOR.json"
            committed = output.read_bytes()
            (session / "project-evidence-pack.md").write_text(
                "changed evidence\n",
                encoding="utf-8",
            )
            self.assertEqual(2, capsule_builder.main(args))
            self.assertEqual(committed, output.read_bytes())

    def test_identical_rebuild_rejects_weakened_immutable_permissions(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            session = self.write_session(Path(temporary))
            args = [
                str(session),
                "--packet-id",
                "C01-R1-MENTOR",
                "--checkpoint",
                "ROLE_BOUNDARY",
                "--artifact",
                "project-evidence-pack.md",
            ]
            self.assertEqual(0, capsule_builder.main(args))
            output = session / "context-capsules" / "C01-R1-MENTOR.json"
            output.chmod(0o600)
            self.assertEqual(2, capsule_builder.main(args))
            self.assertEqual(0o600, output.stat().st_mode & 0o777)

    def test_concurrent_immutable_publish_never_overwrites_the_winner(self) -> None:
        if not capsule_builder._HAS_SECURE_DIR_FD:
            self.skipTest("secure POSIX dir-fd operations are unavailable")
        try:
            context = multiprocessing.get_context("fork")
        except ValueError:
            self.skipTest("fork multiprocessing context is unavailable")
        with tempfile.TemporaryDirectory() as temporary:
            session = self.write_session(Path(temporary))
            barrier = context.Barrier(2)
            results = context.Queue()
            contenders = [
                context.Process(
                    target=concurrent_immutable_write,
                    args=(str(session), raw, barrier, results),
                )
                for raw in (b"first contender\n", b"second contender\n")
            ]
            for process in contenders:
                process.start()
            for process in contenders:
                process.join(timeout=15)
                self.assertFalse(process.is_alive(), "concurrent writer hung")
                self.assertEqual(0, process.exitcode)
            outcomes = [results.get(timeout=2) for _ in contenders]
            self.assertEqual(1, sum(status == "ok" for status, _ in outcomes))
            self.assertEqual(1, sum(status == "error" for status, _ in outcomes))
            committed = (
                session / "context-capsules" / "race.json"
            ).read_bytes()
            self.assertIn(
                committed,
                {b"first contender\n", b"second contender\n"},
            )

    def test_same_byte_concurrent_winner_must_still_be_immutable(self) -> None:
        if not capsule_builder._HAS_SECURE_DIR_FD:
            self.skipTest("secure POSIX dir-fd operations are unavailable")
        with tempfile.TemporaryDirectory() as temporary:
            session = self.write_session(Path(temporary))
            raw = b"same contender bytes\n"
            real_link = capsule_builder.os.link

            def publish_weak_winner(
                source: str,
                target: str,
                *,
                src_dir_fd: int,
                dst_dir_fd: int,
                follow_symlinks: bool,
            ) -> None:
                descriptor = capsule_builder.os.open(
                    target,
                    os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                    0o600,
                    dir_fd=dst_dir_fd,
                )
                try:
                    capsule_builder.os.write(descriptor, raw)
                finally:
                    capsule_builder.os.close(descriptor)
                real_link(
                    source,
                    target,
                    src_dir_fd=src_dir_fd,
                    dst_dir_fd=dst_dir_fd,
                    follow_symlinks=follow_symlinks,
                )

            with mock.patch.object(
                capsule_builder.os,
                "link",
                side_effect=publish_weak_winner,
            ):
                with self.assertRaisesRegex(
                    capsule_builder.CapsuleError,
                    "permissions must be exactly 0400",
                ):
                    capsule_builder.write_session_file(
                        session,
                        "context-capsules/race.json",
                        raw,
                        immutable=True,
                    )
            target = session / "context-capsules" / "race.json"
            self.assertEqual(raw, target.read_bytes())
            self.assertEqual(0o600, target.stat().st_mode & 0o777)

    def test_fifo_leafs_fail_closed_without_waiting_for_a_writer(self) -> None:
        if not hasattr(os, "mkfifo"):
            self.skipTest("FIFOs are unavailable")
        with tempfile.TemporaryDirectory() as temporary:
            session = self.write_session(Path(temporary))

            source_fifo = session / "source.fifo"
            os.mkfifo(source_fifo)
            with self.assertRaisesRegex(
                capsule_builder.CapsuleError,
                "regular file",
            ):
                capsule_builder.read_session_artifact(session, "source.fifo")

            output_directory = session / "context-capsules"
            output_directory.mkdir()
            output_fifo = output_directory / "target.json"
            os.mkfifo(output_fifo)
            with self.assertRaisesRegex(
                capsule_builder.CapsuleError,
                "regular file",
            ):
                capsule_builder.write_session_file(
                    session,
                    "context-capsules/target.json",
                    b"payload\n",
                    immutable=True,
                )

            immutable_fifo = session / "immutable.fifo"
            os.mkfifo(immutable_fifo)
            with self.assertRaisesRegex(
                capsule_builder.CapsuleError,
                "must be regular",
            ):
                capsule_builder.assert_immutable_session_artifact(
                    session,
                    "immutable.fifo",
                )

    def test_file_identity_includes_ctime(self) -> None:
        common = {
            "st_dev": 1,
            "st_ino": 2,
            "st_size": 3,
            "st_mtime_ns": 4,
        }
        before = SimpleNamespace(**common, st_ctime_ns=5)
        after = SimpleNamespace(**common, st_ctime_ns=6)
        self.assertNotEqual(
            capsule_builder._stat_identity(before),
            capsule_builder._stat_identity(after),
        )

    def test_platform_without_secure_no_follow_support_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            session = self.write_session(Path(temporary))
            with mock.patch.object(
                capsule_builder,
                "_HAS_SECURE_DIR_FD",
                False,
            ):
                with self.assertRaisesRegex(
                    capsule_builder.CapsuleError,
                    "secure handle-relative",
                ):
                    capsule_builder.read_session_artifact(
                        session,
                        "project-evidence-pack.md",
                    )
                with self.assertRaisesRegex(
                    capsule_builder.CapsuleError,
                    "secure handle-relative",
                ):
                    capsule_builder.write_session_file(
                        session,
                        "context-capsules/blocked.json",
                        b"blocked\n",
                    )

    def test_ancestor_replacement_cannot_redirect_reads_or_writes(self) -> None:
        if not capsule_builder._HAS_SECURE_DIR_FD:
            self.skipTest("secure POSIX dir-fd operations are unavailable")
        for operation in ("read", "write"):
            with self.subTest(operation=operation), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                parent = root / "parent"
                session = parent / "session"
                session.mkdir(parents=True)
                (session / "evidence.md").write_text(
                    "original evidence\n",
                    encoding="utf-8",
                )
                external_parent = root / "external"
                external_session = external_parent / "session"
                external_session.mkdir(parents=True)
                (external_session / "evidence.md").write_text(
                    "external evidence\n",
                    encoding="utf-8",
                )
                held_parent = root / "held-parent"
                real_open = capsule_builder.os.open
                replaced = False

                def replace_after_open(path, *args, **kwargs):
                    nonlocal replaced
                    descriptor = real_open(path, *args, **kwargs)
                    if path == "parent" and not replaced:
                        replaced = True
                        parent.rename(held_parent)
                        parent.symlink_to(
                            external_parent,
                            target_is_directory=True,
                        )
                    return descriptor

                with mock.patch.object(
                    capsule_builder.os,
                    "open",
                    side_effect=replace_after_open,
                ):
                    with self.assertRaisesRegex(
                        capsule_builder.CapsuleError,
                        "session_dir",
                    ):
                        if operation == "read":
                            capsule_builder.read_session_artifact(
                                session,
                                "evidence.md",
                            )
                        else:
                            capsule_builder.write_session_file(
                                session,
                                "context-capsules/race.json",
                                b"bounded output\n",
                            )
                if operation == "write":
                    self.assertFalse(
                        (
                            external_session
                            / "context-capsules"
                            / "race.json"
                        ).exists()
                    )
                    self.assertTrue(
                        (
                            held_parent
                            / "session"
                            / "context-capsules"
                            / "race.json"
                        ).exists()
                    )


if __name__ == "__main__":
    unittest.main()
