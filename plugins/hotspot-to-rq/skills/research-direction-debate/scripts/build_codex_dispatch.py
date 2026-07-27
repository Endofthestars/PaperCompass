#!/usr/bin/env python3
"""Build and persist one final Codex role dispatch before state commit.

The input draft deliberately omits context_fingerprint and allowed_artifacts.
This builder first creates the immutable evidence capsule, then constructs the
final envelope with the capsule's absolute path, computes the fingerprint, and
persists the exact packet bytes used for initial dispatch and every retry.
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


capsules = _load_module(
    "hotspot_build_context_capsule",
    "build_context_capsule.py",
)
session_validator = _load_module(
    "hotspot_validate_session_for_dispatch",
    "validate_session.py",
)

DISPATCH_SCHEMA_VERSION = "codex-dispatch-packet-1"
MAX_ROLE_INPUT_BYTES = 192_000
ROLE_INPUT_FRAMING_RESERVE_BYTES = 8_192
TEN_MIB = 10 * 1024 * 1024
SEARCH_ROLE = "Search and Verification Specialist"
DRAFT_KEYS = {
    "envelope",
    "role_instructions",
    "inline_payload",
    "search_budget",
}
BASE_ENVELOPE_KEYS = {
    "schema_version",
    "session_id",
    "project_root",
    "project_snapshot",
    "phase",
    "role",
    "candidate_id",
    "round",
    "packet_id",
}
PACKET_KEYS = {
    "schema_version",
    "envelope",
    "role_instructions",
    "inline_payload",
    "allowed_artifact_paths",
    "search_budget",
    "context_capsule",
}
CAPSULE_META_KEYS = {
    "path",
    "sha256",
    "checkpoint",
    "source_char_budget",
    "excerpt_chars_total",
}
CAPSULE_KEYS = {
    "schema_version",
    "packet_id",
    "checkpoint",
    "source_char_budget",
    "excerpt_chars_total",
    "sources",
    "usage",
}
CAPSULE_SOURCE_KEYS = {
    "path",
    "sha256",
    "source_chars",
    "excerpt_chars",
    "truncated",
    "text",
}
SHA256_CHARS = frozenset("0123456789abcdef")
SEARCH_BUDGET_KEYS = {
    "profile",
    "max_query_batches",
    "max_queries_per_batch",
    "max_new_sources",
    "extension",
    "large_downloads",
}
SEARCH_EXTENSION_KEYS = {
    "approved",
    "approval_packet_id",
    "judge_reason",
    "extra_query_batches",
    "extra_sources",
}
SEARCH_DOWNLOAD_KEYS = {
    "url",
    "size_bytes",
    "necessity",
    "user_approved",
}


class DispatchError(ValueError):
    """Raised when a draft or persisted dispatch violates the Codex contract."""


def strict_json(raw: bytes, label: str) -> Any:
    def pairs_hook(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise DispatchError(f"{label} contains duplicate key {key!r}")
            result[key] = value
        return result

    def reject_constant(value: str) -> None:
        raise DispatchError(f"{label} contains non-finite number {value}")

    try:
        return json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=pairs_hook,
            parse_constant=reject_constant,
        )
    except UnicodeDecodeError as error:
        raise DispatchError(f"{label} must be UTF-8 JSON") from error
    except json.JSONDecodeError as error:
        raise DispatchError(f"{label} is invalid JSON: {error}") from error


def require_exact_keys(value: Any, expected: set[str], label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise DispatchError(f"{label} must be an object")
    actual = set(value)
    if actual != expected:
        missing = sorted(expected - actual)
        extra = sorted(actual - expected)
        raise DispatchError(
            f"{label} keys differ; missing={missing}, extra={extra}"
        )
    return value


def nonempty_string(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def bounded_integer(
    value: Any,
    *,
    minimum: int,
    maximum: int,
    label: str,
) -> int:
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or value < minimum
        or value > maximum
    ):
        raise DispatchError(
            f"{label} must be an integer from {minimum} through {maximum}"
        )
    return value


def validate_search_budget(value: Any, role: str, label: str) -> None:
    if role != SEARCH_ROLE:
        if value is not None:
            raise DispatchError(f"{label} must be null for non-search roles")
        return
    budget = require_exact_keys(value, SEARCH_BUDGET_KEYS, label)
    if budget["profile"] != "standard":
        raise DispatchError(f"{label}.profile must be 'standard'")
    max_query_batches = bounded_integer(
        budget["max_query_batches"],
        minimum=0,
        maximum=2,
        label=f"{label}.max_query_batches",
    )
    if max_query_batches != 2:
        raise DispatchError(f"{label}.max_query_batches must equal 2")
    max_queries_per_batch = bounded_integer(
        budget["max_queries_per_batch"],
        minimum=0,
        maximum=4,
        label=f"{label}.max_queries_per_batch",
    )
    if max_queries_per_batch != 4:
        raise DispatchError(f"{label}.max_queries_per_batch must equal 4")
    max_new_sources = bounded_integer(
        budget["max_new_sources"],
        minimum=0,
        maximum=8,
        label=f"{label}.max_new_sources",
    )
    if max_new_sources != 8:
        raise DispatchError(f"{label}.max_new_sources must equal 8")
    extension = require_exact_keys(
        budget["extension"],
        SEARCH_EXTENSION_KEYS,
        f"{label}.extension",
    )
    if not isinstance(extension["approved"], bool):
        raise DispatchError(f"{label}.extension.approved must be boolean")
    approval_packet_id = extension["approval_packet_id"]
    judge_reason = extension["judge_reason"]
    if extension["approved"]:
        if not nonempty_string(approval_packet_id):
            raise DispatchError(
                f"{label}.extension.approval_packet_id must be non-empty"
            )
        capsules.validate_safe_id(
            approval_packet_id,
            f"{label}.extension.approval_packet_id",
        )
        if not nonempty_string(judge_reason):
            raise DispatchError(
                f"{label}.extension.judge_reason must be non-empty"
            )
    elif approval_packet_id is not None or judge_reason is not None:
        raise DispatchError(
            f"{label}.extension approval fields must be null when unapproved"
        )
    extra_batches = bounded_integer(
        extension["extra_query_batches"],
        minimum=0,
        maximum=1,
        label=f"{label}.extension.extra_query_batches",
    )
    extra_sources = bounded_integer(
        extension["extra_sources"],
        minimum=0,
        maximum=4,
        label=f"{label}.extension.extra_sources",
    )
    if not extension["approved"] and (extra_batches or extra_sources):
        raise DispatchError(
            f"{label}.extension cannot grant capacity unless approved is true"
        )

    downloads = budget["large_downloads"]
    if not isinstance(downloads, list):
        raise DispatchError(f"{label}.large_downloads must be an array")
    download_cap = max_new_sources + (
        extra_sources if extension["approved"] else 0
    )
    if len(downloads) > download_cap:
        raise DispatchError(
            f"{label}.large_downloads cannot exceed the granted source quota "
            f"of {download_cap}"
        )
    download_urls: set[str] = set()
    for index, download_value in enumerate(downloads):
        download_label = f"{label}.large_downloads[{index}]"
        download = require_exact_keys(
            download_value,
            SEARCH_DOWNLOAD_KEYS,
            download_label,
        )
        if not nonempty_string(download["url"]):
            raise DispatchError(f"{download_label}.url must be non-empty")
        if download["url"] in download_urls:
            raise DispatchError(f"{download_label}.url is duplicated")
        download_urls.add(download["url"])
        size = download["size_bytes"]
        if isinstance(size, bool) or not isinstance(size, int) or size <= 0:
            raise DispatchError(
                f"{download_label}.size_bytes must be a positive integer"
            )
        necessity = download["necessity"]
        if necessity is not None and not nonempty_string(necessity):
            raise DispatchError(
                f"{download_label}.necessity must be non-empty or null"
            )
        if not isinstance(download["user_approved"], bool):
            raise DispatchError(
                f"{download_label}.user_approved must be boolean"
            )
        if size <= TEN_MIB:
            raise DispatchError(
                f"{download_label} belongs in large_downloads only above 10 MiB"
            )
        if not nonempty_string(necessity) or not download["user_approved"]:
            raise DispatchError(
                f"{download_label} exceeds 10 MiB without necessity and approval"
            )


def validate_authorized_search_budget(
    value: Any,
    role: str,
    envelope: dict[str, Any],
    state: dict[str, Any],
    label: str,
) -> None:
    validate_search_budget(value, role, label)
    if role != SEARCH_ROLE:
        return
    authoritative = state.get("search_budget")
    if not isinstance(authoritative, dict):
        raise DispatchError("session-state.json.search_budget must be an object")
    approved_downloads = authoritative.get("large_downloads")
    if not isinstance(approved_downloads, list):
        raise DispatchError(
            "session-state.json.search_budget.large_downloads must be an array"
        )
    for download in value["large_downloads"]:
        if download not in approved_downloads:
            raise DispatchError(
                f"{label}.large_downloads contains no matching authoritative "
                "session approval"
            )

    extension = value["extension"]
    if not extension["approved"]:
        return
    approved_extensions = authoritative.get("approved_extensions", [])
    if not isinstance(approved_extensions, list):
        raise DispatchError(
            "session-state.json.search_budget.approved_extensions must be an array"
        )
    authorization = {
        "approval_packet_id": extension["approval_packet_id"],
        "judge_reason": extension["judge_reason"],
        "extra_query_batches": extension["extra_query_batches"],
        "extra_sources": extension["extra_sources"],
    }
    if authorization not in approved_extensions:
        raise DispatchError(
            f"{label}.extension has no matching authoritative state approval"
        )
    accepted_products_value = state.get("accepted_work_products")
    accepted_products = (
        accepted_products_value
        if isinstance(accepted_products_value, list)
        else []
    )
    approval_product = next(
        (
            product
            for product in accepted_products
            if isinstance(product, dict)
            and product.get("packet_id") == extension["approval_packet_id"]
            and product.get("role") == "Panel Judge"
            and product.get("candidate_id") == envelope.get("candidate_id")
            and product.get("round") == envelope.get("round")
        ),
        None,
    )
    if approval_product is None:
        raise DispatchError(
            f"{label}.extension approval is not bound to an accepted Panel Judge"
        )


def validate_base_envelope(value: Any) -> dict[str, Any]:
    envelope = require_exact_keys(value, BASE_ENVELOPE_KEYS, "draft.envelope")
    if envelope["schema_version"] != "1.0":
        raise DispatchError("draft.envelope.schema_version must be '1.0'")
    for field in (
        "session_id",
        "project_root",
        "project_snapshot",
        "phase",
        "role",
        "packet_id",
    ):
        if not nonempty_string(envelope[field]):
            raise DispatchError(f"draft.envelope.{field} must be non-empty")
    capsules.validate_safe_id(envelope["packet_id"], "draft.envelope.packet_id")
    if not Path(envelope["project_root"]).is_absolute():
        raise DispatchError("draft.envelope.project_root must be absolute")
    phase = envelope["phase"]
    role = envelope["role"]
    if phase == "CONTROL":
        raise DispatchError("Codex role dispatch builder must not build CONTROL")
    phase_roles = session_validator.PHASE_ROLES
    if phase not in phase_roles:
        raise DispatchError(f"draft.envelope.phase is unsupported: {phase!r}")
    if role not in phase_roles[phase]:
        raise DispatchError(
            f"draft.envelope.role {role!r} is not valid for phase {phase!r}"
        )
    candidate_id = envelope["candidate_id"]
    if candidate_id is not None and not nonempty_string(candidate_id):
        raise DispatchError("draft.envelope.candidate_id must be a string or null")
    round_number = envelope["round"]
    if round_number is not None and (
        isinstance(round_number, bool)
        or not isinstance(round_number, int)
        or round_number < 1
    ):
        raise DispatchError("draft.envelope.round must be a positive integer or null")
    return dict(envelope)


def validate_draft(value: Any) -> dict[str, Any]:
    draft = require_exact_keys(value, DRAFT_KEYS, "draft")
    validate_base_envelope(draft["envelope"])
    if not nonempty_string(draft["role_instructions"]):
        raise DispatchError("draft.role_instructions must be non-empty")
    role = draft["envelope"]["role"]
    validate_search_budget(draft["search_budget"], role, "draft.search_budget")
    return draft


def load_session_state(session_dir: Any) -> dict[str, Any]:
    raw, relative = capsules.read_session_artifact(
        session_dir,
        "session-state.json",
    )
    state = strict_json(raw, relative)
    if not isinstance(state, dict):
        raise DispatchError("session-state.json must be an object")
    return state


def require_codex_transport_profile(
    state: dict[str, Any],
    location: str = "session-state.json",
) -> None:
    if (
        state.get("schema_version") != "1.4"
        or state.get("transport_profile") != "CODEX"
    ):
        raise DispatchError(
            f"{location} must use schema_version 1.4 with transport_profile CODEX"
        )


def session_identity(state: dict[str, Any]) -> dict[str, Any]:
    identity: dict[str, Any] = {}
    for field in ("session_id", "project_root", "project_snapshot"):
        value = state.get(field)
        if not nonempty_string(value):
            raise DispatchError(f"session-state.json.{field} must be non-empty")
        identity[field] = value
    if not Path(identity["project_root"]).is_absolute():
        raise DispatchError("session-state.json.project_root must be absolute")
    return identity


def validate_envelope_identity(
    envelope: dict[str, Any],
    session_identity: dict[str, Any],
) -> None:
    for field, expected in session_identity.items():
        if envelope.get(field) != expected:
            raise DispatchError(
                f"draft.envelope.{field} does not match session-state.json"
            )


def serialize_packet(packet: dict[str, Any]) -> bytes:
    return (json.dumps(packet, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def validate_role_input_budget(packet_raw: bytes, capsule_raw: bytes) -> None:
    total = (
        len(packet_raw)
        + len(capsule_raw)
        + ROLE_INPUT_FRAMING_RESERVE_BYTES
    )
    if total > MAX_ROLE_INPUT_BYTES:
        raise DispatchError(
            "final Codex role input exceeds the conservative UTF-8 byte budget: "
            f"{total} > {MAX_ROLE_INPUT_BYTES}; reduce --max-chars, role "
            "instructions, or inline payload and use a new packet id"
        )


def build_dispatch(
    session_dir: Path,
    *,
    draft_relative_path: str,
    checkpoint: str,
    artifacts: list[str],
    max_chars: int = capsules.DEFAULT_MAX_CHARS,
) -> tuple[dict[str, Any], bytes, Path]:
    with capsules.session_scope(session_dir) as root:
        draft_raw, draft_relative = capsules.read_session_artifact(
            root,
            draft_relative_path,
        )
        draft = validate_draft(strict_json(draft_raw, draft_relative))
        base_envelope = validate_base_envelope(draft["envelope"])
        state = load_session_state(root)
        require_codex_transport_profile(state)
        validate_envelope_identity(base_envelope, session_identity(state))
        validate_authorized_search_budget(
            draft["search_budget"],
            base_envelope["role"],
            base_envelope,
            state,
            "draft.search_budget",
        )
        packet_id = base_envelope["packet_id"]

        capsule = capsules.build_capsule(
            root,
            packet_id=packet_id,
            checkpoint=checkpoint,
            artifacts=artifacts,
            max_chars=max_chars,
        )
        capsule_raw = capsules.serialize_capsule(capsule)
        capsule_path = root.path / "context-capsules" / f"{packet_id}.json"
        absolute_capsule_path = str(capsule_path)
        envelope = dict(base_envelope)
        envelope["context_fingerprint"] = (
            session_validator.expected_context_fingerprint(envelope)
        )
        envelope["allowed_artifacts"] = [absolute_capsule_path]
        packet = {
            "schema_version": DISPATCH_SCHEMA_VERSION,
            "envelope": envelope,
            "role_instructions": draft["role_instructions"],
            "inline_payload": draft["inline_payload"],
            "allowed_artifact_paths": [absolute_capsule_path],
            "search_budget": draft["search_budget"],
            "context_capsule": {
                "path": absolute_capsule_path,
                "sha256": hashlib.sha256(capsule_raw).hexdigest(),
                "checkpoint": checkpoint,
                "source_char_budget": capsule["source_char_budget"],
                "excerpt_chars_total": capsule["excerpt_chars_total"],
            },
        }
        raw = serialize_packet(packet)
        validate_role_input_budget(raw, capsule_raw)
        capsules.write_session_file(
            root,
            f"context-capsules/{packet_id}.json",
            capsule_raw,
            immutable=True,
        )
        output = capsules.write_session_file(
            root,
            f"control-inputs/dispatches/{packet_id}.json",
            raw,
            immutable=True,
        )
        return packet, raw, output


def validate_persisted_packet(
    session_dir: Path | Any,
    packet_id: str,
) -> tuple[dict[str, Any], bytes]:
    with capsules.session_scope(session_dir) as root:
        return _validate_persisted_packet(root, packet_id)


def _validate_persisted_packet(
    session_root: Any,
    packet_id: str,
) -> tuple[dict[str, Any], bytes]:
    capsules.validate_safe_id(packet_id, "packet_id")
    packet_relative = f"control-inputs/dispatches/{packet_id}.json"
    raw, _relative = capsules.read_immutable_session_artifact(
        session_root,
        packet_relative,
    )
    packet = require_exact_keys(
        strict_json(raw, packet_relative),
        PACKET_KEYS,
        "dispatch packet",
    )
    if packet["schema_version"] != DISPATCH_SCHEMA_VERSION:
        raise DispatchError("dispatch packet schema_version is unsupported")
    envelope = packet["envelope"]
    if not isinstance(envelope, dict):
        raise DispatchError("dispatch packet envelope must be an object")
    expected_envelope_keys = BASE_ENVELOPE_KEYS | {
        "context_fingerprint",
        "allowed_artifacts",
    }
    require_exact_keys(envelope, expected_envelope_keys, "dispatch packet envelope")
    base_envelope = validate_base_envelope(
        {key: envelope[key] for key in BASE_ENVELOPE_KEYS}
    )
    state = load_session_state(session_root)
    require_codex_transport_profile(state)
    validate_envelope_identity(base_envelope, session_identity(state))
    if envelope["packet_id"] != packet_id:
        raise DispatchError("dispatch packet id does not match its filename")
    expected_fingerprint = session_validator.expected_context_fingerprint(envelope)
    if envelope["context_fingerprint"] != expected_fingerprint:
        raise DispatchError("dispatch packet context_fingerprint is invalid")

    capsule_meta = require_exact_keys(
        packet["context_capsule"],
        CAPSULE_META_KEYS,
        "dispatch packet context_capsule",
    )
    capsule_digest = capsule_meta["sha256"]
    if (
        not isinstance(capsule_digest, str)
        or len(capsule_digest) != 64
        or any(character not in SHA256_CHARS for character in capsule_digest)
    ):
        raise DispatchError("dispatch packet capsule sha256 is invalid")
    source_budget = capsule_meta["source_char_budget"]
    excerpt_count = capsule_meta["excerpt_chars_total"]
    if (
        isinstance(source_budget, bool)
        or not isinstance(source_budget, int)
        or source_budget < 1024
        or source_budget > capsules.DEFAULT_MAX_CHARS
    ):
        raise DispatchError("dispatch packet capsule source budget is invalid")
    if (
        isinstance(excerpt_count, bool)
        or not isinstance(excerpt_count, int)
        or excerpt_count < 0
        or excerpt_count > source_budget
    ):
        raise DispatchError("dispatch packet capsule excerpt count is invalid")
    expected_capsule_path = (
        session_root.path / "context-capsules" / f"{packet_id}.json"
    )
    if capsule_meta["path"] != str(expected_capsule_path):
        raise DispatchError("dispatch packet capsule path is not canonical")
    try:
        capsules.validate_checkpoint(capsule_meta["checkpoint"])
    except capsules.CapsuleError as error:
        raise DispatchError(str(error)) from error
    expected_allowlist = [str(expected_capsule_path)]
    if envelope["allowed_artifacts"] != expected_allowlist:
        raise DispatchError("dispatch envelope must allow only its capsule")
    if packet["allowed_artifact_paths"] != expected_allowlist:
        raise DispatchError("dispatch transport must allow only its capsule")
    capsule_raw, _capsule_relative = capsules.read_immutable_session_artifact(
        session_root,
        f"context-capsules/{packet_id}.json",
    )
    if hashlib.sha256(capsule_raw).hexdigest() != capsule_digest:
        raise DispatchError("dispatch packet capsule digest does not match")
    capsule = strict_json(capsule_raw, "context capsule")
    require_exact_keys(capsule, CAPSULE_KEYS, "context capsule")
    if capsule["schema_version"] != capsules.CAPSULE_SCHEMA_VERSION:
        raise DispatchError("context capsule schema_version is unsupported")
    if capsule["packet_id"] != packet_id:
        raise DispatchError("context capsule packet id does not match")
    try:
        capsules.validate_checkpoint(capsule["checkpoint"])
    except capsules.CapsuleError as error:
        raise DispatchError(str(error)) from error
    if capsule["checkpoint"] != capsule_meta["checkpoint"]:
        raise DispatchError("context capsule checkpoint metadata does not match")
    if not nonempty_string(capsule["usage"]):
        raise DispatchError("context capsule usage must be non-empty")
    if capsule["source_char_budget"] != source_budget:
        raise DispatchError("context capsule budget metadata does not match")
    if capsule["excerpt_chars_total"] != excerpt_count:
        raise DispatchError("context capsule excerpt metadata does not match")
    sources = capsule["sources"]
    if not isinstance(sources, list) or not sources:
        raise DispatchError("context capsule sources must be a non-empty array")
    excerpt_total = 0
    source_paths: set[str] = set()
    for index, source in enumerate(sources):
        location = f"context capsule sources[{index}]"
        require_exact_keys(source, CAPSULE_SOURCE_KEYS, location)
        try:
            normalized_path = capsules.normalize_session_relative(
                source["path"],
                f"{location}.path",
            ).as_posix()
        except capsules.CapsuleError as error:
            raise DispatchError(str(error)) from error
        if normalized_path in source_paths:
            raise DispatchError(f"{location}.path is duplicated")
        source_paths.add(normalized_path)
        digest = source["sha256"]
        if (
            not isinstance(digest, str)
            or len(digest) != 64
            or any(character not in SHA256_CHARS for character in digest)
        ):
            raise DispatchError(f"{location}.sha256 is invalid")
        source_chars = source["source_chars"]
        excerpt_chars = source["excerpt_chars"]
        if (
            isinstance(source_chars, bool)
            or not isinstance(source_chars, int)
            or source_chars < 0
        ):
            raise DispatchError(f"{location}.source_chars is invalid")
        if (
            isinstance(excerpt_chars, bool)
            or not isinstance(excerpt_chars, int)
            or excerpt_chars < 0
        ):
            raise DispatchError(f"{location}.excerpt_chars is invalid")
        if not isinstance(source["text"], str) or len(source["text"]) != excerpt_chars:
            raise DispatchError(f"{location}.text length does not match")
        if not isinstance(source["truncated"], bool):
            raise DispatchError(f"{location}.truncated must be boolean")
        if excerpt_chars > source_chars:
            raise DispatchError(f"{location} excerpt exceeds source length")
        if not source["truncated"] and excerpt_chars != source_chars:
            raise DispatchError(f"{location} untruncated lengths do not match")
        excerpt_total += excerpt_chars
    if excerpt_total != capsule["excerpt_chars_total"]:
        raise DispatchError("context capsule aggregate excerpt count does not match")
    if excerpt_total > capsule["source_char_budget"]:
        raise DispatchError("context capsule source entries exceed the hard budget")
    if not nonempty_string(packet["role_instructions"]):
        raise DispatchError("dispatch packet role_instructions must be non-empty")
    validate_authorized_search_budget(
        packet["search_budget"],
        envelope["role"],
        envelope,
        state,
        "dispatch packet search_budget",
    )
    validate_role_input_budget(raw, capsule_raw)
    return packet, raw


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Build one immutable final Codex role packet from a session-relative "
            "draft and bounded evidence sources."
        )
    )
    parser.add_argument("session_dir", type=Path)
    parser.add_argument("--draft", required=True)
    parser.add_argument("--checkpoint", required=True)
    parser.add_argument("--artifact", action="append", default=[])
    parser.add_argument("--max-chars", type=int, default=capsules.DEFAULT_MAX_CHARS)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        packet, raw, output = build_dispatch(
            args.session_dir,
            draft_relative_path=args.draft,
            checkpoint=args.checkpoint,
            artifacts=args.artifact,
            max_chars=args.max_chars,
        )
        validate_persisted_packet(args.session_dir, packet["envelope"]["packet_id"])
    except (DispatchError, capsules.CapsuleError, OSError) as error:
        print(f"Codex dispatch build failed: {error}", file=sys.stderr)
        return 2
    print(
        f"Codex dispatch written: {output} sha256={hashlib.sha256(raw).hexdigest()}",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
