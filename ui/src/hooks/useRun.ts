import { useCallback, useEffect, useRef, useState } from "react";
import type { ConnectionState, ZeroDropApi } from "../api/client";
import type { MappingVersion, ReconciliationReport, RunDetail, RunEvent } from "../api/types";
import { applyEvents, emptyRunModel, isTerminal, type RunModel } from "../lib/runModel";
import { buildSchedule } from "../lib/schedule";

const POLL_MS = 2000;
/** Resubscribe when the polled status is ahead of the stream and no event arrived for this long. */
const STALL_MS = 6000;

export interface ReplayState {
  active: boolean;
  speed: number;
  /** Events released so far / total, 0..1. */
  progress: number;
}

export interface RunView {
  model: RunModel;
  detail: RunDetail | null;
  report: ReconciliationReport | null;
  mappings: MappingVersion[];
  connection: ConnectionState;
  connectionDetail: string | null;
  error: string | null;
  /** The run had already finished when it was opened: everything shown is a replay. */
  recorded: boolean;
  replay: ReplayState;
  startReplay: (speed: number) => void;
  stopReplay: () => void;
}

function scheduleFrame(fn: () => void): () => void {
  if (typeof requestAnimationFrame === "function") {
    const id = requestAnimationFrame(fn);
    return () => cancelAnimationFrame(id);
  }
  const id = setTimeout(fn, 16);
  return () => clearTimeout(id);
}

function message(err: unknown): string {
  return err instanceof Error ? err.message : String(err);
}

