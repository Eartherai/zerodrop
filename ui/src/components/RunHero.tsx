import type { ConnectionState } from "../api/client";
import {
  ENTITIES,
  type Entity,
  type EntityCounts,
  type ReconciliationReport,
  type RunDetail,
  type Scenario,
} from "../api/types";
import type { ReplayState } from "../hooks/useRun";
import { formatDuration, formatInt, formatUsd } from "../lib/format";
import {
  excludedRecords,
  expectedRecords,
  isTerminal,
  pendingRecords,
  type EntityProgress,
  type RunModel,
} from "../lib/runModel";
import { SPEEDS } from "../lib/schedule";
import { TONES, type Tone } from "../lib/tones";
import { Dot } from "./ui";

const ENTITY_LABELS: Record<Entity, string> = {
  customers: "Customers",
  subscriptions: "Subscriptions",
  invoices: "Invoices",
};

interface Verdict {
  headline: string;
  detail: string;
  tone: Tone;
}

function plural(n: number, one: string, many = `${one}s`): string {
  return `${formatInt(n)} ${n === 1 ? one : many}`;
}

/** The one sentence the page exists to say, in the words of someone reading a migration report. */
export function verdictOf(
  model: RunModel,
  report: ReconciliationReport | null,
  moved: number,
  expected: number,
): Verdict {
  const status = model.status;
  if (status === null) {
    return {
      headline: "Pick a scenario and start a migration.",
      detail:
        "The agent writes the mapping, moves the records through whatever the target API throws at it, and hands the result to a checker it cannot influence.",
      tone: "neutral",
    };
  }
  const verify = model.verify;
  if (verify && report) {
    const passed = report.checks.filter((c) => c.passed).length;
    const total = report.checks.length;
    const checks = `${passed} of ${total} checks passed`;
    if (verify.status === "SUCCESS") {
      return {
        headline: "Nothing was lost.",
        detail: `${plural(moved, "record")} moved, then re-read from both systems and compared. ${checks}.`,
        tone: "success",
      };
    }
    if (verify.status === "PARTIAL_SUCCESS") {
      const aside = report.quarantined.length;
      return {
        headline: `${plural(aside, "record")} set aside. Everything else arrived.`,
        detail: `Each one is listed below with the reason it could not be moved. ${checks}.`,
        tone: "warning",
      };
    }
    if (verify.falseSuccess) {
      return {
        headline: "The agent said it succeeded. The checker disagrees.",
        detail: `${checks}. The verdict below comes from re-reading both systems, not from the agent.`,
        tone: "danger",
      };
    }
    return {
      headline: "The migration did not verify.",
      detail: `${checks}. The failed checks below say exactly what is missing or different.`,
      tone: "danger",
    };
  }
  switch (status) {
    case "WAITING_FOR_APPROVAL":
      return {
        headline: "Stopped, waiting for you.",
        detail: "The agent hit something it must not decide alone, such as a revoked credential. Nothing was guessed.",
        tone: "warning",
      };
    case "FAILED":
      return {
        headline: "The run stopped before it finished.",
        detail: "The agent halted and reported the failure itself. The timeline shows where and why.",
        tone: "danger",
      };
    case "VERIFYING":
      return {
        headline: "Re-reading both systems.",
        detail: "The checker compares counts, money per currency, references and every field against the source.",
        tone: "accent",
      };
    case "RECOVERING":
      return {
        headline: "Recovering.",
        detail: `${formatInt(moved)} of ${formatInt(expected)} records moved so far. The timeline shows what went wrong and what the agent is doing about it.`,
        tone: "warning",
      };
    case "EXECUTING":
      return {
        headline: "Moving records.",
        detail: `${formatInt(moved)} of ${formatInt(expected)} so far, in batches that are safe to repeat.`,
        tone: "accent",
      };
    case "DRY_RUN":
      return {
        headline: "Testing the mapping on samples.",
        detail: "Nothing is written until every sample passes the target's own schema.",
        tone: "accent",
      };
    default:
      return {
        headline: "Reading both systems.",
        detail: "The model is looking at samples and field documentation to work out how the two schemas line up.",
        tone: "accent",
      };
  }
}

const STEPS = ["Plan", "Dry run", "Migrate", "Verify"] as const;

