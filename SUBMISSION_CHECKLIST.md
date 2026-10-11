# Submission checklist

Submission: a public X quote post of the official neatlogs post, **Mon Oct 12, 19:00 to 23:55 IST**,
with team, name, project, public repo and demo link. Everything below must be ready for the
owner's approval by Mon Oct 12, 17:00 IST.

Status key: DONE (verified, evidence linked) / PARTIAL / TODO / OWNER (needs the owner).

## Required by the rules
| # | Requirement | Status | Evidence or what is missing |
|---|---|---|---|
| 1 | Demo video, 3 minutes or less, covering Neatlogs, Entire and cfo.ai (architecture, implementation, runtime, reasoning, result) | PARTIAL | Rendered: `evidence/video/zerodrop-demo.mp4`, 2:35, 1920x1080, narrated (synthetic voice). Nine scenes: problem, the rule, replay of the real Gemini S16 run, verification certificate, a real model's false success caught and fixed, Neatlogs trace, Entire checkpoint, cfo.ai plan, close. Still to do: owner review, upload, link. Known gaps: the Entire scene shows CLI output because the entire.io page is not reachable yet; the 19/20 to 20/20 figure is from the scripted evaluation and is labelled so |
| 2 | Public repository with commits dated during the hackathon | OWNER | Repo `github.com/Eartherai/zerodrop` is private until the security gate passes and the owner approves. First commit after the window opened (Oct 10, 12:30 IST); history never rewritten |
| 3 | Accessible Entire checkpoint link plus its ID | OWNER | ID `01M4KEGN3Q174N063453HK5XC6`, stored at `refs/entire/checkpoints/C6/01M4KEGN3Q174N063453HK5XC6` and pushed to GitHub; every commit since carries the `Entire-Checkpoint` trailer. **The entire.io page is a 404**: the site only knows the Entire-hosted repo `/et/hackathone/hackathon`. The owner needs to run `git remote add entire entire://aws-ap-south-1.entire.io/et/hackathone/hackathon` and `git push entire main 'refs/entire/*:refs/entire/*'`, then make that repo public. Audited Oct 11: no keys, no images, no personal details; it does show local folder paths |
| 4 | cfo.ai business plan (pricing, costs, revenue, runway) | PARTIAL | Built in cfo.ai on Oct 11 from `BUSINESS.md`: 24-month model with assumptions, monthly forecast, scenarios and a written plan. Base case as cfo.ai computed it: break-even month Mar 2027, lowest cash $35,861, cash never runs out. Capture: `evidence/screenshots/08-cfo-ai-monthly-forecast.png`. Still to do: share link or export, and fold cfo.ai's own critique (20% monthly growth is aggressive; fixed costs never rise; failed runs are not costed) into `BUSINESS.md` |
| 5 | X quote post with team, name, project, repo, demo link | OWNER | Draft: `posts/06-submission.md`. Posting is the owner's action |

## Judging criteria
| Weight | Criterion | Status | Evidence or what is missing |
|---|---|---|---|
| 30% | Agent that works | DONE (single runs) | All 20 scenarios verified with a real Gemini model, one run each (`evidence/runs/`, `EVALUATION.md`). A real false success from the smallest model was caught by the verifier in 5 runs, root-caused, fixed test first (`251cdd4`) and re-verified. Scripted evaluation 18/18 at the fix commit. Single-model evaluation on `gemini-3.1-flash-lite`: 18/18, 0 false successes (`evidence/eval/*single-model.md`). Not done: repeated passes, any Claude run |
| 25% | Sponsor tools | PARTIAL | Neatlogs: every run traced, trace linked from the dashboard, captures of real-model traces in `evidence/screenshots/07` to `11`. cfo.ai: plan built, six scenarios and its criticism in `BUSINESS.md`. Entire: checkpoint exists and is referenced by every commit, but its web page is not reachable yet (row 3) |
| 20% | Video | PARTIAL | `evidence/video/zerodrop-demo.mp4` (2:35) and `zerodrop-demo-x.mp4` (2:18 for X); synthetic narration; needs the owner's review and an upload link |
| 15% | Building in public | OWNER | Seven drafts in `posts/`, none posted |
| 10% | Usefulness and originality | DONE | `README.md`, `BUSINESS.md`; the verifier catching a real model's false success is the thesis shown on real data |

## Engineering gates
| Gate | Status | Evidence |
|---|---|---|
| Tests, lint, format | DONE | `uv run pytest -q` 756 passed; `ruff check` and `ruff format --check` clean; 61 UI tests (Oct 11, 18:30 IST) |
| Docker kit | DONE | Rebuilt Oct 11, 18:20 IST with the redesigned UI: `docker compose up`, both services healthy, S07 through `POST /api/runs` verified SUCCESS |
| Secret scan, full history | DONE | `gitleaks git --log-opts=--all --redact`: no leaks, 24 commits (Oct 10, 23:18 IST). Re-run before going public |
| `/security-review` | DONE | Oct 10, 23:55 IST: reviewed the API (run start, public-mode access code and budget checks, static file serving), the sandbox bind-host option, the trace-id link and the Docker kit. No high-confidence findings. Static serving resolves paths and requires them inside `ui/dist`; the access code is compared in constant time; the container runs as a non-root user and ports publish to 127.0.0.1 only. Re-run before going public |
| Real-model evaluation with saved evidence | DONE | Single-model pass: 18/18 on `gemini-3.1-flash-lite` (`evidence/eval/*single-model.md`). Per-scenario runs: 20 of 20 matched, 28 runs in `evidence/runs/`. One pass each; repeated passes need a billed key |
| Neatlogs trace screenshots in `evidence/` | DONE | `evidence/screenshots/07`, `09`, `10`: real Gemini runs with WORKFLOW, AGENT, LLM, TOOL, CHAIN and EVALUATOR spans |

## Links to fill in at submission
- Public repo:
- Demo video:
- Entire checkpoint:
- Neatlogs trace of the demo run:
- cfo.ai plan:
