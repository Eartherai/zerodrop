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
- 23:40 IST: **Submission docs, first complete drafts.** `README.md` (pitch, how it works, results, quick start, sponsor tools), `DEMO.md` (2:55 script with timestamps; each sponsor tool covered for architecture, implementation, runtime, reasoning, result), `BUSINESS.md` (customer, pricing, unit economics, break-even, runway scenario for cfo.ai; model cost per migration left as "pending measurement"), `SUBMISSION_CHECKLIST.md`, and six post drafts in `posts/` (two are marked NOT READY until real-model numbers exist). Nothing posted. Full-history secret scan: no leaks.

#### Self-assessment after this step (my own judgment, 1 to 10; not a measurement)
| Criterion | Weight | Score | Why | Next action |
|---|---|---|---|---|
| Agent that works | 30% | 6 | Engine, recovery and verifier are proven on 20 scenarios, but only with the scripted planner. No real-model run yet | **Weakest by weight.** Real Claude runs as soon as API credits are available |
| Sponsor tools | 25% | 6 | Neatlogs traces link to runs; Entire checkpoint exists; cfo.ai plan not built; no trace screenshots | Trace screenshots, cfo.ai plan (owner sign-in) |
| Video | 20% | 3 | Script only | Record dashboard assets, write recording steps |
| Building in public | 15% | 2 | Drafts only, nothing posted | Owner approval to post |
| Usefulness, originality | 10% | 7 | Clear problem, independent verifier is the differentiator | Business plan in cfo.ai |
- 23:50 IST: **Video assets, first pass.** Recorded with Playwright at 1920x1080 against the live dashboard (oracle and naive planners, $0): `evidence/video/s16-demo-chaos-oracle-dashboard.mp4` (run `run_113d17d09ecf`, verified SUCCESS, 24/24 checks, trace `808ee43d4bc2e50e1766d8e46549d0b8`), `evidence/video/s01-naive-false-success-dashboard.mp4` (run `run_6f860e513488`: agent claimed SUCCESS, verifier FAILED, 21/24), and six screenshots in `evidence/screenshots/`. Recording and voice-over steps for the owner: `evidence/video/RECORDING.md`. These are backup assets; the final take should use the Claude planner once it is measured.
- 23:55 IST: **Security review** of the API, public mode, static file serving, sandbox bind host, trace link and Docker kit: no high-confidence findings. Secret scan of the full history (24 commits at scan time): no leaks.
- 23:58 IST: **State at end of this stretch.** Still blocked on two owner actions: (1) API credits on the Anthropic key's organization (a one-token test call still answers "credit balance is too low"; $0 of the $25 budget spent), (2) browser approval for Neatlogs read access (two device codes expired unapproved). Not started because they need the owner: cfo.ai plan, final video, posts, making the repo public.
- Provenance and honesty notes:
  - All code so far was written in a Claude Code cloud session and its subagents.
  - These session transcripts will **not** be attached to Entire, because they contain private account information pasted during setup. Entire checkpoints start with clean coding sessions.
  - Everything above used the deterministic oracle/naive planners (no model calls, $0). Real Claude runs and Neatlogs traces are pending API keys.

### 2026-10-11 (Day 2)
- 00:45 IST: Ruling: the owner's Anthropic API account had no credit and the owner offered a Gemini API key instead, so Gemini was added as a second planner provider behind the existing backend protocol (`src/zerodrop/agent/gemini.py`, planner mode `gemini`, key `ZERODROP_GEMINI_KEY`). Claude Opus 5.5 remains the default planner. Every evaluation file records which planner and model produced it (`planner` and `model` in the summary and in each outcome). No Gemini run has been made yet: the adapter is tested only against fakes and the google-genai SDK over an offline transport.
- 03:10 to 04:05 IST: **First real-model runs (Gemini).** The Gemini planner was built test first by a coding agent and then reviewed by a second, adversarial agent; its one major finding (a blank `ZERODROP_GEMINI_KEY` was treated as configured, so the SDK could have fallen back to another Google key in the environment) was fixed with a failing test first. 751 tests pass. Runs at commit `d656f98`, all with Neatlogs tracing on, files in `evidence/runs/`:
  - **S01 clean, `gemini-3.8-flash`:** `run_5cf87ea5eab7`, verified **SUCCESS**, 24/24 checks, 6 model calls, $0.083 at list price, trace `a3e4055baf826c2f7c59859c739a7247`. Wall time 294 s; the same scenario took 42 s an hour earlier with the same 6 calls, so most of this is waiting on the free tier's 5 requests per minute.
  - **S16 demo chaos, `gemini-3.8-flash`:** `run_df3f40bbda91`, **FAILED**, and correctly so: the key's free tier allows 20 requests per day on this model and the quota ran out during the subscriptions migration. The engine halted, claimed FAILED (no false success), and the verifier listed exactly what was missing (333 subscriptions, 1,226 invoices). Trace `67a01d50a204521684e4849dc1a82def`.
  - **S16 demo chaos, `gemini-3.6-flash`** (separate daily quota): `run_aa73127580bb`, verified **SUCCESS**, 24/24 checks. The model wrote the v1 mappings, then after the API changed to v2 mid-run it diagnosed the change and rewrote the subscriptions and invoices mappings (1 replan); 4 retries on rate limits; 50 records found already committed after a timeout and not re-sent. 12 model calls, $0.082 at list price, 145 s. Trace `0652c95c208d53311eecccf73fe1cae0`.
  - **A real failure found by running it:** the first S16 attempt died on its first model call with a per-minute quota 429. Same lesson as fix 1 for NovaBill, now on the model side: a 429 with a retry hint is a wait, not a failure. Fix (test first): the Gemini backend waits as long as the server asks and retries, up to 12 times; a daily quota is not waited on.
  - **Limit, stated plainly:** these are three runs, not an evaluation. The full 20-scenario real-model evaluation needs roughly 150 to 250 model calls; the free tier gives 20 per model per day, so it needs a billed Gemini key or Anthropic credit. Total real-model spend so far: $0 charged (free tier); $0.33 at list price against the $25 cap.

## Demo
- Local: `uv sync && (cd ui && npm ci && npm run build) && uv run zerodrop serve --planner oracle`, then open http://127.0.0.1:8700 and start "Demo - everything goes wrong".

## Known limitations and next steps
- Real model runs and Neatlogs traces need `ZERODROP_ANTHROPIC_KEY` (or `ZERODROP_GEMINI_KEY` for `--planner gemini`) and `NEATLOGS_API_KEY` in the environment.

## Submission
- Confirmed requirements (from neatlogs.com/hackathon, read 2026-10-10):
  - Public quote post of the official neatlogs submission post on X: team, name, project, public repository, demo link. Window: Mon Oct 12, 7:00–11:55 PM IST.
  - Demo video of 3 minutes or less covering neatlogs, Entire and cfo.ai: architecture, implementation, runtime, reasoning and result.
  - Public repository with commits dated during the hackathon. All code written between Oct 10 12:30 PM IST and the deadline.
  - An accessible Entire checkpoint link plus its checkpoint ID.
  - A cfo.ai business plan covering pricing, costs, revenue and runway.
- Outstanding: everything above.
