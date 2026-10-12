# entire-verdict: an Entire CLI plugin

`entire verdict` joins two records a repository already keeps:

- **Entire's build record**: the checkpoint (agent session) each commit came from, read from the
  commit's `Entire-Checkpoint` trailer and from `refs/entire/checkpoints/*`;
- **saved evaluation results**: JSON files in which every run records the commit it ran on.

For the code at each commit it answers one question: which session produced it, and what did an
independent check measure there? In ZeroDrop that is the question the whole project is about, so
the build record and the checker's verdict belong in one table.

## Install and run

Entire discovers plugins as executables named `entire-<name>`. From the repository root:

```sh
entire plugin install ./tools/entire-verdict/entire-verdict
entire verdict --models-only          # one row per commit that has real-model runs
entire verdict 933a7a9                # every run recorded at that commit
entire verdict --format md            # a Markdown table
entire verdict --format json          # machine-readable
```

It needs Python 3.10 or newer and git. It uses the standard library only and makes no network
calls. It also runs without Entire installed: `./tools/entire-verdict/entire-verdict`.

## What it prints

```
date              commit   Entire checkpoint                      runs  passed  false success  models
2026-10-11 15:45  78d92da  none                                   11    5       5              gemini-3-flash-preview, gemini-3.1-flash-lite
2026-10-11 23:32  933a7a9  01M4KEGN3Q174N063453HK5XC6 (recorded)  18    15      1              gemini-3.1-flash-lite
2026-10-11 23:53  1838455  01M4KEGN3Q174N063453HK5XC6 (recorded)  22    22      0              gemini-3.5-flash-lite
```

Each row also carries the commit's public Entire page, worked out from the `entire://` remote
(or the GitHub remote). A checkpoint is shown as `recorded` when its ref is in the clone and as
`trailer only` when the commit names a checkpoint whose ref is not there. The full output for
this repository is saved in [`evidence/entire/verdict-by-commit.md`](../../evidence/entire/verdict-by-commit.md).

## On another repository

Every path and key is an option, so it works wherever result files record a commit:

```sh
entire verdict --results 'bench/**/*.json' --commit-key sha --pass-key ok --flag-key regression --flag-label regressions
```

A result file is either one run (an object with the commit key) or a batch (an object with an
`outcomes` list). The same run saved twice is counted once, by `run_id`.

## Limits

- It reads what is in the clone. It does not call Entire's API or fetch checkpoints.
- In this repository every commit with a trailer points to the same checkpoint, because the build
  session was started one folder above the repository and Entire's hooks did not see it. The
  table shows that plainly.
- "passed" counts runs that ended as the scenario expects. Passes cut short by a provider's quota
  are in the files too, so a row is the record at that commit, not a pass rate.

Tests: `uv run pytest -q tests/test_entire_verdict_plugin.py` (they build a throwaway git repository).
