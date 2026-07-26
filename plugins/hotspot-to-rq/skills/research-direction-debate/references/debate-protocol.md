# Internal Socratic Debate Protocol

## Contents

1. Session initialization
2. Machine-readable state
3. Mainline control plane
4. Macro direction mapping, gate, or existing-experiment intake
5. Candidate selection, lineage, or evaluation target
6. Round sequence
7. Search triggers and budgets
8. Evidence ledger
9. Identification or experiment-validity gate
10. Convergence and transitions
11. User gates
12. Artifacts and validation
13. Failure paths

## Session initialization

Create `reports/research-direction/<session-id>/` without overwriting another
session. In `discover`, `refine`, or `rq-only`, initialize these files before
delegation:

- `session-state.json`
- `project-evidence-pack.md`
- `direction-map.md`
- `candidate-directions.md`
- `debate-transcript.md`
- `external-evidence.md`
- `decision-packet.md`

Begin every Markdown artifact with:

```yaml
---
session_id: <same id as the directory and state file>
artifact: <exact filename>
status: <current session status>
updated_at: <ISO date-time>
---
```

For `evaluate`, initialize instead:

- `session-state.json`
- `experiment-evidence-pack.md`
- `result-validation.md`
- `claim-evidence-matrix.md`
- `evaluation-debate.md`
- `external-positioning.md`
- `evaluation-decision.md`

Update all metadata headers at each checkpoint. Create `rq-brief.md` only after
the user confirms the final RQ in non-evaluation modes. Create
`next-experiment-plan.md` only after an evaluation decision.

## Machine-readable state

Use UTF-8 JSON, schema version `1.3`, and keep it valid after every committed
transition. The validator continues to accept legacy `1.1` and `1.2` sessions;
do not create a new legacy session. Regardless of schema version,
`session-state.json` must be strict UTF-8 JSON: no byte-order mark, duplicate
object keys, or non-finite numbers.
Required top-level fields:

```text
schema_version
session_id
mode
interaction_mode
execution_mode
project_root
project_snapshot
status
min_rounds
default_rounds
max_rounds
macro_directions
selected_macro_direction_ids
direction_selection
generated_candidate_ids
initial_debate_candidate_ids
user_gate_candidate_ids
selected_candidate_id
candidates
source_ledger
search_budget
accepted_work_products
rejected_work_products
mainline_control
gate_receipts
user_required
updated_at
```

`evaluate` sessions additionally require:

```text
evaluation_target
experiment_inventory
claim_evidence_matrix
evaluation_rounds
evaluation_decision
next_experiment
```

Use:

- `mode`: `discover|refine|rq-only|evaluate`
- `interaction_mode`: `GUIDED|AUTONOMOUS`
- `execution_mode`: `MULTI_AGENT|DEGRADED_INLINE`
- non-evaluation `status`: `SCANNING|DIRECTION_GATE|CANDIDATE_GENERATION|DEBATING|USER_GATE|RQ_REFINEMENT|COMPLETE|BLOCKED`
- evaluation `status`: `EVIDENCE_INTAKE|RESULT_VALIDATION|EXTERNAL_POSITIONING|EVALUATION_DEBATE|DECISION_GATE|NEXT_EXPERIMENT|COMPLETE|BLOCKED`
- `min_rounds`: `3`
- `default_rounds`: `4`
- `max_rounds`: `6`

Initialize control fields before the first delegated call:

```json
{
  "mainline_control": {
    "controller_id": "MAINLINE",
    "controller_status": "ACTIVE",
    "revision": 0,
    "last_checkpoint": null,
    "pending_user_gate": null,
    "last_controller_packet_id": null,
    "retry_counts": {},
    "lane_search_requests": [],
    "transition_log": []
  },
  "gate_receipts": []
}
```

Before dispatching an ARS-mapped role, read the corresponding bundled prompt
from `ars-bridge.md`; no separately installed ARS dependency is required.

Revision 0 is a bootstrap state. It is valid only at `SCANNING` for
non-evaluation modes or `EVIDENCE_INTAKE` for evaluation, before any accepted
work product. The first `SESSION_INIT` transition has no role dispatch and runs
exactly `BUILD_PROJECT_EVIDENCE_PACK` outside evaluation mode, or
`BUILD_EVALUATION_INPUT_SNAPSHOT` in evaluation mode. The evaluation action
resolves the target and initial inventory shell; the Experiment Auditor creates
the full experiment evidence pack afterward. Commit this transition before
calling a research role.

Default `interaction_mode` to `GUIDED`. Use `AUTONOMOUS` only when the user
explicitly asks the panel to select broad directions without an early pause.

Each macro direction must contain:

