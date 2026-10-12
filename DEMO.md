# Demo video (hard limit 3:00)

**Current cut:** `evidence/video/zerodrop-demo.mp4`, 2:39, 1920x1080, sixth cut, rendered Oct 12.
`evidence/video/zerodrop-demo-x.mp4` is the same video played 13% faster (2:20) so it can be
attached to a post on X, where the limit for standard accounts is 2:20.

It answers the organisers' three asks in one video: the problem the agent solves, how Entire
and cfo.ai were part of the project, and how Neatlogs was used to identify and resolve the
incidents the agent ran into.

What it is and is not:
- The run on screen is a replay of a real recorded run planned by Gemini (`run_aa73127580bb`),
  played at twice its speed. Narration is a synthetic voice.
- The Neatlogs pages are screenshots of our project taken on Oct 12 (files in
  `evidence/screenshots/18` to `29`).
- The before and after pair in the fix scene uses a scripted flawed planner, because the
  mistakes real models made are now rejected before any write. Both runs are in
  `evidence/experiments/early-check-*.json`.
- The Entire scene shows command output from this repository.

## Narration, as rendered
| Time | Scene | Narration |
|---|---|---|
| 0:00 | Problem | Every time a company switches a billing tool, someone has to move the data. And migrations lose data quietly. Worse, the tool doing the work is the one that reports success. |
| 0:12 | The rule | ZeroDrop is a migration agent built on one rule. The model decides the field mapping. Code executes it, in batches it can resume. And an independent checker re-reads both systems and judges. |
| 0:27 | Real run (replay at 2x), then the certificate | A real run, planned by Gemini, with everything going wrong. It waits out rate limits. After a timeout on a write that landed, it looks the records up instead of sending them twice. When the A P I changes version mid run, it rewrites the mapping. Twenty four of twenty four checks pass. |
| 0:46 | Neatlogs: the incident is identified | Every run is one Neatlogs trace, with the checker's verdict on it. We asked Neatlogs' investigation agent to go through all of them. It raised three incidents. The critical one: the agent said success, the evaluator said failed, in ten traces. Its evidence traces are the same real runs our checker had flagged. |
| 1:07 | Neatlogs: root cause and recommended action | The cause was the model's mapping. It gave every record the same I D, or wrote yen a hundred times too large. Valid in shape, so the dry run passed. We had closed those mistakes the day before. But the incident recommended one more step: a blocking check that asks the evaluator before the agent may claim success. |
| 1:29 | Neatlogs: the fix, before and after | So we built it. After the first batch, the independent checker re-reads those records, and the run stops if they do not match. Two traces, same flawed plan. Before: one hundred eighty two records written, and a false success. After: stopped at twenty eight, and the agent says failed itself. |
| 1:48 | Neatlogs: detector on, incidents resolved | Neatlogs A I had also suggested a false success detector from our traces. It is on now, and it flagged the real runs. All three incidents are resolved. |
| 2:00 | Entire | Entire is the build record. A checkpoint of the coding session is stored in git, secrets redacted. Its code graph, entire graph, showed what a change would touch before we made it. |
| 2:12 | cfo.ai | C F O dot A I holds the business plan. Four hundred ninety nine dollars per verified migration, about thirty seven to deliver. Break even in March twenty twenty seven, even with growth halved, and cash never drops below thirty five thousand dollars. |
| 2:30 | Close | ZeroDrop. The migration agent that proves nothing was lost. |

## Where each claim in the video comes from
| Claim | Source |
|---|---|
| 24 of 24 checks, 1,901 of 1,901 records | `evidence/runs/S16-demo-chaos-gemini-3.6-flash.json` |
| Three incidents; the critical one in ten traces; five evidence traces | `evidence/neatlogs/investigation-report.md`, screenshots `20`, `27` |
| Seven real-model runs with a wrong mapping; three guards shipped Oct 11 | `EVALUATION.md` ("All real-model false successes"), commits `251cdd4`, `933a7a9`, `7b34f8c` |
| The recommended step we implemented | `evidence/neatlogs/incident-false-success-fix-prompt.md`, commit `286c728` |
| 182 records and a false success before; stopped at 28 after | `evidence/experiments/early-check-off-naive-S01.json`, `early-check-on-naive-S01.json` |
| Detector suggested by Neatlogs AI; it flagged the real-model runs; three incidents resolved | screenshots `22` to `25` |
| Checkpoint id; 17 callers, 6 co-change files | `git ls-remote https://github.com/Eartherai/zerodrop 'refs/entire/*'`, `evidence/entire/impact-set-status.txt` |
| $499, about $37 to deliver, break-even March 2027 also with growth halved, cash never below $35K | `BUSINESS.md` (cfo.ai scenario table) |
| 7 false successes caught; 20 of 20 on a real model | `EVIDENCE.md` section 7 |
