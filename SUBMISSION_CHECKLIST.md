# Submission checklist

Submission: a public X quote post of the official neatlogs post, **Mon Oct 12, 19:00 to 23:55 IST**,
with team, name, project, public repo and demo link. Everything below must be ready for the
owner's approval by Mon Oct 12, 17:00 IST.

Status key: DONE (verified, evidence linked) / PARTIAL / TODO / OWNER (needs the owner).

Judges: [`EVIDENCE.md`](EVIDENCE.md) maps every item below to a file, run id or trace.

## Required by the rules
| # | Requirement | Status | Evidence or what is missing |
|---|---|---|---|
| 1 | Demo video, 3 minutes or less, covering Neatlogs, Entire and cfo.ai (architecture, implementation, runtime, reasoning, result) | OWNER | Rendered Oct 12: `evidence/video/zerodrop-demo.mp4`, 2:35, 1920x1080, narrated (synthetic voice); `zerodrop-demo-x.mp4`, 2:18, for attaching to the X post. Nine scenes: problem, the rule, replay of the real Gemini S16 run, verification certificate, a real model's false success caught and fixed, Neatlogs trace, Entire checkpoint, cfo.ai plan, close. Owner: watch it, upload the 2:35 file somewhere linkable, put the link below. Known gaps: the Entire scene shows CLI output because the entire.io page is not reachable yet; entire-graph is not in the video |
| 2 | Public repository with commits dated during the hackathon | OWNER | Repo `github.com/Eartherai/zerodrop` is private until the owner approves. First commit Oct 10, 15:38 IST, after the window opened (12:30 IST); more than 50 commits; history never rewritten. Secret scan of the full history is clean (see gates) |
| 3 | Accessible Entire checkpoint link plus its ID | OWNER | ID `01M4KEGN3Q174N063453HK5XC6`, stored at `refs/entire/checkpoints/C6/01M4KEGN3Q174N063453HK5XC6` and pushed to GitHub; every commit since carries the `Entire-Checkpoint` trailer. **The entire.io page is a 404**: the site only knows the Entire-hosted repo `/et/hackathone/hackathon`. The owner needs to run `git remote add entire entire://aws-ap-south-1.entire.io/et/hackathone/hackathon` and `git push entire main 'refs/entire/*:refs/entire/*'`, then make that repo public. Audited Oct 11: no keys, no images, no personal details; it does show local folder paths |
| 4 | cfo.ai business plan (pricing, costs, revenue, runway) | PARTIAL | Built in cfo.ai on Oct 11 from `BUSINESS.md`: 24-month model with assumptions, monthly forecast, six scenarios and a written plan. Base case: break-even March 2027, lowest cash $35,861, $1.88M at month 24; with growth halved, still March 2027 and $587K. Its criticism is kept in `BUSINESS.md`. Capture: `evidence/screenshots/08-cfo-ai-monthly-forecast.png`. Owner: a share link or export from cfo.ai, if it offers one |
| 5 | X quote post with team, name, project, repo, demo link | OWNER | Draft: `posts/06-submission.md`. Posting is the owner's action |

