# The fix prompt Neatlogs generated for the critical incident

Copied on Oct 12, 2026 with the incident's "Copy prompt to clipboard" button (the same content
its "Fix in → Claude Code" action hands to a coding agent). Only this heading and the note at
the end are ours. Screenshot of the menu: `evidence/screenshots/26-neatlogs-incident-fix-in-coding-agent.png`.

---

# Task

Address the following critical-severity issue in this codebase. Read the Context to understand
what is failing and why, then apply the changes described in the Fix section. When you need
production evidence (real span payloads, errors, timings), use the Neatlogs MCP tools on the
trace IDs in References [...]

# Context

## zerodrop-migration: False Success Claims (Agent SUCCESS, Evaluator FAILED)

**Severity:** Critical · **Category:** Migration validation mismatch · **Pattern:** Silent degradation · **Confidence:** 55%
**Status:** Open · **Source:** Neatlogs Agent · **Created:** 2026-10-12 03:19 UTC

## Root cause

Root cause is not established because the repository code has not been inspected. We observe a
mismatch where the migration agent claims a successful migration, but the independent-verifier
evaluator span reports multiple validation failures in traces such as
{{trace:509754ef50864d5aabbbe1327815dd39}} on Oct 11 17:48 UTC. It is hypothesized that the
dry-run phase fails to execute validation checks locally before finalizing the migration, but
the exact orchestration logic remains unknown.

## Evidence

The system flagged multiple traces with a false success claim. In traces like
{{trace:509754ef50864d5aabbbe1327815dd39}} on Oct 11 17:48 UTC,
{{trace:0a9fa961f2a27bd8112473fba6707bf8}} on Oct 11 18:20 UTC, and
{{trace:b16fb4d59904d8be5a0867f80e0addad}} on Oct 11 17:43 UTC, the migration agent claimed a
successful execution status. However, the independent-verifier evaluator span executed
validation checks and identified multiple failures [...] A likely hypothesis is that the
`planner.plan` dry-run phase does not run or enforce the 24-point validation suite locally
before finalizing the migration status.

# Fix

## Inspect orchestration logic and integrate validation checks into the dry-run phase

**Steps**

1. Locate and inspect the orchestration code for the `planner.plan` dry-run phase and the
   independent-verifier evaluator.
2. Confirm whether the 24-point validation suite can be executed locally within the planner
   phase prior to finalizing the migration.
3. If feasible, integrate the validation suite into the dry-run phase and configure the agent
   to block a `SUCCESS` status if any validation checks fail.
4. If local execution is not feasible, implement a blocking pre-commit validation step that
   queries the evaluator before claiming success.

# References

- **triage_id:** `abf51057-b0d0-48b6-851b-7808682d9c65`
- **thread_id:** `b870673f-1aaf-4c20-8b3f-d978017f553f`

# After the fix

Once work on this fix is done, update its status on Neatlogs so the team's board stays
accurate. [...] `resolved` — the fix is shipped and the failure pattern has been confirmed gone
(via traces, evals, or user signal).

---

## What we did with it

- Steps 1 and 2: the verifier compares the target with the source and with golden records the
  agent must never see, so it cannot run inside the planner. Step 3 is not feasible without
  ending its independence.
- Step 4 is commit `286c728`: after the first batch of each mapping, the engine asks the
  independent verifier to re-read exactly those records (`spot_check`) and halts if they do not
  match. Before and after traces: `c2fce46175145a8e7473297151bf04da` (182 records written,
  false success claim true) and `35bb1a754af7df0c21393e7118cd203e` (stopped after 28, the agent
  reports FAILED itself). Files: `evidence/experiments/early-check-*.json`,
  `evidence/screenshots/18` and `19`.
- The three example traces in the prompt are healthy runs (False Success Claim: false). The
  incident's original five evidence traces are the right ones; see `investigation-report.md`.
- Status set to Resolved on the board on Oct 12 (`evidence/screenshots/21`, `22`).
