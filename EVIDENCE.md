# Evidence for judges

One page that maps what the neatHack rules ask for to a file, a run id or a trace in this
repository. Every number here is copied from a saved result file; nothing is estimated.
Where something is missing or weak, it says so.

Trace links have the form `https://app.neatlogs.com/traces/<trace id>`. They open for members
of the Neatlogs project, so each one also has a screenshot in `evidence/screenshots/`.

## 1. Before and after, with compared numbers (two Neatlogs traces)

Same scenario (S02, 1,901 records, no injected faults), same model (`gemini-3.1-flash-lite`),
before and after one fix. The fix: the dry run rejects a mapping that gives different source
records the same identity (commit `251cdd4`).

| | Before | After |
|---|---|---|
| Commit | `78d92da` | `251cdd4` |
| Run | `run_5d0171f3cddf` | `run_0a92f29d3a45` |
| What the agent believed | SUCCESS | SUCCESS |
| What the independent verifier found | **FAILED** | **SUCCESS** |
| Verifier checks failed | 10 of 24 | 0 of 24 |
| Writes the target treated as a record it already had | 1,898 of 1,901 | 0 |
| Model calls | 5 | 5 |
| Model cost at list price | $0.0109 | $0.0078 |
| Duration | 66.7 s | 11.1 s |
| Neatlogs trace | `75f5abadcc7c45344ee5639e556c2621` | `229e14d548b58ab6938fc70ec4009b34` |
| Screenshot | `evidence/screenshots/14-before-trace-s02-false-success.png` | `evidence/screenshots/15-after-trace-s02-verified.png` |
| Result file | `evidence/runs/S02-clean-demo-size-gemini-3.1-flash-lite-before-identity-guard.json` | `evidence/runs/S02-clean-demo-size-gemini-3.1-flash-lite.json` |

Root cause: the model wrote `external_id` as a constant,
so every record had the same id and the target kept one per entity. The engine saw 1,901
accepted writes and believed it was done.

Two more pairs from later passes on the same model, both a yen amount written 100 times too
large:

| Fix | Scenario | Before | After |
|---|---|---|---|
| Contradictory decimal parameters are an error (`933a7a9`) | S16, everything goes wrong | `run_14ded6031abe`: agent SUCCESS, verifier FAILED, JPY total 1,205,966,500 instead of 12,059,665. Trace `874c2d43e3b1995e85980d50264aed3f` | `run_e5294505e55c`: verified SUCCESS. Trace `f062910ba90fe51c92e716b566606abd` |
| Fixed decimals must fit the record's currency (`7b34f8c`) | S03, rate-limit storm | `run_acc170ca8785`: agent SUCCESS, verifier FAILED, JPY total 328,713,000 instead of 3,287,130. Trace `81e79b05a4b1b6f2c15dbd833823ef1f` | `run_30e7764a777f`: verified SUCCESS. Trace `03b05b42cf288529acd3ad3809141357` |

Files: `evidence/eval/*pass2.json`, `*pass3-after-fix4.json`, `*pass4-after-fix5.json`.
All five fixes with root cause and regression test: [`EVALUATION.md`](EVALUATION.md).

## 2. A failure-recovery run

S16, "everything goes wrong", planned by `gemini-3.6-flash`: `run_aa73127580bb`, commit
`d656f98`, trace `0652c95c208d53311eecccf73fe1cae0`.

| What went wrong during the run | What the agent did | Count |
|---|---|---|
| Target answered 429 with `Retry-After` | Waited what the server asked, then retried | 4 retries, 2.0 s waited |
| A write timed out after the target had committed it | Looked the records up before sending anything again | 1 ambiguous write, 50 lookups, 50 found, 0 duplicates |
| Target API changed from v1 to v2 mid-run | The model diagnosed the change and rewrote two mappings | 1 replan; subscriptions and invoices moved to mapping version 2 |

Result: 1,901 of 1,901 records written, verifier SUCCESS, 12 model calls, $0.082 at list
price, 145 s. File: `evidence/runs/S16-demo-chaos-gemini-3.6-flash.json`. Screenshots:
`evidence/screenshots/10-neatlogs-trace-s16-gemini.png` (trace),
`03-s16-finished-full.png` and `04-s16-certificate.png` (dashboard). The demo video replays
this run.

Crash and resume (the process is killed mid-run and restarted from the ledger) is covered by
S09, S10 and S20; each evaluation file reports its `crash_resumes` count.

## 3. Neatlogs

Rules: traces "should capture model and tool calls, state changes, retries, failures,
latency, token usage, and cost".

