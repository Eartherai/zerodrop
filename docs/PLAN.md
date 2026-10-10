# neatHack 2026 — Phase 0 Plan (research mode, no implementation code)

Prepared: 2026-10-10 00:50 IST (2026-10-09 19:20 UTC). Coding starts 2026-10-10 12:30 IST (in about 11h40m).

---

## 0. What was verified, and what was not

This plan was prepared in a Claude Code **cloud container**, not on your Mac. That limits what could be checked directly.

| Item | Status | Evidence / blocker |
|---|---|---|
| Date/time | Verified | 2026-10-10 00:49 IST at start of session. Research mode is in effect. |
| Your Entire checkout `/et/hackathone/hackathon` | **Not reachable from here** | This container holds only an unrelated repo (`Eartherai/TensorTonic-Solutions`, 1 commit). The Entire CLI is not installed here, and `entire.io` is blocked by this environment's network policy. You need to run the diagnostics in section 10 on your Mac. |
| Official rules page `neatlogs.com/hackathon` and `/hackathon/skill` | **Not reachable from here** | `neatlogs.com`, `docs.neatlogs.com`, `entire.io`, and `dev.to` are denied by the container's egress policy. Rules below are taken from your verified summary, plus public corroboration. |
| Neatlogs SDK guidance | Verified from primary source | Official `neatlogs/skills` and `neatlogs/neatlogs` GitHub repos (SDK v1.4.26, Python 3.10–3.13). |
| Entire CLI behavior | Verified from primary source | Official `entireio/cli` repo, CHANGELOG through v0.11.4 (2026-10-06). |
| `NEATLOGS_API_KEY` | Not set in this container | Expected. It must be set on your Mac, never pasted into chat. |
| `ANTHROPIC_API_KEY` | Not set in this container | Your Mac's Claude Code billing must be checked with `/status` there. |
| Provider of the ~$100 credits | **Confirmed by you: Anthropic API** | App model decided: Claude Opus 5.5 (see section 8). Expiry date and balance still to be checked in the Console. |
| cfo.ai neatHack offer | Not independently verifiable | Search found cfo.ai (formerly Runway Financial, AI CFO "Ari", 14-day trial) but no public page for the neatHack credits. Use `cfo.ai/neathacks` as you were instructed. |

### Check-in confirmation (received Oct 10): team **Tokenmaxing**
- **Neatlogs:** paid plans free during the event. Official setup guide with a coding-agent prompt: neatlogs.com/hackathon/neatlogs-setup-guide.html. Build-log skill: neatlogs.com/hackathon/skill.
- **Entire:** official guide at hack.entire.io/neathacks-2026/ says *connect your GitHub repository*, install the CLI, and capture a first checkpoint. Explore **Trails** and optional **Graph/Brain**. **The submission must include an accessible checkpoint link and ID.**
  - In the CLI source: Graph is the `entire graph` plugin (semantic index, `.graphignore`), Brain is the `entire-brain` plugin, and Trails are `entire trail`.
- **cfo.ai:** signup at cfo.ai/neathacks needs a card; cancel immediately in Settings → Billing. **Credits are provided by the neatHack team.**
- **Crustdata:** 5,000 credits via promo code (email signup only). Optional for ZeroDrop: could ground `BUSINESS.md` market sizing in real company data.
- **AWS:** a separate email gives the team one **$25 allowance** through an IAM login (EC2/Lambda/IAM roles/load balancers; us-east-1; Hackathon_VPC; one instance). It is used only for the optional hosted demo (section 9). Inference stays on the Anthropic API credits.
- **Decision point at T0:** if the Entire guide requires a GitHub repo, Option A (native `/et/` repo public) needs revisiting, with your approval, before any remote changes.

### Rule discrepancy to resolve at kickoff (09:00 IST)
- Your summary says coding runs from Oct 10 12:30 IST, with submissions Oct 12 19:00–23:55 IST.
- A participant's public planning note (JannetEkka/DSProjects) says "Oct 10 00:00 to Oct 11 23:59 IST". That is not an official source, but **confirm the exact coding cutoff, and whether video and docs may be finalized after it**, before relying on the Oct 12 timeline.
- A competitor's public repo names the track **"Build an agent that works"** and states that the three tools are worth 25%. This matches your summary.

---

## 1. Decision: concept scoring

Scores are my judgment on a 1–10 scale against the official weights, not measurements. The weighted total is out of 10.

| Concept | Functionality (30%) | Sponsor-tool fit (25%) | Demo (20%) | Build in public (15%) | Useful/original (10%) | **Weighted** | 48h feasibility | Main risk |
|---|---|---|---|---|---|---|---|---|
| **ZeroDrop-Migrate**: autonomous SaaS data migration that proves zero loss | 9 | 9 | 9 | 8 | 8 | **8.75** | High | Sandbox APIs must feel real |
| ZeroDrop-Incident: autonomous incident recovery (original candidate) | 8 | 8 | 7 | 7 | 4 | 7.25 | Medium-low | Very crowded; needs a credible system to break |
| AP invoice-exception resolver (three-way match, ledger posting) | 8 | 8 | 7 | 6 | 5 | 7.20 | Medium | Crowded (Peakflo, Kognitos, Sage Intacct); document parsing cost |
| Backup restore-drill agent (proves backups actually restore) | 8 | 7 | 6 | 6 | 8 | 7.05 | Medium | Heavy infrastructure; less visual |
| Due-diligence research agent (Crustdata + source reconciliation) | 7 | 7 | 6 | 7 | 5 | 6.60 | High | Verification is soft, so it is hard to benchmark |
| Issue → verified PR with fault injection | 7 | 7 | 6 | 7 | 3 | 6.40 | Medium | Crowded (Devin, Copilot agent, OpenHands); high LLM cost |

