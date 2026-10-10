# hackathon.md: ZeroDrop build log (neatHack 2026)

## Project
- **Name:** ZeroDrop
- **Purpose:** An autonomous agent that migrates a company's billing data between SaaS systems, recovers from API failures and breaking schema changes on its own, and proves nothing was lost.
- **Problem:** Switching SaaS tools means moving customer, subscription and invoice data through rate-limited, changing APIs with different schemas. Today this is done with brittle scripts or consultants, and failures show up later as silently dropped, duplicated or corrupted records.

## Team
- Team Tokenmaxing

## Stack
- Python 3.12+, FastAPI, Pydantic v2, SQLite, httpx
- Anthropic API (Claude Opus 5.5) for mapping inference and failure diagnosis
- neatlogs: runtime tracing of every agent run (planned; key not yet configured in this environment)
- Entire: checkpoints for coding-agent sessions (planned)
- cfo.ai: business plan (pending)
- Sandbox services built during the hackathon: LegacyBill (source) and NovaBill (target), with a seeded fault injector

## Build log

### 2026-10-10 (Day 1)
- 12:30 IST: coding window opened. Plan prepared beforehand (research and planning only): `docs/PLAN.md`.
- 15:40 IST: project skeleton and frozen shared contracts (`src/zerodrop/models.py`, `docs/CONTRACTS.md`). Telemetry layer that no-ops without a Neatlogs key. Neatlogs SDK 1.4.26 offline Doctor check passed (`python -m neatlogs doctor --local`: LOCAL_ENVELOPE_VALID). No traces sent yet.
- Provenance note: this initial work was written in a Claude Code cloud session. Coding-agent sessions are captured with Entire where the environment allows; anything not captured is stated here.

## Demo
- Not available yet.

## Known limitations and next steps
- Real model runs and Neatlogs traces need `ZERODROP_ANTHROPIC_KEY` and `NEATLOGS_API_KEY` in the environment.

## Submission
- Confirmed requirements (from neatlogs.com/hackathon, read 2026-10-10):
  - Public quote post of the official neatlogs submission post on X: team, name, project, public repository, demo link. Window: Mon Oct 12, 7:00–11:55 PM IST.
  - Demo video of 3 minutes or less covering neatlogs, Entire and cfo.ai: architecture, implementation, runtime, reasoning and result.
  - Public repository with commits dated during the hackathon. All code written between Oct 10 12:30 PM IST and the deadline.
  - An accessible Entire checkpoint link plus its checkpoint ID.
  - A cfo.ai business plan covering pricing, costs, revenue and runway.
- Outstanding: everything above.