```json
{
  "direction_id": "D01",
  "title": "Agent reliability and long-horizon state",
  "scope": "Reliability, memory, context, and evaluation for tool-using agents",
  "local_signals": [],
  "plausible_contribution_types": [],
  "indicative_cost": "medium",
  "indicative_risk": "high",
  "uncertainty": [],
  "panel_note": "Strong local momentum; novelty remains unchecked",
  "status": "PROPOSED"
}
```

Use macro-direction statuses:

- `PROPOSED`: available at the early direction gate
- `SELECTED`: chosen for detailed candidate generation
- `NOT_SELECTED`: retained in the audit trail but not expanded

Before direction selection, use:

```json
{
  "selected_macro_direction_ids": [],
  "direction_selection": null
}
```

After selection, store:

```json
{
  "selected_macro_direction_ids": ["D01"],
  "direction_selection": {
    "selected_by": "USER",
    "selected_at": "2026-07-23T17:00:00+08:00",
    "rationale": "User selected D01"
  }
}
```

Use `selected_by`:

- `USER`: the user chose from the displayed map
- `PANEL_DELEGATED`: the user saw the map and asked the panel to choose
- `PANEL_AUTONOMOUS`: explicit `AUTONOMOUS` mode
- `PRESEEDED`: refine/RQ-only input already fixed the broad area

In `evaluate`, do not use macro directions, selected macro direction IDs, or a
direction selection. Keep `macro_directions`, `selected_macro_direction_ids`,
and all candidate fields empty. The supplied `evaluation_target.direction` is
the preseeded subject of analysis, not a new candidate.

Each candidate object must contain:

```json
{
  "candidate_id": "C01",
  "macro_direction_id": "D01",
  "origin": "GENERATED",
  "parent_id": null,
  "status": "ACTIVE",
  "gate_ready": false,
  "rounds_completed": 0,
  "rounds": [],
  "early_exit_reason": null,
  "identification_audit": null
}
```

Use candidate statuses:

- `SCREENED_OUT`: generated locally but not selected for debate
- `ACTIVE`: currently debated
- `READY_FOR_GATE`: converged and eligible after identification audit
- `DOWNGRADED`: a derived, narrower candidate with explicit lineage
- `DEFERRED`: potentially useful but blocked by a current user-owned constraint
- `ELIMINATED`: terminal; never reactivate the same ID
- `SELECTED`: chosen by the user

Each round object must contain:

```json
{
  "round": 1,
  "verdict": "CONTINUE",
  "confidence": "medium",
  "search_usage": {
    "query_batches": 0,
    "queries": 0,
    "sources_inspected": 0,
    "budget_extension": null
  }
}
```

Store confidence only as `low`, `medium`, or `high`. Do not store numeric or
decimal confidence anywhere in session state.

An `evaluate` session stores its target and evidence state as follows:

```json
{
  "evaluation_target": {
    "direction": "Existing research direction",
    "primary_claim": "Claim under evaluation",
    "study_type": "code",
    "constraints": []
  },
  "experiment_inventory": [
    {
      "experiment_id": "E01",
      "hypothesis": "What this experiment tested",
      "artifact_paths": ["results/run-01.json"],
      "outcome_summary": "Observed outcome only",
      "status": "OBSERVED"
    }
  ],
  "claim_evidence_matrix": [
    {
      "claim_id": "CL01",
      "claim": "The exact claim being evaluated",
      "evidence_ids": ["E01"],
      "support_status": "PARTIALLY_SUPPORTED",
      "limitations": []
    }
  ],
  "evaluation_rounds": [
    {
      "round": 1,
      "verdict": "CONTINUE",
      "confidence": "medium",
      "search_usage": {
        "query_batches": 0,
        "queries": 0,
        "sources_inspected": 0,
        "budget_extension": null
      }
    }
  ],
  "evaluation_decision": null,
  "next_experiment": null
}
```

At `EVIDENCE_INTAKE` only, a missing `direction`, `primary_claim`, or
`study_type` may be an empty string when `user_required` contains the matching
code `EVALUATION_DIRECTION`, `PRIMARY_CLAIM`, or `STUDY_TYPE`. Ask for that
smallest clarification before calling the Experiment Auditor. All three fields
must be non-empty before `RESULT_VALIDATION`.

Initialize the top-level search budget as:

```json
{
  "profile": "standard",
  "large_downloads": []
}
```

Record every accepted role output in `accepted_work_products`:

```json
{
  "packet_id": "C01-R1-MENTOR",
  "phase": "DEBATE",
  "role": "Socratic Mentor",
  "session_id": "20260723-160000",
  "project_root": "/absolute/project",
  "project_snapshot": "snapshot-id",
  "candidate_id": "C01",
  "round": 1,
  "context_fingerprint": "<lowercase sha256>"
}
```

Copy identity fields from the echoed role envelope. The validator recomputes the
fingerprint and checks phase-specific role coverage.

