"""Evaluation and demo scenarios: dataset options, fault plans and the outcome a correct agent should reach."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field

from zerodrop.models import FaultPlan, RunStatus

DEFAULT_GOAL = (
    "Move all customers, subscriptions and invoices from LegacyBill to NovaBill. "
    "Do not lose, duplicate or alter any record; skip records the legacy system marks as deleted."
)

SCENARIO_FILE = Path(__file__).resolve().parents[2] / "scenarios" / "scenarios.yaml"


class DatasetOptions(BaseModel):
    model_config = ConfigDict(extra="forbid")
    seed: int = 7
    size: str = "small"
    deleted_customers: int | None = None
    jpy_invoices: bool = True
    orphan_invoices: int = 0
    duplicate_emails: int = 0
    injection_note: bool = True


class Scenario(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    title: str
    description: str
    goal: str = DEFAULT_GOAL
    dataset: DatasetOptions = Field(default_factory=DatasetOptions)
    fault_plan: FaultPlan = Field(default_factory=FaultPlan)
    source_fault_plan: FaultPlan | None = None
    initial_version: str = "v1"
    crash_after_batches: int | None = None  # crash once mid-run, then resume from the ledger
    rotated_token_available: bool = False  # write the rotated token to a file the engine may re-read on 401
    batch_size: int = 50
    expect: RunStatus = RunStatus.SUCCESS  # what the independent verifier should report for a correct agent
    tags: list[str] = Field(default_factory=list)


def load_scenarios(path: str | Path | None = None) -> list[Scenario]:
    raw: Any = yaml.safe_load(Path(path or SCENARIO_FILE).read_text(encoding="utf-8"))
    scenarios = [Scenario.model_validate(item) for item in raw["scenarios"]]
    ids = [s.id for s in scenarios]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate scenario ids")
    return scenarios


def get_scenario(scenario_id: str, path: str | Path | None = None) -> Scenario:
    for scenario in load_scenarios(path):
        if scenario.id == scenario_id:
            return scenario
    raise KeyError(f"unknown scenario {scenario_id!r}")
