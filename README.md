# ZeroDrop

**The migration agent that proves nothing was lost.**

ZeroDrop is an autonomous agent for SaaS data migrations. Give it a goal such as "move all customers, subscriptions and invoices from LegacyBill to NovaBill". It explores both systems, infers the field mapping, migrates in idempotent batches, recovers from rate limits, timeouts, crashes and breaking API changes, and finishes with a reconciliation report from an independent verifier that the agent cannot influence.

> Status: under construction during neatHack 2026. See `hackathon.md` for the dated build log and what is actually verified.

## Design in one line
The LLM decides, code executes, and an independent checker judges.

## Quick start (development)
```sh
uv sync
uv run pytest -q
```
Configuration lives in environment variables (see `.env.example`). Never commit real keys.

## Docs
- `docs/PLAN.md`: approved plan
- `docs/CONTRACTS.md`: APIs and module interfaces
- `hackathon.md`: build log and evidence
