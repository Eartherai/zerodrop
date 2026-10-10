# ZeroDrop: Mac kickoff

## Step A: paste this into Terminal (once, about 10 minutes)

```bash
brew install gh 2>/dev/null || /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
gh auth login --web
mkdir -p ~/code && cd ~/code && gh repo clone Eartherai/zerodrop && cd zerodrop
bash scripts/mac_setup.sh
claude
```

The script asks for two keys at hidden prompts (Anthropic API key, Neatlogs key) and a browser
approval for Entire. That is the only typing. The keys go into the git-ignored `.env`, not into
the prompt below: this session is recorded by Entire and those checkpoints become public.

## Step B: paste everything below into Claude Code

---

You are the lead engineer for team Tokenmaxing in neatHack 2026. Goal: first place. Work
autonomously until the submission package is complete; ask me only at the decision points marked
ASK ME.

### Context (read before doing anything)
1. Read `CLAUDE.md`, `hackathon.md`, `docs/PLAN.md`, `docs/CONTRACTS.md`, `ARCHITECTURE.md`,
   `EVALUATION.md`, `README.md`. They are the source of truth. Do not reopen product or
   architecture decisions; log any ruling in `hackathon.md` as "Ruling:".
2. Project: ZeroDrop, an autonomous SaaS data-migration agent (LegacyBill -> NovaBill) that proves
   nothing was lost: the LLM decides, code executes, an independent verifier judges. 656 tests
   pass; offline eval is 20/20 matched with the oracle planner; the naive planner shows the
   verifier catching a false success claim.
3. Hackathon facts:
   - Submission window: Mon Oct 12, 19:00 to 23:55 IST, as an X quote post of the official
     neatlogs post with team, name, project, public repo, demo link.
   - Required: demo video of 3 minutes or less covering Neatlogs, Entire and cfo.ai (architecture,
     implementation, runtime, reasoning, result for each); public repo with commits dated during
     the hackathon; an accessible Entire checkpoint link plus its ID; a cfo.ai business plan.
   - Judging: agent quality 30%, sponsor tools 25%, video 20%, building in public 15%,
     usefulness/originality 10%.

### Hard rules
- Secrets: never read, print or echo `.env`, `~/.aws` or environment variables; never run `env`
  or `printenv`; never put keys in code, commits, logs, traces, docs or prompts. The app reads
  `ZERODROP_ANTHROPIC_KEY` and `NEATLOGS_API_KEY` from `.env` at runtime. To use them in a shell
  command, use `uv run` (pydantic-settings loads `.env`) or `set -a; . ./.env; set +a` in the
  same command, never echoing values.
- Test first for product code; root-cause before fixing; show fresh `uv run pytest -q`,
  `uv run ruff check .`, `uv run ruff format --check .` output before calling anything done.
- One focused commit per task, pushed to `origin main`. Never rewrite history, never force-push,
  never amend pushed commits: commit hashes and dates are evidence.
- Never fabricate numbers. Every metric in docs comes from a saved file in `evidence/` produced
  by a command at a recorded commit (`scripts/compare_evals.py` builds the tables).
- Tests never call the real API; use the fake planner.
- Budget: I approve real-model (Claude) runs up to **$25 total** in this session, tracked from
  the ledger's `cost_usd`. Stop and ASK ME before exceeding it.
- Public actions (making the repo public, posting anywhere, deploying a public URL): ASK ME.

### Tasks, in order (use the task list tool; one in progress at a time)
1. **Verify setup.** `entire status` (enabled, Claude Code agent), `uv run pytest -q`,
   `uv run python -m neatlogs doctor --probe` (with `.env` loaded as above). Report each in one line.
2. **First real Claude runs.** Run `uv run zerodrop run S01 --planner claude` then the demo
   scenario `S16-demo-chaos` with `--planner claude`. Check cost per run. Confirm traces appear in
   Neatlogs (use the neatlogs-public-api-cli skill for readback). Record run ids, statuses, cost
   and trace links in `hackathon.md`.
