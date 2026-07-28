"""Small deterministic fixtures shared by repository workflow tests."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess


def write_markdown(root: Path, relative: str, text: str = "") -> Path:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def build_mini_paper_notes(root: Path) -> Path:
    """Create a corpus with valid, ignored, Unicode, and threshold cases."""
    docs = root / "docs"
    write_markdown(
        docs,
        "CVPR2025/vision/index.md",
        "# Vision\n\n高频主题：生成模型×2 · 可靠性 x1\n",
    )
    write_markdown(
        docs,
        "CVPR2026/vision/index.md",
        "# Vision\n\n高频主题：生成模型×3 · 具身智能 x2\n",
    )
    for year, count in ((2025, 4), (2026, 6)):
        for index in range(count):
            title = (
                '---\ntitle: "统一视觉标题\\n续行"\n---\n'
                if index == 0
                else f"正文 {year}-{index}\n"
            )
            if year == 2026 and index == 1:
                title += "高频主题：可靠性×2\n"
            write_markdown(
                docs,
                f"CVPR{year}/vision/paper-{index:02d}.md",
                title,
            )

    # Equal-count areas exercise deterministic name ordering.
    write_markdown(docs, "ACL2026/zeta/paper.md", "zeta\n")
    write_markdown(docs, "ACL2026/alpha/paper.md", "alpha\n")
    write_markdown(docs, "ACL2026/alpha/search.md", "ignored\n")
    write_markdown(
        docs,
        "NOTACONF2026/invalid/index.md",
        "高频主题：不应出现×99\n",
    )
    write_markdown(docs, "NOTACONF2026/invalid/paper.md", "ignored\n")
    write_markdown(docs, "root-note.md", "ignored\n")
    return docs


def initialize_upstream_repository(root: Path) -> Path:
    upstream = root / "upstream"
    upstream.mkdir()
    subprocess.run(
        ["git", "init", "--initial-branch=main"],
        cwd=upstream,
        check=True,
        capture_output=True,
        text=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test User"],
        cwd=upstream,
        check=True,
    )
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"],
        cwd=upstream,
        check=True,
    )
    build_mini_paper_notes(upstream)
    (upstream / "LICENSE").write_text("CC BY-NC-SA 4.0\n", encoding="utf-8")
    subprocess.run(
        ["git", "add", "docs", "LICENSE"],
        cwd=upstream,
        check=True,
    )
    subprocess.run(
        ["git", "commit", "-m", "fixture corpus"],
        cwd=upstream,
        check=True,
        capture_output=True,
        text=True,
    )
    return upstream


def write_json(path: Path, value: object, *, mode: int | None = None) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    if mode is not None:
        path.chmod(mode)
    return path


def build_schema14_session(
    root: Path,
    *,
    transport_profile: str = "CODEX",
    packet_id: str = "C01-R1-MENTOR",
) -> Path:
    """Create the minimal shared schema-1.4 session used by transport tests."""
    session = root / "session-1"
    (session / "control-inputs" / "dispatch-drafts").mkdir(parents=True)
    (session / "project-evidence-pack.md").write_text(
        "Observed signal A\n",
        encoding="utf-8",
    )
    write_json(
        session / "session-state.json",
        {
            "schema_version": "1.4",
            "transport_profile": transport_profile,
            "session_id": "session-1",
            "project_root": str(root.resolve()),
            "project_snapshot": "snapshot-1",
            "search_budget": {
                "profile": "standard",
                "large_downloads": [],
                "approved_extensions": [],
            },
            "accepted_work_products": [],
        },
    )
    (session / "control-input.json").write_text("{}\n", encoding="utf-8")
    write_dispatch_draft(session, packet_id=packet_id)
    return session


def write_dispatch_draft(
    session: Path,
    *,
    packet_id: str,
    candidate_id: str | None = "C01",
    phase: str = "DEBATE",
    role: str = "Socratic Mentor",
    round_number: int | None = 1,
    role_instructions: str = "Ask one bounded Socratic question.",
    inline_payload: object | None = None,
    search_budget: dict[str, object] | None = None,
) -> Path:
    draft = {
        "envelope": {
            "schema_version": "1.0",
            "session_id": "session-1",
            "project_root": str(session.parent.resolve()),
            "project_snapshot": "snapshot-1",
            "phase": phase,
            "role": role,
            "candidate_id": candidate_id,
            "round": round_number,
            "packet_id": packet_id,
        },
        "role_instructions": role_instructions,
        "inline_payload": (
            {"candidate": candidate_id}
            if inline_payload is None
            else inline_payload
        ),
        "search_budget": search_budget,
    }
    return write_json(
        session
        / "control-inputs"
        / "dispatch-drafts"
        / f"{packet_id}.json",
        draft,
    )


def research_context_fingerprint(envelope: dict[str, object]) -> str:
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
        )
    }
    compact = json.dumps(
        identity,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    return hashlib.sha256(compact.encode("utf-8")).hexdigest()


def write_claude_dispatch(
    session: Path,
    state: dict[str, object],
    *,
    packet_id: str = "MAP-CLAUDE",
    phase: str = "DIRECTION_MAPPING",
    role: str = "Macro Direction Mapper",
    candidate_id: str | None = None,
    round_number: int | None = None,
) -> dict[str, object]:
    """Persist one valid immutable Claude transport and return its dispatch."""
    allowed_artifacts = [str((session / "project-evidence-pack.md").resolve())]
    envelope: dict[str, object] = {
        "schema_version": "1.0",
        "session_id": state["session_id"],
        "project_root": state["project_root"],
        "project_snapshot": state["project_snapshot"],
        "phase": phase,
        "role": role,
        "candidate_id": candidate_id,
        "round": round_number,
        "packet_id": packet_id,
        "context_fingerprint": "",
        "allowed_artifacts": allowed_artifacts,
    }
    envelope["context_fingerprint"] = research_context_fingerprint(envelope)
    transport_relative = f"control-inputs/dispatches/{packet_id}.json"
    transport = {
        "schema_version": "claude-dispatch-input-1",
        "envelope": envelope,
        "role_instructions": "Use only the bounded evidence.",
        "inline_payload": {},
        "allowed_artifact_paths": allowed_artifacts,
        "search_budget": None,
    }
    transport_path = write_json(
        session / transport_relative,
        transport,
        mode=0o400,
    )
    return {
        "packet_id": packet_id,
        "phase": phase,
        "role": role,
        "candidate_id": candidate_id,
        "round": round_number,
        "depends_on_packet_ids": [],
        "transport_path": transport_relative,
        "transport_sha256": hashlib.sha256(
            transport_path.read_bytes()
        ).hexdigest(),
    }
