# ZeroDrop web UI

A single page that makes the agent's behavior obvious in a three-minute demo: the goal, a
pipeline strip that lights up stage by stage, live per-entity progress, the event
timeline, the mapping diff that shows the schema-change recovery, and the verification
certificate decided by the independent verifier.

Stack: Vite 7 + React 19 + TypeScript 5.9 + Tailwind CSS 4, all pinned to exact versions
in `ui/package.json` with a committed `ui/package-lock.json`. No external fonts, CDNs or
chart libraries (bars are plain CSS).

## Running it

```bash
cd ui
npm ci                 # install exactly what package-lock.json pins
npm run dev            # http://127.0.0.1:5173, proxies /api to http://127.0.0.1:8700
npm run dev:mock       # same page on bundled recorded runs, no backend needed (VITE_MOCK=1)
npm run build          # tsc --noEmit + production bundle in ui/dist (no mock data inside)
npm run build:mock     # bundle that serves the recorded runs (for an offline demo)
npm test               # vitest unit tests (pure logic + mock API), ~1 s
npm run typecheck      # tsc --noEmit
npm run format         # prettier (format:check in CI)
```

URL parameters: `?run=<run_id>` opens a run directly (the page keeps it in the URL);
`?speed=2` speeds up mock "live" runs.

## Design (redesigned Oct 11)

The page reads like a reconciliation statement. The verdict is the first thing on it, in plain
words, and next to it the two columns that have to balance: records in LegacyBill and records
found in NovaBill.

- **Palette:** cool ledger paper and green-black ink, one cobalt for anything you can press, and
  stamp colors (green, red, ochre) reserved for verdicts and failures. Light and dark themes
  follow `prefers-color-scheme`; tokens live in `ui/src/index.css`.
- **Type:** Bricolage Grotesque for the verdict and headings, IBM Plex Sans for text, IBM Plex
  Mono for identifiers, mapping code and ledger figures. All three are bundled from npm
  (`@fontsource*`); nothing loads from a CDN.
- **Rules of thumb:** sentence case, no all-caps labels, color only where it changes the reading
  (a failure, the verdict), numbers in tabular figures.

## Page layout (top to bottom)

| Part | What it shows | Demo moment |
|---|---|---|
| Header | Product name and tagline, scenario picker, **Start migration**, past runs, a **Mock data** badge in mock mode | 0:15 |
| Verdict and ledger (`RunHero.tsx`) | Left: what was asked, then one sentence that changes with the run ("Moving records.", "Recovering.", "Nothing was lost.", "The agent said it succeeded. The checker disagrees."), the agent's own claim against the checker's, and four steps (Plan, Dry run, Migrate, Verify). Right: per entity, records in LegacyBill, a thin progress track, records written (or, once verified, found) in NovaBill, and notes: mapping version, set aside, skipped, missing. Under it: duration, model calls and cost, API version change, resumes, stream state, the replay controls (0.5× to 4×) and a **Replay of recorded run** label. Before any run: the three-part rule and the selected scenario | throughout |
| The proof (`Certificate.tsx`) | Appears once the run is verifying or finished. A **False-success claim caught** banner when the agent's claim and the checker disagree. A grid of checks: one row per kind of check in plain words, one column per entity, a tick or a cross in each cell, so 24 checks read at a glance. Every failed check is then written out in full: expected, found, and the detail. Beside it: money per currency in exact minor units, the records set aside with their reasons, and the report fingerprint | 1:02 |
| Mapping diff (`MappingDiff.tsx`) | Pick an entity; version N against N+1 side by side, with the agent's stated reason | 0:55 |
| What happened (`EventTimeline.tsx`) | Newest first. Time offset, the kind in plain words (step, plan, batch, failure, recovery, decision, verdict, model, note), the message and compact facts. Only failures and the verdict get a filled row. Kinds can be hidden; clean batches fold into one line | 0:34 |
| Footer | Run id, link to the Neatlogs trace, the agent's commit, and a note that the two services are sandboxes with injected faults | 1:31 |

Every text and background pair meets WCAG AA in both themes. Status is always written out,
never shown by color alone. Animations stop under `prefers-reduced-motion`. A visually hidden
live region announces status changes. The layout is checked at 390, 820 and 1600 px wide with
no horizontal page scroll; on a phone the ledger's notes move under the entity name.

## API the UI consumes

The lead implements these in Python. The Vite dev server proxies `/api` to
`http://127.0.0.1:8700`. All bodies are JSON; field names are exactly as below. TypeScript
mirrors live in `ui/src/api/types.ts` (keep them in sync with `src/zerodrop/models.py`).

