# Screenshots

| File | What it shows | Captured |
|---|---|---|
| `00-dashboard-idle.png` | Dashboard before a run | Oct 11 |
| `01-s16-running.png` | "Everything goes wrong" (S16) while running: failures and recovery steps | Oct 11 |
| `03-s16-finished-full.png`, `04-s16-certificate.png` | The same run finished, and its verification certificate | Oct 11 |
| `05-naive-false-success-full.png`, `06-naive-false-success-certificate.png` | The scripted naive planner as it was until fix 5: yen amounts 100 times too large, caught by the verifier. The engine now rejects that mapping before any write, so the current naive planner uses a wrong time zone instead and these two cannot be reproduced from the current code | Oct 11 |
| `07-neatlogs-trace-s01-gemini.png` | Neatlogs trace of a clean real-model run | Oct 11 |
| `08-cfo-ai-monthly-forecast.png` | The cfo.ai plan: monthly forecast | Oct 11 |
| `09-neatlogs-llm-span-s01-gemini.png` | One model call in Neatlogs: prompt, tool calls, tokens, cost | Oct 11 |
| `10-neatlogs-trace-s16-gemini.png` | Neatlogs trace of the real-model recovery run (`run_aa73127580bb`) | Oct 11 |
| `11-neatlogs-trace-s07-gemini-grouped.png` | API-change run, steps grouped under one span per entity | Oct 11 |
| `12-real-model-false-success-caught.png` | Dashboard for a real model's false success (`run_5d0171f3cddf`) | Oct 11 |
| `13-neatlogs-trace-state-changes.png` | State changes as spans | Oct 11 |
| `14-before-trace-s02-false-success.png`, `15-after-trace-s02-verified.png` | The before and after pair in `EVIDENCE.md` section 1 | Oct 11 |
| `16-neatlogs-guardrail-blocks-refused-values.png` | Whole trace of `run_937b40adc42e`: dry runs as guardrails, one of them blocking a mapping whose values the target refused, the repair, the verifier as evaluator | Oct 12 |
| `17-neatlogs-model-dry-run-told-refused-values.png` | Trace of `run_173c027fcabe` with the model's four dry-run calls open: input and result of each | Oct 12 |
| `18-neatlogs-before-false-success-flagged.png` | Before fix 7: whole trace of `run_352df589b91d`, 182 records written, False Success Claim: true, flagged by the detector | Oct 12 |
| `19-neatlogs-after-early-check-stops-the-run.png` | After fix 7: whole trace of `run_0c898a7e56b0`, the early-check guardrail finds 0 of 28 matching, the run stops and reports FAILED itself | Oct 12 |
| `20-neatlogs-incidents-board-three-raised.png` | Incidents board: the three incidents Neatlogs raised | Oct 12 |
| `21-neatlogs-incident-false-success-resolved-full-report.png` | The critical incident, resolved, with Neatlogs' full investigation report and recommended action | Oct 12 |
| `22-neatlogs-incidents-board-three-resolved.png` | Incidents board: all three resolved | Oct 12 |
| `23-neatlogs-false-success-detector-flagged-spans.png` | The False Success Claim Detector's flagged spans: today's control run and four real-model runs from Oct 11 | Oct 12 |
| `24-neatlogs-detections-suggested-by-neatlogs-ai.png` | The four detections Neatlogs AI suggested from our traces, before they were added | Oct 12 |
| `25-neatlogs-false-success-detector-rationale.png` | Why Neatlogs AI suggested the false-success detector | Oct 12 |
| `26-neatlogs-incident-fix-in-coding-agent.png` | The incident's "Fix in" menu (Claude Code among the targets) | Oct 12 |
| `27-neatlogs-investigation-report-issue-1.png` | Neatlogs' investigation report: issue 1, ten traces, five evidence traces | Oct 12 |
| `28-neatlogs-incident-contract-loop-resolved.png`, `29-neatlogs-incident-halted-runs-resolved.png` | The two High incidents, resolved | Oct 12 |
| `30-entire-verdict-plugin.png` | The Entire CLI plugin built here, `entire verdict`: each commit, its Entire checkpoint and what the checker measured there (rendered from the command output) | Oct 13 |
