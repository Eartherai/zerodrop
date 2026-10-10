# ZeroDrop: full project context (handoff)

Everything a new Claude Code session needs to continue the neatHack 2026 build. No secrets are
in this file or anywhere in the repo: keys live only in the git-ignored `.env`.

## 1. Team and hackathon
- Team **Tokenmaxing**, one builder (GitHub: Eartherai). Repo: `github.com/Eartherai/zerodrop`
  (private until the security gate passes and the owner approves making it public).
- Build started Sat Oct 10, 12:30 IST. **Submission: Mon Oct 12, 19:00 to 23:55 IST**, as a public
  X quote post of the official neatlogs post with team, name, project, public repo and demo link.
- Required deliverables:
  1. Demo video of 3 minutes or less covering **Neatlogs, Entire and cfo.ai**: architecture,
     implementation, runtime, reasoning and result for each.
  2. Public repo with commits dated during the hackathon.
  3. Accessible **Entire checkpoint link plus its ID**.
  4. A **cfo.ai business plan**.
- Judging weights: agent 30%, sponsor tools 25%, video 20%, building in public 15%,
  usefulness/originality 10%.

## 2. The product
ZeroDrop is an autonomous SaaS data-migration agent that proves nothing was lost:
**the LLM decides, code executes, an independent checker judges.**
- Source sandbox **LegacyBill** (port 8701), target sandbox **NovaBill** (port 8702), with a
  seeded FaultPlan: rate_limit (429 + Retry-After), server_error, timeout_after_write,
  partial_accept, schema_flip v1 -> v2 (plan_code replaced by a price_id lookup; invoice
  currency must be lowercase), auth_revoke (token rotation), slow.
- The planner (Claude) writes a mapping in a whitelisted DSL; the engine executes it
  deterministically with idempotent writes recorded in a SQLite (WAL) ledger; on failure the
  diagnoser classifies and replans; crash and resume never re-sends committed records.
- The **verifier never imports** the engine, DSL, ledger or agent. It re-reads both systems and
  checks the preservation contract. Run statuses: SUCCESS, PARTIAL_SUCCESS, FAILED,
  WAITING_FOR_APPROVAL. A **false_success_claim** is when the engine said SUCCESS and the
  verifier disagreed (the naive planner demonstrates one: JPY amounts off by 100x).
- Dashboard: Vite + React + TypeScript + Tailwind, served by FastAPI; live events over SSE;
  `?run=<id>` deep link; public mode with access code, hourly run cap and spend cap.

## 3. Stack and models
- Python 3.13, uv, FastAPI, Pydantic v2, pydantic-settings, httpx, jsonschema, typer, pytest,
  Hypothesis, ruff.
- Anthropic SDK with `claude-opus-5-5` (default). Adaptive thinking is always on; effort is set
  per call; forced tool_choice returns 400, so the planner relies on instructions. Pricing used
  for cost tracking: $4 / $20 per million input / output tokens, cache reads $0.20.
  Config refuses models outside the claude-*-5 families.
- Second planner provider: google-genai SDK with `gemini-3.8-flash` (`gemini_model`), planner
  mode `gemini`, adapter in `src/zerodrop/agent/gemini.py`. Not yet run against the live API.
- Neatlogs SDK 1.4.26: `init`, `wrap`, spans (WORKFLOW, AGENT, TOOL, CHAIN, EVALUATOR),
  `flush`, `shutdown`; `python -m neatlogs doctor --local` / `--probe`. Telemetry no-ops when
  `NEATLOGS_API_KEY` is unset.
- Entire CLI 0.11.4: checkpoints are git refs under `refs/entire/checkpoints/*`, pushed with the
  branch. Repo config is committed in `.entire/settings.json` with redaction rules for
  Anthropic, Neatlogs and AWS key patterns plus email and phone. Link format:
  `https://entire.io/gh/Eartherai/zerodrop/commit/<sha>`.

## 4. Runtime settings (names only; values in `.env`)
- `ZERODROP_ANTHROPIC_KEY`: the app's Anthropic API key, deliberately not `ANTHROPIC_API_KEY`
  so Claude Code's own subscription login stays separate.
