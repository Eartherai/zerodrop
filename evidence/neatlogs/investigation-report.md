# Neatlogs investigation of the ZeroDrop traces (Oct 12, 2026, 08:42 to 08:49 IST)

What this file is: the report Neatlogs' own Investigate agent (Deep mode, model "Neatlogs Pro")
wrote after going through the `zerodrop-migration` traces in our project, copied from the
dashboard thread "Investigate Zerodrop Migration Traces". It then raised the three issues as
incidents on the Incidents board. Screenshots: `evidence/screenshots/20` to `29`.

Our notes on what it got right and wrong are at the end. Nothing below the two rules is ours.

---

## What we asked

> Start an investigation on every zerodrop-migration trace from the last 3 days and raise the
> critical incidents. Look for: (1) runs whose root span output says "False Success Claim: true"
> - the agent claimed SUCCESS but the independent-verifier EVALUATOR span reported FAILED;
> (2) runs that ended FAILED or halted, including model-provider errors on LLM spans; (3) runs
> stuck repeating recovery.CONTRACT. For each distinct problem give the number of affected
> traces, the root cause from the spans (planner LLM output and its mapping, dry-run,
> novabill.batch_write, independent-verifier), the evidence traces, and a recommended fix.

## What Neatlogs reported (verbatim)

**Issue 1: False Success Claims**
- Affected Traces: 10 traces (identified via search for "False Success Claim: true").
- Evidence Traces: `46ae629e646825d80d8e6d4fb6e11755`, `874c2d43e3b1995e85980d50264aed3f`,
  `5332bd4b8240c164edcbd1b79c6322b9`, `81e79b05a4b1b6f2c15dbd833823ef1f`,
  `e95e9393b3b6ea9c8864834f5bd8ec2f`
- Root Cause Analysis: The root span output reveals a mismatch between the migration agent's
  internal success criteria and the independent verifier's checks. For example, in trace
  46ae629e646825d80d8e6d4fb6e11755, the agent claimed SUCCESS (Agent Claimed Status: SUCCESS)
  and wrote 154 records. However, the evaluator span executed 24 validation checks and found 12
  failures (Checks Failed: 12), triggering the False Success Claim: true flag. The
  planner/dry-run phase currently fails to run these validation checks locally prior to
  finalizing the migration.
- Recommended Fix: Integrate the evaluator's 24-point validation suite directly into the
  planner.plan dry-run phase. The agent should be blocked from emitting a SUCCESS status unless
  Checks Failed == 0 during pre-flight dry-run execution.

**Issue 2: Failed or Halted Runs & Model-Provider Errors**
- Affected Traces: At least 1 trace explicitly verified in the analyzed sample
  (`1ac28c3c5043ae13a42900f9cffc10f3`), with up to 220 total workflow traces potentially affected.
- Uncertainty & Limitations: Broad semantic searches for "model provider error", "rate limit",
  or "timeout" returned 0 direct hits in the gathered snippets. Due to coordination budget
  limits, some background sub-tasks failed or stopped before completing a full database-wide
  scan of all 220 traces. Consequently, exact model-provider error messages could not be fully
  extracted.
- Root Cause Analysis: Halted or failed traces are closely linked to execution loops. The agent
  exhausts its token budget or hits context-length limits due to repeated retry logic, causing
  the entire workflow to halt with an Execution Failed error.
- Recommended Fix: Implement strict global token limits and a maximum iteration cap (e.g., max
  3 replan/repair attempts) on the workflow. If the cap is reached, fail gracefully with a
  descriptive error instead of exhausting context windows.

**Issue 3: Runs Stuck Repeating recovery.CONTRACT**
- Affected Traces: 10 traces (identified via search for "recovery.CONTRACT").
- Evidence Traces: `1ac28c3c5043ae13a42900f9cffc10f3`, `3cba2c6e8dde0a5f1529e6f69aeb5bd7`,
  `46d19e723244bfd21ebb3d2b31029164`, `5c638b85c1ddf46307f24e7bb72f39e7`,
  `0157e5812f9e77b89f1d1ae1c8defa6e`
