# hackathon.md: ZeroDrop build log (neatHack 2026)

## Project
- **Name:** ZeroDrop
- **Purpose:** An autonomous agent that migrates a company's billing data between SaaS systems, recovers from API failures and breaking schema changes on its own, and proves nothing was lost.
- **Problem:** Switching SaaS tools means moving customer, subscription and invoice data through rate-limited, changing APIs with different schemas. Today this is done with brittle scripts or consultants, and failures show up later as silently dropped, duplicated or corrupted records.

## Team
- Team Tokenmaxing

## Stack
- Python 3.12+, FastAPI, Pydantic v2, SQLite, httpx
- Anthropic API (Claude Opus 5.5) for mapping inference and failure diagnosis
- neatlogs: runtime tracing of every agent run (instrumented in code; key not yet configured, so no traces sent yet)
- Entire: checkpoints for coding-agent sessions (planned)
- cfo.ai: business plan (pending)
- Sandbox services built during the hackathon: LegacyBill (source) and NovaBill (target), with a seeded fault injector

## Build log

### 2026-10-10 (Day 1)
- 12:30 IST: coding window opened. Plan prepared beforehand (research and planning only): `docs/PLAN.md`.
- 15:40 IST: project skeleton and frozen shared contracts (`src/zerodrop/models.py`, `docs/CONTRACTS.md`). Telemetry layer that no-ops without a Neatlogs key. Neatlogs SDK 1.4.26 offline Doctor check passed (`python -m neatlogs doctor --local`: LOCAL_ENVELOPE_VALID). No traces sent yet.
- 15:45–17:50 IST: parallel build with Claude Code subagents against the frozen contracts: sandbox (LegacyBill, NovaBill, fault injector, golden records), mapping DSL + validation + connectors, durable engine (ledger, classification, recovery, crash/resume), independent verifier, Claude planner/diagnoser with offline fakes, and the dashboard UI. Then an adversarial review pass per core module. Result: 585 tests passing (including 18 end-to-end tests against real local servers).
- 17:50–18:05 IST: integration: 20 seeded scenarios, runner, `zerodrop` CLI (run, eval, sandbox, serve), dashboard API with live event streaming. End-to-end checks: S01 clean -> verified SUCCESS; S07 breaking API change -> mapping v1 to v2, verified SUCCESS; the naive (flawed) planner on S01 -> engine claimed SUCCESS, **verifier reported FAILED** (JPY totals 100x).
- 18:00 IST: **baseline evaluation** (oracle planner, commit c4766e2): 19/20 scenarios matched the expected verified outcome. **S03 rate-limit storm failed**: six consecutive 429s exhausted the attempt budget and 66 invoices were never written. The verifier caught it; the agent's own claim was also FAILED (no false success). Evidence: `evidence/eval/20261010T122907Z-oracle-harness-check.md`.
- 18:06 IST: dashboard verified in a real browser against a live S16 demo-chaos run (light and dark themes): 7 failures, 16 recovery steps, subscription and invoice mappings v1 -> v2, 50 committed records found after a timeout (0 re-sent), verifier 24/24 checks passed.
- 18:08 IST: **fix 1** (commit 8c0a017): 429 waits get their own budget. Re-evaluation at that commit: 20/20 matched, 0 false success claims.
- 18:10 IST: **fix 2** (commit 574aa2b): wait exactly the server's Retry-After instead of a longer own backoff. S03 12.1 s -> 2.8 s; outcomes unchanged (20/20). Details and tables: `EVALUATION.md`.
- 22:15 IST: **Neatlogs connected.** Key stored in git-ignored `.env`. Two traced agent runs (oracle planner): S07 `run_9ac0d4eb1354` and S16 `run_08b45d4bf581`, both verified SUCCESS. `neatlogs doctor --probe`: export accepted and durably stored (stage `raw_durable`), readback still `processing` at check time (TRACE_READBACK_TIMEOUT, remediation WAIT_FOR_TRACE). Dashboard confirmation pending.
- 23:10 IST: **Mac session.** Repo cloned on the builder's Mac; `scripts/mac_setup.sh` installed the toolchain. 656 tests pass, `neatlogs doctor --probe` passes end to end (trace visible, finalized, hierarchy valid). **Entire enabled**; first checkpoint `01M4KEGN3Q174N063453HK5XC6` on commit `b7b0b52` (this session was attached with `entire session attach`, because it started one folder above the repo and the hooks had not loaded).
- 23:20 IST: **Docker kit.** `Dockerfile` (multi-stage: UI build, then uv runtime, non-root user, healthcheck on `/api/meta`), `docker-compose.yml` (dashboard `app` plus a standalone `sandbox` service with LegacyBill and NovaBill), `.dockerignore` (excludes `.env`, `runs/`, `.git`). Verified locally: `docker compose up` -> both services healthy; `POST /api/runs` with S16 demo-chaos and the oracle planner -> verified SUCCESS, 24/24 checks. Two small supporting changes, test first: the sandbox listening interface is configurable (`zerodrop sandbox --host`), and run outcomes take the commit from `ZERODROP_GIT_COMMIT` when the image has no `.git`. 658 tests pass.
- 23:28 IST: **Run-to-trace link.** Every traced run now records its Neatlogs trace id: as an event in the run log, in the outcome metrics (`neatlogs_trace_id`), in `GET /api/runs/{id}` (`trace_id`) and in the dashboard footer. The id is read through the SDK's supported propagation API (`inject_trace_context`), because Neatlogs keeps spans in a private context (a first attempt through the global OpenTelemetry context returned nothing in a real traced run; caught by running it, then fixed). The WORKFLOW root span is now explicit and carries the outcome: run id, verifier status, the agent's own claim, false-success flag, checks total/failed, report hash, replans, records written. Checked on a real traced oracle run of S16: `run_c5403f3755ba`, trace `db295599ad67b4214fbb562c8c7259ab`, verified SUCCESS. 667 tests pass.
- Blocked at this point (owner action): the Anthropic key is valid but the API answers "credit balance is too low", so no real-model run has happened yet ($0 spent); trace readback through the Neatlogs CLI needs a browser approval.
- Provenance and honesty notes:
  - All code so far was written in a Claude Code cloud session and its subagents.
  - These session transcripts will **not** be attached to Entire, because they contain private account information pasted during setup. Entire checkpoints start with clean coding sessions.
  - Everything above used the deterministic oracle/naive planners (no model calls, $0). Real Claude runs and Neatlogs traces are pending API keys.

## Demo
- Local: `uv sync && (cd ui && npm ci && npm run build) && uv run zerodrop serve --planner oracle`, then open http://127.0.0.1:8700 and start "Demo - everything goes wrong".

## Known limitations and next steps
- Real model runs and Neatlogs traces need `ZERODROP_ANTHROPIC_KEY` and `NEATLOGS_API_KEY` in the environment.

## Submission
- Confirmed requirements (from neatlogs.com/hackathon, read 2026-10-10):
  - Public quote post of the official neatlogs submission post on X: team, name, project, public repository, demo link. Window: Mon Oct 12, 7:00–11:55 PM IST.
  - Demo video of 3 minutes or less covering neatlogs, Entire and cfo.ai: architecture, implementation, runtime, reasoning and result.
  - Public repository with commits dated during the hackathon. All code written between Oct 10 12:30 PM IST and the deadline.
  - An accessible Entire checkpoint link plus its checkpoint ID.
  - A cfo.ai business plan covering pricing, costs, revenue and runway.
- Outstanding: everything above.
