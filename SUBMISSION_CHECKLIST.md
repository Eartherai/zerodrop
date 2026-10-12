# Submission checklist

Submission: a public X quote post of the official neatlogs post, **Mon Oct 12, 19:00 to 23:55 IST**,
with team, name, project, public repo and demo link. Everything below must be ready for the
owner's approval by Mon Oct 12, 17:00 IST.

Status key: DONE (verified, evidence linked) / PARTIAL / TODO / OWNER (needs the owner).

Judges: [`EVIDENCE.md`](EVIDENCE.md) maps every item below to a file, run id or trace.

## Required by the rules
| # | Requirement | Status | Evidence or what is missing |
|---|---|---|---|
| 1 | One demo video, 3 minutes or less: the problem, how Entire and cfo.ai were part of it, how Neatlogs identified and resolved the incidents (organisers' instruction of Oct 12) | DONE | `evidence/video/zerodrop-demo.mp4`, 2:39, sixth cut, linkable at https://eartherai.github.io/zerodrop/video/zerodrop-demo.mp4. `zerodrop-demo-x.mp4` (2:20) is the cut to attach on X. Ten scenes, four on the Neatlogs incidents. Synthetic voice. Owner: watch it once |
| 2 | Public repository with commits dated during the hackathon | DONE | https://github.com/Eartherai/zerodrop, public since Oct 12, 14:04 IST with the owner's approval. First commit Oct 10, 15:38 IST; history never rewritten; full-history secret scan clean |
| 3 | Accessible Entire checkpoint link plus its ID | OWNER | ID `01M4KEGN3Q174N063453HK5XC6`, git ref `refs/entire/checkpoints/C6/01M4KEGN3Q174N063453HK5XC6`, in the public repo (`git ls-remote https://github.com/Eartherai/zerodrop 'refs/entire/*'`). entire.io only shows repositories that have the Entire GitHub App installed: on entire.io open Repositories, Add repository, and install it for `Eartherai/zerodrop`; then `https://entire.io/gh/Eartherai/zerodrop` works |
| 4 | cfo.ai business plan (pricing, costs, revenue, runway) | DONE | Public view-only link: https://cfo.ai/s/VyrSUZBAxHyXEJfC (monthly forecast, assumptions, six scenarios, written plan). Summary and cfo.ai's criticism in `BUSINESS.md`; capture `evidence/screenshots/08` |
| 5 | X quote post with team, name, project, repo, demo link | OWNER | Text ready in `SUBMISSION.md` (275 characters, tags @neatlogs, @EntireHQ and @arithecfo as the organisers require), with a reply, form answers, a Discord post and a long form. The quote post and the form are both mandatory. Posting is the owner's action, 19:00 IST |

## Judging criteria
| Weight | Criterion | Status | Evidence or what is missing |
|---|---|---|---|
| 30% | Agent that works | DONE | Real model, all 20 scenarios: 20 of 20 with 0 false successes, three passes in a row, the last on the final code `d92588d` (`evidence/eval/*final-code-early-check.md`); and 18 of 18 on the final code with `gemini-3.1-flash-lite`, the model that produced the false successes. Seven real false successes in total, all caught by the verifier; three causes fixed test first; since Oct 12 the verifier also re-reads the first batch so a wrong mapping stops early (`286c728`). Bad passes are published (`EVIDENCE.md` section 7). Not done: repeated passes for a failure rate, any Claude run |
| 25% | Sponsor tools | DONE except the Entire page | Neatlogs: every run traced; three incidents raised on our traces, investigated and resolved, two code changes came from them; suggested detections switched on (`EVIDENCE.md` section 1, screenshots 18 to 29). Entire: one checkpoint in git, entire-graph installed and used (`evidence/entire/`); entire.io page needs the GitHub App (row 3). cfo.ai: plan with a public link |
| 20% | Video | DONE | Sixth cut, built around the organisers' three asks; every claim mapped to a file in `DEMO.md` |
| 15% | Building in public | OWNER | Repo, site and evidence are public. Nine drafts in `posts/`, none posted yet |
| 10% | Usefulness and originality | DONE | `README.md`, `BUSINESS.md`; the verifier catching a real model's false success is the thesis shown on real data |

## Engineering gates
| Gate | Status | Evidence |
|---|---|---|
| Tests, lint, format | DONE | `uv run pytest -q`: 780 tests pass; `ruff check` and `ruff format --check` clean; 81 UI tests (Oct 12, 14:06 IST) |
| Docker kit | DONE | Rebuilt again Oct 12, 14:15 IST at `ab5e1e8` (same result). Earlier: rebuilt Oct 12, 00:38 IST from the then-final code: `docker compose up --build`, both services healthy, the chaos demo (S16) through `POST /api/runs` verified SUCCESS, 24 of 24 checks, dashboard served |
| Secret scan, full history | DONE | `gitleaks git --log-opts=--all --redact`: no leaks, 61 commits, run at 14:00 IST right before the repo went public. Author addresses in the history are GitHub no-reply addresses |
| `/security-review` | DONE | Oct 10, 23:55 IST: reviewed the API (run start, public-mode access code and budget checks, static file serving), the sandbox bind-host option, the trace-id link and the Docker kit. No high-confidence findings. Static serving resolves paths and requires them inside `ui/dist`; the access code is compared in constant time; the container runs as a non-root user and ports publish to 127.0.0.1 only. Oct 12, 00:39 IST: the code changed since then that is reachable from outside (API, public-mode gate, CLI, runner, config) was re-read by hand, not with the skill: paid planners are an allow-list of free ones inverted, so a new planner is capped by default; the trace link is built from a server-side id. No findings. Run the skill once more right before going public |
| Real-model evaluation with saved evidence | DONE | Ten Gemini evaluation files in `evidence/eval/` (see `EVIDENCE.md` section 7), 28 single runs in `evidence/runs/`, eight experiment files in `evidence/experiments/`. $4.06 at list price in total, $0 charged |
| Neatlogs trace screenshots in `evidence/` | DONE | `evidence/screenshots/07`, `09`, `10`, `11`, `13` to `17`: real Gemini runs with WORKFLOW, AGENT, LLM, TOOL, CHAIN and EVALUATOR spans, state changes, and the before and after pair |

## What only the owner can do, in order
1. Watch the video once: https://eartherai.github.io/zerodrop/video/zerodrop-demo.mp4
2. Entire page: on entire.io open Repositories, Add repository, install the Entire GitHub App for `Eartherai/zerodrop`.
3. Post at least one #neatHack post from `posts/` before submitting (07 or 08).
4. At 19:00 IST sharp, quote the official neatlogs post with the text in `SUBMISSION.md` and attach `evidence/video/zerodrop-demo-x.mp4`. The sponsors engage with the first 50 quote posts.
5. Optional: choose a licence for the repository (none is set).
6. After the hackathon: the key hygiene items you already know about.

## Links
- Public repo: https://github.com/Eartherai/zerodrop
- Live demo (dashboard replaying real runs): https://eartherai.github.io/zerodrop/
- Evidence page: https://eartherai.github.io/zerodrop/evidence/
- Demo video: https://eartherai.github.io/zerodrop/video/zerodrop-demo.mp4
- Entire checkpoint: `01M4KEGN3Q174N063453HK5XC6` (page pending the GitHub App, row 3)
- Neatlogs trace of the demo run: `https://app.neatlogs.com/traces/0652c95c208d53311eecccf73fe1cae0` (project members only; screenshot `10`)
- cfo.ai plan: https://cfo.ai/s/VyrSUZBAxHyXEJfC
