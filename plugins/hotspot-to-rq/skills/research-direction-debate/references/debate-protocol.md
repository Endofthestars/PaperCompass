# Internal Socratic Debate Protocol

## Contents

1. Session initialization
2. Machine-readable state
3. Macro direction mapping, gate, or existing-experiment intake
4. Candidate selection, lineage, or evaluation target
5. Round sequence
6. Search triggers and budgets
7. Evidence ledger
8. Identification or experiment-validity gate
9. Convergence and transitions
10. User gates
11. Artifacts and validation
12. Failure paths

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

Use UTF-8 JSON, schema version `1.2`, and keep it valid after every transition.
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
5. If search is triggered, retrieve and verify evidence, then send the evidence
   back to the Evidence Researcher for one revised answer.
6. A fresh Panel Judge reads the structured question, answer, challenge, search
   result, and revision.
7. Judge emits one transition and next-round focus.
8. Orchestrator validates role envelopes, updates JSON state, and appends a
   concise round record.

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

At six rounds, stop automatically. Return the best supported state, unresolved
issues, and a user gate instead of manufacturing convergence.

## User gates

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
valid and resumable at `DIRECTION_GATE`.

### Candidate decision gate

Open `USER_GATE` when:

- two or three candidates are ready and preference matters
- only one candidate survives and the user must accept it or broaden scope
- `USER_REQUIRED` fields affect ranking or feasibility
- the final RQ is ready to freeze

Before setting status `USER_GATE`:

1. Populate `user_gate_candidate_ids`.
2. Confirm each listed candidate has at least three rounds.
3. Confirm each is gate-ready and has a passing identification audit.
4. Run `scripts/validate_session.py`.
5. Present actual per-candidate round counts.

Do not surface `SCREENED_OUT`, `DEFERRED`, or `ELIMINATED` candidates as options.
Include them in the audit trail with reasons.

### Evaluation decision gate

Open `DECISION_GATE` only after all of the following are true:

1. The experiment inventory and claim-evidence matrix are complete enough to
   state the primary claim and its central comparison.
2. Statistical Reviewer and Reproducibility Auditor work products are present.
3. External positioning is either source-ledgered or explicitly `UNRESOLVED`.
4. At least three evaluation debate rounds are recorded.
5. A fresh Panel Judge has issued the evaluation decision.
6. `scripts/validate_session.py` passes.

Ask the user to confirm whether to act on `CONTINUE`, `REPAIR`, `PIVOT`, `STOP`,
or `INSUFFICIENT_EVIDENCE`. User-owned constraints such as deadline, compute,
data access, and risk tolerance remain `USER_REQUIRED`; do not guess them.

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
python3 scripts/validate_session.py reports/research-direction/<session-id>
```

Validation must pass before `DIRECTION_GATE`, `USER_GATE`, `DECISION_GATE`, and
`COMPLETE`. If it fails, repair state or report the exact failure; never claim
generic completion.

## Failure paths

- **No user response at direction gate**: remain at `DIRECTION_GATE`; do not
  auto-select or start debate.
- **User rejects the direction map**: revise the map once using the user's
  boundary; preserve the first map in the audit trail.
- **Insufficient local signal**: broaden the local scan, then run one bounded
  external three-way scan.
- **Search unavailable**: continue only with `UNRESOLVED`; make no novelty claim.
- **No candidate survives**: return the elimination matrix and ask whether to
  reopen the selected macro direction or choose another.
- **Existing experiment lacks a primary claim**: remain at `EVIDENCE_INTAKE` and
  ask for the smallest clarification needed to identify the claim and comparison.
- **Critical validity or integrity flaw**: record the flaw, return `REPAIR` or
  `STOP`, and do not use external popularity to override it.
- **No rerunnable artifact**: continue with `ARTIFACT_INSPECTED` or `UNRESOLVED`;
  never imply local reproduction.
- **No decision-changing next experiment**: choose `STOP` or
  `INSUFFICIENT_EVIDENCE` rather than fabricate a generic ablation list.
- **Non-convergence**: stop at six rounds and open a user gate.
- **Agent disagreement**: preserve the disagreement; Judge may request another
  round but cannot erase dissent.
- **Context contamination**: reject, log, and rerun the work product once with a
  clean envelope.
- **Repeated role failure**: mark the packet unresolved and continue or block
  the candidate; do not reuse a contaminated answer.
- **Subjective unknown**: emit `USER_REQUIRED`; Evidence Researcher must not guess.
