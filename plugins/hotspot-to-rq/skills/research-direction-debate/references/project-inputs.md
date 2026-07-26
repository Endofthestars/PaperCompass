# Project Inputs and Evidence Policy

## Contents

1. Project discovery
2. PaperNotes defaults
3. Evidence pack
4. Opportunity signals
5. Freshness and consistency
6. Local evidence labels
7. Existing-experiment evaluation inputs
8. Output location

## Project discovery

Start from the active workspace root. Inspect, in order:

1. root instructions and README files
2. existing reports and structured trend data
3. analysis scripts and their source paths
4. the canonical note corpus
5. existing direction-specific reports

Do not scan unrelated home directories. Do not combine mirrored corpora merely
because they are all present.

## PaperNotes defaults

For this project, prefer these sources:

- Canonical paper corpus: `data/Paper-Notes/docs`
- Fallback corpus only when canonical is absent or explicitly incomplete:
  `data/Paper-Notes.incomplete/docs`
- Generated site copy: `data/Paper-Notes-docs`; use for display checks, not counting
- Structured trend data: `reports/paper-notes-trends.json`
- Human-readable trend report: `reports/trend-report.md`
- Existing topical reports: other Markdown files under `reports/`
- Existing analyzers: `scripts/analyze_paper_notes.py` and
  `scripts/build_trend_report.py`

Never merge `Paper-Notes`, `Paper-Notes.incomplete`, and `Paper-Notes-docs` into
one count. Record which source each number came from.

## Evidence pack

Produce a compact evidence pack with:

```yaml
session_id: <id>
interaction_mode: <GUIDED|AUTONOMOUS>
project_root: <absolute path>
canonical_corpus: <path>
project_snapshot: <stable path, commit, or snapshot id>
snapshot_date: <date or unknown>
paper_count: <count>
conference_count: <count>
known_count_mismatches: []
top_areas: []
fastest_growth: []
cross_venue_topics: []
existing_recommendations: []
coverage_gaps: []
source_files: []
```

Existing recommendations are evidence about prior analysis, not proof that the
recommended direction is novel or feasible.

## Opportunity signals

Use broad opportunity signals to build the macro direction map before evaluating
specific candidates. Keep macro directions mutually distinguishable by research
object, contribution family, or execution setting; do not present several minor
variants of one method family as separate broad choices.

Evaluate scoped candidates on:

- normalized growth, not raw delta alone
- cross-conference recurrence
- recency and field velocity
- unresolved contradictions or inconsistent evaluation
- method, benchmark, data, or reproducibility gaps
- public code and data feasibility
- expected compute and time
- user fit when known
- saturation and incremental-work risk

Do not use a single aggregate score as the sole selector. Preserve component
scores and uncertainty so the Judge can explain tradeoffs.

The macro direction map is a local orientation aid, not a novelty finding. Do
not spend candidate-level external search budget before the `GUIDED` user
selects a direction. If the local snapshot is stale, perform only the minimum
bounded refresh needed to avoid a materially misleading map.

## Freshness and consistency

For fast-moving AI/ML topics, treat a local snapshot older than 30 days as stale
for "current" or "latest" claims. Staleness triggers an external update search; it
does not invalidate historical counts.

If Markdown and JSON reports disagree:

1. identify the generating scripts and source paths
2. report both values
3. select one canonical source for the current run
4. mark the other as stale or differently scoped only when evidence supports it

Do not silently overwrite existing reports during discovery. Regenerate them only
when the current user task authorizes project changes.

## Local evidence labels

Label every local statement:

- `OBSERVED`: directly read or computed from project material
- `INFERRED`: reasoned from observed evidence
- `RECOMMENDED`: a prior report's judgment
- `PROPOSED`: a new direction or repair proposed in the current session
- `UNRESOLVED`: requires local recomputation, user input, or external confirmation

Do not use `VERIFIED` as a catch-all label. External verification uses the
source-ledger levels in `debate-protocol.md`.

## Existing-experiment evaluation inputs

For `EVALUATE` mode, start from the user-provided direction and inspect the
available local experiment record before asking for more context. Prefer these
inputs, in order:

1. the primary claim or hypothesis the experiment was intended to test
2. code revision, command/configuration, environment, and random-seed records
3. data source, split definitions, preprocessing, and exclusion rules
4. complete result tables, logs, checkpoints, plots, and failed or negative runs
5. baseline definitions, comparison budgets, ablations, and sensitivity checks
6. existing notes about interpretation, limitations, deadline, compute, or data
   constraints

Create an experiment inventory rather than treating a selected best result as
the experiment. For every experiment, distinguish the observed outcome from the
claim it is being used to support. Mark absent seeds, missing baselines, unknown
data provenance, or unavailable reruns as `UNRESOLVED`; do not silently infer
that they passed.

The evaluation evidence pack should make these fields explicit:

```yaml
evaluation_target:
  direction: <existing research direction>
  primary_claim: <claim under evaluation>
  study_type: <code|human|observational|mixed|other>
  constraints: []
experiment_inventory:
  - experiment_id: E01
    hypothesis: <what this run tests>
    artifact_paths: []
    outcome_summary: <observed result only>
    status: <OBSERVED|PARTIAL|UNRESOLVED>
claim_evidence_matrix: []
```

During `EVIDENCE_INTAKE`, use an empty string only for a target field that is
genuinely missing and add the corresponding `user_required` code:
`EVALUATION_DIRECTION`, `PRIMARY_CLAIM`, or `STUDY_TYPE`. Do not create an
Experiment Auditor call until those fields are resolved.

External positioning begins only after this local inventory is complete enough
to state the primary claim and its most important comparison. Search current
literature, benchmarks, and artifacts when novelty, direct prior, contradiction,
or feasibility is decision-relevant. Keep experimental validity, external
positioning, and the final continue/repair/pivot/stop recommendation separate.

## Output location

Use `reports/research-direction/<session-id>/`, where `session-id` is a stable,
filesystem-safe timestamp or user-provided label. Never overwrite another session.
Create `session-state.json` first and use the same `session_id` in the metadata
header of every Markdown artifact.
