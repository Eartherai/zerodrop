# Recording the demo video

Target length 2:50, hard limit 3:00. Script and voice-over lines: `DEMO.md`.

## What exists
`zerodrop-demo.mp4` in this folder is a finished cut (2:41, the eighth, narrated with a synthetic voice),
built from a dashboard replay of the real Gemini S16 run and captures of Neatlogs, the Entire
CLI and cfo.ai. Script as rendered: `DEMO.md`. The steps below are for recording your own take
with your own voice, if you prefer that to the synthetic one.

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
