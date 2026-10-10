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
- 18:00–18:40 IST: integration: 20 seeded scenarios, runner, `zerodrop` CLI (run, eval, sandbox, serve), dashboard API with live event streaming. End-to-end checks: S01 clean -> verified SUCCESS; S07 breaking API change -> mapping v1 to v2, verified SUCCESS; the naive (flawed) planner on S01 -> engine claimed SUCCESS, **verifier reported FAILED** (JPY totals 100x).
- 18:29 IST: **baseline evaluation** (oracle planner, commit c4766e2): 19/20 scenarios matched the expected verified outcome. **S03 rate-limit storm failed**: six consecutive 429s exhausted the attempt budget and 66 invoices were never written. The verifier caught it; the agent's own claim was also FAILED (no false success). Evidence: `evidence/eval/20261010T122907Z-oracle-harness-check.md`.
- 19:00 IST: **fix 1** (commit 8c0a017): 429 waits get their own budget. Re-evaluation at that commit: 20/20 matched, 0 false success claims.
- 19:10 IST: **fix 2** (commit 574aa2b): wait exactly the server's Retry-After instead of a longer own backoff. S03 12.1 s -> 2.8 s; outcomes unchanged (20/20). Details and tables: `EVALUATION.md`.
- 18:35 IST: dashboard verified in a real browser against a live S16 demo-chaos run (light and dark themes): 7 failures, 16 recovery steps, subscription and invoice mappings v1 -> v2, 50 committed records found after a timeout (0 re-sent), verifier 24/24 checks passed.
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
