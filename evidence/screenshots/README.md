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
