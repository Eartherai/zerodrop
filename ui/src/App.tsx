import { useCallback, useEffect, useRef, useState } from "react";
import type { ZeroDropApi } from "./api/client";
import type { RunListItem, Scenario } from "./api/types";
import { Certificate } from "./components/Certificate";
import { EventTimeline } from "./components/EventTimeline";
import { Footer } from "./components/Footer";
import { Header } from "./components/Header";
import { MappingDiff } from "./components/MappingDiff";
import { RunHero } from "./components/RunHero";
import { statusLabel } from "./components/ui";
import { useRun } from "./hooks/useRun";
import { toDate } from "./lib/format";
import { isTerminal } from "./lib/runModel";

const RUNS_POLL_MS = 5000;

function runFromUrl(): string | null {
  return new URLSearchParams(window.location.search).get("run");
}

function syncUrl(runId: string | null): void {
  const url = new URL(window.location.href);
  if (runId && !runId.startsWith("run_mock")) url.searchParams.set("run", runId);
  else url.searchParams.delete("run");
  window.history.replaceState(null, "", url);
}

function newestFirst(runs: RunListItem[]): RunListItem[] {
  const time = (r: RunListItem) => toDate(r.created_at)?.getTime() ?? 0;
  return [...runs].sort((a, b) => time(b) - time(a));
}

function errorText(err: unknown): string {
  return err instanceof Error ? err.message : String(err);
}

export function App({ api }: { api: ZeroDropApi }) {
  const mock = api.mode === "mock";
  const [scenarios, setScenarios] = useState<Scenario[]>([]);
  const [scenarioId, setScenarioId] = useState("");
  const [runs, setRuns] = useState<RunListItem[]>([]);
  const [runId, setRunId] = useState<string | null>(runFromUrl);
  const [starting, setStarting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [replaySpeed, setReplaySpeed] = useState(1);
  const [dismissed, setDismissed] = useState<string | null>(null);
  const run = useRun(api, runId);
  const { model } = run;

  useEffect(() => {
    api
      .listScenarios()
      .then((list) => {
        setScenarios(list);
        setScenarioId((current) => current || list[0]?.id || "");
      })
      .catch((err: unknown) => setError(`Could not load scenarios: ${errorText(err)}`));
  }, [api]);

  const refreshRuns = useCallback(() => {
    api
      .listRuns()
      .then((list) => setRuns(newestFirst(list)))
      .catch((err: unknown) => setError(`Could not load runs: ${errorText(err)}`));
  }, [api]);

  useEffect(() => {
    refreshRuns();
    const id = setInterval(refreshRuns, RUNS_POLL_MS);
    return () => clearInterval(id);
  }, [refreshRuns]);

  useEffect(() => syncUrl(runId), [runId]);

  // Keep the run picker's status labels current as the selected run moves on.
  useEffect(() => {
    if (model.status) refreshRuns();
  }, [model.status, refreshRuns]);

  const start = async () => {
    if (!scenarioId) return;
    setStarting(true);
    setError(null);
    try {
      const { run_id } = await api.startRun(scenarioId);
      setRunId(run_id);
      refreshRuns();
    } catch (err) {
      setError(`Could not start the run: ${errorText(err)}`);
    } finally {
      setStarting(false);
    }
  };

  // Bring the certificate into view when a verdict arrives while watching (live or replay).
  const certificateSeen = useRef(false);
  const verified = model.verify !== null;
  const watching = run.replay.active || (!run.recorded && run.connection === "open");
  useEffect(() => {
    if (!verified) {
      certificateSeen.current = false;
      return;
    }
    if (certificateSeen.current) return;
    certificateSeen.current = true;
    if (!watching) return;
    const id = setTimeout(() => {
      const reduce = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
      document.getElementById("certificate")?.scrollIntoView({ behavior: reduce ? "auto" : "smooth", block: "start" });
    }, 600);
    return () => clearTimeout(id);
  }, [verified, watching]);

  const scenario = scenarios.find((s) => s.id === (run.detail?.scenario_id ?? model.scenario));
  const current = error ?? run.error;
  const problem = current !== dismissed ? current : null;

  return (
    <div className="flex min-h-screen flex-col bg-bg text-fg">
      <Header
        mock={mock}
        scenarios={scenarios}
        scenarioId={scenarioId}
        onScenario={setScenarioId}
        onStart={() => void start()}
        starting={starting}
        runs={runs}
        runId={runId}
        onSelectRun={setRunId}
      />
      <p className="sr-only" aria-live="polite">
        {model.status ? `Run status: ${statusLabel(model.status)}` : ""}
      </p>
      <main className="mx-auto flex w-full max-w-[1480px] flex-1 flex-col gap-10 px-5 py-8 lg:px-10">
        {problem ? (
          <div
            role="alert"
            className="flex items-start justify-between gap-4 rounded-md border border-danger bg-danger-soft px-4 py-3 text-sm text-danger"
          >
            <span>{problem}</span>
            <button
              type="button"
              className="font-semibold underline"
              onClick={() => {
                setDismissed(problem);
                setError(null);
              }}
            >
              Dismiss
            </button>
          </div>
        ) : null}
        <RunHero
          model={model}
          detail={run.detail}
          report={run.report}
          scenario={scenario}
          selected={scenarios.find((s) => s.id === scenarioId)}
          counts={run.replay.active || model.events.length ? undefined : run.detail?.counts}
          connection={run.connection}
          connectionDetail={run.connectionDetail}
          recorded={run.recorded}
          replay={run.replay}
          onReplay={run.startReplay}
          onStopReplay={run.stopReplay}
          replaySpeed={replaySpeed}
          onReplaySpeed={setReplaySpeed}
        />
        {model.status !== null ? (
          <>
            {verified || isTerminal(model.status) || model.status === "VERIFYING" ? (
              <Certificate report={run.report} model={model} />
            ) : null}
            <div className="grid items-start gap-6 xl:grid-cols-[minmax(0,6fr)_minmax(0,5fr)]">
              <MappingDiff mappings={run.mappings} model={model} />
              <EventTimeline events={model.events} />
            </div>
          </>
        ) : null}
      </main>
      <Footer detail={run.detail} mock={mock} />
    </div>
  );
}
