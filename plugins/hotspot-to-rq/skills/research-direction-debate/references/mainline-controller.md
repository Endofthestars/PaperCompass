# Mainline Workflow Controller

## Purpose and authority

Run one Mainline Workflow Controller lane for each session. It is a bounded
control-plane agent: it checks protocol prerequisites, chooses the next legal
workflow state, and schedules the next independent role batch.

The main agent remains the only Orchestrator. Only the Orchestrator may inspect
raw project material, call tools, write files, accept or reject work products,
change session state, communicate with the user, or present a final decision.
The controller proposes one directive; the Orchestrator validates and commits
or rejects it.

The controller must not:

- decide scientific merit or rewrite a Panel Judge verdict
- infer a user's preference, risk tolerance, deadline, or resources
- override a Critical stop, validator failure, user gate, or budget limit
- read paper text, experiment logs, search-result text, hidden role reasoning,
  or the full user/Orchestrator conversation
- invoke tools, edit artifacts, message research roles, or address the user

A runtime that cannot launch a tool-less agent may grant the controller one
metadata-only tool (for example a path lister) so the lane can start; invoking
any granted tool remains a contract violation.

## Lifecycle and isolation

Create the controller after `session-state.json` is initialized and before the
first research-role call. Start it with a clean context. Reuse it only inside
the `(session_id, null, Mainline Workflow Controller)` lane.

Every call carries a complete authoritative control input. If remembered
context conflicts with that input, the input wins. Never reuse the lane for
another session or project.

Use `phase: CONTROL`, `role: Mainline Workflow Controller`,
`candidate_id: null`, and `round: null` in the standard role envelope. Add
`control_revision`, equal to `mainline_control.revision`, `state_digest`, and
`control_input_digest`, the SHA-256 of the exact companion `control-input.json`
bytes, to the envelope. For a CONTROL work product, include all three fields in
the compact JSON used to compute `context_fingerprint`.
Set `allowed_artifacts` to an empty array; send `control_input` as the only
inline payload after the envelope.

## Control input

Pass only a compact scheduling snapshot:

```yaml
control_input:
  control_revision: 7
  state_digest: <lowercase sha256 of current session-state.json bytes>
  observed_status: DEBATING
  mode: discover
  interaction_mode: GUIDED
  checkpoint: ROUND_BOUNDARY
  completed_packet_ids: [<every accepted research packet ID>]
  failed_packets: []
  active_lanes:
    - phase: DEBATE
      candidate_id: C01
      round: 3
      last_resolved_role: null
      next_role: Socratic Mentor
      dependency_packet_ids: [C01-R2-JUDGE]
      search_required: false
      lane_revision: 7
  accepted_verdicts:
    - candidate_id: C01
      round: 2
      verdict: CONTINUE
  artifact_readiness:
    PROJECT_EVIDENCE_PACK: READY
    DIRECTION_MAP: NOT_READY
  latest_validation:
    result: NOT_RUN
    error_codes: []
  budget_flags: []
  unresolved_blockers: []
  user_event:
    kind: NONE
    receipt_id: null
    selected_ids: []
  allowed_target_statuses: [DEBATING, USER_GATE, BLOCKED]
```

Build this snapshot with `scripts/build_control_input.py` rather than by hand:
it derives the projected fields below with the validators' own functions,
writes `control-input.json` and `control-inputs/<packet>.json` byte-identically,
and prints the sha256 digest for the envelope's `control_input_digest`.

`completed_packet_ids`, `failed_packets`, `active_lanes`, and
`accepted_verdicts` are exact projections of persisted state, not controller
claims. A failed packet also includes its original `phase`, `candidate_id`, and
`round` (null where applicable), so a retry is self-contained. Each active lane
contains the exact next role and already accepted dependency packet IDs.
Every dependency in a proposed dispatch must appear in
`completed_packet_ids`; every ready debate lane must be represented in the same
controller batch. The immutable archived snapshot is checked against these
relations during full-session validation.
`WAIT_FOR_RESULT` means a committed call is unresolved; `COMMIT_ROUND` means the
Judge returned and the Orchestrator must persist the round delta before invoking
`ROUND_BOUNDARY`.