/** How many of the four steps are behind us, and which one is active (-1 when none). */
function stepState(model: RunModel): { done: number; active: number } {
  const status = model.status;
  if (status === null) return { done: 0, active: -1 };
  if (model.verify) return { done: 4, active: -1 };
  const planned = Object.keys(model.mappingVersions).length > 0;
  const migrating = ENTITIES.some((e) => model.entities[e].written + model.entities[e].quarantined > 0);
  if (status === "DISCOVERING" || status === "PLANNING") return { done: 0, active: 0 };
  if (status === "DRY_RUN") return { done: 1, active: 1 };
  if (status === "EXECUTING" || status === "RECOVERING") return { done: 2, active: 2 };
  if (status === "VERIFYING") return { done: 3, active: 3 };
  return { done: migrating ? 2 : planned ? 1 : 0, active: -1 };
}

function Steps({ model, tone }: { model: RunModel; tone: Tone }) {
  const { done, active } = stepState(model);
  return (
    <ol className="flex flex-wrap items-center gap-x-2 gap-y-1 text-sm" aria-label="Run steps">
      {STEPS.map((label, i) => {
        const isDone = i < done;
        const isActive = i === active;
        const color = isActive ? TONES[tone].text : isDone ? "text-fg" : "text-muted";
        return (
          <li key={label} className="flex items-center gap-2" aria-current={isActive ? "step" : undefined}>
            {i > 0 ? (
              <span aria-hidden className={`h-px w-6 ${isDone || isActive ? "bg-line-strong" : "bg-line"}`} />
            ) : null}
            <span className={`flex items-center gap-1.5 ${color} ${isActive ? "font-semibold" : ""}`}>
              <span aria-hidden className="w-3 text-center">
                {isDone ? "✓" : isActive ? <Dot tone={tone} pulse /> : "·"}
              </span>
              {label}
            </span>
          </li>
        );
      })}
    </ol>
  );
}

function withFallback(p: EntityProgress, counts: EntityCounts | undefined): EntityProgress {
  // The event stream is the source of truth; polled ledger counts are passed only while no event has arrived.
  if (!counts) return p;
  return { ...p, written: counts.written, quarantined: counts.quarantined, total: counts.total || p.total };
}

function LedgerRow({
  p,
  version,
  arrived,
}: {
  p: EntityProgress;
  version: number | undefined;
  /** What the checker counted on the target, once it has looked. */
  arrived: number | undefined;
}) {
  const expected = expectedRecords(p);
  const pending = pendingRecords(p);
  const excluded = excludedRecords(p);
  const target = arrived ?? p.written;
  const short = arrived !== undefined && arrived + p.quarantined < expected;
  const balanced = arrived !== undefined && !short;
  const notes: string[] = [];
  if (version !== undefined) notes.push(version > 1 ? `mapping rewritten (v${version})` : "mapping v1");
  if (p.quarantined) notes.push(`${formatInt(p.quarantined)} set aside`);
  if (p.failed) notes.push(`${formatInt(p.failed)} failed`);
  if (excluded) notes.push(`${formatInt(excluded)} marked deleted in the source, skipped`);
  if (p.replayed) notes.push(`${formatInt(p.replayed)} repeated safely`);
  if (short) notes.push(`${formatInt(expected - arrived - p.quarantined)} missing`);
  else if (pending && arrived === undefined) notes.push(`${formatInt(pending)} to go`);
  const pct = (n: number) => `${expected > 0 ? Math.min(100, (n / expected) * 100) : 0}%`;
  return (
    <tr className="border-t border-line align-baseline">
      <th scope="row" className="py-3 pr-4 text-left text-base font-medium text-fg">
        {ENTITY_LABELS[p.entity]}
        {notes.length ? (
          <span className="mt-1 block text-xs leading-snug font-normal text-muted md:hidden">{notes.join(", ")}</span>
        ) : null}
      </th>
      <td className="py-3 pr-4 text-right font-mono text-xl tabular sm:text-2xl text-fg">
        {p.loaded !== null || expected ? formatInt(expected) : "—"}
      </td>
      <td className="hidden w-[30%] py-3 pr-4 align-middle sm:table-cell">
        <div
          className="flex h-1.5 w-full overflow-hidden rounded-full bg-surface-2"
          role="progressbar"
          aria-label={`${ENTITY_LABELS[p.entity]} moved`}
          aria-valuemin={0}
          aria-valuemax={expected || 1}
          aria-valuenow={p.written + p.quarantined + p.failed}
        >
          <div
            className={`h-full transition-[width] duration-500 ease-out ${short ? "bg-danger" : "bg-success"}`}
            style={{ width: pct(arrived ?? p.written) }}
          />
          <div
            className="h-full bg-warning transition-[width] duration-500 ease-out"
            style={{ width: pct(p.quarantined) }}
          />
          <div className="h-full bg-danger transition-[width] duration-500 ease-out" style={{ width: pct(p.failed) }} />
        </div>
      </td>
      <td
        className={`py-3 pr-4 text-right font-mono text-xl tabular sm:text-2xl ${short ? "font-medium text-danger" : balanced ? "text-success" : "text-fg"}`}
      >
        {formatInt(target)}
      </td>
      <td className="hidden w-[30%] py-3 text-sm leading-snug text-muted md:table-cell">{notes.join(", ")}</td>
    </tr>
  );
}

