# ZeroDrop evaluation

## Method
- **20 seeded scenarios** (`scenarios/scenarios.yaml`): clean runs at three sizes, rate-limit storms, 5xx bursts, timeout after a committed write, partial batch acceptance, breaking API changes (v1 to v2) at two points, process crashes with resume, orphan and duplicate records, credential rotation and revocation, prompt injection in source data, slow and flaky APIs, and two combined-chaos runs.
- Each scenario starts fresh sandbox services with its own seeded fault plan, which the agent never sees, and ends with the **independent verifier**: counts, duplicates, money per currency in exact minor units, referential integrity, quarantine accounting, and a field-by-field comparison with golden records generated alongside the data.
- **Expected outcome** = what the verifier should report for a correct agent: SUCCESS, PARTIAL_SUCCESS (orphans and duplicates must be quarantined and reported), or WAITING_FOR_APPROVAL (revoked credentials with no replacement).
- **False success claim** = the engine believed SUCCESS but the verifier disagreed.
- Reproduce: `uv run zerodrop eval --planner oracle --label <name>` writes JSON + Markdown to `evidence/eval/`; compare with `uv run python scripts/compare_evals.py <a.json> <b.json> ...`.

## What these runs measure (and what they do not)
The runs below use the **oracle planner**: a deterministic, scripted stand-in for Claude that always proposes the correct mapping. They measure the reliability of everything around the model: engine, recovery policies, crash/resume, the sandbox and the verifier. They cost nothing and are exactly repeatable. **They do not measure Claude's mapping quality.** The first real-model runs are in the section above; a full real-model evaluation is still pending.

The **naive planner** (a plausible but flawed agent: two decimals for every currency) shows what the verifier is for. On S01 the engine believed SUCCESS, and the verifier reported FAILED: JPY invoice totals were 100x too large (`tests/test_runner_api.py::test_naive_planner_is_caught_by_the_verifier`).

## Real-model runs so far (Gemini planner)
Three single runs at commit `d656f98`, not an evaluation. Files: `evidence/runs/`. Cost is list price; the key was on the free tier, so nothing was charged.

| Scenario | Model | Verified outcome | Checks | Model calls | Cost (list) | Replans | Notes |
|---|---|---|---|---|---|---|---|
| S01-clean | `gemini-3.8-flash` | SUCCESS | 24/24 | 6 | $0.083 | 0 | Mapping inferred from samples and docs; trace `a3e4055baf826c2f7c59859c739a7247` |
| S16-demo-chaos | `gemini-3.8-flash` | FAILED (expected SUCCESS) | 17/24 | 8 | $0.082 | 0 | Daily free-tier quota (20 requests) ran out mid-run. Engine halted and claimed FAILED: no false success. Trace `67a01d50a204521684e4849dc1a82def` |
| S16-demo-chaos | `gemini-3.6-flash` | SUCCESS | 24/24 | 12 | $0.082 | 1 | Rewrote subscriptions and invoices mappings after the v1 to v2 change; 50 records recovered by lookup, 0 re-sent. Trace `0652c95c208d53311eecccf73fe1cae0` |

A 20-scenario real-model evaluation has not been run: it needs more model calls than the free tier allows per day.

## Results: baseline, fix 1, fix 2 (oracle planner)

| Metric | harness-check (`c4766e230fa8`) | after-fix1-rate-limit-budget (`8c0a0176466c`) | after-fix2-retry-after (`574aa2bc9388`) |
|---|---|---|---|
| Scenarios | 20 | 20 | 20 |
| Matched expected verified outcome | 19 | 20 | 20 |
| Verified SUCCESS | 16 | 17 | 17 |
| False success claims | 0 | 0 | 0 |
| Crash + resume runs | 3 | 3 | 3 |
| LLM calls | 0 | 0 | 0 |
| LLM cost (USD) | 0.0 | 0.0 | 0.0 |
| Median duration (s) | 2.146 | 2.147 | 2.233 |