Use only IDs, counts, verdicts, validation results, budget flags, and reason
codes. Summarize a user reply as its event kind and explicit selected IDs or
constraint codes; do not forward conversational prose.

Persist every bounded search trigger in
`mainline_control.lane_search_requests`:

```json
{
  "phase": "DEBATE",
  "candidate_id": "C01",
  "round": 2,
  "source_packet_id": "C01-R2-DEVIL",
  "reason_codes": ["PIVOTAL_CLAIM_UNVERIFIED"]
}
```

The source must be the accepted same-lane Devil's Advocate packet. Requests are
append-only audit events, unique per lane and round. They make
`active_lanes.search_required` deterministic: the next role is Search, then one
explicitly superseding Evidence revision, then Judge.

Use uppercase artifact names as `artifact_readiness` keys and only
`READY|NOT_READY|STALE|UNRESOLVED` as values. Include every artifact required
for the proposed transition; treat an absent key as `NOT_READY`.
In particular, Direction Mapping requires `PROJECT_EVIDENCE_PACK: READY`;
evaluation Evidence Intake requires `EVALUATION_INPUT_SNAPSHOT: READY`; Result
Validation requires `EXPERIMENT_EVIDENCE_PACK: READY`. Never mark an output
artifact ready merely to authorize the role that creates it.

## Control directive

Require strict JSON with exactly this shape after the unchanged echoed
envelope:

```json
{
  "envelope": "<unchanged echoed envelope>",
  "control_directive": {
    "observed_revision": 7,
    "observed_state_digest": "<lowercase sha256>",
    "observed_status": "DEBATING",
    "checkpoint": "ROUND_BOUNDARY",
    "action": "ADVANCE",
    "target_status": "DEBATING",
    "pending_user_gate": null,
    "dispatches": [
      {
        "packet_id": "C01-R3-MENTOR",
        "phase": "DEBATE",
        "role": "Socratic Mentor",
        "candidate_id": "C01",
        "round": 3,
        "depends_on_packet_ids": ["C01-R2-JUDGE"]
      }
    ],
    "required_actions": [],
    "required_checks": ["PERSIST_STATE", "VERIFY_ENVELOPES", "ENFORCE_BUDGET"],
    "reason_codes": ["NEXT_ROUND_READY"],
    "blocking_reasons": [],
    "retry_key": null
  }
}
```

Allowed actions are:

- `ADVANCE`: enter a legal state and perform at least one dispatch or
  deterministic action.
- `HOLD_FOR_USER`: enter or remain at a user gate, dispatch nothing, and require
  `RUN_SESSION_VALIDATOR`.
- `REPAIR_STATE`: dispatch nothing and name the deterministic state/artifact
  repairs required before proceeding. It may use only
  `REPAIR_ARTIFACT_METADATA` and `REPAIR_SESSION_STATE`.
- `RETRY_ROLE`: schedule exactly one fresh-context retry for a recorded rejected
  packet named by `retry_key`. The new dispatch must preserve the original
  phase, role, candidate, and round. Each logical call may be retried at most
  once: do not retry a retry packet or reschedule a rejected call with
  `ADVANCE`. `RETRY_ROLE` answers content rejections only; a transport failure
  is not a rejection and does not consume this credit (see Transport failures
  under Failure and fallback).
- `BLOCK_SESSION`: set the target to `BLOCKED`, dispatch nothing, and preserve
  explicit blocking reason codes.
- `COMPLETE`: set the target to `COMPLETE`, dispatch nothing, and require
  `RUN_SESSION_VALIDATOR`.

Every directive must include `PERSIST_STATE` in `required_checks`. A directive
with dispatches must also include `VERIFY_ENVELOPES` and `ENFORCE_BUDGET`.
Use uppercase machine codes for required actions, checks, reasons, and blocking
reasons; keep explanatory prose in the Orchestrator's audit artifacts.

