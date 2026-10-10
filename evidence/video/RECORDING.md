# Recording the demo video

Target length 2:50, hard limit 3:00. Script and voice-over lines: `DEMO.md`.

## Assets already captured (Oct 10, oracle planner, $0)
| File | What it shows | Use at |
|---|---|---|
| `s16-demo-chaos-oracle-dashboard.mp4` (1920x1080, 20 s) | Live S16 run in the dashboard: 429 storm, timeout after a write, API v1 to v2, mapping diff, certificate 24/24 | Backup for 0:30 to 1:30 if the live take goes wrong |
| `s01-naive-false-success-dashboard.mp4` (1920x1080, 10 s) | The flawed planner: engine claims SUCCESS, verifier says FAILED | 1:30 to 1:45 |
| `../screenshots/01-s16-running.png` | Mid-run: failures and recovery steps streaming | Thumbnail, posts |
| `../screenshots/04-s16-certificate.png` | Certificate, money totals per currency, trace id and commit in the footer | 1:15 |
| `../screenshots/06-naive-false-success-certificate.png` | "False-success claim caught" banner, JPY off by 100x | 1:30, posts |

These were recorded with the scripted oracle planner (0 model calls). The final video should
show the same run with the **Claude** planner once real-model runs are measured; re-record
with the steps below and say on screen which planner is running.

## Before recording
1. `cd` to the repo, then start the dashboard with tracing on:
   ```sh
   set -a; . ./.env; set +a; uv run zerodrop serve --planner claude --db runs/demo.db
   ```
2. Open `http://127.0.0.1:8700` in Chrome, window at 1920x1080, zoom 100%, dark theme,
   bookmarks bar hidden.
3. Open in other tabs, already signed in: the Neatlogs project (traces list), the Entire
   checkpoint page for the fix commit, the cfo.ai plan. Open a terminal with a large font in
   the repo folder.
4. Do one full practice run so nothing is being loaded for the first time on camera.

## Recording (QuickTime Player)
1. QuickTime Player, File, New Screen Recording. Options: the built-in microphone (or record
   voice separately and add it in the edit), "Show Mouse Clicks" on. Record the selected window.
2. Take 1 (0:00 to 0:30): title card and the architecture diagram (`ARCHITECTURE.md` on GitHub
   or in the editor preview).
3. Take 2 (0:30 to 1:30): dashboard. Pick "Demo - everything goes wrong", press
   **Start migration**. Keep the mouse still while events stream. When the status turns
   SUCCESS: click the **subscriptions** tab in the mapping diff, pause two seconds, then scroll
   to the verification certificate and pause three seconds.
4. Take 3 (1:30 to 1:45): in the terminal run
   `uv run zerodrop run S01-clean --planner naive --quiet | head -20`, or open the naive run in
   the dashboard from the Runs menu, and show the red certificate.
5. Take 4 (1:45 to 2:10): Neatlogs. Open the trace whose id is in the dashboard footer. Expand
   the tree, click the `contract-diagnoser` agent span and one LLM span, then the root span's
   attributes (status, agent_claimed_status, false_success_claim).
6. Take 5 (2:10 to 2:30): Entire. The checkpoint page, then in the terminal
   `entire checkpoint list`.
7. Take 6 (2:30 to 2:45): cfo.ai plan: pricing, break-even, runway chart.
8. Take 7 (2:45 to 2:55): the results table in `EVALUATION.md`, then the repo URL.

## Edit
- Join the takes in iMovie or CapCut, cut dead time, keep the total under 3:00.
- Captions for the one-line rule: "The LLM decides, code executes, an independent checker judges."
- Check every spoken number against the file named in `DEMO.md`.
- Export 1080p MP4. Upload unlisted to YouTube (or as the hackathon asks) and put the link in
  `SUBMISSION_CHECKLIST.md`.

## Before publishing the video
- No keys, tokens, e-mail addresses or account pages visible in any frame (check the Neatlogs
  settings page and the terminal scrollback).
- The dashboard footer shows a trace id and a commit: both are safe to show.