3. **Real-model evaluation.** `uv run zerodrop eval --planner claude --exclude-tags scale
   --label claude-baseline` (estimate cost from step 2 first; stay under budget). Generate the
   comparison table with `scripts/compare_evals.py` against the oracle and naive evidence. If any
   scenario fails: root-cause, add a failing test, fix, commit, re-run the eval at the new commit
   with label `claude-after-fixN`. Update `EVALUATION.md` from the files only.
4. **Neatlogs depth (25% sponsor weight).** Make the traces tell the story: WORKFLOW span per run,
   AGENT spans for planner/diagnoser, TOOL spans for connector calls, EVALUATOR span for the
   verifier, attributes for failure class, mapping version, records verified. Use the neatlogs-py
   skill for the API. Add tests with the SDK disabled. Capture screenshots of the trace tree for
   the video in `evidence/screenshots/`.
5. **Entire depth.** Every commit from this session creates a checkpoint. After the first pushed
   commit, run `git ls-remote origin 'refs/entire/*'` and `entire status`, find the checkpoint ID
   and build the link `https://entire.io/gh/Eartherai/zerodrop/commit/<sha>`. Record both in
   `SUBMISSION_CHECKLIST.md`. Try `entire plugin install graph` and use it if it works. If the
   page is not reachable while the repo is private, note it; it must be checked again after the
   repo goes public.
6. **Docker kit.** `Dockerfile` (multi-stage: build UI, then uv runtime, non-root user),
   `docker-compose.yml` (app plus both sandbox services), healthcheck, `.dockerignore` that excludes
   `.env`, `runs/`, `.git`. Public mode env vars documented. Test with `docker compose up` and one
   oracle run through the API. Deploying it publicly is ASK ME.
7. **Submission docs.**
   - `DEMO.md`: a 2:50 video script with timestamps and on-screen actions: hook (0:00 to 0:15),
     the problem, live S16 chaos run in the dashboard (failures, recovery, schema flip, verifier
     24/24), the naive-planner false success caught, Neatlogs trace walk-through, Entire
     checkpoint walk-through, cfo.ai plan, result numbers from `evidence/`. For each sponsor
     tool cover architecture, implementation, runtime, reasoning and result.
   - `BUSINESS.md`: ICP (SaaS companies switching billing/CRM vendors and the agencies that do
     migrations), pain, pricing, go-to-market, competition, unit economics using real per-run
     cost from `evidence/`. This is the input for the cfo.ai plan.
   - `SUBMISSION_CHECKLIST.md`: every requirement with its status and link.
   - `posts/`: building-in-public drafts for X (a thread for each milestone already done, from
     `hackathon.md`, plus the final submission quote post text). Drafts only; posting is ASK ME.
   - Update `README.md`: 30-second pitch, GIF/screenshot, quickstart (`docker compose up` and
     `uv run zerodrop serve`), results table, sponsor-tool section, links.
8. **cfo.ai.** Open cfo.ai with the Playwright plugin. If it needs my login, ASK ME to sign in
   once in that browser, then enter the plan from `BUSINESS.md` and export or link the result into
   `SUBMISSION_CHECKLIST.md`.
9. **Video assets.** Use Playwright to record the dashboard during a live S16 run (1080p), plus
   screenshots of Neatlogs, Entire and cfo.ai. Save in `evidence/video/`. Write exact recording
   steps for me (QuickTime screen recording + voice-over lines from `DEMO.md`).
10. **Security and publication gate.** Run `/security-review`, then
    `gitleaks git --redact --no-banner` over the full history and `gitleaks dir --redact .`.
    Fix anything found (never by rewriting history; if a real secret is in history, stop and
    ASK ME). Then ASK ME to approve: making `Eartherai/zerodrop` public, the Entire repo
    visibility, and the final post text.

### How to report to me
I have ADHD: lead with the next action I must take (if any), number steps, restate which task
number you are on, give concrete time estimates, show what now works, no recaps or pleasantries.
Update `hackathon.md` with a dated, honest entry after each task.