Record an accepted agent controller output with `phase: CONTROL`, role
`Mainline Workflow Controller`, null candidate and round, plus
`control_revision`, `state_digest`, and `control_input_digest`:

```json
{
  "packet_id": "CTRL-0001",
  "phase": "CONTROL",
  "role": "Mainline Workflow Controller",
  "session_id": "20260723-160000",
  "project_root": "/absolute/project",
  "project_snapshot": "snapshot-id",
  "candidate_id": null,
  "round": null,
  "control_revision": 0,
  "state_digest": "<lowercase sha256>",
  "control_input_digest": "<lowercase sha256>",
  "context_fingerprint": "<lowercase sha256>"
}
```

For a deterministic fallback, use the same shape with role
`Deterministic Mainline Fallback`.

## Mainline control plane

Read `mainline-controller.md` before invoking the controller. Persist each
accepted directive as one transition:

```json
{
  "revision": 1,
  "observed_revision": 0,
  "packet_id": "CTRL-0001",
  "observed_state_digest": "<lowercase sha256>",
  "control_input_digest": "<lowercase sha256>",
  "control_input_path": "control-inputs/CTRL-0001.json",
  "checkpoint": "SESSION_INIT",
  "from_status": "SCANNING",
  "action": "ADVANCE",
  "to_status": "SCANNING",
  "pending_user_gate": null,
  "dispatches": [],
  "required_actions": ["BUILD_PROJECT_EVIDENCE_PACK"],
  "required_checks": ["PERSIST_STATE"],
  "reason_codes": ["SESSION_INITIALIZED"],
  "blocking_reasons": [],
  "retry_key": null,
  "recorded_at": "2026-07-25T12:00:00+08:00"
}
```

The committed state must satisfy all of these:

- revisions begin at 1 and are consecutive
- `observed_revision` is exactly `revision - 1`
- every transition's `from_status` equals the prior transition's `to_status`
- top-level control revision equals the transition count
- the last packet, checkpoint, pending gate, and state status match the last
  transition
- accepted CONTROL packets and transition packet IDs form a one-to-one set
- the CONTROL packet's `control_revision`, `state_digest`, and
  `control_input_digest` match the transition's observed values
- `control_input_path` is exactly `control-inputs/<CONTROL packet ID>.json`;
  the file exists, has the recorded digest, uses the strict control-input
  schema, and binds the transition's revision, state, status, mode, and
  checkpoint

Only `HOLD_FOR_USER` may set a pending gate. Use `REPAIR_STATE` or
`RETRY_ROLE` as a same-status transition. A retry must reference one recorded
rejected packet, preserve its original phase/role/candidate/round, and may occur
once for that logical call; a retry packet cannot start another retry chain.
`BLOCK_SESSION` targets `BLOCKED`; `COMPLETE` targets `COMPLETE`.

Stage a proposed controller transition, state update, and artifact metadata
together. Validate the controller output, then validate the staged session.
Replace live state only when both pass. At user gates and completion, fail
closed rather than committing a half-valid state.

Before every controller call, write an immutable per-revision control snapshot
(for example `control-inputs/CTRL-0007.json`) and copy those exact bytes to the
companion `control-input.json` used by the runtime validator. Hash the bytes into
the CONTROL envelope and committed transition. The snapshot contains exact
accepted/failed packet projections, active-lane next roles and dependencies,
persisted verdicts, readiness, receipts, blockers, and legal target statuses.

Do not upgrade a legacy `1.1` or `1.2` session in place. Start a new `1.3`
session, reference the legacy artifact paths in the evidence pack, and route
through `SESSION_INIT`; this avoids inventing controller dispatches for old work
products. Use `RESUME` only when a session already has non-empty, valid `1.3`
control history.

## Macro direction mapping and gate

In `discover` mode:

1. Let a clean Macro Direction Mapper generate 4-6 distinct areas from local
   evidence.
2. Preserve breadth across research objects, contribution families, or
   execution settings.
3. Write every area to `direction-map.md` and `macro_directions`.
4. Make no novelty claim and do no candidate-level external search.

In `GUIDED`:

1. Set status to `DIRECTION_GATE`.
2. Keep all macro directions `PROPOSED`.
3. Keep `selected_macro_direction_ids`, `generated_candidate_ids`,
   `initial_debate_candidate_ids`, and `candidates` empty.
4. Validate the session.
5. Present the complete map in chat.
6. Ask the user to select 1-2 direction IDs, request a panel default, or ask for
   one revised map.
7. Stop. Do not generate detailed candidates or begin debate until the user
   answers.

After a user selection, mark 1-2 directions `SELECTED`, mark the remainder
`NOT_SELECTED`, record `direction_selection`, set status to
`CANDIDATE_GENERATION`, and continue. This intermediate state may be checkpointed
before or after the Hotspot Analyst returns. Set `DEBATING` only after detailed
candidate screening is complete.