**Why the incident agent is demoted.** "System monitoring" and "GitHub issue fixing" are named as example tasks in the hackathon, so many teams will build them. Commercially, AI SRE is dominated by well-funded players: Resolve.ai (~$1B valuation), Datadog Bits AI SRE (GA), Cleric, Traversal, and New Relic's SRE agent. The judges build an observability product, so an observability agent invites direct comparison with their own field. A credible "real incident" environment is expensive to build in 48h.

**Winner: ZeroDrop: the migration agent that proves nothing was lost.** It keeps your name, which fits even better here.
**Fallback concept: AP invoice-exception resolver.** It reuses roughly 70% of the same runtime: durable state machine, independent verifier, chaos layer, telemetry, and the cfo.ai finance story. Decide between them at kickoff, after tracks are announced, never mid-build.
**Scope fallback inside ZeroDrop:** see the cut list in section 9.

### Why ZeroDrop scores highest
- **Reliability is the product, not decoration.** Idempotency, checkpoint/resume, backoff, replanning, and independent reconciliation are exactly what a migration customer pays for. This lines up directly with the 30% functionality weight and the "agent that works" track.
- **Verification is objective.** Counts, money totals to the cent, referential integrity, duplicates, and golden field-level truth are all computable by code, not judged by an LLM.
- **Failures are natural, not staged.** Real APIs rate-limit, time out after a write lands, change schemas, and reject odd records. The benchmark is easy to make deterministic with seeded fixtures and a seeded fault plan.
- **The demo reads instantly:** a progress counter, a breaking API change mid-run, the agent adapting, and a green reconciliation certificate.
- **The commercial value is concrete.** SaaS switching costs and migration consulting are real spend. Silent data loss is a known fear, and per-migration pricing makes cfo.ai modeling natural.
- **It is clearly differentiated.** The public competitor (ecom-profit-analyst) analyzes data read-only. ZeroDrop writes to live systems under failure and proves the result.

---

## 2. Product definition

**One line:** Tell ZeroDrop "move all customers, subscriptions and invoices from LegacyBill to NovaBill." It infers the mapping, migrates through rate-limited and changing APIs, survives failures and crashes, and hands back a reconciliation certificate. The certificate either proves every record arrived intact, or names exactly which records did not and why.

**User:** an ops or RevOps lead, or a migration consultant, at an SMB or mid-market company switching billing, CRM, or helpdesk tools.

**Environment, built during the hackathon and labeled honestly in the UI and README:**
- **LegacyBill (source):** a read-only REST API over a seeded SQLite dataset. Target size is about 2,000 customers, ~2,400 subscriptions, and ~9,000 invoices. The data has realistic mess: duplicate emails that differ by case, cents vs. decimal amounts, timezone-less dates, orphan invoices, soft-deleted rows, and one record whose notes field contains a prompt-injection string.
- **NovaBill (target):** a FastAPI service with an OpenAPI spec, scoped API keys, token-bucket rate limits with `Retry-After`, idempotency-key support, validation, pagination, and **versioned schemas**.
- **Chaos layer:** a deterministic, seeded fault plan. It injects 429 bursts, 5xx errors, timeouts where the write actually succeeded, partial batch acceptance, a mid-run v1→v2 schema change, credential rotation, and process kill. Faults are labeled as injected. The agent is never told when or which faults will occur, and the eval varies them so nothing can be hardcoded.
- **Stretch:** a real external target adapter, Stripe test mode (free, real rate limits, native idempotency keys). Only after section 9's Phase 4 exit criteria are met. It requires your Stripe test key.

---

## 3. Architecture

Python 3.12 + FastAPI + Pydantic v2 + SQLite (WAL) + pytest. The UI is Vite + React + Tailwind, a single page fed by server-sent events. No LangGraph: an explicit state machine is easier to verify and to explain in the demo.

### Division of labor: "the LLM decides, code executes, an independent checker judges"
| Responsibility | Owner | Why |
|---|---|---|
| Goal interpretation (entities, scope, constraints) | LLM, structured output | Natural-language goal |
| Schema understanding and mapping (`MappingSpec`) | **LLM agent loop** with tools | Semantic matching, units, enums, ambiguity |
| Mapping language | Whitelisted ops only: `rename`, `minor_to_major`, `parse_date(fmt,tz)`, `enum_map`, `split_name`, `lowercase`, `fk_lookup`, `default` | No arbitrary code execution, so it is safe against prompt injection |
| Dry run against target schema | Deterministic | Cheap, repeatable |
| Bulk transfer, batching, idempotency keys, checkpoints | Deterministic engine | Reliability must not depend on the model |
| Failure classification | Deterministic first, LLM only for `CONTRACT`/`UNKNOWN` | Cheap and predictable |
| Diagnosis and replanning after contract change | **LLM agent loop** (spec diff, error samples) | Requires reasoning |
| Verification | **Independent deterministic verifier** | The agent cannot certify itself |

### State machine (persisted, event-sourced in SQLite, streamed to the UI, mirrored as Neatlogs spans)
```
CREATED → DISCOVERING → PLANNING → DRY_RUN → EXECUTING ⇄ RECOVERING → VERIFYING
        → SUCCESS | PARTIAL_SUCCESS | FAILED | WAITING_FOR_APPROVAL
```
- Each record has a ledger row: `source_id, entity, mapping_version, idempotency_key, state (PENDING/WRITTEN/QUARANTINED/FAILED), target_id, last_error`.
- A checkpoint is written after every batch. Restart resumes from the ledger, and idempotency keys guarantee that re-sent writes cannot duplicate.