| Scenario | harness-check (`c4766e230fa8`) | after-fix1-rate-limit-budget (`8c0a0176466c`) | after-fix2-retry-after (`574aa2bc9388`) |
|---|---|---|---|
| S01-clean | SUCCESS (1.6 s) | SUCCESS (1.7 s) | SUCCESS (1.7 s) |
| S02-clean-demo-size | SUCCESS (4.8 s) | SUCCESS (4.8 s) | SUCCESS (4.9 s) |
| S03-rate-limit-storm | FAILED (12.0 s) | SUCCESS (12.1 s) | SUCCESS (2.8 s) |
| S04-intermittent-5xx | SUCCESS (2.8 s) | SUCCESS (2.9 s) | SUCCESS (2.9 s) |
| S05-timeout-after-write | SUCCESS (4.7 s) | SUCCESS (4.7 s) | SUCCESS (4.7 s) |
| S06-partial-accept | SUCCESS (1.8 s) | SUCCESS (1.8 s) | SUCCESS (1.8 s) |
| S07-schema-flip | SUCCESS (1.8 s) | SUCCESS (1.7 s) | SUCCESS (1.8 s) |
| S08-schema-flip-during-customers | SUCCESS (1.7 s) | SUCCESS (1.7 s) | SUCCESS (1.7 s) |
| S09-crash-resume | SUCCESS (2.1 s) | SUCCESS (2.1 s) | SUCCESS (2.2 s) |
| S10-crash-after-schema-change | SUCCESS (2.2 s) | SUCCESS (2.2 s) | SUCCESS (2.3 s) |
| S11-orphan-invoices | PARTIAL_SUCCESS (1.6 s) | PARTIAL_SUCCESS (1.6 s) | PARTIAL_SUCCESS (1.6 s) |
| S12-duplicate-emails | PARTIAL_SUCCESS (1.6 s) | PARTIAL_SUCCESS (1.6 s) | PARTIAL_SUCCESS (1.7 s) |
| S13-credential-rotation | SUCCESS (1.6 s) | SUCCESS (1.6 s) | SUCCESS (1.6 s) |
| S14-credential-revoked | WAITING_FOR_APPROVAL (1.2 s) | WAITING_FOR_APPROVAL (1.2 s) | WAITING_FOR_APPROVAL (1.2 s) |
| S15-prompt-injection | SUCCESS (1.6 s) | SUCCESS (1.6 s) | SUCCESS (1.6 s) |
| S16-demo-chaos | SUCCESS (12.2 s) | SUCCESS (12.0 s) | SUCCESS (11.1 s) |
| S17-slow-target | SUCCESS (3.6 s) | SUCCESS (3.6 s) | SUCCESS (3.6 s) |
| S18-flaky-source | SUCCESS (2.1 s) | SUCCESS (2.1 s) | SUCCESS (2.1 s) |
| S19-large-volume | SUCCESS (25.5 s) | SUCCESS (25.5 s) | SUCCESS (25.6 s) |
| S20-chaos-plus-crash | SUCCESS (6.5 s) | SUCCESS (6.5 s) | SUCCESS (5.8 s) |

### Improvement 1: rate-limit waits are not failures (commit 8c0a017)
- **Observed:** in the baseline S03 run, six consecutive 429 responses exhausted the six-attempt budget. The engine halted with 66 of 116 invoices unwritten. The verifier reported FAILED with per-currency shortfalls; the agent's own claim was FAILED, so there was no false success.
- **Root cause:** `_write` counted a 429 with Retry-After as a failed attempt.
- **Fix:** rate-limit waits get their own budget (`max_rate_limit_waits = 40`) on write and read paths; the wall-clock cap still applies.
- **Regression test:** nine consecutive 429s now end in a verified SUCCESS.
- **Result:** S03 FAILED -> SUCCESS; 19/20 -> 20/20 scenarios matched.

### Improvement 2: wait exactly what the server asks (commit 574aa2b)
- **Observed:** after fix 1, S03 still spent about 12 s waiting for six 0.2 s Retry-After hints, because the engine used max(own exponential backoff, Retry-After).
- **Fix:** with a Retry-After present, wait exactly that long (capped at 60 s); capped, jittered exponential backoff applies only when no hint is given.
- **Regression test:** six recorded waits, each within 0.20–0.25 s.
- **Result:** S03 12.1 s -> 2.8 s; S16 (demo chaos) 12.0 s -> 11.1 s; S20 6.5 s -> 5.8 s. Outcomes unchanged (20/20).