- `ZERODROP_GEMINI_KEY`: Gemini API key for `--planner gemini` (optional).
- `NEATLOGS_API_KEY`: Neatlogs project key.
- Limits per run: 30 LLM calls, $1.50, 900 s wall clock, 3 replans, 6 attempts per request,
  40 rate-limit waits. Batch size 50, HTTP timeout 2 s.

## 5. Repository map
- `src/zerodrop/models.py`: frozen contracts (do not change without a "Ruling:" entry).
- `sandbox/`, `dsl.py`, `validation.py`, `connectors/`, `ledger.py`, `classify.py`,
  `engine.py`, `verifier/verify.py`, `agent/` (llm, planner, diagnoser, prompts, fake planners),
  `scenarios.py` + `scenarios/scenarios.yaml` (S01 to S20; demo is `S16-demo-chaos`),
  `runner.py`, `cli.py` (scenarios, run, eval, sandbox, serve), `api.py`, `public_mode.py`,
  `telemetry.py`, `config.py`; `ui/`.
- Docs: `docs/PLAN.md`, `docs/CONTRACTS.md`, `docs/UI.md`, `ARCHITECTURE.md`, `EVALUATION.md`,
  `hackathon.md` (dated build log), `README.md`, `CLAUDE.md`.
- `scripts/compare_evals.py` builds evidence tables; `scripts/mac_setup.sh` sets up a Mac.

## 6. Commands
```
uv run pytest -q
uv run ruff check . && uv run ruff format --check .
uv run zerodrop scenarios
uv run zerodrop run S16-demo-chaos --planner oracle|naive|claude|gemini
uv run zerodrop eval --planner claude --exclude-tags scale --label <label>
uv run zerodrop serve            # dashboard on the printed port
uv run python scripts/compare_evals.py evidence/eval/A.json evidence/eval/B.json
```

## 7. Evidence so far (all reproducible from `evidence/eval/`)
- Baseline at `c4766e2`: 19/20 scenarios matched; S03 (rate-limit storm) FAILED.
- Root cause: 429 waits consumed the general retry budget. Fix 1 (`8c0a017`): separate 429
  budget, 20/20. Fix 2 (`574aa2b`): wait exactly Retry-After, 20/20, S03 12.1 s -> 2.8 s.
- 656 tests pass. Dashboard verified in Chromium on S16: 7 injected failures, 16 recovery steps,
  mapping v1 -> v2, 50 records found already committed and 0 re-sent, verifier 24/24 checks.
- Neatlogs: traced oracle runs S07 and S16 arrived in the dashboard (readback was still
  processing at probe time).
- **Not done yet: any run with the real Claude planner.** No real-model numbers exist; do not
  write any until they are measured.

## 8. Remaining work (in order)
1. Real Claude runs (S01, S16) and a real-model eval; fix failures test-first with evidence.
2. Richer Neatlogs spans and trace screenshots.
3. Entire checkpoint from a clean session; record the link and ID.
4. Docker kit (Dockerfile, compose, healthcheck, `.dockerignore`).
5. `DEMO.md` (2:50 script), `BUSINESS.md`, `SUBMISSION_CHECKLIST.md`, `posts/` drafts, README.
6. cfo.ai business plan (owner signs in once).
7. Video assets and recording steps.
8. `/security-review`, gitleaks over full history, then owner approval to go public and post.

## 9. Rules that stay in force
- Never read, print or echo `.env`, `~/.aws` or environment variables; never run `env` or
  `printenv`; never put keys in code, commits, logs, traces, docs or prompts. Session
  transcripts become public through Entire.
- Test first; root cause before fixing; show fresh test output before claiming done.
- One focused commit per task; never rewrite or force-push history (hashes and dates are evidence).
- Never fabricate numbers. Tests never call the real API.
- Ask the owner before anything public: repo visibility, posts, public deployment.
- Owner follow-ups after the hackathon: rotate the Neatlogs key and the AWS keys that were shared
  in an earlier chat, and delete the AWS root access key.