### Failure taxonomy → recovery policy
| Class | Signals | Policy |
|---|---|---|
| TRANSIENT | 429, 5xx, timeouts, connection resets | Exponential backoff with jitter, honoring `Retry-After`; max 6 attempts per request; circuit breaker after N consecutive failures |
| AMBIGUOUS_WRITE | Timeout after the request was sent | Look up by idempotency key or natural key before retrying; never blindly re-POST |
| CONTRACT | Same validation error across ≥ k% of a batch, or a spec version change | Pause writers, fetch the new spec, LLM diagnoses the diff and proposes `MappingSpec vN+1`, dry-run on samples, resume (max 3 replans) |
| DATA | Single-record validation failure | Quarantine with reason and continue; ends as PARTIAL_SUCCESS unless resolved |
| AUTH | 401/403 | Re-read credentials once; otherwise WAITING_FOR_APPROVAL |
| DESTRUCTIVE | Any delete/overwrite on target | Always WAITING_FOR_APPROVAL |
| BUDGET | LLM call/cost/time caps hit | Stop safely; FAILED or PARTIAL_SUCCESS with an honest report |

**Hard limits** (configurable): ≤ 30 LLM calls/run, ≤ $1.50/run, ≤ 15 min wall time, ≤ 3 replans, retry caps as above.

### Independent verifier (the core of the evidence)
- It is a separate module with **read-only** credentials. It reads source and target fresh, and never reads the agent's ledger or LLM output.
- **It must not reuse the agent's mapping.** Otherwise a wrong mapping would "verify" itself. It checks instead:
  - (a) mapping-independent invariants: per-entity counts, money totals per currency in minor units, referential integrity, uniqueness of normalized natural keys, no target duplicates;
  - (b) a user-declared **preservation contract** (e.g., "amount, currency, email, start date must be preserved");
  - (c) in eval only, **golden expected target records** produced by the fixture generator, which the agent never sees.
- Output: a signed-hash `ReconciliationReport`. The final status comes from the verifier, not the agent. Any case where "the agent claimed success but the verifier disagreed" is counted as a **false-success claim**.

### Safety
- Source data goes to the model only as delimited samples.
- Tools are a fixed set: no shell, no free-form HTTP.
- Writes use a scoped key; deletes need approval.
- The injected-instruction record is an eval case.

---