| Method and path | Response |
|---|---|
| `GET /api/scenarios` | `[{id, title, description}]` |
| `POST /api/runs` body `{scenario_id}` | `{run_id}`; unknown scenario: 404 with `{"detail": "..."}` (shown in the UI) |
| `GET /api/runs` | `[{run_id, status, scenario_id, created_at}]` (the UI sorts by `created_at`, newest first). `created_at` may be epoch seconds or an ISO-8601 string |
| `GET /api/runs/{id}` | `{run_id, status, agent_claimed_status, goal, scenario_id, counts: {entity: {total, written, quarantined, pending}}, mapping_versions: {entity: int}, llm: {calls, cost_usd}, trace_url?, commit?}`. `trace_url`/`commit`: a URL renders as a link, any other string as text; null or absent hides it |
| `GET /api/runs/{id}/events?after_seq=N` | Server-Sent Events. Each event's `data:` line is one `RunEvent` JSON (`models.RunEvent`, `ts` in epoch seconds) with `seq > N`, in seq order |
| `GET /api/runs/{id}/report` | `ReconciliationReport` JSON, or **404** while it does not exist |
| `GET /api/runs/{id}/mappings` | `[{entity, version, spec}]` where `spec` is a full `MappingSpec`; every stored version of every entity |

How the UI uses them:

- **Event stream.** Opens `EventSource(/api/runs/{id}/events?after_seq=<last seq seen>)`.
  It listens to unnamed events (SSE `message`) and to events named `run_event`; events
  named `end` or `done` close the stream. It closes the stream itself after the `state`
  event whose `state` is terminal (`SUCCESS`, `PARTIAL_SUCCESS`, `FAILED`,
  `WAITING_FOR_APPROVAL`). On an error it reconnects manually with exponential backoff
  (0.5 s → 8 s) and the **latest** `after_seq`, so it never relies on `Last-Event-ID`.
  Events with `seq <= last seen` are dropped, so replays after a reconnect are harmless.
  Unknown `kind`/`state`/`entity` values are rejected (a contract drift shows up as
  missing events, not as a wrong UI).
- **Stall watchdog.** A proxy can keep a dead stream open (observed with the Vite dev
  proxy when the upstream connection drops). While a run is not terminal the UI polls
  `GET /api/runs/{id}` every 2 s; if that status differs from the last streamed state and
  no event arrived for 6 s, it resubscribes from the last seq.
- **Report** is fetched when the `verify` event arrives and again at the terminal state
  (404 just means "not yet"). **Mappings** are refetched whenever the stream announces a
  new mapping version. **Run list** refreshes every 5 s and on every status change.
- For a finished run, the server may send all events at once and then close the stream
  (or keep it open); both work.

Server-side suggestions (not required): send `id: <seq>` lines; send a comment heartbeat
(`: ping`) every ~15 s to keep proxies from timing out idle streams; return
`Cache-Control: no-cache`; end the response after the terminal `state` event.

### Event data keys the UI reads

The view model (`ui/src/lib/runModel.ts`) only depends on event kinds/states plus these
`data` keys, all emitted by `src/zerodrop/engine.py` today. Anything else is ignored.

| Event | Keys used | For |
|---|---|---|
| first `state` event | message prefix `run created: ` | goal (fallback when the detail has none) |
| `state` | `state` | current status, pipeline stage |
| `info` (discovery) | `records_loaded`, `target_api_version`, `timezone` | progress denominators, API version |
| `info` (resume) | message prefix `resuming` | resume counter, RECOVERY stage |
| `plan` | `mappings.{entity}.version`, `entity` + `version_from`/`version_to`, `changes.{added,removed,changed}` | mapping versions, diff auto-follow |
| `batch` | `written`, `size`, `attempt`, `replayed`, `quarantined`, `retry`, `contract_rejected`, `api_version` | progress, timeline facts, folding |
| `failure` | `failure_class`, `status`, `attempt`, `dominant_code`, `version_from`/`version_to` | FAILURE counters, API version history |
| `recovery` | `failure_class`, `delay_s`, `retry_after`, `found`/`resend`, `schema_changes`, `mapping_versions` | RECOVERY tactics, progress (`found`) |
| `decision` | `failure_class == "DATA"` + message `quarantined N ...` (fallback `items`); `total`/`written`/`quarantined`/`failed` ("entity complete"); `checked`/`passed` (dry run); `codes` (repair request); message `engine believes the run is X` | quarantine counts, authoritative per-entity totals, agent claim |
| `llm` | `calls`, `cost_usd` | LLM usage |
| `verify` | `status`, `agent_claimed_status`, `false_success_claim`, `failed_checks`, `report_hash` | certificate gating, verification color |

Progress semantics: written and quarantined come from the stream (batch `written`,
ambiguous-write `found`, DATA quarantine decisions) and are replaced by the
authoritative counts of the "`<entity>` complete" decision. The denominator is the
source rows loaded at discovery until the entity completes, then the ledger total; the
difference is shown as "excluded by mapping rule (soft-deleted)". Pending = denominator −
written − quarantined − failed. The polled `counts` are used only when the stream has
delivered nothing at all.

Pipeline mapping (`stagesForEvent`): `state` CREATED → GOAL; DISCOVERING/PLANNING/DRY_RUN →
PLAN; EXECUTING → ACTION; RECOVERING → RECOVERY; VERIFYING and final verdicts →
VERIFICATION; WAITING_FOR_APPROVAL → FAILURE. `plan`/`llm` → PLAN (RECOVERY when emitted
while recovering); `batch` → OBSERVATION + ACTION; `failure` → FAILURE; `recovery` →
RECOVERY; DATA quarantine decisions → RECOVERY; other classified decisions (BUDGET, AUTH)
→ FAILURE; dry runs → ACTION + OBSERVATION (RECOVERY while recovering); `verify` →
VERIFICATION.