The only required actions are `BUILD_PROJECT_EVIDENCE_PACK`,
`BUILD_EVALUATION_INPUT_SNAPSHOT`, `APPLY_USER_DIRECTION_SELECTION`,
`APPLY_PANEL_DIRECTION_SELECTION`, `APPLY_CANDIDATE_SELECTION`,
`APPLY_RQ_CONFIRMATION`, `APPLY_RQ_REVISION`,
`APPLY_EVALUATION_DECISION`, `APPLY_USER_REPAIR`, `REPAIR_ARTIFACT_METADATA`,
`REPAIR_SESSION_STATE`, and
`RECORD_UNRESOLVED_BLOCKER`. The only checks are `PERSIST_STATE`,
`VERIFY_ENVELOPES`, `ENFORCE_BUDGET`, `RUN_SESSION_VALIDATOR`,
`VERIFY_GATE_RECEIPT`, and `VERIFY_PREREQUISITES`. Validators reject unknown or
inapplicable codes; action names are not an extension point.

Use these pending gate values:

- `DIRECTION_SELECTION` at `DIRECTION_GATE`
- `CANDIDATE_SELECTION` at `USER_GATE`
- `RQ_CONFIRMATION` while holding in `RQ_REFINEMENT`
- `EVALUATION_DECISION` at `DECISION_GATE`
- `null` for every non-user action

`BLOCK_SESSION` is a fail-closed user boundary but is not a pending gate:
`pending_user_gate` remains `null`. The Orchestrator records the direct reply as
a `BLOCKER_DECISION` receipt based on the `BLOCK_SESSION` revision that first
entered `BLOCKED` in the current episode. `REPAIR` binds its `values` to that
transition's `from_status`; `STOP` uses an empty array and leaves the session
status and control revision unchanged. Only a `REPAIR` receipt permits a later
`RECOVERY`/`RESUME` directive to advance from `BLOCKED` back to that status.
Once blocked, do not append another `BLOCK_SESSION`; wait for the direct
blocker reply. A `STOP` receipt changes the state bytes but leaves the session
status and control revision unchanged.

Dispatch only roles whose dependencies are already accepted. Put independent
candidate lanes in the same directive so the Orchestrator can run them in
parallel. Never put dependent Mentor, Evidence, Devil's Advocate, and Judge
steps in the same batch. At a debate boundary, every dispatch must match the
authoritative lane's `next_role` and include its `dependency_packet_ids`. After
an accepted same-round Search, allow exactly one Evidence Researcher
supersession with reason `SUPERSEDE_ACCEPTED_CALL` and dependencies on the
original Evidence and Search packets. Other accepted debate calls cannot be
replayed. An accepted non-debate call may be superseded only with the same
reason code and a dependency on the latest accepted packet.

Dispatch phases are constrained by the directive's target status:

| Target status | Schedulable phases |
|---|---|
| `SCANNING` | `DIRECTION_MAPPING`, `DIRECTION_SELECTION` |
| `CANDIDATE_GENERATION` | `DIRECTION_SELECTION`, `HOTSPOT`, `SCREENING` |
| `DEBATING` | `SCREENING`, `DEBATE`, `IDENTIFICATION`, `FINAL_SELECTION` |
| `RQ_REFINEMENT` | `RQ_REFINEMENT` |
| `EVIDENCE_INTAKE` | `EVIDENCE_INTAKE` |
| `RESULT_VALIDATION` | `RESULT_VALIDATION` |
| `EXTERNAL_POSITIONING` | `EXTERNAL_POSITIONING` |
| `EVALUATION_DEBATE` | `EVALUATION_DEBATE`, `EVALUATION_DECISION` |
| `NEXT_EXPERIMENT` | `NEXT_EXPERIMENT` |
| any gate, `BLOCKED`, or `COMPLETE` | none |