/** Subscribes to one run: event stream, polled detail, report and mapping history. */
export function useRun(api: ZeroDropApi, runId: string | null): RunView {
  const [model, setModel] = useState<RunModel>(() => emptyRunModel(runId));
  const [detail, setDetail] = useState<RunDetail | null>(null);
  const [report, setReport] = useState<ReconciliationReport | null>(null);
  const [mappings, setMappings] = useState<MappingVersion[]>([]);
  const [connection, setConnection] = useState<ConnectionState>("closed");
  const [connectionDetail, setConnectionDetail] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [recorded, setRecorded] = useState(false);
  const [replay, setReplay] = useState<ReplayState>({ active: false, speed: 1, progress: 1 });

  const [streamNonce, setStreamNonce] = useState(0);

  const allEvents = useRef<RunEvent[]>([]);
  const lastSeq = useRef(0);
  const lastStreamState = useRef<RunEvent["state"]>(null);
  const lastEventAt = useRef(0);
  const queue = useRef<RunEvent[]>([]);
  const cancelFlush = useRef<(() => void) | null>(null);
  const replayTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const flush = useCallback(() => {
    cancelFlush.current = null;
    const batch = queue.current.splice(0);
    if (batch.length) setModel((m) => applyEvents(m, batch));
  }, []);

  const enqueue = useCallback(
    (event: RunEvent) => {
      queue.current.push(event);
      if (!cancelFlush.current) cancelFlush.current = scheduleFrame(flush);
    },
    [flush],
  );

  const clearReplayTimer = () => {
    if (replayTimer.current !== null) clearTimeout(replayTimer.current);
    replayTimer.current = null;
  };

  // Reset whenever the selected run changes.
  useEffect(() => {
    clearReplayTimer();
    cancelFlush.current?.();
    cancelFlush.current = null;
    queue.current = [];
    allEvents.current = [];
    lastSeq.current = 0;
    lastStreamState.current = null;
    setModel(emptyRunModel(runId));
    setDetail(null);
    setReport(null);
    setMappings([]);
    setError(null);
    setRecorded(false);
    setReplay({ active: false, speed: 1, progress: 1 });
    if (!runId) {
      setConnection("closed");
      return;
    }
    let cancelled = false;
    api
      .getRun(runId)
      .then((d) => {
        if (cancelled) return;
        setDetail(d);
        setRecorded(isTerminal(d.status));
      })
      .catch((err: unknown) => !cancelled && setError(message(err)));
    return () => {
      cancelled = true;
    };
  }, [api, runId]);

  // Subscribe (and resubscribe after a stall) from the last event seen.
  useEffect(() => {
    if (!runId) return;
    let cancelled = false;
    lastEventAt.current = Date.now();
    const sub = api.subscribeEvents(runId, lastSeq.current, {
      onEvent: (event) => {
        if (cancelled || event.seq <= lastSeq.current) return;
        lastSeq.current = event.seq;
        lastStreamState.current = event.state ?? lastStreamState.current;
        lastEventAt.current = Date.now();
        allEvents.current.push(event);
        enqueue(event);
      },
      onConnection: (state, info) => {
        if (cancelled) return;
        setConnection(state);
        setConnectionDetail(info ?? null);
      },
    });
    return () => {
      cancelled = true;
      sub.close();
    };
  }, [api, runId, enqueue, streamNonce]);

  const terminal = isTerminal(model.status);

  // Poll the run detail while it is running; fetch once more when it ends.
  useEffect(() => {
    if (!runId || replay.active) return;
    let cancelled = false;
    const load = () =>
      api
        .getRun(runId)
        .then((d) => {
          if (cancelled) return;
          setDetail(d);
          // A proxy can swallow a dropped stream; if the server's status moved on without us, reconnect.
          const stalled = Date.now() - lastEventAt.current > STALL_MS;
          if (stalled && d.status !== lastStreamState.current) {
            lastEventAt.current = Date.now();
            setConnectionDetail("stream stalled; reconnecting");
            setStreamNonce((n) => n + 1);
          }
        })
        .catch((err: unknown) => !cancelled && setError(message(err)));
    if (terminal) {
      void load();
      return () => {
        cancelled = true;
      };
    }
    const id = setInterval(load, POLL_MS);
    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, [api, runId, terminal, replay.active]);

  // Mapping history: refetch whenever a new mapping version shows up in the stream.
  const versionsKey = JSON.stringify(model.mappingVersions);
  useEffect(() => {
    if (!runId || replay.active || versionsKey === "{}") return;
    let cancelled = false;
    api
      .getMappings(runId)
      .then((rows) => !cancelled && setMappings(rows))
      .catch((err: unknown) => !cancelled && setError(message(err)));
    return () => {
      cancelled = true;
    };
  }, [api, runId, versionsKey, terminal, replay.active]);

  // The report exists once the verifier has run; the terminal state follows it.
  const verified = model.verify !== null;
  useEffect(() => {
    if (!runId || replay.active || (!verified && !terminal)) return;
    let cancelled = false;
    api
      .getReport(runId)
      .then((r) => !cancelled && r && setReport(r))
      .catch((err: unknown) => !cancelled && setError(message(err)));
    return () => {
      cancelled = true;
    };
  }, [api, runId, verified, terminal, replay.active]);

  const stopReplay = useCallback(() => {
    clearReplayTimer();
    cancelFlush.current?.();
    cancelFlush.current = null;
    queue.current = [];
    setModel(applyEvents(emptyRunModel(runId), allEvents.current));
    setReplay((r) => ({ ...r, active: false, progress: 1 }));
  }, [runId]);

  const startReplay = useCallback(
    (speed: number) => {
      const events = allEvents.current.slice();
      if (!events.length) return;
      clearReplayTimer();
      cancelFlush.current?.();
      cancelFlush.current = null;
      queue.current = [];
      setModel(emptyRunModel(runId));
      setReplay({ active: true, speed, progress: 0 });
      const offsets = buildSchedule(events, speed);
      const start = Date.now();
      let index = 0;
      const tick = () => {
        const elapsed = Date.now() - start;
        while (index < events.length && offsets[index]! <= elapsed) enqueue(events[index++]!);
        setReplay({ active: index < events.length, speed, progress: index / events.length });
        if (index < events.length)
          replayTimer.current = setTimeout(tick, Math.max(0, offsets[index]! - (Date.now() - start)));
        else replayTimer.current = null;
      };
      replayTimer.current = setTimeout(tick, 0);
    },
    [enqueue, runId],
  );

  useEffect(() => () => clearReplayTimer(), []);

  return {
    model,
    detail,
    report,
    mappings,
    connection,
    connectionDetail,
    error,
    recorded,
    replay,
    startReplay,
    stopReplay,
  };
}