- Root Cause Analysis: These traces exhibit infinite loops between the planner.repair and
  contract-diagnoser spans. [...] This leads the agent to repeatedly invoke recovery.CONTRACT
  with the same parameters, resulting in an infinite execution loop.
- Recommended Fix: Introduce state tracking into the planner.repair loop. If recovery.CONTRACT
  is invoked with the same input parameters or contract violations more than twice, the agent
  must halt and escalate the mismatch to a manual human-in-the-loop review queue.

## The incidents it raised

| Incident | Severity | Category | Id |
|---|---|---|---|
| zerodrop-migration: False Success Claims (Agent SUCCESS, Evaluator FAILED) | Critical | migration_validation_mismatch | `abf51057-b0d0-48b6-851b-7808682d9c65` |
| zerodrop-migration: Failed or Halted Runs & Model-Provider Errors | High | execution_failure | `a8978690-78c6-4dd7-b14a-cecafb7a0754` |
| zerodrop-migration: Runs Stuck Repeating recovery.CONTRACT Loop | High | infinite_loop | `fd05c880-efe4-4d3e-b1e9-ac0f874e9613` |

Each incident's own "Investigate" run then produced a root cause, evidence and a recommended
action (`incident-false-success-fix-prompt.md` is the one for the critical incident, as handed
to a coding agent).

---

## Our notes: what was right, what was wrong

Checked against `evidence/eval/*.json` and `evidence/runs/*.json`, which store each run's trace id.

**Issue 1 is right, and its evidence is exact.** All five evidence traces are real-model false
successes we had recorded, and they cover all three causes:

| Trace | Our run | Scenario | Cause |
|---|---|---|---|
| `46ae629e…` | `run_00ec744c49a4` | S20, Oct 11 | same id for every record (fix 3) |
| `5332bd4b…` | `run_68722c4ecf72` | S17, Oct 11 | same id for every record (fix 3) |
| `e95e9393…` | `run_a0d8eb72824f` | S05, Oct 11 | same id for every record (fix 3) |
| `874c2d43…` | `run_14ded6031abe` | S16, pass 2 | both amount parameters, yen x100 (fix 4) |
| `81e79b05…` | `run_acc170ca8785` | S03, pass 3 | fixed decimals on yen records (fix 5) |

Its recommended fix is where we differ. Moving the verifier's checks into the agent would end
the verifier's independence, which is the point of the product. What we did instead is in
`EVALUATION.md` (fixes 3, 4, 5 and 7): the dry run rejects each of those mappings, and the
engine now asks the independent verifier about the first batch before writing the rest.

The follow-up investigation on the incident itself was weaker: it says the root cause "is not
established because the repository code has not been inspected", and the three traces it cites
as examples (`509754ef…`, `0a9fa961…`, `b16fb4d5…`) are healthy runs whose root output says
False Success Claim: false. Its fourth recommended step is the one we implemented.

**Issue 3 names a real problem with the wrong evidence.** Four of the five traces are runs in
our files, and all four ended verified SUCCESS after exactly one replan when the target API
changed version (`run_795c81d8034d`, `run_1a495871e794`, `run_aaba62ebd5ca`, `run_7625953b6400`).
That is the recovery working, not a loop, and nothing is infinite: repairs are capped at three
rounds. The run that really did repeat itself is trace `a5b9ad484e4fac9e428f5eb00ba46088`
(`run_ab090e6c2fc6`, pass 3, S12), which Neatlogs did not list. The recommended state tracking
is what fix 6 does.

**Issue 2 is mostly a misread.** The caps it recommends already exist in code (30 model calls,
$1.50, three repair rounds, 15 minutes) and halts end as FAILED with a reason. Its example
trace is a verified-success run that contains an errored span: our scenarios inject target
faults on purpose, and a model call that hit a rate limit is retried. So "has an ERROR span"
does not mean "the run failed" here. The real halts were the model provider: a per-minute 429
(waited on since `d656f98`), a 503 (retried since `6c096ad`) and the free tier's daily quota.