| Asked for | Where it is in a ZeroDrop trace | Code |
|---|---|---|
| Model calls, tokens, cost, latency | LLM spans from the wrapped model client, under AGENT spans for the planner and the diagnoser | `src/zerodrop/agent/` |
| Tool calls | TOOL spans for schema discovery, every batch write (`novabill.batch_write`, with attempt number), every lookup, and every tool the model calls (`tool.<name>`) | `src/zerodrop/engine.py`, `src/zerodrop/agent/llm.py` |
| State changes | One `state.<STATUS>` span per run status change, with `from_state` and `to_state` | `MigrationEngine._set_status` |
| Retries and failures | One `recovery.<class>` span per failure handled: transient (wait and retry), ambiguous write (look up first), contract change (replan), bad data (quarantine), auth, budget (halt) | `src/zerodrop/engine.py` |
| The verdict | Root WORKFLOW span: verifier status, the agent's own claim, false-success flag, checks failed, report hash. EVALUATOR span for the verifier with its input, verdict and a score (checks passed / total) | `MigrationEngine._finish`, `_verify` |
| The gate before any write | One GUARDRAIL span per dry run (`dry-run.<entity>`): what was checked, passed or not, share of valid samples, and the reason when it blocks a mapping | `MigrationEngine._guarded_dry_run` |
| What the model's tools returned | Each tool the model calls records its input and its result, so a rejected dry run or submission is readable in the trace, not only in the next model call | `src/zerodrop/agent/llm.py` |

