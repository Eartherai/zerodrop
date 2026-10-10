// In-browser stand-in for the ZeroDrop API (VITE_MOCK=1). It serves the bundled
// recordings: as finished history runs, and as paced "live" runs when a scenario
// is started. Every payload is derived from the recorded events, so the UI sees
// exactly what the real endpoints would return at that point of the run.

import { ApiError, type EventHandlers, type EventSubscription, type ZeroDropApi } from "../api/client";
import {
  ENTITIES,
  TERMINAL_STATUSES,
  type EntityCounts,
  type MappingVersion,
  type RunDetail,
  type RunEvent,
  type RunListItem,
} from "../api/types";
import { applyEvents, emptyRunModel, type RunModel } from "../lib/runModel";
import { buildSchedule, parseSpeed } from "../lib/schedule";
import { RECORDINGS, type Recording } from "./recordings";

interface MockRun {
  id: string;
  recording: Recording;
  events: RunEvent[];
  /** Release offsets in ms from `startedAt`. */
  schedule: number[];
  /** Wall-clock ms when the run started; -Infinity for history runs (fully released). */
  startedAt: number;
  createdAt: number;
}

export interface MockOptions {
  recordings?: readonly Recording[];
  speed?: number;
  now?: () => number;
}

function urlSpeed(): number {
  if (typeof location === "undefined") return 1;
  return parseSpeed(new URLSearchParams(location.search).get("speed"));
}

function historyRun(recording: Recording): MockRun {
  return {
    id: recording.summary.run_id,
    recording,
    events: recording.events,
    schedule: recording.events.map(() => 0),
    startedAt: Number.NEGATIVE_INFINITY,
    createdAt: recording.summary.created_at,
  };
}

/** Copy a recording under a new run id, keeping the recorded spacing between events. */
function rebase(events: readonly RunEvent[], runId: string, startTs: number): RunEvent[] {
  const first = events[0]?.ts ?? startTs;
  return events.map((e) => ({ ...e, run_id: runId, ts: startTs + (e.ts - first) }));
}

export function createMockApi(options: MockOptions = {}): ZeroDropApi {
  const recordings = options.recordings ?? RECORDINGS;
  const speed = options.speed ?? urlSpeed();
  const now = options.now ?? (() => Date.now());
  const runs = new Map<string, MockRun>(recordings.map((r) => [r.summary.run_id, historyRun(r)]));
  let counter = 0;

  function find(runId: string): MockRun {
    const run = runs.get(runId);
    if (!run) throw new ApiError(404, `unknown run ${runId}`);
    return run;
  }

  function released(run: MockRun): RunEvent[] {
    const elapsed = now() - run.startedAt;
    let n = 0;
    while (n < run.events.length && run.schedule[n]! <= elapsed) n++;
    return run.events.slice(0, n);
  }

  function model(run: MockRun): RunModel {
    return applyEvents(emptyRunModel(run.id), released(run));
  }

  function detail(run: MockRun): RunDetail {
    const m = model(run);
    const counts: Partial<Record<(typeof ENTITIES)[number], EntityCounts>> = {};
    for (const entity of ENTITIES) {
      const p = m.entities[entity];
      counts[entity] = {
        total: p.total ?? p.written + p.quarantined,
        written: p.written,
        quarantined: p.quarantined,
        pending: 0,
      };
    }
    return {
      run_id: run.id,
      status: m.status ?? "CREATED",
      agent_claimed_status: m.agentClaim,
      goal: run.recording.summary.goal,
      scenario_id: run.recording.scenario.id,
      counts,
      mapping_versions: m.mappingVersions,
      llm: { calls: m.llm.calls, cost_usd: m.llm.costUsd },
      trace_url: run.recording.summary.trace_url ?? null,
      commit: run.recording.summary.commit ?? null,
    };
  }

  function subscribeEvents(runId: string, afterSeq: number, handlers: EventHandlers): EventSubscription {
    const run = runs.get(runId);
    let timer: ReturnType<typeof setTimeout> | null = null;
    let closed = false;
    const close = () => {
      if (closed) return;
      closed = true;
      if (timer !== null) clearTimeout(timer);
      handlers.onConnection?.("closed");
    };
    if (!run) {
      timer = setTimeout(() => close(), 0);
      return { close };
    }
    const pending = run.events
      .map((e, i) => ({ e, at: run.startedAt + run.schedule[i]! }))
      .filter((x) => x.e.seq > afterSeq);
    let index = 0;
    const tick = () => {
      if (closed) return;
      const t = now();
      while (index < pending.length && pending[index]!.at <= t) {
        const { e } = pending[index]!;
        index++;
        handlers.onEvent(e);
        if (closed) return;
        if (e.kind === "state" && e.state !== null && TERMINAL_STATUSES.has(e.state)) {
          close();
          return;
        }
      }
      if (index >= pending.length) return; // stream stays open, like a live run with no news
      timer = setTimeout(tick, Math.max(0, pending[index]!.at - now()));
    };
    timer = setTimeout(() => {
      handlers.onConnection?.("open");
      tick();
    }, 0);
    return { close };
  }

  return {
    mode: "mock",
    listScenarios: async () => recordings.map((r) => r.scenario),
    startRun: async (scenarioId) => {
      const recording = recordings.find((r) => r.scenario.id === scenarioId);
      if (!recording) throw new ApiError(404, `unknown scenario ${scenarioId}`);
      counter += 1;
      const id = `run_mock${String(counter).padStart(3, "0")}`;
      const startedAt = now();
      const events = rebase(recording.events, id, startedAt / 1000);
      runs.set(id, {
        id,
        recording,
        events,
        schedule: buildSchedule(events, speed),
        startedAt,
        createdAt: startedAt / 1000,
      });
      return { run_id: id };
    },
    listRuns: async (): Promise<RunListItem[]> =>
      [...runs.values()]
        .sort((a, b) => b.createdAt - a.createdAt)
        .map((run) => ({
          run_id: run.id,
          status: model(run).status ?? "CREATED",
          scenario_id: run.recording.scenario.id,
          created_at: run.createdAt,
        })),
    getRun: async (runId) => detail(find(runId)),
    getReport: async (runId) => {
      const run = find(runId);
      const report = run.recording.report;
      return report && model(run).verify ? { ...report, run_id: run.id } : null;
    },
    getMappings: async (runId): Promise<MappingVersion[]> => {
      const run = find(runId);
      const versions = model(run).mappingVersions;
      return run.recording.mappings.filter((m) => m.version <= (versions[m.entity] ?? 0));
    },
    subscribeEvents,
  };
}