The Experiment Auditor is additionally blocked until direction, primary claim,
and study type are non-empty. Accepted and rejected packet coordinates must
match their originating dispatch.

## Checkpoints and call policy

Call the controller at stable boundaries, not between every ordinary role:

- `SESSION_INIT`: after state initialization and before the first research role
- `PHASE_BOUNDARY`: after a phase's required role batch is accepted
- `ROLE_BOUNDARY`: after at least one role dispatched since the previous
  `PHASE_BOUNDARY`, `ROLE_BOUNDARY`, or `ROUND_BOUNDARY` resolves (a pending
  recovery retry batch does not hide resolved sibling lanes); use it to
  schedule the next dependency-safe role across ready lanes
- `ROUND_BOUNDARY`: after all current-lane Judges return for a round
- `PRE_USER_GATE`: immediately before any user-facing gate
- `POST_USER_GATE`: after the Orchestrator records the user's explicit reply
- `RECOVERY`: after validator failure, rejected role output, budget exhaustion,
  or a Critical stop
- `RESUME`: before doing new work in a resumed session
- `PRE_COMPLETE`: before declaring the session complete

The controller may schedule multiple independent calls at one boundary. The
Orchestrator must still create and validate a separate role envelope for each
dispatch.

`SESSION_INIT` is mandatory at revision 0 and illegal later. `RESUME` requires
existing schema-1.3 control history. `POST_USER_GATE` must immediately consume
the direct receipt for the current hold; while a gate has no reply, leave its
revision unchanged and do not call the controller again. `PRE_USER_GATE` must
produce `HOLD_FOR_USER`, and `PRE_COMPLETE` must produce `COMPLETE`.

Coalesce adjacent boundaries when no state, receipt, verdict, failure, or budget
event occurred between them. For example, use one `PRE_USER_GATE` call instead
of a `PHASE_BOUNDARY` call immediately followed by `PRE_USER_GATE`; use
`PRE_COMPLETE` instead of a redundant final `PHASE_BOUNDARY`. Never call the
controller twice with the same revision and state digest merely to rename the
checkpoint.

At `SESSION_INIT`, discovery/refinement modes perform only
`BUILD_PROJECT_EVIDENCE_PACK`; evaluation performs only
`BUILD_EVALUATION_INPUT_SNAPSHOT`. Do not dispatch a role in the same
transition. The evaluation snapshot resolves the target and creates the initial
inventory shell; the Experiment Auditor then produces the full experiment
evidence pack.

`ROLE_BOUNDARY` and `ROUND_BOUNDARY` are valid only in `DEBATING` or
`EVALUATION_DEBATE`. A round boundary requires accepted Judge packets for the
latest batch and no unresolved research dispatches. The exact `active_lanes`
projection prevents one lane from advancing around a lagging lane. At
`ROLE_BOUNDARY`, continue every ready current-round lane, while
`COMMIT_ROUND` lanes and next-round Mentor lanes wait; this lets a lagging lane
finish without starting a new round elsewhere. Invoke `ROUND_BOUNDARY` only
after every continuing lane projects its next-round `Socratic Mentor`, then
coalesce all of those Mentor calls in that batch. RQ refinement is a clean
`Research Question Architect` pass followed by `RQ_CONFIRMATION`; it does not
reuse the capped candidate-debate rounds.

An RQ `CONFIRM` receipt has exactly two `values`: the selected candidate ID and
the accepted Research Question Architect packet ID that was shown to the user.
Consume it with one no-dispatch `POST_USER_GATE` `ADVANCE` that stays in
`RQ_REFINEMENT` and requires exactly `APPLY_RQ_CONFIRMATION`. The only legal
next controller transition is `PRE_COMPLETE`/`COMPLETE`. A `REVISE` receipt has
empty `values`; consume it with exactly `APPLY_RQ_REVISION` and one fresh
Research Question Architect dispatch that supersedes and depends on the prior
RQ packet. Do not reopen `RQ_CONFIRMATION` until that replacement is resolved
and is the latest accepted RQ dispatch. A result accepted only after the HOLD
snapshot is not the version shown to the user and cannot satisfy its receipt.
Never dispatch or supersede RQ refinement after confirmation.

