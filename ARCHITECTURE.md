# ZeroDrop architecture

**The LLM decides, code executes, and an independent checker judges.**

```
             goal ("move all customers, subscriptions and invoices ...")
                                   |
                     +-------------v--------------+
                     |  MigrationEngine (engine)  |   explicit state machine, SQLite ledger
                     |  CREATED -> DISCOVERING -> |   (runs, records, id map, mapping versions,
                     |  PLANNING -> DRY_RUN ->    |    events), checkpoint after every batch
                     |  EXECUTING <-> RECOVERING  |
                     |  -> VERIFYING -> terminal  |
                     +--+---------+---------+-----+
        read-only tools |         | batches | read-only
        +---------------v--+   +--v---------v--+   +------------------------------+
        | Planner (agent)  |   | Target API     |   | Independent verifier         |
        | Claude Opus 5.5  |   | (NovaBill)     |   | own canonicalization of the  |
        | tool loop:       |   | idempotency    |   | source semantics; never      |
        | samples, docs,   |   | keys, 409s,    |   | imports engine/DSL/agent;    |
        | schema, dry_run  |   | v1 -> v2 drift |   | decides SUCCESS / PARTIAL /  |
        | -> MappingSpec   |   +----------------+   | FAILED                       |
        | (whitelisted DSL)|   +----------------+   +------------------------------+
        | diagnoser on     |   | Source API     |
        | contract change  |   | (LegacyBill)   |
        +------------------+   +----------------+
```

## Division of labor

| Responsibility | Owner | Why |
|---|---|---|
| Understand both schemas, infer the field mapping | **Claude** (`agent/planner.py`), bounded tool loop | Semantic matching, units, codes, time zones |
| Mapping language | Whitelisted DSL ops (`models.OpName`, executed by `dsl.py`) | No arbitrary code from the model; safe against prompt injection in source data |
| Dry-run every mapping against the target schema | Deterministic (`engine.PlannerTools.dry_run`, `validation.py`) | Cheap, repeatable; feeds errors back to the model |
| Bulk transfer, batching, idempotency, checkpoints | Deterministic engine | Reliability must not depend on the model |
| Failure classification | Deterministic (`classify.py`) | Predictable; the model is consulted only for contract changes |
| Diagnose a breaking API change and patch mappings | **Claude** (`agent/diagnoser.py`) | Needs reasoning over errors and a schema diff |
| Final verdict | **Independent verifier** (`verifier/verify.py`) | The agent cannot certify its own work |

## Failure taxonomy and recovery

| Class | Signals | Policy |
|---|---|---|
| TRANSIENT | 429, 5xx, per-item 503, connection resets | 429: wait exactly the server's `Retry-After` (own budget of 40 waits, the wall-clock cap still applies); others: capped exponential backoff with seeded jitter, at most 6 attempts |
| AMBIGUOUS_WRITE | Timeout after the request was sent | Look up each item by `external_id` before re-sending; never blind re-POST |
| CONTRACT | The same 422 code on >= 50% of a batch, or a new `NovaBill-Version` | Pause, refetch the schema, Claude patches the failing mapping **and every pending mapping** affected, dry-run, resume |
| DATA | An isolated record-level 422 or an unresolvable reference | Quarantine with a reason; the run ends PARTIAL_SUCCESS |
| AUTH | 401 | Re-read the configured token file once; otherwise WAITING_FOR_APPROVAL |
| BUDGET | LLM call, cost or wall-clock cap | Stop safely and report honestly |

Records already WRITTEN in the ledger are never re-sent. Idempotency key = `"{entity}:{source_id}"`. A crash at any point resumes from the ledger without duplicates (property-tested with Hypothesis).

## Honesty by construction
- The engine records its own belief (`agent_claimed_status`) before verification; the verifier's status is final. A disagreement is a measured **false-success claim**.
- The verifier checks counts, duplicate ids and e-mails, money per currency in exact ISO-4217 minor units, referential integrity, quarantine accounting and (in evaluation) every field against golden records the agent never sees.

## Safety
- Source records, notes and the legacy data dictionary are treated as untrusted data in prompts; the planner has no write or delete tools.
- Keys come from the environment only (`ZERODROP_ANTHROPIC_KEY`, `NEATLOGS_API_KEY`); `ZERODROP_ANTHROPIC_KEY` is deliberately not `ANTHROPIC_API_KEY`, so coding tools never pick it up.
- Hard limits per run: LLM calls, cost (USD), wall clock, replans, attempts.

## Observability (Neatlogs)
`telemetry.py` initialises Neatlogs once per process (no-op without a key). The Anthropic client is wrapped with `neatlogs.wrap()`, so model calls are LLM spans. The engine adds a WORKFLOW root (`zerodrop.migration`), AGENT spans for the planner and diagnoser loops, TOOL spans for discovery, batch writes and lookups, CHAIN spans for recovery decisions, and an EVALUATOR span for the independent verifier.

## Test environment
LegacyBill and NovaBill (`sandbox/`) are services built for this project. Faults come from a seeded fault plan (`FaultPlan`), so every scenario is reproducible; the agent never sees the plan. The dashboard labels them as sandbox services.

## Code map
`models.py` (contracts) · `dsl.py` · `validation.py` · `connectors/` · `ledger.py` · `classify.py` · `engine.py` · `verifier/verify.py` · `agent/` (llm, planner, diagnoser, prompts, fake) · `sandbox/` · `scenarios.py` + `scenarios/scenarios.yaml` · `runner.py` · `cli.py` · `api.py` · `ui/`
