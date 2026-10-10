import type { ReactNode } from "react";
import type { ConnectionState } from "../api/client";
import type { RunDetail, Scenario } from "../api/types";
import type { ReplayState } from "../hooks/useRun";
import { formatDuration, formatUsd } from "../lib/format";
import { isTerminal, type RunModel } from "../lib/runModel";
import { SPEEDS } from "../lib/schedule";
import { TONES } from "../lib/tones";
import { Dot, Pill, StatusBadge } from "./ui";

interface GoalProps {
  model: RunModel;
  detail: RunDetail | null;
  scenario: Scenario | undefined;
  recorded: boolean;
  replay: ReplayState;
  onReplay: (speed: number) => void;
  onStopReplay: () => void;
  replaySpeed: number;
  onReplaySpeed: (speed: number) => void;
}

export function GoalPanel({
  model,
  detail,
  scenario,
  recorded,
  replay,
  onReplay,
  onStopReplay,
  replaySpeed,
  onReplaySpeed,
}: GoalProps) {
  const goal = detail?.goal ?? model.goal;
  const runId = detail?.run_id ?? model.runId;
  const canReplay = model.events.length > 0 && isTerminal(model.status);
  return (
    <section
      aria-labelledby="goal-title"
      className="flex min-w-0 flex-col rounded-xl border border-line bg-surface px-5 py-4 shadow-sm"
    >
      <div className="flex flex-wrap items-center gap-2">
        <h2 id="goal-title" className="text-sm font-semibold tracking-wide text-fg uppercase">
          Goal
        </h2>
        {runId ? <span className="font-mono text-xs text-muted">{runId}</span> : null}
        {recorded ? (
          <span className="rounded-md bg-info-soft px-2 py-0.5 text-xs font-bold tracking-wide text-info">
            Replay of recorded run
          </span>
        ) : null}
        {replay.active ? <Pill tone="info">replaying {Math.round(replay.progress * 100)}%</Pill> : null}
        {canReplay || replay.active ? (
          <div className="ml-auto flex items-center gap-2">
            <label htmlFor="speed" className="text-xs text-muted">
              Speed
            </label>
            <select
              id="speed"
              value={replaySpeed}
              onChange={(e) => onReplaySpeed(Number(e.target.value))}
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
                onClick={onStopReplay}
                className="h-8 rounded-md border border-line px-3 text-xs font-semibold text-fg hover:bg-surface-2"
              >
                Skip to end
              </button>
            ) : (
              <button
                type="button"
                onClick={() => onReplay(replaySpeed)}
                className="h-8 rounded-md border border-accent px-3 text-xs font-semibold text-accent hover:bg-accent-soft"
              >
                ▶ Replay run
              </button>
            )}
          </div>
        ) : null}
      </div>
      {goal ? (
        <blockquote className="mt-2 border-l-4 border-accent pl-4 text-xl leading-snug font-medium text-fg">
          “{goal}”
        </blockquote>
      ) : (
        <p className="mt-2 text-xl leading-snug text-muted">
          Pick a scenario and press Start migration. The agent plans, migrates, recovers and hands its work to an
          independent verifier.
        </p>
      )}
      {scenario ? (
        <p className="mt-2 text-sm text-muted">
          <span className="font-semibold text-fg">{scenario.title}.</span> {scenario.description}
        </p>
      ) : null}
    </section>
  );
}

const CONNECTION_LABEL: Record<ConnectionState, string> = {
  connecting: "connecting",
  open: "live",
  reconnecting: "reconnecting",
  closed: "stream closed",
};

function Metric({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="min-w-0">
      <dt className="text-[0.7rem] font-semibold tracking-wide text-muted uppercase">{label}</dt>
      <dd className="mt-0.5 text-base font-bold text-fg tabular">{children}</dd>
    </div>
  );
}

export function StatusCard({
  model,
  detail,
  connection,
  connectionDetail,
}: {
  model: RunModel;
  detail: RunDetail | null;
  connection: ConnectionState;
  connectionDetail: string | null;
}) {
  const running = model.status !== null && !isTerminal(model.status);
  const elapsed = model.firstTs !== null && model.lastTs !== null ? model.lastTs - model.firstTs : null;
  const llm = model.llm.calls || !detail ? model.llm : { calls: detail.llm.calls, costUsd: detail.llm.cost_usd };
  const history = model.apiVersionHistory;
  const connTone = connection === "open" ? "success" : connection === "reconnecting" ? "warning" : "neutral";
  return (
    <section
      aria-label="Run status"
      className="flex min-w-0 flex-col gap-3 rounded-xl border border-line bg-surface px-5 py-4 shadow-sm"
    >
      <div className="flex flex-wrap items-center justify-between gap-2">
        <StatusBadge status={model.status ?? detail?.status ?? null} size="lg" live={running} />
        {model.runId ? (
          <span
            className={`flex items-center gap-1.5 text-xs font-semibold ${TONES[connTone].text}`}
            title={connectionDetail ?? undefined}
          >
            <Dot tone={connTone} pulse={connection === "open" && running} />
            {CONNECTION_LABEL[connection]}
          </span>
        ) : null}
      </div>
      <dl className="grid grid-cols-2 gap-x-4 gap-y-2 sm:grid-cols-4">
        <Metric label="Engine time">{elapsed !== null ? formatDuration(elapsed) : "—"}</Metric>
        <Metric label="Target API">
          {history.length ? (
            <span>
              {history.map((v, i) => (
                <span key={`${v}${i}`}>
                  {i > 0 ? <span className="text-muted"> → </span> : null}
                  <span className={i > 0 ? TONES.plan.text : ""}>{v}</span>
                </span>
              ))}
            </span>
          ) : (
            "—"
          )}
        </Metric>
        <Metric label="LLM calls / cost">
          {llm.calls} · {formatUsd(llm.costUsd)}
        </Metric>
        <Metric label="Resumes">{model.resumes}</Metric>
      </dl>
    </section>
  );
}