## Commit protocol

The Orchestrator must reject a directive unless:

1. the echoed role envelope matches, including `control_revision`
2. `observed_state_digest` equals the digest sent to the controller and the
   current state bytes still have that digest
3. `observed_revision` equals the revision sent to the controller
4. `observed_status` equals the state sent to the controller
5. `target_status` is allowed by the mode-specific state graph
6. action, gate, dispatch, retry, and required-check constraints are satisfied
7. any user event names a gate receipt written from a direct user reply
8. the directive does not override a user choice, Judge verdict, Critical stop,
   validator result, or budget

After acceptance, the Orchestrator:

1. records the CONTROL work product
2. preserves the exact input at
   `control-inputs/<CONTROL packet ID>.json` and records that relative path
3. increments `mainline_control.revision` by exactly one
4. appends the committed directive to `transition_log`
5. stages status, artifact metadata, gate receipts, and the mainline summary
   fields together
6. runs the full session validator on every staged snapshot
7. atomically commits a valid snapshot
8. executes the deterministic actions and independent dispatch batch

The persisted session status must equal the last transition's `to_status`.
Never execute a stale directive even if its proposed next step looks correct.
Every accepted or rejected research packet must resolve a packet ID from a
committed controller dispatch. Do not upgrade schema 1.1 or 1.2 history in
place; start a new schema-1.3 session and reference the legacy artifacts from
its evidence pack.

## Failure and fallback

Reject stale, contaminated, illegal, or out-of-scope controller output using a
CONTROL rejection reason. Retry once in a fresh context with the same
authoritative control snapshot.

After a second controller failure, set `controller_status` to
`DEGRADED_FALLBACK`. Run the deterministic protocol checklist in the
Orchestrator rather than impersonating an independent controller. Record the
fallback control product as role `Deterministic Mainline Fallback`.

At a user gate, Critical stop, or completion boundary, fail closed: do not
present the gate or claim completion until all protocol checks and
`validate_session.py` pass. If deterministic recovery cannot establish that,
set or remain at `BLOCKED` and report the exact blocker.

Research-role failure remains separate. The controller may schedule one
fresh-context retry, but it may not repair or substitute the role's answer.

### Transport failures

At commit time, before invoking any delegation vehicle, persist every
dispatch's complete role envelope and inline payload to
`control-inputs/dispatches/<packet id>.json` inside the session directory.
Re-invocation and cross-session resume rebuild the call from that file —
never from the conversation transcript or a runtime-scoped workflow run id,
which do not survive the session.

A dispatch whose agent dies in the harness — API overload, timeout,
session-limit termination, or a killed subagent — is a transport failure, not
a rejected work product. The committed dispatch stays pending:

- Do not record the failure in `rejected_work_products`, and do not spend the
  single `RETRY_ROLE` credit on it. Re-invoking the identical dispatch is the
  same logical call, not a retry.
- Re-invoke the identical dispatch (same envelope, fresh context) up to three
  total attempts, backing off between attempts. Switching the delegation
  vehicle — bundled agent type, generic delegation tool, or another model —
  is allowed and does not change the packet's identity.
- After the third failed attempt, list the packet in the control input's
  `failed_packets`, run a `RECOVERY` checkpoint, and execute that single role
  call inline in the Orchestrator. Label the work product `DEGRADED_INLINE`
  and disclose the degradation to the user before presenting anything built
  on it. A single-call degradation does not switch the session to inline mode
  and does not touch `controller_status`.
- If inline execution is also impossible (for example a Search role without
  network access), mark the packet unresolved: a missing Search continues the
  lane with its claims recorded as `UNRESOLVED`, while a missing Mentor,
  Evidence Researcher, Devil's Advocate, or Judge blocks that lane — use
  `BLOCK_SESSION` when no other lane can proceed.
