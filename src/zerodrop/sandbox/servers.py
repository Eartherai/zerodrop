"""Run LegacyBill and NovaBill as real HTTP servers (uvicorn in background threads)."""

from __future__ import annotations

import argparse
import contextlib
import json
import socket
import threading
import time
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx
import uvicorn
import yaml
from fastapi import FastAPI

from zerodrop.models import FaultPlan
from zerodrop.sandbox import legacybill, novabill
from zerodrop.sandbox.chaos import coerce_plan
from zerodrop.sandbox.fixtures import Dataset, generate

HOST = "127.0.0.1"
STARTUP_TIMEOUT_S = 10.0


@dataclass
class SandboxHandle:
    source_url: str
    target_url: str
    admin_token: str
    target_token: str
    rotated_token: str
    dataset: Dataset | None = field(default=None, repr=False)

    def admin(self, method: str, path: str, json: Any = None) -> Any:
        """Call a NovaBill admin endpoint (``/_admin/...``) and return the decoded JSON body."""
        with httpx.Client(base_url=self.target_url, timeout=10.0, trust_env=False) as client:
            response = client.request(method, path, json=json, headers={"X-Admin-Token": self.admin_token})
        response.raise_for_status()
        return response.json()

    def reset(self, seed: int = 0, fault_plan: FaultPlan | dict[str, Any] | None = None) -> Any:
        plan = coerce_plan(fault_plan)
        return self.admin(
            "POST", "/_admin/reset", json={"seed": seed, "fault_plan": plan.model_dump(mode="json")}
        )

    def stats(self) -> Any:
        return self.admin("GET", "/_admin/stats")


class _ServerThread:
    """One uvicorn server on a pre-bound socket, so port 0 resolves before the thread starts."""

    def __init__(self, app: FastAPI, port: int, name: str) -> None:
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.sock.bind((HOST, port))
        except OSError:
            self.sock.close()  # e.g. the port is taken: do not leak the descriptor
            raise
        self.port: int = self.sock.getsockname()[1]
        config = uvicorn.Config(
            app,
            log_level="warning",
            access_log=False,
            lifespan="off",
            loop="asyncio",
            timeout_graceful_shutdown=2,
        )
        self.server = uvicorn.Server(config)
        self.stop_stalls: threading.Event | None = getattr(app.state, "stop_stalls", None)
        self.thread = threading.Thread(
            target=self.server.run, kwargs={"sockets": [self.sock]}, name=f"sandbox-{name}", daemon=True
        )

    @property
    def url(self) -> str:
        return f"http://{HOST}:{self.port}"

    def start(self) -> None:
        self.thread.start()
        deadline = time.monotonic() + STARTUP_TIMEOUT_S
        while not self.server.started:
            if not self.thread.is_alive() or time.monotonic() > deadline:
                raise RuntimeError(f"sandbox server on port {self.port} failed to start")
            time.sleep(0.01)

    def stop(self) -> None:
        if self.stop_stalls is not None:
            self.stop_stalls.set()  # stalled fault requests answer now instead of being cancelled
        self.server.should_exit = True
        if self.thread.is_alive():
            self.thread.join(timeout=STARTUP_TIMEOUT_S)
        self.sock.close()


def _wait_until_answering(url: str, path: str) -> None:
    deadline = time.monotonic() + STARTUP_TIMEOUT_S
    with httpx.Client(timeout=1.0, trust_env=False) as client:
        while True:
            try:
                if client.get(url + path).status_code < 500:
                    return
            except httpx.TransportError:
                pass
            if time.monotonic() > deadline:
                raise RuntimeError(f"{url}{path} did not answer within {STARTUP_TIMEOUT_S}s")
            time.sleep(0.02)


@contextlib.contextmanager
def run_sandbox(
    dataset: Dataset,
    fault_plan: FaultPlan | dict[str, Any] | None = None,
    source_port: int = 0,
    target_port: int = 0,
    *,
    source_fault_plan: FaultPlan | dict[str, Any] | None = None,
    initial_version: str = "v1",
    target_token: str = novabill.DEFAULT_TOKEN,
    rotated_token: str = novabill.ROTATED_TOKEN,
    admin_token: str = novabill.DEFAULT_ADMIN_TOKEN,
) -> Iterator[SandboxHandle]:
    """Start LegacyBill and NovaBill on 127.0.0.1 (port 0 = any free port); stop both on exit.

    ``fault_plan`` drives NovaBill; LegacyBill only gets faults from ``source_fault_plan``.
    """
    source_app = legacybill.create_app(dataset, fault_plan=source_fault_plan)
    target_app = novabill.create_app(
        dataset.prices,
        token=target_token,
        admin_token=admin_token,
        initial_version=initial_version,
        rotated_token=rotated_token,
        fault_plan=fault_plan,
    )
    started: list[_ServerThread] = []
    try:
        for app, port, name in (
            (source_app, source_port, "legacybill"),
            (target_app, target_port, "novabill"),
        ):
            server = _ServerThread(app, port, name)
            started.append(server)
            server.start()
        source, target = started
        _wait_until_answering(source.url, "/api/account")
        _wait_until_answering(target.url, "/api/meta")
        yield SandboxHandle(source.url, target.url, admin_token, target_token, rotated_token, dataset)
    finally:
        for server in reversed(started):
            server.stop()


def load_fault_plan(path: str | Path | None) -> FaultPlan | None:
    """Read a FaultPlan from a JSON or YAML file."""
    if path is None:
        return None
    text = Path(path).read_text(encoding="utf-8")
    data = json.loads(text) if str(path).endswith(".json") else yaml.safe_load(text)
    return coerce_plan(data or {})


def serve_forever(
    seed: int,
    size: str = "demo",
    fault_plan: FaultPlan | dict[str, Any] | None = None,
    source_port: int = 8701,
    target_port: int = 8702,
    golden_path: str | Path | None = None,
) -> None:
    """Demo helper: serve a generated dataset on fixed ports until interrupted."""
    dataset = generate(seed, size)
    if golden_path is not None:
        dataset.write_golden(golden_path)
    with run_sandbox(dataset, fault_plan, source_port, target_port) as handle:
        print(f"LegacyBill (source): {handle.source_url}")
        print(f"NovaBill   (target): {handle.target_url}  [sandbox token: {handle.target_token}]")
        print("Faults are injected from the seeded fault plan. Ctrl+C to stop.", flush=True)
        with contextlib.suppress(KeyboardInterrupt):
            threading.Event().wait()


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Run the ZeroDrop sandbox (LegacyBill + NovaBill).")
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--size", default="demo", choices=["small", "demo", "large"])
    parser.add_argument("--fault-plan", help="JSON or YAML FaultPlan file")
    parser.add_argument("--source-port", type=int, default=8701)
    parser.add_argument("--target-port", type=int, default=8702)
    parser.add_argument("--golden", help="write the golden expected records to this path")
    args = parser.parse_args(argv)
    serve_forever(
        args.seed,
        args.size,
        load_fault_plan(args.fault_plan),
        args.source_port,
        args.target_port,
        golden_path=args.golden,
    )


if __name__ == "__main__":
    main()