When the user delegates the choice, record `DIRECTION_SELECTION/DELEGATE`,
return to `SCANNING`, and dispatch a fresh `DIRECTION_SELECTION` Panel Judge.
Only after that accepted product identifies 1-2 directions may the Orchestrator
record `PANEL_DELEGATED` and advance to `CANDIDATE_GENERATION`.

In explicit `AUTONOMOUS`, use a fresh `DIRECTION_SELECTION` Panel Judge to
select 1-2 directions, record `PANEL_AUTONOMOUS`, and continue without pausing.

In refine/RQ-only mode, seed 1-6 macro directions. When the user's existing
direction is already explicit, mark it selected with `PRESEEDED` and skip the
early gate.

The macro map is an orientation aid. It must show:

- title and scope
- local hotspot signals
- plausible contribution types
- indicative cost and risk
- unresolved uncertainty
- a short panel note

Do not hide any proposed macro direction because the panel personally prefers
another one.

## Existing-experiment evaluation path

Use `evaluate` only when the user gives an existing direction and asks to assess
completed or in-progress experiments, results, logs, code, data, or accumulated
evidence. It is not a shortcut for inventing a new topic.

1. Set status to `EVIDENCE_INTAKE` and write a preseeded `evaluation_target`.
   Keep macro directions, candidates, and candidate-selection fields empty.
2. Have an Experiment Auditor create the complete experiment inventory. Include
   negative, failed, and incomplete runs when their artifacts are available.
3. Before moving to `RESULT_VALIDATION`, require at least one inventory entry
   and one claim-evidence row. The claim matrix must distinguish `SUPPORTED`,
   `PARTIALLY_SUPPORTED`, `CONTRADICTED`, and `INSUFFICIENT_EVIDENCE`.
4. In `RESULT_VALIDATION`, obtain independent Statistical Reviewer and
   Reproducibility Auditor products. A local rerun is optional and requires
   separate user authorization; absent a rerun, record `ARTIFACT_INSPECTED` or
   `UNRESOLVED`, never `LOCALLY_REPRODUCED`.
5. In `EXTERNAL_POSITIONING`, perform bounded external search for direct prior,
   current benchmark conventions, contradictory evidence, and contribution risk.
   Local validity findings must not be overwritten by popularity or publication
   volume.
6. In `EVALUATION_DEBATE`, complete at least three rounds before the decision
   gate. Recommended themes are: claim support; validity and robustness;
   contribution and external positioning; then the smallest decision-changing
   next step. Use the same Mentor -> Evidence Researcher -> Devil's Advocate ->
   search/repair -> fresh Judge sequence, but with a null candidate ID.
7. In `DECISION_GATE`, record exactly one decision:
   `CONTINUE`, `REPAIR`, `PIVOT`, `STOP`, or `INSUFFICIENT_EVIDENCE`. Present
   the evidence, strongest objection, uncertainty, and what could change the
   decision. Do not continue to substantial new experimentation without the
   user's confirmation.
8. In `NEXT_EXPERIMENT`, have an Experiment Planner specify exactly one minimum
   information-gain experiment. For `STOP`, the plan must explicitly state that
   no further experiment is recommended and why.

An evaluation decision is valid only when it contains:

```json
{
  "verdict": "REPAIR",
  "confidence": "medium",
  "rationale": "Concise evidence-grounded rationale",
  "decisive_evidence": [],
  "strongest_objection": "Most important unresolved challenge",
  "unresolved": [],
  "next_action": "One smallest action"
}
```

The next-experiment object must contain:

```json
{
  "action": "RUN",
  "question": "Decision-changing question",
  "design": "Minimal design",
  "expected_outcomes": [],
  "decision_rule": "How results change the decision",
  "resource_requirements": [],
  "stop_condition": "When to stop"
}
```

Use `action: NONE` only for `STOP`. Do not turn a long wishlist of ablations
into the next experiment; choose the smallest test that can change the current
decision.

## Candidate selection and lineage

Generate detailed candidates only inside selected macro directions:

- `GUIDED` discover mode: 3-6 candidates
- `AUTONOMOUS` discover mode: 5-8 candidates
- refine/RQ-only mode: 1-8 seeded or generated candidates

Attach every generated candidate to exactly one selected
`macro_direction_id`. Let a fresh Panel Judge select at most three for debate
using component evidence, not a single opaque score. Record all candidate IDs in
`generated_candidate_ids` and the debated subset in
`initial_debate_candidate_ids`.

Candidate directions should name a problem, setting, or constraint. Reject
generic shells such as "the impact of X on Y" or "using AI for X" unless
operationalized.