Every run stores its trace id in the ledger; the dashboard links to it ("Open the trace in
Neatlogs"). Layer: `src/zerodrop/telemetry.py`.

| Screenshot | What it shows |
|---|---|
| `07-neatlogs-trace-s01-gemini.png` | Whole trace of a clean real-model run |
| `09-neatlogs-llm-span-s01-gemini.png` | One model call: prompt, tool calls, tokens, cost |
| `10-neatlogs-trace-s16-gemini.png` | The recovery run in section 2 |
| `11-neatlogs-trace-s07-gemini-grouped.png` | API change run, steps grouped under one span per entity |
| `13-neatlogs-trace-state-changes.png` | State-change spans (trace `f3cc2e33aa500430a9f221eeb9c468fa`) |
| `14-…` and `15-…` | The before and after pair in section 1 |
| `16-neatlogs-guardrail-blocks-refused-values.png` | A whole real-model trace on one page: state changes, three dry-run guardrails, the target refusing a batch, the guardrail then blocking the same mapping (`refused_reference`), the model's repair, the verifier, the verdict |
| `17-neatlogs-model-dry-run-told-refused-values.png` | Inside a repair: the model's own dry-run calls with input and result |

Each real-model false success has its trace id saved with the run (section 1), so the model
call that proposed the wrong mapping can be opened next to the verifier's result. Each cause
was then reproduced as a failing test before the fix.

## 4. Entire: checkpoints and entire-graph

| Item | Evidence |
|---|---|
| Checkpoint | ID `01M4KEGN3Q174N063453HK5XC6`, git ref `refs/entire/checkpoints/C6/01M4KEGN3Q174N063453HK5XC6`, pushed with the repo. Commits carry an `Entire-Checkpoint` trailer |
| Redaction | Secret and personal-data redaction configured in `.entire/settings.json` |
| entire-graph installed | Plugin v0.4.0; index of 145 files, 3,217 symbols, 12,502 relations; agent guide in `.entire/graph-agent.md`, loaded by `CLAUDE.md` and `AGENTS.md` |
| entire-graph used for a real change | Before making state changes visible in the trace: `entire graph search` located `_set_status` (`evidence/entire/search-state-changes.txt`) and `entire graph impact` listed its 17 callers (`evidence/entire/impact-set-status.txt`). The change is commit `1838455` |
| entire-graph on a commit | Entities changed by fix 5: `evidence/entire/commit-7b34f8c-entity-changes.txt` |

Weak point, stated plainly: the checkpoint covers the first part of the build session, not
all of it, and its entire.io page only works once the Entire-hosted mirror is pushed and made
public (owner action, see [`SUBMISSION_CHECKLIST.md`](SUBMISSION_CHECKLIST.md)).

## 5. cfo.ai: pricing, costs, revenue, runway

Built in cfo.ai from [`BUSINESS.md`](BUSINESS.md); screenshot
`evidence/screenshots/08-cfo-ai-monthly-forecast.png`.

| | cfo.ai base case | cfo.ai with growth halved to 10% a month |
|---|---|---|
| Break-even month | March 2027 | March 2027, by only $215 |
| Lowest cash balance | $35,861 | $35,213 |
| Cash at month 24 | $1.88M | $587K |

Unit economics as cfo.ai computed them: a $499 migration costs $36.77 to deliver (92.6%
margin).

Pricing is per verified migration, so revenue is tied to the same verifier result the product
shows. `BUSINESS.md` has the six scenarios cfo.ai computed and where its agent pushed back on
the plan (growth rate, flat fixed costs, failed runs not costed), kept in.

## 6. Does the agent work: every evaluation, including the bad ones

"Matched" means the independent verifier's result equals the outcome that scenario should
have (SUCCESS, PARTIAL_SUCCESS with records quarantined, or WAITING_FOR_APPROVAL).

| Evaluation | Planner | Commit | Matched | False success claims | Model calls | Cost (list) |
|---|---|---|---|---|---|---|
| Baseline | scripted | `c4766e2` | 19 of 20 | 0 | 0 | $0 |
| After fix 1 (rate-limit waits) | scripted | `8c0a017` | 20 of 20 | 0 | 0 | $0 |
| After fix 2 (`Retry-After`) | scripted | `574aa2b` | 20 of 20 | 0 | 0 | $0 |
| Per-scenario real-model runs | 5 Gemini Flash models | four commits, `d656f98` to `251cdd4` | 20 of 28 runs, all 20 scenarios | 5 (all before fix 3) | 176 | $0.91 |
| Pass 1 | `gemini-3.1-flash-lite` | `f858712` | 18 of 18 | 0 | 111 | $0.2233 |
| Pass 2 | `gemini-3.1-flash-lite` | `e65cc45` | 17 of 18 | 1 (led to fix 4) | 117 | $0.2472 |
| Second model | `gemini-3.5-flash-lite` | `e65cc45` | 18 of 18 | 0 | 119 | $0.4186 |
| Pass 3 | `gemini-3.1-flash-lite` | `933a7a9` | 15 of 18 | 1 (led to fix 5) | 108 | $0.2278 |
| Pass 4 | `gemini-3.1-flash-lite` | `7b34f8c` | 10 of the 10 that ran | 0 | 57 | $0.1203 |
| **All 20 scenarios, after fix 5** | `gemini-3.5-flash-lite` | `1838455` | **20 of 20** | **0** | 138 | $0.4570 |
| **All 20 scenarios, final code (after fix 6)** | `gemini-3.5-flash-lite` | `6c07c9f` | **20 of 20** | **0** | 141 | $0.4650 |
| Scripted regression after fixes 3, 4, 5, 6 | scripted | `251cdd4`, `933a7a9`, `7b34f8c`, `6c07c9f` | 18 of 18 each | 0 | 0 | $0 |

Real-model cost of the saved runs above and the four in `evidence/experiments/`: $3.13 at list
price, $0 charged (free tier).

Reading it honestly:
- Seven real false success claims in total. The verifier caught all seven. Each of the three
  causes was fixed test first, and no later run repeated a fixed cause.
- Pass 3 also had one run the model never repaired (S12: it sent a price id where the plan
  code belongs, three times; the run ended FAILED and said FAILED) and one halted by a
  provider 503. Both led to changes: the engine now remembers values the target refused and
  fails a repair that repeats them before any write, and the model client retries a 503. The
  first of these has not yet been seen rescuing a real run (`EVALUATION.md`, improvement 6).
- The two rows to weigh: every scenario, real model, 20 of 20, twice in a row, the second
  time on the final code.
- Pass 4 was cut short: the free tier's daily quota ran out after ten scenarios. The other
  eight halted, said FAILED, and the verifier agreed. They are counted as not run.
- One pass per commit. This shows what happened, not a failure rate.
- All real-model runs used Gemini Flash models on the free tier (nothing was charged). No
  Claude run exists: the Anthropic account had no credit during the hackathon.

Files: `evidence/eval/` (one JSON and one Markdown per evaluation), `evidence/runs/` (one
JSON per single run). Reproduce the scripted ones with no keys:
`uv run zerodrop eval --planner oracle --label my-run`.

## 7. Built during the hackathon, in public

| Item | Evidence |
|---|---|
| Commit dates | First commit `104ff06` on Oct 10, 15:38 IST, after the window opened at 12:30 IST. More than 50 commits since (`git log`), one per task. History never rewritten or force-pushed |
| Build log | [`hackathon.md`](hackathon.md): dated entries, including what failed |
| Posts | Drafts in `posts/`; links to the posted versions are in `SUBMISSION_CHECKLIST.md` once posted |
| Tests | 766 Python tests and 61 UI tests; `uv run pytest -q` |
| Run it yourself | `docker compose up --build`, then http://127.0.0.1:8700 and start "Demo - everything goes wrong". No keys needed |
