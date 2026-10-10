# Submission checklist

Submission: a public X quote post of the official neatlogs post, **Mon Oct 12, 19:00 to 23:55 IST**,
with team, name, project, public repo and demo link. Everything below must be ready for the
owner's approval by Mon Oct 12, 17:00 IST.

Status key: DONE (verified, evidence linked) / PARTIAL / TODO / OWNER (needs the owner).

## Required by the rules
| # | Requirement | Status | Evidence or what is missing |
|---|---|---|---|
| 1 | Demo video, 3 minutes or less, covering Neatlogs, Entire and cfo.ai (architecture, implementation, runtime, reasoning, result) | PARTIAL | Script: `DEMO.md`. Recording steps: `evidence/video/RECORDING.md`. Backup dashboard recordings and screenshots (oracle planner): `evidence/video/`, `evidence/screenshots/`. Final recording, voice-over and upload: OWNER |
| 2 | Public repository with commits dated during the hackathon | OWNER | Repo `github.com/Eartherai/zerodrop` is private until the security gate passes and the owner approves. First commit after the window opened (Oct 10, 12:30 IST); history never rewritten |
| 3 | Accessible Entire checkpoint link plus its ID | PARTIAL | ID `01M4KEGN3Q174N063453HK5XC6`. Link: https://entire.io/gh/Eartherai/zerodrop/commit/dda3a4ea468bd53ff5a64618fe179ed57a36f820 . Ref pushed: `refs/entire/checkpoints/C6/01M4KEGN3Q174N063453HK5XC6`. Not reachable by outsiders while the repo is private: re-check logged out after it goes public |
| 4 | cfo.ai business plan (pricing, costs, revenue, runway) | PARTIAL | Input written: `BUSINESS.md`. Building it in cfo.ai needs the owner's sign-in |
| 5 | X quote post with team, name, project, repo, demo link | OWNER | Draft: `posts/06-submission.md`. Posting is the owner's action |

## Judging criteria
| Weight | Criterion | Status | Evidence or what is missing |
|---|---|---|---|
| 30% | Agent that works | PARTIAL | Engine, recovery, crash/resume and verifier: 20/20 scenarios with the deterministic oracle planner (`EVALUATION.md`). **Real Claude planner not measured yet** (blocked: API credit balance) |
| 25% | Sponsor tools | PARTIAL | Neatlogs: traced runs with trace id linked to each run; trace-tree screenshots TODO. Entire: checkpoint created and pushed. cfo.ai: plan input ready |
| 20% | Video | PARTIAL | Script, recording steps and backup dashboard recordings ready; Neatlogs, Entire and cfo.ai footage not captured yet |
| 15% | Building in public | TODO | Drafts in `posts/`; posting is the owner's action |
| 10% | Usefulness and originality | PARTIAL | `README.md`, `BUSINESS.md` |

## Engineering gates
| Gate | Status | Evidence |
|---|---|---|
| Tests, lint, format | DONE | `uv run pytest -q` 667 passed; `ruff check` and `ruff format --check` clean (Oct 10, 23:28 IST) |
| Docker kit | DONE | `docker compose up` then S16 through `POST /api/runs`: verified SUCCESS, 24/24 checks (Oct 10, 23:20 IST) |
| Secret scan, full history | DONE | `gitleaks git --log-opts=--all --redact`: no leaks, 24 commits (Oct 10, 23:18 IST). Re-run before going public |
| `/security-review` | DONE | Oct 10, 23:55 IST: reviewed the API (run start, public-mode access code and budget checks, static file serving), the sandbox bind-host option, the trace-id link and the Docker kit. No high-confidence findings. Static serving resolves paths and requires them inside `ui/dist`; the access code is compared in constant time; the container runs as a non-root user and ports publish to 127.0.0.1 only. Re-run before going public |
| Real-model evaluation with saved evidence | TODO | Blocked: API credit balance |
| Neatlogs trace screenshots in `evidence/` | TODO | Needs dashboard or CLI read access |

## Links to fill in at submission
- Public repo:
- Demo video:
- Entire checkpoint:
- Neatlogs trace of the demo run:
- cfo.ai plan:
