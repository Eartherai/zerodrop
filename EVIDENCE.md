# Evidence for judges

One page that maps what the neatHack rules ask for to a file, a run id or a trace in this
repository. Every number here is copied from a saved result file; nothing is estimated.
Where something is missing or weak, it says so.

The result rows in section 7 and the totals (seven false successes, 182 and 28 records, $4.06)
are recomputed from those files on every push by
[the ci workflow](https://github.com/Eartherai/zerodrop/actions/workflows/ci.yml)
([`scripts/verify_numbers.py`](scripts/verify_numbers.py)); it fails if a number here stops
matching a file. The same workflow runs the tests and three runs of the agent with scripted
planners (no model, no keys).

**For judges, in 60 seconds:**

| Criterion | What to look at | What it does not show |
|---|---|---|
| Agent (30%) | 20 of 20 scenarios on a real model in each of three full passes; 18 of 18 on the model that made the mistakes; 7 real false successes, all caught ([section 7](#7-does-the-agent-work-every-evaluation-including-the-bad-ones)). Try it: `EARLY_CHECK=false uv run zerodrop run S01-clean --planner naive` | Sandbox systems, one pass per commit, no Claude run |
| Sponsor tools (25%) | neatlogs: 3 incidents raised on our traces, all resolved, 2 code changes ([section 1](#1-neatlogs-incidents-identified-and-resolved)). Entire: public page https://entire.io/et/hackathone/hackathon , checkpoint `01M4KEGN3Q174N063453HK5XC6`, `git ls-remote https://github.com/Eartherai/zerodrop 'refs/entire/*'`, graph output in [`evidence/entire/`](evidence/entire). cfo.ai: https://cfo.ai/s/VyrSUZBAxHyXEJfC | One Entire checkpoint, covering the start of the build |
| Video (20%) | https://eartherai.github.io/zerodrop/video/zerodrop-demo.mp4 (2:41) | Synthetic voice; the run shown is a recording of a real run |
| Building in public (15%) | [`hackathon.md`](hackathon.md), dated, including what failed; commits from Oct 10, 15:38 IST: `git log --reverse --format='%ci %h %s'` | |
| Usefulness (10%) | The verdict comes from a checker that imports nothing from the engine, the planner or the mapping language, only the shared data models and the tracing helper (enforced by `tests/test_verifier_independence.py`) | No real billing system migrated |

Trace links have the form `https://app.neatlogs.com/traces/<trace id>`. They open for members
of the Neatlogs project, so each one also has a screenshot in `evidence/screenshots/`
(index: [`evidence/screenshots/README.md`](evidence/screenshots/README.md)).

## 1. Neatlogs incidents: identified and resolved

The organisers asked every team to show how Neatlogs' Incidents feature helped identify and
resolve the incidents their agent ran into. This is what happened, in order, with the parts
that do not flatter us left in.

| When (IST) | What | Evidence |
|---|---|---|
| Oct 10 to 11 | The agent ran into real failures. We found and fixed them from the independent verifier's reports and the traces, before anything was on the Incidents board | `EVALUATION.md`, fixes 1 to 6 |
| Oct 11 | Neatlogs AI, on its own, suggested four detections from our traces. One is a "False Success Claim Detector": "Detects instances where the agent claims the migration was successful, but the actual status is FAILED" | screenshots `24`, `25` |
| Oct 12, 08:42 | We asked Neatlogs' Investigate agent to go through every `zerodrop-migration` trace. It reported three issues and raised them as incidents: false success claims (Critical), halted runs and model-provider errors (High), runs repeating `recovery.CONTRACT` (High) | `evidence/neatlogs/investigation-report.md`, screenshots `20`, `27` |
| Oct 12, 08:49 | Each incident's own investigation produced a root-cause section, evidence and a recommended action. For the critical incident that section reads "Root cause is not established because the repository code has not been inspected"; its recommended action is what we used | screenshot `21`, `evidence/neatlogs/incident-false-success-fix-prompt.md` |
| Oct 12, 08:58 | **Fix 7, from the critical incident's recommended action** (commit `286c728`): after the first batch of each mapping the independent verifier re-reads those records, and the run stops if they do not match | before and after traces below |
| Oct 12, 09:02 | **From the repair-loop incident** (commit `d92588d`): a run that cannot be repaired now halts naming the field and value the target refused, for a person to act on | `tests/test_engine.py::test_a_run_that_cannot_be_repaired_halts_saying_what_the_target_refused` |
| Oct 12 | The suggested detections were switched on. The false-success detector's suggested pattern did not match our span output, so we widened it first. It then flagged six spans: two from the day's control run and four of the seven real-model false successes from Oct 11 | screenshot `23` |
| Oct 12 | All three incidents moved Raised → Investigated → Resolved | screenshots `22`, `28`, `29` |

**The critical incident, before and after the fix it led to.** Same scenario (S01), same flawed
plan (a scripted planner that reads dates in the wrong time zone, a mistake the dry run cannot
see), commit `286c728`, early check off and on.

| | Before | After |
|---|---|---|
| Run | `run_352df589b91d` | `run_0c898a7e56b0` |
| Records written before anyone noticed | 182 (all of them) | 28 (one batch of customers) |
| What the agent said | SUCCESS | FAILED |
| What the independent verifier said | FAILED | FAILED |
| False success claim | **true** | **false** |
| Neatlogs trace | `c2fce46175145a8e7473297151bf04da` | `35bb1a754af7df0c21393e7118cd203e` |
| Screenshot | `18-neatlogs-before-false-success-flagged.png` | `19-neatlogs-after-early-check-stops-the-run.png` |
| Result file | `evidence/experiments/early-check-off-naive-S01.json` | `evidence/experiments/early-check-on-naive-S01.json` |

The run still fails, as it should with a wrong plan. What changed is that the agent stops after
one batch and says so itself, instead of writing everything and claiming success.

**What Neatlogs got right and wrong** (full notes in `evidence/neatlogs/investigation-report.md`):
- Right: the five evidence traces on the critical incident are exactly our recorded real-model
  false successes, covering all three causes. Its count of ten comes from a search for
  "False Success Claim: true".
- We did not take its first recommendation (move the verifier's checks into the agent's dry
  run): that would end the verifier's independence. We took its fourth step, a blocking check
  that asks the evaluator.
- Wrong: the follow-up investigation cites three healthy runs as examples, and the repair-loop
  incident's evidence traces are successful one-replan recoveries. The run that really looped
  is trace `a5b9ad484e4fac9e428f5eb00ba46088`.
- Honest timing: fixes 1 to 6 were made before the board had an incident on it. Fix 7 and the
  halt message are the two changes that came from the incidents.

## 2. Before and after, with compared numbers (more pairs)

Same scenario (S02, 1,901 records, no injected faults), same model (`gemini-3.1-flash-lite`),
before and after fix 3: the dry run rejects a mapping that gives different source records the
same identity (commit `251cdd4`).

| | Before | After |
|---|---|---|
| Commit | `78d92da` | `251cdd4` |
| Run | `run_5d0171f3cddf` | `run_0a92f29d3a45` |
| What the agent believed | SUCCESS | SUCCESS |
| What the independent verifier found | **FAILED** | **SUCCESS** |
| Verifier checks failed | 10 of 24 | 0 of 24 |
| Writes the target treated as a record it already had | 1,898 of 1,901 | 0 |
| Model calls | 5 | 5 |
| Neatlogs trace | `75f5abadcc7c45344ee5639e556c2621` | `229e14d548b58ab6938fc70ec4009b34` |
| Screenshot | `14-before-trace-s02-false-success.png` | `15-after-trace-s02-verified.png` |
| Result file | `evidence/runs/S02-clean-demo-size-gemini-3.1-flash-lite-before-identity-guard.json` | `evidence/runs/S02-clean-demo-size-gemini-3.1-flash-lite.json` |

The before run also took longer (66.7 s against 11.1 s) and cost more ($0.0109 against
$0.0078 at list price). That gap is not the fix: the before run includes a model call that hit
a rate limit and was retried.

Two more pairs from later passes on the same model, both a yen amount written 100 times too
large:

| Fix | Scenario | Before | After |
|---|---|---|---|
| Contradictory decimal parameters are an error (`933a7a9`) | S16, everything goes wrong | `run_14ded6031abe`: agent SUCCESS, verifier FAILED, JPY total 1,205,966,500 instead of 12,059,665. Trace `874c2d43e3b1995e85980d50264aed3f` | `run_e5294505e55c`: verified SUCCESS. Trace `f062910ba90fe51c92e716b566606abd` |
| Fixed decimals must fit the record's currency (`7b34f8c`) | S03, rate-limit storm | `run_acc170ca8785`: agent SUCCESS, verifier FAILED, JPY total 328,713,000 instead of 3,287,130. Trace `81e79b05a4b1b6f2c15dbd833823ef1f` | `run_30e7764a777f`: verified SUCCESS. Trace `03b05b42cf288529acd3ad3809141357` |

All seven fixes with root cause and regression test: [`EVALUATION.md`](EVALUATION.md).

## 3. A failure-recovery run

S16, "everything goes wrong", planned by `gemini-3.6-flash`: `run_aa73127580bb`, commit
`d656f98`, trace `0652c95c208d53311eecccf73fe1cae0`.

| What went wrong during the run | What the agent did | Count |
|---|---|---|
| Target answered 429 with `Retry-After` | Waited what the server asked, then retried | 4 retries, 2.0 s waited |
| A write timed out after the target had committed it | Looked the records up before sending anything again | 1 ambiguous write, 50 lookups, 50 found, 0 duplicates |
| Target API changed from v1 to v2 mid-run | The model diagnosed the change and rewrote two mappings | 1 replan; subscriptions and invoices moved to mapping version 2 |

Result: 1,901 of 1,901 records written, verifier SUCCESS, 12 model calls, $0.082 at list
price, 145 s. File: `evidence/runs/S16-demo-chaos-gemini-3.6-flash.json`. Screenshots:
`10-neatlogs-trace-s16-gemini.png` (trace), `03-s16-finished-full.png` and
`04-s16-certificate.png` (dashboard). The demo video replays this run.

Crash and resume (the process is killed mid-run and restarted from the ledger) is covered by
S09, S10 and S20; each evaluation file reports its `crash_resumes` count.

## 4. Neatlogs tracing

Rules: traces "should capture model and tool calls, state changes, retries, failures,
latency, token usage, and cost".

| Asked for | Where it is in a ZeroDrop trace | Code |
|---|---|---|
| Model calls, tokens, cost, latency | LLM spans from the wrapped model client, under AGENT spans for the planner and the diagnoser | `src/zerodrop/agent/` |
| Tool calls | TOOL spans for schema discovery, every batch write (`novabill.batch_write`, with attempt number), every lookup, and every tool the model calls, with its input and result | `src/zerodrop/engine.py`, `src/zerodrop/agent/llm.py` |
| State changes | One `state.<STATUS>` span per run status change, with `from_state` and `to_state` | `MigrationEngine._set_status` |
| Retries and failures | One `recovery.<class>` span per failure handled: transient (wait and retry), ambiguous write (look up first), contract change (replan), bad data (quarantine), auth, budget (halt) | `src/zerodrop/engine.py` |
| The gates before and during writing | GUARDRAIL spans: one per dry run (`dry-run.<entity>`) and one per early check (`early-check.<entity>`), each with what was checked, passed or not, a score, and the reason when it blocks | `MigrationEngine._guarded_dry_run`, `_check_early` |
| The verdict | Root WORKFLOW span: verifier status, the agent's own claim, false-success flag, checks failed, report hash. EVALUATOR span for the verifier with its input, verdict and a score | `MigrationEngine._finish`, `_verify` |

Every run stores its trace id in the ledger; the dashboard links to it. Layer:
`src/zerodrop/telemetry.py`. What Neatlogs itself showed for the project on the morning of
Oct 12 (read off its project overview; no file was saved): 225 traces in seven days, a 28.4%
trace error rate and $2.56 of measured model spend. The error rate counts runs with any errored
span, and our scenarios inject faults on purpose, so it is not the agent's failure rate.

## 5. Entire: checkpoints and entire-graph

| Item | Evidence |
|---|---|
| Entire page | https://entire.io/et/hackathone/hackathon : public, no sign-in. Commits, and under Sessions the coding session with its checkpoint. Checked public on Oct 12, 19:36 IST |
| Checkpoint | ID `01M4KEGN3Q174N063453HK5XC6`, git ref `refs/entire/checkpoints/C6/01M4KEGN3Q174N063453HK5XC6`, pushed with the repo. There is one checkpoint; it covers the first part of the build session. 52 of the repository's 79 commits carry an `Entire-Checkpoint` trailer that points to it (counted Oct 13, 04:40 IST) |
| Redaction | Secret and personal-data redaction configured in `.entire/settings.json` |
| Deep links, public | The session: https://entire.io/et/hackathone/hackathon/session/3ca2e4c1-0518-40bc-86bb-a3d3f8786516 . The incident fix as a commit page: https://entire.io/et/hackathone/hackathon/commit/286c7286038c6558f82f89853b120a573ffd87e7 |
| An Entire CLI plugin, built here | [`tools/entire-verdict`](tools/entire-verdict): `entire verdict` joins each commit's Entire checkpoint to what the independent checker measured at that commit. Installed with `entire plugin install ./tools/entire-verdict/entire-verdict`; tested in `tests/test_entire_verdict_plugin.py`. Its output for this repository, [`evidence/entire/verdict-by-commit.md`](evidence/entire/verdict-by-commit.md), recomputes the seven false successes from the result files: five at `78d92da`, one at `e65cc45`, one at `933a7a9` |
| entire-graph installed | Plugin v0.4.0; index of the repo; agent guide in `.entire/graph-agent.md`, loaded by `CLAUDE.md` and `AGENTS.md` |
| entire-graph used before a change | Before making state changes visible in the trace: `entire graph search` located `_set_status` (`evidence/entire/search-state-changes.txt`) and `entire graph impact` listed its 17 callers (`evidence/entire/impact-set-status.txt`). The change is commit `1838455` |
| entire-graph on commits | Entity-level change lists for fix 5 (`commit-7b34f8c-…`), fix 6 (`commit-6c07c9f-…`), the guardrail and evaluator spans (`commit-0ae1d2b-…`) and fix 7 (`commit-286c728-…`) in `evidence/entire/` |
| entire-graph on the riskiest function | `evidence/entire/impact-check-mapping.txt`: the blast radius of the dry run, where four of the fixes live |

Weak point, stated plainly: one checkpoint, covering the setup part of the session, not the
whole build.

## 6. cfo.ai: pricing, costs, revenue, runway

Built in cfo.ai from [`BUSINESS.md`](BUSINESS.md); screenshot `08-cfo-ai-monthly-forecast.png`.

| | cfo.ai base case | cfo.ai with growth halved to 10% a month |
|---|---|---|
| Price | $499 per verified migration; failed runs are not billed | same |
| Cost to deliver one | $36.77 (92.6% margin) | same |
| Break-even month | March 2027 | March 2027, by only $215 |
| Lowest cash balance (from $60,000) | $35,861 | $35,213 |
| Cash at month 24 | $1.88M | $587K |

`BUSINESS.md` has the six scenarios cfo.ai computed and where its agent pushed back on the
plan (growth rate, flat fixed costs, failed runs not costed), kept in.

## 7. Does the agent work: every evaluation, including the bad ones

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
| All 20 scenarios, after fix 5 | `gemini-3.5-flash-lite` | `1838455` | **20 of 20** | **0** | 138 | $0.4570 |
| All 20 scenarios, after fix 6 | `gemini-3.5-flash-lite` | `6c07c9f` | **20 of 20** | **0** | 141 | $0.4650 |
| After fix 7, morning | `gemini-3.5-flash-lite` | `286c728` for S01 to S06, `d92588d` for S07 and S08 (that commit landed during the pass) | 8 of the 8 that ran | 0 | 57 | $0.2140 |
| **All 20 scenarios, final code** | `gemini-3.5-flash-lite` | `d92588d` | **20 of 20** | **0** | 133 | $0.4539 |
| **Final code, the model that made the mistakes** | `gemini-3.1-flash-lite` | `d92588d` (file records `ab5e1e8`; no engine code changed between them) | **18 of 18** | **0** | 117 | $0.2593 |
| Scripted regression after fixes 3 to 7 | scripted | `251cdd4`, `933a7a9`, `7b34f8c`, `6c07c9f`, `286c728` | all matched each time | 0 | 0 | $0 |

Reading it honestly:
- Seven real false success claims in total. The verifier caught all seven. Each of the three
  causes was fixed test first, and no later run repeated a fixed cause.
- Three full passes of all 20 scenarios in a row matched with no false success, the last one
  on the final code. On the final code, `gemini-3.1-flash-lite`, the model that produced all
  seven false successes, also matched 18 of 18 with none.
- Pass 3 also had one run the model never repaired (S12) and one halted by a provider 503.
  Both led to changes (fix 6, the 503 retry). When we later seeded the same wrong mapping and
  let real models repair it, both `gemini-3.5-flash-lite` and `gemini-3.1-flash-lite` repaired
  it at the first attempt with the guard off and on (`evidence/experiments/`), so fix 6 is
  shown harmless and seen working inside one repair conversation, but not shown rescuing a run.
- Pass 4 and the morning pass after fix 7 were cut short when the free tier's daily quota ran
  out. Scenarios stopped by the quota are counted as not run; two of them had already made
  model calls and wrote no records.
- One pass per commit. This shows what happened, not a failure rate.
- All real-model runs used Gemini Flash models on the free tier (nothing was charged). No
  Claude run exists: the Anthropic account had no credit during the hackathon.

Real-model cost of every saved run: $4.06 at list price, $0 charged (free tier).

Files: `evidence/eval/` (one JSON and one Markdown per evaluation), `evidence/runs/` (one
JSON per single run), `evidence/experiments/`. Reproduce the scripted ones with no keys:
`uv run zerodrop eval --planner oracle --label my-run`.

## 8. Built during the hackathon, in public

| Item | Evidence |
|---|---|
| Commit dates | First commit `104ff06` on Oct 10, 15:38 IST, after the window opened at 12:30 IST. More than 60 commits since (`git log`), one per task. History never rewritten or force-pushed |
| Build log | [`hackathon.md`](hackathon.md): dated entries, including what failed |
| Posts | Texts in [`posts/`](posts); the submission post links the public thread |
| Tests | 780 Python tests and 81 UI tests; `uv run pytest -q` |
| Run it yourself | `docker compose up --build`, then http://127.0.0.1:8700 and start "Demo - everything goes wrong". No keys needed |
