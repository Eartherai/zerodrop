# ZeroDrop: working rules for coding agents

## Source of truth
- Approved plan: docs/PLAN.md. Frozen interfaces: docs/CONTRACTS.md and src/zerodrop/models.py. Do not reopen product or architecture decisions; if something is wrong, make the smallest consistent fix and log it as "Ruling:" in hackathon.md.

## Engineering
- Test first for product code (pytest; Hypothesis for invariants). Find the root cause before fixing a failure. Show fresh test output before saying something is done.
- Work in place on the current branch: no git worktrees. One focused commit per task.
- Tests never call the real Anthropic API; use the fake planner/client. Real-model runs only when the user approves.
- Commands: `uv run pytest -q`, `uv run ruff check .`, `uv run ruff format --check .`.

## Secrets: this repo and its coding-session transcripts become public
- Never read, print or echo .env files, ~/.aws, or environment variables; never run env or printenv; never put keys in prompts, plans, logs, traces or commits.
- The app reads ZERODROP_ANTHROPIC_KEY and NEATLOGS_API_KEY from the environment or a git-ignored .env at runtime only.
- Fixtures use synthetic data only.

## Docs lookup
- Anthropic SDK: the claude-api skill. Neatlogs: the neatlogs-py / neatlogs-py-openai / neatlogs-public-api-cli skills. Other libraries: Context7 with short generic queries (never include project code, data or secrets).

<!-- entire-graph:begin -->
This repo has the entire-graph code graph installed. Before exploring code with
grep/find/whole-file reads, read .entire/graph-agent.md — resolution-first guidance
for using graph retrieval, focused source inspection, and verification.
@.entire/graph-agent.md
<!-- entire-graph:end -->
