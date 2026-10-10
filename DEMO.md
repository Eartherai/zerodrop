# Demo video script (target 2:50, hard limit 3:00)

Recording steps are in `evidence/video/RECORDING.md`. Every number spoken here must match the
file named next to it; where a line says **[from evidence]**, read the value from that file on
the day of recording.

| Time | On screen | Voice-over |
|---|---|---|
| 0:00 to 0:12 | Title card: "ZeroDrop: the migration agent that proves nothing was lost" | "Every time a company switches a SaaS tool, someone moves the data. And migrations lose data quietly: a dropped batch, a duplicate after a timeout, an API that changes halfway through." |
| 0:12 to 0:30 | Architecture diagram from `ARCHITECTURE.md` | "ZeroDrop is an agent built on one rule: the LLM decides, code executes, and an independent checker judges. Claude writes the field mapping in a restricted language. A deterministic engine runs it with idempotent writes and a durable ledger. A verifier that shares no code with the agent re-reads both systems and gives the verdict." |
| 0:30 to 1:15 | Dashboard, start "Demo: everything goes wrong" (S16) with the Claude planner. Point at: failures panel, recovery steps, mapping v1 to v2 diff, "found already committed, 0 re-sent" | "Here it migrates customers, subscriptions and invoices while the target API misbehaves. Rate limits: it waits exactly what the server asks. A timeout after a write that actually landed: it looks the records up instead of sending them twice. Then the API changes version mid-run. Retrying cannot fix that, so the agent reads the new schema, rewrites the mapping, tests it on samples and resumes from its checkpoint." |
| 1:15 to 1:30 | Reconciliation certificate, all checks green | "The verifier checks counts, duplicates, money per currency to the cent, references and every field. All checks pass. That status comes from the verifier, not from the agent." |
| 1:30 to 1:45 | Run S01 with the naive planner; red certificate | "And this is why it matters. A plausible but wrong mapping: the engine believes it succeeded. The verifier disagrees: yen totals are a hundred times too large. We measure that as a false success claim." |
| 1:45 to 2:10 | **Neatlogs**: trace tree of the S16 run (WORKFLOW, AGENT, LLM, TOOL, CHAIN, EVALUATOR), click the diagnoser's LLM span, then the root span's attributes | "Neatlogs is the runtime record. Every run is one trace: the planner and diagnoser are agent spans, each model call is captured by the wrapped client, each batch is a tool span, each recovery decision is a chain span, and the verifier is an evaluator span. The root carries the verdict and whether the agent's own claim matched. This is how we found our first real bug: a rate-limit storm that used up the retry budget. **[from `EVALUATION.md`]** nineteen of twenty scenarios before the fix, twenty of twenty after." |
| 2:10 to 2:30 | **Entire**: checkpoint page for the fix commit, then `entire checkpoint list` in the terminal | "Entire is the record of how it was built. Each commit links to the coding session that produced it: the prompt, the reasoning, the tests that failed first. The run page links its trace and its commit, so a failure in Neatlogs leads to the session in Entire that fixed it." |
| 2:30 to 2:45 | **cfo.ai**: the plan summary, pricing and runway chart | "cfo.ai holds the business model. We charge per verified migration. Model cost is capped in code at a dollar fifty per run, **[from `BUSINESS.md`]** against a four hundred ninety-nine dollar price, so the cost that matters is support time, and the plan shows break-even at twenty-nine migrations a month." |
| 2:45 to 2:55 | Results table from `EVALUATION.md`, then repo URL | "Twenty failure scenarios, **[from evidence]** verified outcomes, zero false successes. ZeroDrop. The code, traces and checkpoints are public." |

## What each sponsor section must cover (checklist for the edit)
| | Architecture | Implementation | Runtime | Reasoning | Result |
|---|---|---|---|---|---|
| Neatlogs | One trace per run, span kinds map to components | `telemetry.py`, wrapped Anthropic client, spans in the engine and verifier | Live trace of the S16 run | Diagnoser LLM span shows why the mapping changed | Found the S03 bug; before/after table |
| Entire | Checkpoint per commit, stored as git refs | Enabled for Claude Code, redaction rules in `.entire/settings.json` | `entire checkpoint list`, checkpoint page | Session transcript behind a fix | Trace to commit to session chain |
| cfo.ai | Per-migration pricing model | Plan built from `BUSINESS.md` | The plan in cfo.ai | Why per verified migration; sensitivity to support time | Break-even and runway |