const CONNECTION_LABEL: Record<ConnectionState, string> = {
  connecting: "connecting",
  open: "live",
  reconnecting: "reconnecting",
  closed: "stream closed",
};

interface HeroProps {
  model: RunModel;
  detail: RunDetail | null;
  report: ReconciliationReport | null;
  scenario: Scenario | undefined;
  /** The scenario chosen in the header, shown before any run exists. */
  selected: Scenario | undefined;
  counts: Partial<Record<Entity, EntityCounts>> | undefined;
  connection: ConnectionState;
  connectionDetail: string | null;
  recorded: boolean;
  replay: ReplayState;
  onReplay: (speed: number) => void;
  onStopReplay: () => void;
  replaySpeed: number;
  onReplaySpeed: (speed: number) => void;
}

export function RunHero(props: HeroProps) {
  const { model, detail, report, scenario, counts, connection, connectionDetail, recorded, replay } = props;
  const rows = ENTITIES.map((e) => withFallback(model.entities[e], counts?.[e]));
  const moved = rows.reduce((n, p) => n + p.written, 0);
  const expected = rows.reduce((n, p) => n + expectedRecords(p), 0);
  const verdict = verdictOf(model, model.verify ? report : null, moved, expected);
  const tone = TONES[verdict.tone];
  const goal = detail?.goal ?? model.goal;
  const running = model.status !== null && !isTerminal(model.status);
  const elapsed = model.firstTs !== null && model.lastTs !== null ? model.lastTs - model.firstTs : null;
  const llm = model.llm.calls || !detail ? model.llm : { calls: detail.llm.calls, costUsd: detail.llm.cost_usd };
  const canReplay = model.events.length > 0 && isTerminal(model.status);
  const claim = model.verify?.agentClaim ?? model.agentClaim;
  const facts: string[] = [];
  if (elapsed !== null) facts.push(formatDuration(elapsed));
  const planner = detail?.planner ?? null;
  if (planner) {
    facts.push(
      planner.kind === "model" ? `planned by ${planner.name}` : `scripted planner (${planner.name}), not a model`,
    );
  }
  if (model.status !== null && planner?.kind !== "scripted") {
    facts.push(llm.calls ? `${plural(llm.calls, "model call")}, ${formatUsd(llm.costUsd)}` : "no model calls");
  }
  if (model.apiVersionHistory.length > 1) facts.push(`target API changed ${model.apiVersionHistory.join(" to ")}`);
  if (model.resumes) facts.push(`resumed ${model.resumes === 1 ? "once" : `${model.resumes} times`} after a crash`);
  const showLedger = model.status !== null;
  return (
    <section
      aria-labelledby="verdict"
      className="grid gap-x-12 gap-y-8 pt-2 pb-2 xl:grid-cols-[minmax(0,5fr)_minmax(0,6fr)]"
    >
      <div className="min-w-0">
        {goal ? (
          <p className="max-w-[62ch] text-sm leading-relaxed text-muted">
            <span className="text-fg">{scenario ? `${scenario.title}. ` : ""}</span>
            Asked to: {goal.charAt(0).toLowerCase() + goal.slice(1)}
          </p>
        ) : null}
        <h2
          id="verdict"
          className={`font-display mt-3 max-w-[18ch] text-5xl leading-[1.02] font-semibold tracking-tight text-balance sm:text-6xl ${verdict.tone === "neutral" ? "text-fg" : tone.text}`}
        >
          {verdict.headline}
        </h2>
        <p className="mt-4 max-w-[58ch] text-lg leading-relaxed text-fg">{verdict.detail}</p>
        {model.verify && claim ? (
          <p className="mt-3 text-sm text-muted">
            Decided by the independent checker. The agent's own claim was{" "}
            <span className={`font-semibold ${claim === model.verify.status ? "text-fg" : TONES.danger.text}`}>
              {claim.replaceAll("_", " ").toLowerCase()}
            </span>
            {claim === model.verify.status ? ", which matches." : ", which does not match."}
          </p>
        ) : null}
        {model.status !== null ? (
          <div className="mt-6">
            <Steps model={model} tone={verdict.tone} />
          </div>
        ) : null}
      </div>

      <div className="min-w-0">
        {model.status === null ? (
          <div className="max-w-[56ch] border-l border-line-strong pl-6">
            <ol className="space-y-4 text-base leading-relaxed text-fg">
              <li>
                <span className="font-semibold">The model decides.</span> It reads samples and field notes from both
                systems and writes the mapping in a small, restricted language.
              </li>
              <li>
                <span className="font-semibold">Code executes.</span> Batches that are safe to repeat, a ledger of every
                record, and a resume point after each batch.
              </li>
              <li>
                <span className="font-semibold">A checker judges.</span> It shares no code with the agent, re-reads both
                systems, and its verdict is the one shown here.
              </li>
            </ol>
            {props.selected ? (
              <p className="mt-6 text-sm leading-relaxed text-muted">
                <span className="text-fg">Ready to run: {props.selected.title}.</span> {props.selected.description}
              </p>
            ) : null}
          </div>
        ) : null}
        {showLedger ? (
          <table className="w-full border-collapse">
            <caption className="sr-only">Records in the source and on the target, per entity</caption>
            <thead>
              <tr className="text-sm text-muted">
                <th scope="col" className="pb-2 text-left font-normal">
                  <span className="sr-only">Entity</span>
                </th>
                <th scope="col" className="pb-2 pr-4 text-right font-normal whitespace-nowrap">
                  In LegacyBill
                </th>
                <th scope="col" className="hidden pb-2 sm:table-cell" />
                <th scope="col" className="pb-2 pr-4 text-right font-normal whitespace-nowrap">
                  {model.verify ? "Found in NovaBill" : "Written to NovaBill"}
                </th>
                <th scope="col" className="hidden pb-2 text-left font-normal md:table-cell">
                  <span className="sr-only">Notes</span>
                </th>
              </tr>
            </thead>
            <tbody>
              {rows.map((p) => (
                <LedgerRow
                  key={p.entity}
                  p={p}
                  version={model.mappingVersions[p.entity]}
                  arrived={model.verify && report ? report.target_counts[p.entity] : undefined}
                />
              ))}
            </tbody>
          </table>
        ) : null}
        {model.status !== null ? (
          <div className="mt-4 flex flex-wrap items-center gap-x-4 gap-y-2 border-t border-line pt-3 text-sm text-muted">
            <span>{facts.join(" · ")}</span>
            {detail?.trace_url ? (
              <a
                href={detail.trace_url}
                target="_blank"
                rel="noreferrer noopener"
                className="font-medium text-accent underline underline-offset-2 hover:opacity-80"
              >
                Open the trace in Neatlogs
              </a>
            ) : null}
            {model.runId && running ? (
              <span
                className={`flex items-center gap-1.5 ${TONES[connection === "open" ? "success" : connection === "reconnecting" ? "warning" : "neutral"].text}`}
                title={connectionDetail ?? undefined}
              >
                <Dot
                  tone={connection === "open" ? "success" : connection === "reconnecting" ? "warning" : "neutral"}
                  pulse={connection === "open"}
                />
                {CONNECTION_LABEL[connection]}
              </span>
            ) : null}
            {recorded ? (
              <span className="rounded bg-info-soft px-1.5 py-0.5 text-xs font-medium text-info">
                Replay of recorded run
              </span>
            ) : null}
            {replay.active ? (
              <span className="text-xs text-info">replaying {Math.round(replay.progress * 100)}%</span>
            ) : null}
            {canReplay || replay.active ? (
              <span className="ml-auto flex items-center gap-2">
                <label htmlFor="speed" className="text-xs">
                  Speed
                </label>
                <select
                  id="speed"
                  value={props.replaySpeed}
                  onChange={(e) => props.onReplaySpeed(Number(e.target.value))}
                  className="h-8 rounded-md border border-line bg-surface px-2 text-xs text-fg"
                >
                  {SPEEDS.map((s) => (
                    <option key={s} value={s}>
                      {s}×
                    </option>
                  ))}
                </select>
                {replay.active ? (
                  <button
                    type="button"
                    onClick={props.onStopReplay}
                    className="h-8 rounded-md border border-line px-3 text-xs font-medium text-fg hover:bg-surface-2"
                  >
                    Skip to end
                  </button>
                ) : (
                  <button
                    type="button"
                    onClick={() => props.onReplay(props.replaySpeed)}
                    className="h-8 rounded-md border border-line-strong px-3 text-xs font-medium text-fg hover:bg-surface-2"
                  >
                    Replay run
                  </button>
                )}
              </span>
            ) : null}
          </div>
        ) : null}
      </div>
    </section>
  );
}