Treat `ELIMINATED` as terminal. If a repair materially changes the original
method, contribution, or interpretation:

1. Give the Judge verdict `DOWNGRADE`.
2. Set the original candidate to `ELIMINATED`.
3. Record early-exit code `MATERIAL_RESCOPING`.
4. Create a derived ID such as `C04-R1`.
5. Inherit the parent's `macro_direction_id`.
6. Set `origin` to `DERIVED`, `parent_id` to `C04`, and status to `DOWNGRADED`.
7. Reset the derived candidate's round count to zero.
8. Require the derived candidate to complete its own minimum rounds.

Use `REVISE` with the same ID only when the core contribution and interpretation
remain intact.

## Round sequence

Run this exact sequence separately for each active candidate:

1. Mentor emits one structured question.
2. Evidence Researcher answers from available evidence.
3. Devil's Advocate issues an independent challenge.
4. Orchestrator collects `SEARCH_NEEDED` and counter-search requests.
   If search is required, append one immutable
   `mainline_control.lane_search_requests` record sourced from the accepted
   same-lane Devil packet.
5. If search is triggered, retrieve and verify evidence, then send the evidence
   back to the Evidence Researcher for exactly one revised answer. Mark this
   dispatch `SUPERSEDE_ACCEPTED_CALL` and depend on both the original Evidence
   and Search packets.
6. A fresh Panel Judge reads the structured question, answer, challenge, search
   result, and revision.
7. Judge emits one transition and next-round focus.
8. Orchestrator validates role envelopes, updates the candidate/evaluation
   delta, and appends a concise round record.
9. After each dependency level resolves, invoke `ROLE_BOUNDARY`; the controller
   uses the exact `active_lanes.next_role` and dependency packet IDs to batch
   the next ready role across independent lanes.
10. Invoke `ROUND_BOUNDARY` only after every continuing lane is ready for its
    next Mentor and all current-lane Judges have returned. The controller checks
    retry/search budgets, stop conditions, and gate readiness.
11. Orchestrator validates and commits each control transition before executing
    its batch.

Never put multiple candidates in one role prompt. Run candidate lanes in
parallel only when each lane has a separate envelope and isolated role contexts.

Recommended round themes:

| Round | Primary test |
|---|---|
| 1 | What precise problem is rising, and who is affected? |
| 2 | Is the apparent gap real, or an artifact of growth or terminology? |
| 3 | Are data, code, benchmarks, compute, and methods feasible? |
| 4 | What evidence would falsify the direction or favor an alternative? |
| 5 | What contribution remains after the strongest counterargument? |
| 6 | Repair only unresolved Major issues; do not add new scope casually. |

Do not expose private chain-of-thought. Record questions, evidence, concise
rationales, challenges, decisions, and citations.

## Search triggers and budgets

Trigger candidate-level external search only after macro-direction selection
when any of these is true:

- an answer returns `SEARCH_NEEDED`
- a claim uses current, latest, first, novel, saturated, or no prior work
- fewer than three independent sources support a pivotal claim
- local sources conflict
- a paper, DOI, dataset, benchmark, or repository needs verification
- feasibility depends on public artifacts or current hardware cost
- one venue, year, geography, or method accounts for at least 70% of known evidence

If the local snapshot is older than 30 days before `DIRECTION_GATE`, run only
the minimum bounded refresh needed to prevent a materially misleading macro map.
Do not spend candidate-level novelty or feasibility budget before selection.

Use the default budget separately for each candidate and round:

- at most 2 query batches
- at most 4 focused queries per batch
- at most 8 newly inspected primary or authoritative sources
- at most one Judge-approved extension of 1 query batch and 4 sources

Record an extension under `search_usage.budget_extension`:

```json
{
  "judge_reason": "Why the unresolved decision warrants more retrieval",
  "extra_query_batches": 1,
  "extra_sources": 4
}
```

Reuse source-ledger rows without recounting them as newly inspected. Do not
repeat the same retrieval unless a new decision question requires it. Stop
searching a candidate when a direct prior resolves the claimed gap.

Do not download an artifact larger than 10 MiB by default. Prefer metadata,
repository file browsers, APIs, range requests, or smaller source files. A
larger download requires a recorded size estimate, necessity, and explicit user
approval in `search_budget.large_downloads`.

After one timeout, try at most one materially different endpoint or method.
Otherwise record `UNRESOLVED` and continue. Return every search result to the
active round.

## Evidence ledger

Store every externally inspected source once in `source_ledger` and render it in
`external-evidence.md`. Each row must contain:

```json
{
  "source_id": "S001",
  "title": "Source title",
  "url": "https://direct.example/source",
  "source_kind": "paper",
  "publication_status": "peer-reviewed",
  "version_or_commit": "unknown",
  "published_or_updated": "2026-01-01",
  "claim_locator": "Section 4, Table 2",
  "verification_level": "CLAIM_SUPPORTED_BY_SOURCE",
  "claim_status": "SUPPORTED",
  "limitations": []
}
```