## Judging criteria
| Weight | Criterion | Status | Evidence or what is missing |
|---|---|---|---|
| 30% | Agent that works | DONE | **Real model, all 20 scenarios: 20 of 20 with 0 false successes, twice in a row** (`gemini-3.5-flash-lite`; `1838455`, `evidence/eval/*final-code.md`; final code `6c07c9f`, `evidence/eval/*after-fix6.md`). Earlier passes on `gemini-3.1-flash-lite`: 18/18, 17/18, 15/18, then 10 of 10 before the quota ended. Seven real false successes in total, all caught by the verifier; three causes fixed test first (`251cdd4`, `933a7a9`, `7b34f8c`) with scripted regression 18/18 after each. A fourth fix (`6c07c9f`) for a run the model never repaired, shown harmless but not yet shown rescuing a real run. Not done: repeated passes for a failure rate, any Claude run |
| 25% | Sponsor tools | PARTIAL | Neatlogs: every run traced (model calls with tokens and cost, tool calls, retries and failures as `recovery.*` spans, state changes as `state.*` spans, verdict on the root), linked from the dashboard; before and after trace pair with compared numbers in `EVIDENCE.md`; captures `evidence/screenshots/07` to `15`. Entire: checkpoint referenced by every commit; entire-graph installed, repo indexed and used for a change (`evidence/entire/`); the checkpoint web page is not reachable yet (row 3). cfo.ai: plan built, six scenarios and its criticism in `BUSINESS.md` |
| 20% | Video | PARTIAL | `evidence/video/zerodrop-demo.mp4` (2:35) and `zerodrop-demo-x.mp4` (2:18 for X); synthetic narration; needs the owner's review and an upload link |
| 15% | Building in public | OWNER | Seven drafts in `posts/`, none posted |
| 10% | Usefulness and originality | DONE | `README.md`, `BUSINESS.md`; the verifier catching a real model's false success is the thesis shown on real data |

## Engineering gates
| Gate | Status | Evidence |
|---|---|---|
| Tests, lint, format | DONE | `uv run pytest -q`: 764 tests pass; `ruff check` and `ruff format --check` clean (Oct 12, 00:12 IST); 61 UI tests (Oct 11) |
| Docker kit | DONE | Rebuilt Oct 11, 18:20 IST with the redesigned UI: `docker compose up`, both services healthy, S07 through `POST /api/runs` verified SUCCESS |
| Secret scan, full history | DONE | `gitleaks git --log-opts=--all --redact`: no leaks, 52 commits (Oct 12, 00:12 IST). The only findings in a scan of the folder are in the git-ignored `.env`. Re-run right before going public |
| `/security-review` | DONE | Oct 10, 23:55 IST: reviewed the API (run start, public-mode access code and budget checks, static file serving), the sandbox bind-host option, the trace-id link and the Docker kit. No high-confidence findings. Static serving resolves paths and requires them inside `ui/dist`; the access code is compared in constant time; the container runs as a non-root user and ports publish to 127.0.0.1 only. Re-run before going public |
| Real-model evaluation with saved evidence | DONE | Seven passes in `evidence/eval/` (see `EVIDENCE.md` section 6), 28 single runs in `evidence/runs/`, two experiment runs in `evidence/experiments/`. $3.09 at list price in total, $0 charged |
| Neatlogs trace screenshots in `evidence/` | DONE | `evidence/screenshots/07`, `09`, `10`, `11`, `13`, `14`, `15`: real Gemini runs with WORKFLOW, AGENT, LLM, TOOL, CHAIN and EVALUATOR spans, state changes, and the before and after pair |

## What only the owner can do, in order
1. Watch `evidence/video/zerodrop-demo.mp4`. Upload it somewhere linkable (for example unlisted on YouTube).
2. Entire: `git remote add entire entire://aws-ap-south-1.entire.io/et/hackathone/hackathon`, then `git push entire main 'refs/entire/*:refs/entire/*'`, then make that repo public on entire.io and open the checkpoint page once to check it loads.
3. Say "make the repo public" (a last secret scan and security review run first), or do it in GitHub settings.
4. Post at least one #neatHack post from `posts/` before submitting (07 is the strongest).
5. At 19:00 IST sharp, quote the official neatlogs post with the text in `posts/06-submission.md`, the two links, and `zerodrop-demo-x.mp4` attached. The sponsors engage with the first 50 quote posts.
6. After the hackathon: delete the two Gemini keys (one was pasted in a chat), rotate the Neatlogs key and the AWS keys shared earlier, delete the AWS root access key.

## Links to fill in at submission
- Public repo:
- Demo video:
- Entire checkpoint:
- Neatlogs trace of the demo run:
- cfo.ai plan:
