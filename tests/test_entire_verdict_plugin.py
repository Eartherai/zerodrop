"""The `entire verdict` plugin (tools/entire-verdict): commits, their Entire checkpoint, their results."""

from __future__ import annotations

import json
import subprocess
from importlib.machinery import SourceFileLoader
from importlib.util import module_from_spec, spec_from_loader
from pathlib import Path

import pytest

PLUGIN = Path(__file__).resolve().parents[1] / "tools" / "entire-verdict" / "entire-verdict"
CHECKPOINT = "01TESTCHECKPOINT0000000000"


def load_plugin():
    loader = SourceFileLoader("entire_verdict", str(PLUGIN))
    spec = spec_from_loader("entire_verdict", loader)
    assert spec is not None
    module = module_from_spec(spec)
    loader.exec_module(module)
    return module


def git(repo: Path, *args: str) -> str:
    done = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, check=True)
    return done.stdout.strip()


def commit(repo: Path, message: str) -> str:
    (repo / "file.txt").write_text(message, encoding="utf-8")
    git(repo, "add", "-A")
    git(
        repo,
        "-c",
        "user.name=t",
        "-c",
        "user.email=t@example.invalid",
        "commit",
        "-q",
        "--no-verify",
        "-m",
        message,
    )
    return git(repo, "rev-parse", "HEAD")


@pytest.fixture
def repo(tmp_path: Path) -> dict:
    git(tmp_path, "init", "-q")
    first = commit(tmp_path, "first, no checkpoint")
    second = commit(tmp_path, f"second\n\nEntire-Checkpoint: {CHECKPOINT}")
    git(tmp_path, "update-ref", f"refs/entire/checkpoints/00/{CHECKPOINT}", second)
    git(tmp_path, "remote", "add", "entire", "entire://example.entire.io/et/team/project")
    results = tmp_path / "evidence" / "eval"
    results.mkdir(parents=True)
    run = {"scenario_id": "S01", "status": "FAILED", "agent_claimed_status": "SUCCESS", "model": "m-small"}
    batch = {
        "outcomes": [
            {
                **run,
                "run_id": "r1",
                "git_commit": first[:12],
                "matched_expectation": False,
                "false_success_claim": True,
            },
            {
                **run,
                "run_id": "r2",
                "git_commit": second[:12],
                "matched_expectation": True,
                "false_success_claim": False,
            },
            {
                **run,
                "run_id": "r3",
                "git_commit": second[:12],
                "matched_expectation": True,
                "false_success_claim": False,
                "model": None,
            },
        ]
    }
    (results / "pass.json").write_text(json.dumps(batch), encoding="utf-8")
    # The same run saved a second time on its own must not be counted twice.
    (results / "single.json").write_text(json.dumps(batch["outcomes"][1]), encoding="utf-8")
    (results / "not-a-result.json").write_text(json.dumps({"hello": "world"}), encoding="utf-8")
    return {"path": tmp_path, "first": first, "second": second}


def rows(repo: dict, capsys: pytest.CaptureFixture[str], *extra: str) -> list[dict]:
    assert load_plugin().main(["--repo", str(repo["path"]), "--format", "json", *extra]) == 0
    return json.loads(capsys.readouterr().out)


def test_each_commit_gets_its_checkpoint_and_its_counts(
    repo: dict, capsys: pytest.CaptureFixture[str]
) -> None:
    first, second = rows(repo, capsys)
    assert (first["sha"], first["checkpoints"], first["runs"], first["passed"], first["flagged"]) == (
        repo["first"],
        [],
        1,
        0,
        1,
    )
    assert second["sha"] == repo["second"]
    assert second["checkpoints"] == [CHECKPOINT]
    assert second["checkpoint_state"] == ["recorded"]
    assert (second["runs"], second["passed"], second["flagged"]) == (2, 2, 0)
    assert second["url"] == f"https://entire.io/et/team/project/commit/{repo['second']}"


def test_models_only_leaves_out_scripted_runs(repo: dict, capsys: pytest.CaptureFixture[str]) -> None:
    assert [row["runs"] for row in rows(repo, capsys, "--models-only")] == [1, 1]


def test_one_commit_lists_its_runs(repo: dict, capsys: pytest.CaptureFixture[str]) -> None:
    assert load_plugin().main(["--repo", str(repo["path"]), repo["second"][:8]]) == 0
    out = capsys.readouterr().out
    assert CHECKPOINT in out and "S01" in out and "r1" not in out


def test_a_trailer_without_its_ref_is_reported_as_trailer_only(
    repo: dict, capsys: pytest.CaptureFixture[str]
) -> None:
    git(repo["path"], "update-ref", "-d", f"refs/entire/checkpoints/00/{CHECKPOINT}")
    assert rows(repo, capsys)[1]["checkpoint_state"] == ["trailer only"]


def test_no_results_is_an_error_not_an_empty_table(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    git(tmp_path, "init", "-q")
    assert load_plugin().main(["--repo", str(tmp_path)]) == 1
    assert "no result files" in capsys.readouterr().err