Use verification levels:

- `SOURCE_EXISTS`: identity or metadata was confirmed
- `CLAIM_SUPPORTED_BY_SOURCE`: the relevant claim location was inspected
- `ARTIFACT_INSPECTED`: relevant repository, code, or data content was inspected
- `LOCALLY_REPRODUCED`: the procedure was executed locally and its result recorded
- `UNRESOLVED`: verification was not completed

Use claim statuses:

- `SUPPORTED`
- `CONTRADICTED`
- `INFERRED`
- `PROPOSED`
- `UNRESOLVED`

For `LOCALLY_REPRODUCED`, add a `reproduction` object containing non-secret
`environment`, `procedure`, `result`, and `artifact_path`. Never label an
artifact reproduced merely because a repository or dataset exists.

## Identification gate

Before a candidate enters `user_gate_candidate_ids`, run a clean Methodology
Architect audit and store:

```json
{
  "estimand": "Target quantity or contrast",
  "unit_of_analysis": "Unit",
  "treatment_or_contrast": "Intervention, comparison, or none with reason",
  "identifying_assumptions": [],
  "falsifier": "Observation or test that would defeat the interpretation",
  "prohibited_interpretations": [],
  "power_or_information_gate": "Minimum information required",
  "validity_threats": [],
  "resource_requirements": [],
  "verdict": "PASS",
  "limitations": []
}
```

Only `PASS` and `PASS_WITH_LIMITS` may proceed. Send `REVISE` back to another
debate round. Treat `BLOCK` as a Critical flaw and eliminate or materially
rescope. The final Judge must receive this audit and use its exact
interpretation.

## Convergence and transitions

Require every candidate surfaced at the later candidate gate to complete at
least three rounds. Default to four when uncertainty remains.

Permit elimination before three rounds only when one of these is documented:

- `DIRECT_PRIOR`
- `UNREPAIRABLE_CRITICAL_FLAW`
- `INACCESSIBLE_REQUIRED_DATA`
- `NO_DEFENSIBLE_CONTRIBUTION`

`MATERIAL_RESCOPING` is allowed only with a `DOWNGRADE` verdict and a derived
child candidate. Use `USER_OWNED_CONSTRAINT` when `DEFER` pauses a candidate.

A candidate may converge when all are true:

- the problem can be stated in one precise sentence
- scope has remained stable for two rounds
- no unresolved Critical issue exists
- Major issues have repair plans or acknowledged tradeoffs
- pivotal current claims have source support or explicit uncertainty
- a plausible data and method route exists
- Judge confidence is `medium` or `high`

After `CONVERGED`, set a generated candidate to `READY_FOR_GATE`; keep a derived
candidate `DOWNGRADED`. Set `gate_ready` to `true` only after the identification
audit passes.

At six rounds, stop automatically instead of manufacturing convergence. Set
`early_exit_reason.code` to `MAX_ROUND_NONCONVERGENCE`, preserve the actual last
verdict and unresolved issues, and run the identification audit on the
best-supported state. A passing audit may mark the candidate
`READY_FOR_GATE`/`DOWNGRADED` and `gate_ready: true` for an explicitly uncertain
human choice; it does not relabel the candidate `CONVERGED`.

## User gates

Only the Orchestrator may create a gate receipt, and only after a direct user
reply. Record:

```json
{
  "receipt_id": "GATE-CANDIDATE-0001",
  "gate": "CANDIDATE_SELECTION",
  "action": "SELECT",
  "values": ["C01"],
  "based_on_revision": 8,
  "received_at": "2026-07-25T12:30:00+08:00"
}
```

`based_on_revision` must identify a committed `HOLD_FOR_USER` transition for the
same gate, except that a blocker receipt references the `BLOCK_SESSION`
transition that first entered `BLOCKED` in the current blocking episode.
Allowed actions are:

- direction: `SELECT|DELEGATE|REVISE`
- candidate: `SELECT|REJECT|BROADEN`
- RQ confirmation: `CONFIRM|REVISE`
- evaluation decision: `CONFIRM|OVERRIDE`
- blocker decision: `REPAIR|STOP`

For `SELECT`, put the selected direction or candidate IDs in `values`. For RQ
`CONFIRM`, put exactly `[selected_candidate_id, confirmed_rq_packet_id]` in
`values`; the packet must be the accepted Research Question Architect result
actually shown to the user. For an evaluation confirmation or override, put the
resulting decision verdict in `values`.
For blocker `REPAIR`, put the blocked transition's `from_status` in `values`;
this is an audit binding, not a user-selected workflow status. Blocker `STOP`
and other actions that do not select or confirm anything use an empty `values`
array.

