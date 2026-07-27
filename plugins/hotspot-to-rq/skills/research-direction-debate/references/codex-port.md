# Codex-native execution port

Use this reference only when the workflow runs in Codex. Codex does not ingest
the Claude-only `agents` or `workflows` manifest fields, so this port reproduces
their sequencing and audit contracts with generic delegated tasks and
deterministic transport artifacts. The session MUST use schema 1.4 with
`transport_profile: CODEX`; every Codex builder, pre-commit gate, manifest
verification, and packet-emission entry point rejects any other profile.

## Enforcement boundary

| Claude Code component | Codex-native mechanism | Enforcement level |
| --- | --- | --- |
| `mainline-controller` bundled agent | One generic delegated task with no parent-context fork; pass the inline controller contract, envelope, and `control_input` only | Model-level instruction. Generic Codex tasks inherit the available tool surface, so this is not a technical tool whitelist. |
| `research-role` / `search-verification` bundled agents | One generic delegated task per final persisted role packet | Model-level role and artifact constraint, followed by envelope and session validation. |
| `dispatch-batch` workflow | Keep available child slots full with independent ready tasks; validate each result separately | Work-conserving orchestrator protocol plus the deterministic pre-commit batch gate below. |
| Post-write hook | Codex hook when attached; otherwise an immediate manual `validate_session.py` run | Hook backstop or model-level preflight, depending on host support. |

Never claim that generic Codex tasks are technically unable to inspect, write,
or search. The controller receives `project_root` as an envelope identity field
and normally inherits the project working directory and runtime tools. It is
instructed to use no tools and receives no evidence or artifact path. A
non-search research role is instructed to read only its capsule. A Search role
may additionally use its bounded web tools. The orchestrator remains
responsible for detecting unexpected output, validating the echoed envelope,
checking repository/session state, and rejecting the work product.

## Long-context profile

Treat a 256K-capable Codex task as a **parent-context budget**, not permission
to copy the full conversation or raw corpus into every role. If the runtime
reports a smaller context, use that actual limit instead.

1. The parent/orchestrator may inspect the broad corpus and maintain session
   state, evidence packs, source ledgers, and decision history.
2. Every non-CONTROL Codex role packet MUST contain one bounded evidence
   capsule. The 160,000-character excerpt cap is only one component limit; it
   is not a token estimate, and `--max-chars` may lower but never raise it.
3. The capsule's canonical absolute path MUST be the only entry in both
   `envelope.allowed_artifacts` and the transport's
   `allowed_artifact_paths`. Original source paths inside the capsule are
   provenance labels only; they MUST NOT be passed to or opened by the child.
4. If a truncated section is decision-critical, the role returns the
   contract's existing unresolved/search-needed status. The orchestrator then
   creates a new focused dispatch with a new packet id. Never mutate or rebuild
   a committed packet.
5. The deterministic builder MUST reject the dispatch unless the persisted
   packet bytes, capsule bytes, and an 8,192-byte transport-framing reserve fit
   the 192,000-byte conservative role-input cap. This UTF-8 byte cap covers
   `role_instructions`, `inline_payload`, search budget, envelope, capsule JSON,
   CJK, and emoji without pretending that character count equals token count.
   If the host reports a smaller context limit, lower `--max-chars` further.
6. Never put the parent chat transcript, hidden reasoning, unrelated files, or
   another role's unaccepted output into a child context.

## Build the final transport packet

After `validate_controller_decision.py` accepts the logical directive, but
before committing its transition to `session-state.json`:

1. Write one session-relative draft at
   `control-inputs/dispatch-drafts/<packet-id>.json`. It contains exactly:
   - `envelope`: the base role identity through `packet_id`, without
     `context_fingerprint` or `allowed_artifacts`;
   - `role_instructions`;
   - `inline_payload`;
   - `search_budget`: `null` for non-search roles; Search roles require the
     exact bounded object enforced by the builder (`profile: standard`, fixed
     grants of 2 query batches, 4 queries per batch, 8 new sources, and only one
     explicitly approved extension of 1 batch / 4 sources). Its
     `large_downloads` entries must be unique, over 10 MiB, explicitly
     approved with a necessity, and no more numerous than the granted source
     quota. Every claimed download and extension approval must exactly match
     `session-state.json.search_budget`; an extension additionally binds an
     accepted Panel Judge packet.
