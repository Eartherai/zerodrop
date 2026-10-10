# ZeroDrop business plan

Input for the cfo.ai model. Numbers marked **measured** come from files in `evidence/`.
Numbers marked **assumption** are planning choices, stated so they can be changed in the model.
Nothing here is a market-size claim we cannot source.

## Problem
Every time a company changes its billing system, CRM or helpdesk, someone has to move the data.
Today that is a one-off script or a consultant. The failure mode is quiet: a rate limit drops a
batch, a timeout hides a write that actually landed and the retry duplicates it, an API version
changes halfway through. Nobody finds out until a customer is billed twice or an invoice is
missing at audit time.

## Product
ZeroDrop is an agent that runs the migration and then proves the result.
- The model reads both systems and writes the field mapping in a restricted mapping language.
- Deterministic code executes it: idempotent batches, a durable ledger, crash and resume.
- An independent verifier re-reads both systems and issues a reconciliation certificate:
  counts, duplicates, money per currency to the minor unit, references, field-level comparison.

What the customer buys is the certificate, or an exact list of what did not arrive and why.

## Customer
1. **Primary: migration agencies and implementation partners.** They run migrations repeatedly,
   carry the liability when data goes missing, and bill by the project. ZeroDrop turns days of
   scripting and manual reconciliation into a supervised run with a report they can hand over.
2. **Secondary: SaaS vendors' onboarding teams.** Slow or risky migration is the main reason a
   signed customer does not go live. A vendor can offer verified import as part of onboarding.
3. **Later: ops and RevOps teams at mid-size companies** doing a one-off switch themselves.

## Pricing (assumption)
| Plan | Price | Includes |
|---|---|---|
| Pay per migration | $499 per verified migration | Up to 50,000 records, certificate, 30-day re-run |
| Volume | $0.004 per record above 50,000 | Same guarantees |
| Agency | $1,500 per month | 5 migrations per month, white-label certificate, priority support |
| Vendor (embedded) | From $4,000 per month | API access, custom connectors, SLA |

Charging per **verified** migration ties revenue to the outcome the customer cares about.
A run that ends FAILED is not billed.

## Unit economics
| Item | Value | Source |
|---|---|---|
| Model cost per verified migration | **$0.08 measured** (two verified runs: $0.083 and $0.082 at Gemini Flash list price) | `evidence/runs/S01-clean-gemini.json`, `evidence/runs/S16-demo-chaos-gemini-3.6-flash.json`. Two runs on sandbox data, not an average over an evaluation |
| Hard ceiling on model cost per run | $1.50 | Enforced in code (`max_cost_usd`), run stops safely at the cap |
| Compute and storage per migration | $0.50 | Assumption: one small container for under an hour plus the ledger |
| Support time per migration | 0.5 h at $40/h = $20 | Assumption: reviewing quarantined records with the customer |
| Payment processing | 2.9% + $0.30 | Assumption: standard card pricing |

Even at the hard ceiling, model cost is at most 0.3% of the $499 price. The dominant variable
cost is human support time, which is why the product reports quarantined records with a reason
for each: it shortens that conversation.

## Costs (assumption, first 12 months)
| Item | Monthly |
|---|---|
| Two founders, minimal salary | $8,000 |
| Infrastructure and tooling | $600 |
| Connector development (contract) | $2,000 |
| Sales and marketing | $1,500 |
| Legal, accounting, insurance | $900 |
| **Total fixed** | **$13,000** |

Variable cost per pay-per-migration sale, with the model at its hard cap: $20.00 support
+ $0.50 compute + $14.77 payment fee + $1.50 model = **$36.77**.
Break-even: 13,000 / (499 - 36.77) = 28.1, so **29 verified migrations per month**.
On the agency plan (5 migrations, one card charge): 1,500 - (5 x $22.00) - $43.80 = $1,346.20
margin per plan, so **10 agency plans** cover fixed costs.

## Go to market
1. Open-source the verifier and the sandbox. The verifier is useful on its own (it checks any
   migration, including one done by hand), and it is the proof that we do not grade ourselves.
2. Sell to migration agencies first: short sales cycle, repeated use, direct feedback on connectors.
3. Build connectors in the order agencies ask for them. The mapping language and engine do not
   change per connector; a connector is a thin client plus the target's schema.
4. Use each certificate as a referral surface: it is shared with the end customer and names the tool.

## Competition
| Alternative | What it does well | Gap ZeroDrop fills |
|---|---|---|
| Hand-written scripts | Free, flexible | No recovery, no proof; every migration starts from zero |
| ETL and sync tools | Reliable pipelines for known schemas | Mapping is manual; they move data but do not certify business-level integrity (money totals, references) |
| Vendor import wizards | Built in | One direction, CSV-shaped, fail on anything unusual |
| Consultants | Handle edge cases | Expensive and slow; verification is sampling by hand |
| General coding agents | Can write the script | The script still has to survive failures, and the agent grades its own work |

The defensible part is not the model call. It is the engine and the independent verifier, plus an
evaluation suite of failure scenarios that every change must pass.

## Risks
- **Trust.** A migration tool that is wrong once is not used again. Mitigation: the verifier is
  independent by construction, false success claims are a tracked metric, and the run stops and
  asks rather than guessing on anything destructive.
- **Connector breadth.** Each new system is work. Mitigation: agencies prioritize; the sandbox
  pattern lets us test a connector against injected failures before a customer sees it.
- **Model price or quality changes.** Mitigation: the model is used for a bounded number of
  decisions per run, with a hard cost cap; the evaluation suite detects quality regressions.

## Runway scenario for cfo.ai (assumption)
- Starting cash: $60,000.
- Fixed costs: $13,000 per month.
- Month 1 to 3: 4, 8, 14 verified migrations and 0, 1, 2 agency plans.
- Growth after month 3: 20% month over month in migrations, one new agency plan per month.
- Sensitivities to model: price ($299 / $499 / $799), support time (0.25 h / 0.5 h / 1 h per
  migration), share of runs that end not billable (5% / 15%).