The controller may consume a receipt but may never create, alter, or infer one.
After blocker `REPAIR`, call it at `RECOVERY` or `RESUME`; it may only advance
back to the status that entered the blocking episode. Blocker `STOP` leaves the
session at `BLOCKED` without another controller transition.

### Macro direction gate

Open `DIRECTION_GATE` in default `GUIDED` after macro mapping and before
detailed candidates. Present all 4-6 directions with:

1. title and scope
2. strongest local hotspot signals
3. plausible contribution types
4. indicative cost and risk
5. main uncertainty
6. panel note

Ask only:

> Select 1-2 direction IDs, ask the panel to choose, or request a revised map.

Do not silently continue if the user has not answered. A paused session remains
valid and resumable at `DIRECTION_GATE`. Enter the state only with a committed
`HOLD_FOR_USER` transition whose gate is `DIRECTION_SELECTION`, then run the
session validator before presenting it. Record the direct reply as a direction
gate receipt before leaving the gate.

### Candidate decision gate

Open `USER_GATE` when:

- two or three candidates are ready and preference matters
- only one candidate survives and the user must accept it or broaden scope
- `USER_REQUIRED` fields affect ranking or feasibility

Before setting status `USER_GATE`:

1. Populate `user_gate_candidate_ids`.
2. Confirm each listed candidate has at least three rounds.
3. Confirm each is gate-ready and has a passing identification audit.
4. Commit `HOLD_FOR_USER` with gate `CANDIDATE_SELECTION`.
5. Run `<skill-root>/scripts/validate_session.py`.
6. Present actual per-candidate round counts.

Do not surface `SCREENED_OUT`, `DEFERRED`, or `ELIMINATED` candidates as options.
Include them in the audit trail with reasons. Do not set
`selected_candidate_id` until a direct candidate-selection receipt is recorded.

### Research-question confirmation gate

After one fresh `Research Question Architect` refinement of the selected
candidate, remain at `RQ_REFINEMENT` and commit `HOLD_FOR_USER` with gate
`RQ_CONFIRMATION`. This refinement does not add candidate-debate rounds. Present
the proposed RQ, scope, estimand, limitations, and strongest counterargument.
Record `CONFIRM|REVISE`. A `CONFIRM` receipt binds both the selected candidate
and the displayed RQ packet. Consume it with a no-dispatch `POST_USER_GATE`
transition that requires exactly `APPLY_RQ_CONFIRMATION`, then immediately run
`PRE_COMPLETE`; no later RQ dispatch or supersession is legal. A `REVISE`
receipt uses empty `values` and requires exactly `APPLY_RQ_REVISION` plus one
fresh Research Question Architect dispatch that supersedes the prior RQ packet.
Only the confirmed two-step path permits `COMPLETE`.

### Evaluation decision gate

Open `DECISION_GATE` only after all of the following are true:

1. The experiment inventory and claim-evidence matrix are complete enough to
   state the primary claim and its central comparison.
2. Statistical Reviewer and Reproducibility Auditor work products are present.
3. External positioning is either source-ledgered or explicitly `UNRESOLVED`.
4. At least three evaluation debate rounds are recorded.
5. A fresh Panel Judge has issued the evaluation decision.
6. `<skill-root>/scripts/validate_session.py` passes.

Ask the user to confirm whether to act on `CONTINUE`, `REPAIR`, `PIVOT`, `STOP`,
or `INSUFFICIENT_EVIDENCE`. User-owned constraints such as deadline, compute,
data access, and risk tolerance remain `USER_REQUIRED`; do not guess them. Enter
the state with `HOLD_FOR_USER` and gate `EVALUATION_DECISION`; do not proceed to
`NEXT_EXPERIMENT` without a direct evaluation-decision receipt.

## Artifacts and validation

### Macro direction card

```markdown
## D01 — <broad area>

- Scope:
- Local hotspot signals:
- Plausible contribution types:
- Indicative cost:
- Indicative risk:
- Main uncertainty:
- Panel note:
- Status:
```

### Candidate card

```markdown
## C01 — <scoped direction>

- Macro direction:
- Problem:
- Local signal:
- External signal:
- Gap hypothesis:
- Feasibility:
- Saturation risk:
- Strongest objection:
- Status:
- Rounds completed:
- Parent candidate:
```

### Round record

```markdown
### C01 / Round 2

**Mentor question**
...

**Evidence answer**
...

**Devil's Advocate**
...

**External evidence**
...

**Revised answer**
...

**Judge**
Verdict: ...
Confidence: low|medium|high
Next focus: ...
```

### Decision packet