2. Run the builder with only the session artifacts relevant to that role:

```bash
python3 -B <skill-root>/scripts/build_codex_dispatch.py \
  <session-directory> \
  --draft control-inputs/dispatch-drafts/<packet-id>.json \
  --checkpoint <CHECKPOINT> \
  --artifact project-evidence-pack.md \
  --artifact candidate-directions.md
```

The builder reads each source once, derives its excerpt and SHA-256 from the
same bytes, enforces the aggregate character limit, writes the capsule
atomically, inserts its absolute path into the final envelope, recomputes the
context fingerprint, and atomically persists the exact transport packet at
`control-inputs/dispatches/<packet-id>.json`. Packet-id outputs are immutable:
identical rebuilds are no-ops and different bytes require a new packet id.
Immutable files are published without replacement and made owner-read-only as
a defense against accidental mutation.

For evaluation or later debate calls, substitute only relevant existing session
artifacts, such as `experiment-evidence-pack.md`, `result-validation.md`, or
`external-evidence.md`.

After every packet in the logical controller batch has been built, run:

```bash
python3 -B <skill-root>/scripts/validate_codex_dispatch_batch.py \
  <session-directory> \
  <session-relative-controller-output.json> \
  --control-input <session-relative-control-input.json>
```

This gate snapshots state, control input, and controller output; runs the full
controller-decision validator against those same bytes; proves that every
logical dispatch has one matching persisted packet; checks each capsule
checkpoint, digest, and hard budget; and fails if any of the three live inputs
changes before completion. It also archives those three exact inputs and writes
an immutable batch manifest at
`control-inputs/dispatch-batches/<controller-packet-id>.json`, binding every
raw packet and capsule SHA-256. A final read-only `.ready.json` receipt is
published only after the last live-input check succeeds. Only after this gate
passes may the orchestrator commit the controller transition.

## Dispatch and recovery

1. Before the initial dispatch and every transport retry, verify the committed
   batch manifest and its current packet/capsule bytes:

```bash
python3 -B <skill-root>/scripts/validate_codex_dispatch_batch.py \
  <session-directory> \
  --verify-manifest <controller-packet-id> \
  --packet-id <role-packet-id> \
  --emit-packet
```

   The verifier requires the archived directive's matching CONTROL transition
   and CONTROL work product in the current valid session, rejects an already
   accepted/rejected role packet, and emits the exact digest-checked packet
   bytes. Send those captured bytes; do not reopen the packet path after
   validation or reconstruct it from the draft/conversation.
2. Launch ready tasks with a work-conserving scheduler. Fill every currently
   available Codex child slot, then start the next independent ready packet as
   soon as a slot completes. Never force independent work into a fully serial
   schedule, and never exceed the host's slot limit. Use no parent-context fork
   (`fork_turns: none` or the runtime equivalent). Send the final envelope,
   role instructions, inline payload, search budget, and capsule path exactly
   as emitted.
3. Await and process results independently. Verify the unchanged envelope,
   reject malformed output, persist accepted work-product metadata, and run the
   normal session validator. When a Search role exercises an extension, record
   its immutable packet id as `search_usage.search_packet_id`; the validator
   resolves that packet through its committed batch manifest and rejects usage
   not granted by the packet itself.
4. A transport retry revalidates the manifest and emits the same persisted
   packet bytes into a fresh child context. It never reruns either builder. One
   failed sibling leaves only that packet pending.
5. After three transport failures, use the existing single-call
   `DEGRADED_INLINE` recovery. Content rejection remains the separate,
   single-credit `RETRY_ROLE` path.

The deterministic builders and validators protect packet identity, evidence
scope, bounds, and recovery. Immutable packet publication requires secure
POSIX handle-relative no-follow operations held from a root-anchored traversal
through the complete build/gate operation; the binding is rechecked before the
handle is released. The port fails closed where those semantics are
unavailable. These controls do not convert Codex's inherited generic-task tools
into Claude's plugin-level tool whitelist.
