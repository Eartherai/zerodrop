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
  verifier disagreed (the naive planner demonstrates one: dates read in the wrong time zone).
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

## 7. Evidence so far (all reproducible from `evidence/`)
`EVIDENCE.md` is the index: it maps every item the rules ask for to a file, run id or trace.
- Scripted (oracle) evaluation: baseline `c4766e2` 19/20 (S03 failed); fix 1 `8c0a017` and fix 2
  `574aa2b` 20/20; 18/18 after each of fixes 3 to 6. Tables in `EVALUATION.md`.
- **Real model (Gemini planner):** full passes in `evidence/eval/` (run with
  `GEMINI_MODEL=<id> uv run zerodrop eval --planner gemini --label <label>` after loading `.env`
  into the shell with `set -a && . ./.env && set +a`, which also turns tracing on); single runs
  per scenario in `evidence/runs/` (table: `uv run python scripts/runs_table.py`); four experiment
  runs in `evidence/experiments/` (`scripts/repro_refused_reference.py`). All 20 scenarios on
  `gemini-3.5-flash-lite`: 20 of 20 at `1838455` and again at `6c07c9f` (final code). Seven real false successes in total, all caught, three
  causes fixed (`251cdd4`, `933a7a9`, `7b34f8c`). Quota-halted runs with model calls are kept;
  runs that made no model call are deleted. The Anthropic key has no credit, so no Claude run
  exists. Both Gemini keys are on the free tier; daily quotas reset at 12:30 IST. The second key
  is `ZERODROP_GEMINI_KEY_2` (use it with `ZERODROP_GEMINI_KEY="$ZERODROP_GEMINI_KEY_2"`).
- Neatlogs: every run is traced; trace ids are in the run files and the dashboard links to
  `https://app.neatlogs.com/traces/<id>`. Captures in `evidence/screenshots/07` to `17`
  (index in `evidence/screenshots/README.md`), including a before and after pair (14, 15).
- Entire: checkpoint `01M4KEGN3Q174N063453HK5XC6` exists as a git ref and is pushed to GitHub.
  Commits carry a hand-written `Entire-Checkpoint` trailer; do **not** run
  `entire session attach` again (later turns of the session have not been reviewed for publication). The entire.io page
  is a 404 because the site only knows the Entire-hosted repo `/et/hackathone/hackathon`; the
  owner must run `git remote add entire entire://aws-ap-south-1.entire.io/et/hackathone/hackathon`
  and `git push entire main 'refs/entire/*:refs/entire/*'` (blocked for the agent).
  entire-graph v0.4.0 is installed and indexed; output in `evidence/entire/`.
- cfo.ai: plan built in the owner's workspace; results and criticism are in `BUSINESS.md`.
- Demo video: `evidence/video/zerodrop-demo.mp4` and `zerodrop-demo-x.mp4` (source project
  outside the repo at `~/Desktop/anti/videos/zerodrop-demo`, rendered with HyperFrames, local
  Kokoro voice).

## 8. Remaining work (in order)
1. Owner actions, listed in order in `SUBMISSION_CHECKLIST.md` ("What only the owner can do").
2. After 12:30 IST on Oct 12 (quota reset): run the fix 6 check on the model that failed,
   `GEMINI_MODEL=gemini-3.1-flash-lite uv run python scripts/repro_refused_reference.py --guard off|on ...`,
   and record the result in `EVALUATION.md` whatever it is.
3. Before the repo goes public: the Entire checkpoint was audited on Oct 11 (see `hackathon.md`).
   It holds only the first 13 turns of the Mac session: no keys, no images, no personal details,
   but it does show local folder paths. Later turns (which do contain personal details) are NOT
   in it; do not re-attach the full session without reviewing it first.
4. Re-run `/security-review` and `gitleaks git --log-opts=--all --redact` right before going public.
5. Owner approval for: repo visibility, posts in `posts/`, the submission quote post.

## 9. Rules that stay in force
- Never read, print or echo `.env`, `~/.aws` or environment variables; never run `env` or
  `printenv`; never put keys in code, commits, logs, traces, docs or prompts. Session
  transcripts become public through Entire.
- Test first; root cause before fixing; show fresh test output before claiming done.
- One focused commit per task; never rewrite or force-push history (hashes and dates are evidence).
- Never fabricate numbers. Tests never call the real API.
- Ask the owner before anything public: repo visibility, posts, public deployment.
- Owner follow-ups after the hackathon: key hygiene, tracked privately by the owner.