Include the macro direction map and selection provenance, candidate options,
eliminated and deferred candidates with reasons, lineage, evidence links,
identification audits, unresolved disagreements, user-required inputs, budget
extensions, rejected work products, and the next gate.

### RQ brief

Include one interrogative primary RQ, 2-3 subquestions, scope, population and
setting when applicable, preliminary FINER assessment, method and data
direction, exact estimand or target quantity, keywords, known limitations,
prohibited interpretations, and the strongest counterargument.

### Evaluation artifacts

`experiment-evidence-pack.md` records the target, full experiment inventory,
and observed-versus-inferred labels. `result-validation.md` records statistical,
methodological, and reproducibility findings. `claim-evidence-matrix.md` maps
each claim to supporting, contradictory, or missing evidence. `evaluation-debate.md`
stores the concise round records. `external-positioning.md` renders the source
ledger and direct-prior or contradiction findings. `evaluation-decision.md`
stores the decision and dissent. `next-experiment-plan.md` records
the one decision-changing experiment or `NONE` rationale.

Run:

```bash
python3 <skill-root>/scripts/validate_controller_decision.py \
  <project-root>/reports/research-direction/<session-id>/session-state.json \
  <controller-output.json> \
  --control-input \
  <project-root>/reports/research-direction/<session-id>/control-input.json
python3 <skill-root>/scripts/validate_session.py \
  <project-root>/reports/research-direction/<session-id>
```

Validate the controller output before staging its effects. Full session
validation must pass before presenting `DIRECTION_GATE`, `USER_GATE`,
`RQ_CONFIRMATION`, or `DECISION_GATE`, and before declaring `COMPLETE`. If it
fails, do not commit the proposed gate/complete transition; record
`CONTROL_PRECONDITION_FAILED`, repair the staged state, or report the exact
failure.

## Failure paths

- **No user response at direction gate**: remain at `DIRECTION_GATE`; do not
  auto-select or start debate.
- **User rejects the direction map**: revise the map once using the user's
  boundary; preserve the first map in the audit trail. Record
  `DIRECTION_SELECTION/REVISE`, advance back to `SCANNING` for the bounded
  remap, then open a new `DIRECTION_GATE` hold at a new control revision.
- **Insufficient local signal**: broaden the local scan, then run one bounded
  external three-way scan.
- **Search unavailable**: continue only with `UNRESOLVED`; make no novelty claim.
- **No candidate survives**: return the elimination matrix and ask whether to
  reopen the selected macro direction or choose another.
- **Existing experiment lacks a primary claim**: remain at `EVIDENCE_INTAKE` and
  ask for the smallest clarification needed to identify the claim and comparison.
- **Critical validity or integrity flaw**: commit `BLOCK_SESSION` at the current
  phase and present the accepted Critical finding as a preliminary
  repair-or-stop blocker. Do not claim a fully evaluated `REPAIR` or `STOP`
  verdict or use external popularity to override it. Resume only after an
  explicit user repair/stop response recorded as a `BLOCKER_DECISION` receipt;
  the formal decision gate still requires its normal evidence and rounds.
- **No rerunnable artifact**: continue with `ARTIFACT_INSPECTED` or `UNRESOLVED`;
  never imply local reproduction.
- **No decision-changing next experiment**: choose `STOP` or
  `INSUFFICIENT_EVIDENCE` rather than fabricate a generic ablation list.
- **Non-convergence**: stop at six rounds and open a user gate.
- **Agent disagreement**: preserve the disagreement; Judge may request another
  round but cannot erase dissent.
- **Context contamination**: reject, log, and rerun the work product once with a
  clean envelope.
- **Stale controller output**: reject it without changing revision, recompute the
  state digest, and retry once in a fresh controller context.
- **Repeated controller failure**: switch to `DEGRADED_FALLBACK` and run the
  deterministic control checklist. At a gate, Critical stop, or completion,
  block unless the same prerequisites and validators pass.
- **Resume**: call the controller at `RESUME` before dispatching new work. Treat
  accepted or rejected packet IDs as resolved. Do not duplicate a pending call,
  repeat an accepted debate-round role, or disguise a rejected call as a new
  `ADVANCE` dispatch.
- **Repeated role failure**: distinguish the failure class. A transport
  failure (API overload, timeout, killed subagent) leaves the dispatch pending
  and never consumes the `RETRY_ROLE` credit: re-invoke up to three attempts,
  then execute the single call `DEGRADED_INLINE` with disclosure (see the
  controller reference). A content rejection gets its one `RETRY_ROLE`; after
  that retry also fails, a missing Search continues the lane with `UNRESOLVED`
  claims, while a missing Mentor, Evidence, Devil's Advocate, or Judge blocks
  the candidate. Never reuse a contaminated answer.
- **Subjective unknown**: emit `USER_REQUIRED`; Evidence Researcher must not guess.