## Mock mode

`VITE_MOCK=1` swaps the HTTP client for `ui/src/mock/mockApi.ts`, which serves three
recorded runs from `ui/src/mock/recordings/*.json`. The header shows **MOCK DATA** and the
footer says the data is recorded. The mock is contract-accurate because the recordings
are real: each was produced by running the actual `MigrationEngine` against the actual
sandbox servers (`run_sandbox`) and the actual verifier (`verify`), with the deterministic
`FakePlanner` instead of Claude (so `llm.calls` is 0 and cost $0). Events, mapping history
(`ledger.mapping_history`), the `ReconciliationReport` and the run summary were captured
verbatim; only scenario titles were shortened afterwards.

| Scenario id | Dataset | Fault plan (NovaBill) | Outcome |
|---|---|---|---|
| `demo-v2-flip` | seed 7, `demo` (300 customers) | 429 ×2 on customers; schema flip to v2 + 429 ×3 at the 4th subscriptions write; timeout-after-write on invoices; partial accept (30 of 50); one 503; process crash after 20 write batches, then `resume()` | SUCCESS, claim SUCCESS, 24/24 checks, 50 idempotent replays |
| `messy-data` | seed 11, `small`, 2 orphan invoices, 2 duplicate e-mails | 429 ×2 on invoices | PARTIAL_SUCCESS, 4 quarantined with reasons |
| `naive-planner` | seed 5, `small` | none; `FakePlanner("naive")` (JPY treated as 2 decimals) | FAILED, claim SUCCESS: false-success claim caught (`money_by_currency`, `source_fidelity`, `golden_records`) |

Behavior: the recorded runs appear in the run history as finished runs (opened as
"Replay of recorded run"); **Start migration** replays the chosen recording as a new
"live" run (`run_mock001`, ...) whose events are released over time, and every endpoint
answers from the events released so far (no report before the `verify` event, only the
mapping versions already announced, status and counts as of now). Pacing
(`ui/src/lib/schedule.ts`) gives each event a minimum on-screen dwell (longer for
failures, recoveries, new mappings and the verdict) and keeps real gaps up to 2.5 s; the
demo recording takes about 60 s at 1×. The same pacing drives **Replay run** for any
finished run, in mock and live mode.

Re-recording (a Python helper was used from a scratch directory and is not committed,
since UI builders do not add Python files; ask the lead if it should live in `scripts/`):
generate the dataset with `fixtures.generate(seed, size, **opts)`, start
`run_sandbox(dataset, FaultPlan(...))`, build `MigrationEngine(settings, SourceClient,
TargetClient, FakePlanner(mode), verify, Ledger(path))` with a `PreservationContract`
whose `golden_path` points at `dataset.write_golden(...)`, run it (catch `SimulatedCrash`
and call `resume(run_id)` for the crash scenario), then dump `ledger.events_since(run_id,
0)`, `ledger.mapping_history(run_id, entity)`, `result.report` and the summary in the
`GET /api/runs/{id}` shape into one JSON file with keys `scenario`, `fault_plan`,
`summary`, `events`, `mappings`, `report`. `ui/src/mock/recordings.test.ts` validates
the shape.

## Code map

```
ui/src/
  api/types.ts        TS mirror of models.py + API payloads
  api/client.ts       ZeroDropApi interface, createApi() (mock or HTTP)
  api/http.ts         fetch + EventSource client with manual reconnect
  api/parse.ts        RunEvent validation
  hooks/useRun.ts     stream + polling + report/mappings + replay for one run
  lib/runModel.ts     pure reducer: events -> view model (stages, progress, verdict)
  lib/mappingDiff.ts  LCS field diff, op formatting
  lib/eventDetails.ts timeline facts; lib/timeline.ts row folding
  lib/schedule.ts     replay pacing; lib/format.ts exact money/dates; lib/tones.ts colors
  components/         Header, RunOverview (goal + status), PipelineStrip, EntityProgress,
                      MappingDiff, EventTimeline, Certificate, Footer, ui primitives
  mock/               mockApi.ts, recordings.ts, recordings/*.json
```

## Verification done

- `npm ci`, `npx tsc --noEmit`, `npm run build`, `VITE_MOCK=1 vite build`, `npx vitest run`
  (8 files, 61 tests), `npx prettier --check .`.
- Headless Chromium at 1920×1080, light and dark: a full mock "live" run of
  `demo-v2-flip` (idle → recovery → certificate), history views of all three
  recordings, the replay control, and phone/tablet widths (no horizontal overflow).
- Live mode end to end through the Vite proxy against a throwaway fake of the API above
  that served the recordings over SSE and deliberately dropped the first stream after
  20 events: the UI resubscribed with `after_seq=19` and finished with exactly 94 events
  (no duplicates, none missing), trace and checkpoint links rendered. This is not a test
  of the real Python API, which did not exist yet when this was written.