## 4. The demo's real failure and recovery (target: 0:35–1:30 of the video)
1. Goal entered. The agent explores both APIs, proposes a mapping, dry-runs it, and starts migrating. Customers complete.
2. Midway through subscriptions, NovaBill rolls to **API v2**: `plan_code` → `price_id`, and currency must be lowercase ISO. Batches start failing with 422 errors, and a 429 storm hits at the same time.
3. The classifier separates the transient 429s (backoff) from the contract failure (retrying won't help). It pauses writers, pulls the v2 spec, and the agent proposes **MappingSpec v2** (diff shown in the UI). The new mapping is dry-run on samples, and the run resumes from its checkpoint.
4. To prove it, we kill the process with `kill -9`, restart it, and it resumes from the ledger with zero duplicates.
5. The verifier shows counts, money totals to the cent, integrity, and 0 duplicates. Status: SUCCESS. The Neatlogs trace and the Entire commit of the agent version are linked from the certificate.

---

## 5. Sponsor tools: meaningful, verifiable use

### Neatlogs (runtime, not just coding sessions)
- **Init:** `neatlogs.init(api_key=os.getenv("NEATLOGS_API_KEY"), workflow_name="zerodrop-migration")`, once per process, before importing `anthropic`. Then `neatlogs.wrap(Anthropic(...))`. Do **not** also list `anthropic` in `instrumentations=`, which would double-capture.
- **Spans:**
  - `WORKFLOW`: `run_migration` (one root per run)
  - `AGENT`: mapping/diagnosis loops
  - `TOOL`: source/target operations, **one span per batch, not per record**, to avoid trace bloat
  - `EVALUATOR`: verifier
  - Recovery decisions recorded as spans/logs with class, attempt, and mapping version
  - Tags: scenario ID, git SHA, agent version
- **Lifecycle:** the CLI calls `flush()` then `shutdown()` in `try/finally`. The server initializes once at startup and flushes/shuts down in the FastAPI lifespan hook.
- **Proof that traces reach project `bdf486c9-…`:**
  1. `python -m neatlogs doctor --local --json` (offline).
  2. `python -m neatlogs doctor --probe --json`, which writes and reads back a controlled trace with your key.
  3. One real workflow, read back by exact trace ID through `neatlogs-cli` (`neatlogs traces get <id> --json`, `traces spans list`), using a profile bound to the project with `observability:read`. The SDK ingest key does **not** necessarily grant Public API reads, so a browser login is needed.

  Installation, HTTP 2xx, or a Doctor pass alone are not proof.
- **Improvement loop (the 25% story):**
  - Baseline eval → find failing runs via trace view, AI Search, and **Detections**. Example rules: "EVALUATOR failed while agent claimed success", "retries > N", "tokens/run > X".
  - Root cause → fix → Entire checkpoint → rerun → before/after table with real trace IDs.
- **Optional:** the Neatlogs Claude Code integration for *development* traces, kept clearly separate from application traces. The Neatlogs MCP integration was not verified from here; check it on your Mac.

### Entire
- **Initial check:** `entire status --json` first. Only if not enabled, run `entire enable -y --agent claude-code`. Existing hooks are preserved as `<hook>.pre-entire`.
- **Commits:** one per real milestone, each capturing its checkpoint. Commit messages for fixes reference the Neatlogs trace ID that exposed the bug.
- **Evidence and demo commands:**
  - `entire checkpoint list` and `entire checkpoint explain <commit>`
  - `entire recap` / `entire dispatch`, used to draft build-in-public posts
  - In the demo, the experimental `entire why <file>:<line>` on the idempotency or replanning fix shows the session and reasoning behind the line. This closes the chain: Neatlogs failure → Entire reasoning → eval improvement. Verify it works on your build; fall back to `checkpoint explain`.
  - v0.11.4 also adds a hidden `entire checkpoint create [session-id]` for sessions that changed no files. That allows legitimately checkpointing the Phase 0 planning session.
- **Submission evidence (from the check-in instructions):** an accessible checkpoint link and ID, ideally the checkpoint behind the main reliability fix. Use one Trail per milestone if the guide recommends it. Run `entire graph` once near the end (optional) if its output strengthens the demo.
- **Public code link: decided, Option A, pending the official Entire guide.** If the guide requires a GitHub repo, we revisit this with you before touching any remote. The existing Entire repo stays private while building, passes the audit in section 15, and is then made public with `entire repo edit /et/hackathone/hackathon --visibility public` (confirm exact syntax with `entire repo edit --help`) at a moment you explicitly approve. Judges see the code and the checkpoints in one place. No second remote; `origin` stays untouched.
- `entire-graph` (from your prompt) could not be found in the CLI docs. Treat it as unverified until `entire help` shows it.

### cfo.ai
- **Signup** via `cfo.ai/neathacks` (requires you). Cancel the trial in Settings → Billing as instructed, and keep a screenshot of the cancellation.
- **Model inputs, from measured data where possible:**
  - Inference cost per verified migration, from Neatlogs token/cost data
  - Hosting/storage
  - Support hours per migration
  - Pricing: per migration, tiered by record volume, plus an agency/white-label tier
  - Growth scenarios, break-even, runway, and sensitivity to model price and to migration failure rate
- **Export** the model into `BUSINESS.md` and screenshots in `evidence/`. Use 15–20 seconds of video on unit economics.

---

## 6. Evaluation plan (20 scenarios, seeded, reproducible)
| # | Scenario | # | Scenario |
|---|---|---|---|
| 1 | Clean small migration | 11 | Partial batch acceptance |
| 2 | Large volume with pagination | 12 | Mid-run schema change (field rename) |
| 3 | Duplicate customers (email case) | 13 | Process crash mid-run → resume |
| 4 | Cents vs. decimal amounts | 14 | Target already has some records (re-run) |
| 5 | Date/timezone formats | 15 | Prompt injection in source notes |
| 6 | Ambiguous status enum | 16 | Malformed model output (fixture) → validation path |
| 7 | Orphan invoices → quarantine → PARTIAL_SUCCESS | 17 | Contradictory counts (soft-deleted rows) |
| 8 | 429 burst with `Retry-After` | 18 | Credential rotation mid-run |
| 9 | Intermittent 5xx | 19 | Target silently truncates a field → verifier catches |
| 10 | Timeout after a successful write | 20 | Ambiguous goal ("move everything") |

**Metrics:**
- Verified success rate
- **False-success claims**
- Records lost / duplicated / corrupted
- Recovery success rate
- Median and p95 latency
- LLM calls
- **Cost per verified completion**
- Manual interventions

**Honest baseline protocol.** The baseline is the **first working version**, built in the natural order (vertical slice first, recovery later). It is never deliberately crippled. It runs the full suite with real traces, and the improved version runs the identical seeds. Both results are committed with trace IDs.

---

## 7. Multi-agent development strategy
- **Sequential by default.** I am the integrator and reviewer.
- **No git worktrees** (tooling audit). Entire documents worktree-related index corruption from `git gc --auto`. Edits Claude Code makes inside `.claude/worktrees/` are dropped from Entire's files-touched record. Moving a session into a worktree mid-session is a documented non-goal.
- Subagents are used only for **read-only** work, such as one milestone review or a research question. They never edit the same files as the main session.
- If real parallel coding is ever needed, run a second top-level `claude` session in a separate clone, with frozen contracts (target OpenAPI, run-event schema, `MappingSpec` schema). It merges through normal commits.

---

## 8. Billing and budget
| Pool | Use | Guardrail |
|---|---|---|
| A. Claude Pro (Claude Code on Mac) | All coding work | Start with `unset ANTHROPIC_API_KEY; claude`, check `/status`. Use Sonnet for routine edits and Opus for architecture and hard debugging. If limits are hit, wait for the reset; **never silently switch to API billing.** |
| B. Anthropic API, **the ~$100 credits (confirmed)** | ZeroDrop's model calls only | Create a dedicated Console workspace and API key for the hackathon. Set a workspace spend limit of $85 if your Console offers it. Store the key under a **different variable name** (`ZERODROP_ANTHROPIC_KEY`) in a git-ignored `.env`, passed explicitly to `Anthropic(api_key=...)`. Never export it as `ANTHROPIC_API_KEY` in the shell that runs Claude Code, or coding work would be billed to the credits. |
| C. AWS allowance: **$25 per team, received** | **Optional hosted live demo only.** Approved services are EC2, Lambda, IAM roles and load balancers, in us-east-1, inside the existing Hackathon_VPC. Bedrock is not approved, so AWS cannot pay for model calls. | Limits: one EC2 instance (t2/t3/t3a, up to `.large`); EBS ≤ 50 GB; the access page does not meter spend. The private access link expires 24h after issue, so reveal it and store the credentials in a password manager before then. Keys go only into `~/.aws/credentials` under a named profile, set up in a plain Terminal. Never put them in the repo, a Claude Code session, screenshots or chat. |
| D. Crustdata 5,000 credits | Not needed for ZeroDrop | Optional market sizing for `BUSINESS.md` |
| E. cfo.ai credits | Business model | Requires your signup |

**Model choice (decided): Claude Opus 5.5** (`claude-opus-5-5`, $4 / $20 per million input/output tokens, cache reads $0.20), called through the direct Anthropic Python SDK, wrapped with `neatlogs.wrap()`. API details that shape the build:
- **Effort is the cost lever.** Thinking cannot be disabled on Opus 5.5, and effort defaults to `medium`. Set it explicitly per call site: `medium` for mapping and diagnosis, `low` for small classification steps. Raise it only if the eval shows a quality gap. This stays on Opus 5.5; it is not a model downgrade.
- **No forced tool use.** `tool_choice` `any`/`tool` returns a 400. Use structured outputs (`messages.parse()` with Pydantic) for `MappingSpec`, and `auto` with `strict: true` tools inside the agent loop.
- **Refusal fallback.** Enable the server-side `fallbacks: "default"` option so a safety-classifier refusal reroutes instead of failing the run. Every run records which model actually served each call (in Neatlogs and the run manifest), so eval results stay honest about which model produced them.
- **Prompt caching.** Keep the system prompt, tool definitions, and target spec as a stable cached prefix. Verify `cache_read_input_tokens > 0` in Phase 1.
- **Per-run cost metering.** Read cost from `response.usage` and enforce the per-run cap in code. Cross-check daily against the Console usage page.

**Estimated cost per run.** These are planning estimates, to be replaced by measured values in Phase 1. On Opus 5.5: about $0.30 for a clean run and $0.60–$0.95 for a heavy-recovery run. Prompt caching of system prompt, tools, and spec reduces input cost substantially. 40 eval runs (20 scenarios × baseline/improved) cost roughly $16–38 on Opus 5.5, or about half on Sonnet 5.5.

**Caps (now active):** prototype $15, core $30, reliability/eval $25, final demo $15, reserve $15. Stop at $85 aggregate without your permission.

**Fitting the eval into $25.** At the upper estimate ($0.95/run), 40 runs would cost $38, which is over the bucket. Plan:
- Measure real per-run cost in Phase 1.
- If the average is above $0.60, tighten in this order:
  1. Caching and context trimming.
  2. `low` effort on classification-only calls.
  3. Run only the 12 most informative scenarios twice (baseline and improved), plus the full 20 once on the final version.
- Report exactly what was run. UI development uses a clearly labeled **replay mode** (recorded runs), so UI iteration costs nothing and is never presented as live.

---

## 9. Schedule (IST) and exit criteria
| Window | Phase | Exit criterion |
|---|---|---|
| Fri 08:00 | **Web check-in at 08:00 sharp** (AWS credits: first 200 teams) | Check-in confirmed |
| Fri 09:00–12:30 | Kickoff; confirm tracks, cutoff, and repo-link rules; finalize the winner/fallback choice; complete section 10 actions | All blockers in section 10 cleared |
| Fri 12:30–16:30 (h0–4) | **P1:** skeleton, Entire on, Neatlogs Doctor, fixtures, NovaBill customers endpoint, verifier v0, agent v0 | One real verified customer migration, **a real trace read back by ID**, Entire checkpoint listed |
| Fri 16:30–Sat 01:00 (h4–12.5) | **P2:** full loop for 3 entities, ledger, idempotency, chaos layer v1, SSE events | First end-to-end verified migration of all entities |
| Sat 01:00–06:30 | Sleep | — |
| Sat 06:30–14:30 | **P3:** recovery policies, resume, contract replanning; run the **baseline** suite; root-cause failures in Neatlogs | Baseline results committed with trace IDs; at least 2 real fixes checkpointed |
| Sat 14:30–22:30 | **P4:** improved-version suite, UI (6h cap), detections configured. Enable the hardened Playwright plugin (runbook Part C) and run its hardening test first. | Before/after table with comparable seeds; UI shows the full goal→verification flow; UI build plus type check green |
| Sat 22:30–Sun 02:30 | **P5:** cfo.ai model, `BUSINESS.md`, docs, post drafts. Stretch, only if P4 exit is met: the **hosted demo on AWS** (one t3.small/t3.medium in Hackathon_VPC running Docker Compose with API, UI and both sandbox services). Going live needs your approval. Then the Stripe adapter. | All three sponsor evidence items captured; if hosted, the public URL works logged-out and the global spend cap is verified |
| Sun 02:30–07:30 | Sleep | — |
| Sun 07:30–12:30 (to h48) | **P6:** feature freeze, full regression, section 15 audit (~1.5h, from about 10:00), then flip to public with your approval (~11:30) | Anonymous clone works; checkpoints visible logged-out; all quality gates checked |
| Sun 12:30–19:00 | Video recording and editing, packaging (no new features; confirm this is allowed) | Video ≤ 3:00 |
| Sun 19:00+ | Submit; quote post on the official announcement within the first hour | Submission confirmed |

**Hosted demo on AWS (stretch) design:**
- **Abuse protection.** A public URL must never let strangers spend the Anthropic credits:
  - Live agent runs need an access code, given to judges in the submission.
  - Rate limiting, plus a hard global API-spend cap of $5 for the hosted instance.
  - Without the code, visitors see **clearly labeled replays** of recorded real runs. The deterministic parts (chaos layer, verifier) still run live.
- **Key handling.** The Anthropic key reaches the instance via `scp` to a root-only env file. Never via EC2 user-data, which is visible in the console.
- **Lockdown.** Security group open only on 80/443; SSH restricted to your IP. Prefer one instance with Caddy over a load balancer, which adds roughly $0.5/day.
- **Estimated cost** (approximate on-demand us-east-1 rates; check the AWS pricing page): t3.small about $0.02/hour plus about $0.005/hour public IPv4 plus a 20 GB gp3 volume, roughly **$4–5 from Sunday through winners on Oct 16**. A t3.medium is roughly double, so within $25 either way.
- **Afterwards:** stop the instance after the video if no live link is submitted, and terminate it after Oct 16.

**Cut list, in order, if behind:**
1. Hosted AWS demo, then the Stripe adapter
2. Invoices entity (keep customers + subscriptions)
3. UI polish
4. Eval breadth 20 → 12

**Never cut:** the independent verifier, real Neatlogs traces, crash-resume, honest statuses.

---

## 10. Your actions before 12:30 IST
1. **08:00:** complete web check-in.
2. **09:00 kickoff:** confirm the coding cutoff and post-cutoff packaging rules, track list, required submission fields, and whether a public native Entire repo counts as the "public code link".
3. **Anthropic Console (credits confirmed as Anthropic API):**
   - Check the credit balance and expiry date.
   - Create a dedicated "neathack" workspace and API key, and set a spend limit if available.
   - Store the key as `ZERODROP_ANTHROPIC_KEY` in the project's git-ignored `.env` once the repo skeleton exists at 12:30.
   - Do not export it as `ANTHROPIC_API_KEY`.
4. **Neatlogs:**
   - Create the SDK key for project `bdf486c9-c1f5-4fa0-8ee9-cc5c90a61117` and store it in macOS Keychain or a git-ignored `.env`. Do not paste it into Claude.
   - Install the CLI: `npm i -g neatlogs-cli@latest`
   - `neatlogs profile set work --host https://app.neatlogs.com --project bdf486c9-c1f5-4fa0-8ee9-cc5c90a61117`
   - `neatlogs auth login --scope observability:read`
5. **Entire, read-only diagnostics on your Mac.** First locate the checkout, e.g. `find ~ -maxdepth 4 -type d -name hackathon -exec test -d {}/.git \; -print`. Then run:
   ```
   pwd; git status; git remote -v; git branch -a
   git log --format='%h %ad %s' --date=iso -10
   entire version; entire auth status; entire status --json
   entire checkpoint list
   entire repo view /et/hackathone/hackathon
   ls -la .entire .claude 2>/dev/null
   python3 --version; uv --version; node --version
   ```
   Share the output. Confirm the repo has **no pre-existing project code** (commit dates matter under the rules).
6. **cfo.ai:** sign up via `cfo.ai/neathacks`, cancel the trial in Settings → Billing, and screenshot the cancellation.
7. **Claude Code billing:** `unset ANTHROPIC_API_KEY; claude`, then `/status`, and confirm subscription auth.
8. **Decide:**
   - (a) ~~visibility~~: decided, Option A (Entire repo public after audit)
   - (b) ~~app model~~: decided, Opus 5.5
   - (c) ZeroDrop vs. fallback after the track announcement
   - (d) **New, before the first commit at 12:30:** which email to commit under. Commit author emails become public with the repo, and history must not be rewritten afterwards. If you'd rather not publish your personal address, set a different `git config user.email` in the checkout now.
9. **Optional:** if you want me to keep working in this cloud session, add `neatlogs.com`, `docs.neatlogs.com`, `app.neatlogs.com`, `ingest.neatlogs.com`, `entire.io`, and `cfo.ai` to the environment's allowed domains. Otherwise, do the build in Claude Code on your Mac, where the Entire checkout lives.
10. **Open `neatlogs.com/hackathon/skill` on the Mac** so its exact `hackathon.md` format can be followed. I could not read it from here.
11. **Claude Code tooling:** run `mac_tooling_setup.md` Part A (user-level only; about 20 minutes) and send me the output of A0 and A5.

---

## 11. First implementation tasks (start at 12:30 IST; none performed yet)
| # | Task | Acceptance test |
|---|---|---|
| T0 | (You, plain Terminal, 12:30) Runbook Part B1–B2: `entire status` → `entire enable --agent claude-code --telemetry=false` if needed; gitleaks pre-commit hook; then launch `claude` | `entire status --detailed` shows claude-code with no outdated hooks; `/hooks` shows Entire + superpowers only |
| T1 | In the existing Entire checkout: `.gitignore` (`.env`, `.env.local`, `*.db`, `data/`, `.superpowers/`), `.env.example` with names only, `pyproject.toml` (uv; dev deps pytest, hypothesis, ruff), README stub, first `hackathon.md` entry, `docs/PLAN.md`. Also the **leak-prevention settings** from section 15 and runbook B3: deny rules, Entire redaction rules, lean `CLAUDE.md`, and the project `verify` skill. | `git status` clean after commit; `entire checkpoint list` shows the checkpoint; `git ls-files` contains no `.env`; a Claude Code read of `.env` is denied; the verify skill runs green |
| T2 | Neatlogs bring-up: install `neatlogs` + `anthropic`; telemetry module with a single `init()`. Add a **fake Anthropic client fixture** so pytest and Hypothesis never call the real API. | Doctor `--local` passes; Doctor `--probe` passes (run with your approval); the test suite runs with networking to api.anthropic.com unused |
| T3 | Seeded fixture generator: LegacyBill SQLite + golden expected target records | Same seed produces the same hash; unit tests pass |
| T4 | NovaBill service: customers endpoint, OpenAPI, idempotency key, validation | Contract tests pass; a duplicate idempotency key returns the original resource |
| T5 | Verifier v0: counts, money/natural-key invariants, golden comparison | Detects injected loss, duplication, and truncation in unit tests |
| T6 | Agent v0: discovery → `MappingSpec` (structured output) → dry run → batched writes → verifier → status | Scenario 1 ends SUCCESS, confirmed by the verifier |
| T7 | First real trace: run scenario 1, read back the trace by exact ID through `neatlogs-cli` | Trace finalized, one WORKFLOW root, AGENT/LLM/TOOL/EVALUATOR spans, no duplicates; trace ID recorded in `hackathon.md`; commit + checkpoint |

---

## 12. Three-minute video outline
- 0:00–0:15: Hook. "Every SaaS switch is a data migration, and migrations lose data silently."
- 0:15–0:35: What ZeroDrop does, and the line "the LLM decides, code executes, an independent verifier judges."
- 0:35–1:30: Live run: API v2 breaking change, 429 storm, replanned mapping, `kill -9` and resume.
- 1:30–1:55: Reconciliation certificate, plus the before/after eval table (false-success claims, duplicates, cost per verified completion).
- 1:55–2:20: The Neatlogs trace of the failure and recovery, with the detection rule that found the baseline bug; then `entire why` on the fix line and the checkpoint list.
- 2:20–2:40: cfo.ai unit economics and runway.
- 2:40–3:00: Result, links, #neatHack.

---

## 13. Build-in-public plan (drafts for your approval; nothing is posted without you)
1. Fri ~13:00: the problem and concept.
2. Fri night: first verified migration, with a trace screenshot.
3. Sat morning: **a real failure** the baseline hit, shown in its Neatlogs trace, and the fix.
4. Sat evening: before/after eval table.
5. Sun: cfo.ai economics and a demo teaser.
6. Sun 19:00+: quote post on the official submission announcement.

---

## 14. Key risks
1. **Rules timing ambiguity.** Resolve at kickoff.
2. **Claude Pro usage limits during a 48h build.** Use Sonnet for routine work and align sleep with limit resets.
3. **"It's a mock environment" perception.** Mitigate with real HTTP semantics, OpenAPI, honest labels, seed-varied faults, and the optional Stripe test-mode adapter.
4. **Neatlogs compatibility** with the installed `anthropic` SDK version and Opus 5.5 response shapes (e.g., progress-update thinking blocks). Doctor plus the first real trace in hour 1.
4a. **Credit burn.** Opus 5.5 is the most expensive per-token option. Mitigate with effort tuning, caching, per-run caps, replay mode for UI work, and the $85 hard stop.
5. **Public visibility exposes session transcripts, pasted images, and author emails.** Prevention from T1 plus the section 15 audit; rotate any leaked key rather than rewriting history.
6. **Solo fatigue.** Two planned sleep blocks; the cut list is pre-agreed.
7. **Budget.** Hard per-run caps in code, replay mode for UI work, measured cost per run after Phase 1.

---

## 15. Option A: making the Entire repo public safely

**What becomes public.** Everything in the repo, not just the code:
- Every Claude Code session transcript, stored as one git ref per checkpoint under `refs/entire/checkpoints/<shard>/<id>`. This includes prompts, responses, and all tool output, such as file contents the agent read or command output it saw.
- Commit author names and emails.

Source: `entireio/cli` docs/security-and-privacy.md.

**Limits of Entire's redaction (from its own docs):**
- Secret redaction runs before checkpoints are written: entropy scoring, Betterleaks patterns, provider prefixes, credentialed URIs, DB connection strings, and password-like values. It is still **best-effort**; short or low-entropy secrets can slip through.
- **Images pasted into Claude Code are stored unredacted**, as inline base64 in the transcript. Nothing in Entire reads what an image shows.
- The optional PII layer is off by default, and its phone pattern matches **North American numbers only**. Indian (+91) numbers are not caught unless we add a custom pattern.

### Prevention, from the first commit (part of T1)
1. **Entire redaction settings** in `.entire/settings.json`:
   - Turn on `redaction.pii` (email, phone), plus a `custom_patterns` entry for Indian mobile numbers.
   - Add `redaction.custom_redactions` for our known key shapes: Anthropic `sk-ant-…`, Neatlogs `nlsa_…`/`nlpk_…`, and the Neatlogs SDK key prefix once we see its format.
2. **Claude Code deny rules** in the project's `.claude/settings.json`, so the coding agent cannot read `.env` or `.env.*` (except `.env.example`). A key that never enters a session can never reach a transcript.
3. **Working rules for both of us:**
   - Never paste keys into Claude Code.
   - Never paste screenshots into Claude Code; evidence screenshots go into `evidence/` through Finder, after you look at them.
   - Never run commands that print environment values.
   - Fixtures use seeded **synthetic** people only, never real customer data.
4. **Keep the repo private for the whole build.** Checkpoints pushed to a private repo are fine.

### Audit before going public (P6, about 1.5 hours; I prepare and run the commands, you review the findings)
1. **Everything is local and accounted for.**
   - `entire status`: 0 unpushed checkpoints.
   - `entire doctor`: no leftover shadow branches from older Entire versions. Those hold raw, unredacted file snapshots; if any appear, I ask before deleting them.
   - `git for-each-ref`: the checkpoint-ref count matches `entire checkpoint list`.
   - `git branch -a`: only hackathon branches.
2. **Pattern scan across every ref, checkpoints included.** Run `gitleaks git --redact --no-banner -v .` with **no `--log-opts`**.
   - gitleaks' defaults are already `log -p --full-history --all` (verified in its source, `sources/git.go:93-94`), so checkpoint refs are covered.
   - Passing `--log-opts` would replace those defaults.
   - `--redact` keeps the scan's own output secret-free.
   - In a fresh clone, first run `git fetch origin '+refs/entire/*:refs/entire/*'`.
   - The T0 pre-commit hook only sees staged code. Transcripts are written into checkpoint refs after the commit, so this full scan is the real gate for them.
3. **Exact-value scan.** A short script loads our real keys from `.env` and counts their occurrences across all refs (`git grep -F -c`), **printing counts only, never values**. This catches a leaked key even if no pattern would.
4. **Images.** List every checkpoint transcript containing an embedded image. You review each one by eye.
5. **PII sweep.** Search transcripts for your phone number, your home directory path, and any personal names or emails other than intended author info. You decide what is acceptable.
6. **Tracked-files check.**
   - `git ls-files` shows no `.env`, `.entire/settings.local.json`, databases, or data dumps.
   - `.env.example` holds names only.
   - Nothing unrelated to the project is tracked.
7. **If anything leaks:**
   - **Rotate the key immediately** (revoke it in the Anthropic Console or Neatlogs and issue a new one). Under the no-history-rewriting rule, that makes the leaked value useless.
   - Re-run steps 2–3.
   - For non-secret sensitive content inside a checkpoint (e.g., an image), **I stop and ask you**. Removing a checkpoint ref is not a commit-history rewrite, but it removes evidence.
8. **Flip to public, only with your explicit go-ahead at that moment.**
   - Run `entire repo edit /et/hackathone/hackathon --visibility public`, then `entire repo view` should show Public.
9. **Verify as an outsider.**
   - In a logged-out private browser window, the repo page and its checkpoints open.
   - An anonymous `git clone` into a temp directory succeeds, and the clone contains the project.
10. **After the flip.** Every later push (docs, `hackathon.md`, video link) gets a quick re-run of steps 2–3 before pushing.

**Related check:** Neatlogs dashboard trace links probably require login, so judges may not be able to open them. Check whether Neatlogs offers public trace sharing. If not, also commit sanitized trace exports (`neatlogs traces export <id> --format json`) and screenshots to `evidence/`, alongside the trace IDs.

---

## 16. Claude Code tooling (verified 2026-10-10; full steps in `mac_tooling_setup.md`)

| Tool | Decision | When |
|---|---|---|
| superpowers@claude-plugins-official 6.4.1 | Install. Use TDD, systematic-debugging and verification-before-completion; CLAUDE.md overrides its brainstorming/plan/worktree/subagent behaviors. About 2k tokens per session start. | Now |
| context7@claude-plugins-official | Install. Sign in via `/mcp` (OAuth, no API key). Generic queries only; never for Anthropic or Neatlogs docs. | Now |
| frontend-design@claude-plugins-official | Install (~80 tokens) | Now |
| pyright-lsp@claude-plugins-official + `npm i -g pyright` | Install; type diagnostics at 0 always-on tokens | Now |
| playwright@claude-plugins-official | **Your decision: plugin route.** Install now but disabled. Enable at P4 with the `PLAYWRIGHT_MCP_*` env hardening and pass the hardening test first. | P4 |
| Neatlogs skills (3 of 22, pinned at ea7dab7) | Copy into `~/.claude/skills` instead of installing the 22-skill plugin | Now |
| gitleaks, uv, jq | brew install; gitleaks pre-commit hook at T0; full-history scan at P6 | Now / T0 / P6 |
| Status-line Pro-quota gauge | 5h/7d `rate_limits`; doubles as an API-billing tripwire | Now |
| Built-ins | `/status`, `/usage`, `/context`, `/hooks`, `/doctor`; claude-api skill for SDK code; `/code-review medium` at milestones; `/security-review` once at P6 (**your decision**) | Throughout |
| security-guidance | **Skipped (your decision)** | — |
| Vercel skills, Serena, wshobson/agents, anthropics/skills, ccusage, Neatlogs Claude Code tracing | Skipped (duplicates, heavy context, or not needed) | — |

---

## Sources
- Neatlogs SDK and skills (primary): https://github.com/neatlogs/neatlogs , https://github.com/neatlogs/skills
- Entire CLI (primary): https://github.com/entireio/cli (README, CHANGELOG v0.11.4)
- neatHack overview: https://dev.to/neathack_hq/neathack-a-48-hour-online-ai-hackathon-hosted-by-neatlogs-l4l
- Competitor repo (track name, tool weighting): https://github.com/prakharDvedi/ecom-profit-analyst
- Participant note with conflicting dates: https://github.com/JannetEkka/DSProjects/issues/28
- AI SRE landscape: https://wetheflywheel.com/en/guides/best-ai-sre-tools-2026 , https://wetheflywheel.com/en/comparisons/cleric-vs-resolve-ai-vs-traversal/
- AP automation landscape: https://peakflo.co/blog/three-way-matching-exceptions-ai-solutions , https://www.kognitos.com/blog/best-procurement-automation-3-way-match-2026/
- Agent-assisted CRM migration practice: https://www.digitalapplied.com/blog/crm-migration-ai-agents-playbook-2026
- cfo.ai: https://siliconangle.com/2026/09/10/exclusive-ai-finance-cfo-ai-launches-an-agentic-cfo-for-business-founders/ , https://cfo.ai/pricing
- Entire repo visibility: https://github.com/entireio/cli/pull/2547
