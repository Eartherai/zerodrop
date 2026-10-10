import { ApiError, type EventHandlers, type EventSubscription, type ZeroDropApi } from "./client";
import { parseEventData } from "./parse";
import { TERMINAL_STATUSES, type RunEvent } from "./types";

const RECONNECT_BASE_MS = 500;
const RECONNECT_MAX_MS = 8000;
/** SSE event names that carry a RunEvent: unnamed events plus an optional "run_event" name. */
const EVENT_NAMES = ["message", "run_event"] as const;
/** Optional SSE event names the server may send to say the stream is complete. */
const END_NAMES = ["end", "done"] as const;

async function errorMessage(response: Response): Promise<string> {
  try {
    const body: unknown = await response.json();
    if (typeof body === "object" && body !== null && "detail" in body) {
      const detail = (body as { detail: unknown }).detail;
      return typeof detail === "string" ? detail : JSON.stringify(detail);
    }
  } catch {
    // fall through to the status text
  }
  return `${response.status} ${response.statusText}`.trim();
}

export function eventsUrl(base: string, runId: string, afterSeq: number): string {
  return `${base}/api/runs/${encodeURIComponent(runId)}/events?after_seq=${Math.max(0, Math.floor(afterSeq))}`;
}

export function createHttpApi(base: string): ZeroDropApi {
  async function request<T>(path: string, init?: RequestInit): Promise<T> {
    const response = await fetch(`${base}${path}`, {
      ...init,
      headers: { Accept: "application/json", ...(init?.headers ?? {}) },
    });
    if (!response.ok) throw new ApiError(response.status, await errorMessage(response));
    return (await response.json()) as T;
  }

  function subscribeEvents(runId: string, afterSeq: number, handlers: EventHandlers): EventSubscription {
    let lastSeq = afterSeq;
    let source: EventSource | null = null;
    let timer: ReturnType<typeof setTimeout> | null = null;
    let failures = 0;
    let closed = false;

    const finish = () => {
      closed = true;
      if (timer !== null) clearTimeout(timer);
      source?.close();
      source = null;
      handlers.onConnection?.("closed");
    };

    const deliver = (event: RunEvent) => {
      if (event.seq <= lastSeq) return; // replayed after a reconnect
      lastSeq = event.seq;
      handlers.onEvent(event);
      if (event.kind === "state" && event.state !== null && TERMINAL_STATUSES.has(event.state)) finish();
    };

    const open = () => {
      if (closed) return;
      handlers.onConnection?.(failures === 0 ? "connecting" : "reconnecting");
      // Reconnect manually (not via EventSource auto-retry) so after_seq always moves forward.
      const es = new EventSource(eventsUrl(base, runId, lastSeq));
      source = es;
      es.onopen = () => {
        failures = 0;
        handlers.onConnection?.("open");
      };
      const onData = (msg: MessageEvent<string>) => {
        const event = parseEventData(msg.data);
        if (event) deliver(event);
      };
      for (const name of EVENT_NAMES) es.addEventListener(name, onData as EventListener);
      for (const name of END_NAMES) es.addEventListener(name, finish);
      es.onerror = () => {
        es.close();
        if (closed) return;
        failures += 1;
        const delay = Math.min(RECONNECT_MAX_MS, RECONNECT_BASE_MS * 2 ** (failures - 1));
        handlers.onConnection?.("reconnecting", `stream interrupted; retrying in ${(delay / 1000).toFixed(1)}s`);
        timer = setTimeout(open, delay);
      };
    };

    open();
    return { close: finish };
  }

  return {
    mode: "live",
    listScenarios: () => request("/api/scenarios"),
    startRun: (scenarioId) =>
      request("/api/runs", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ scenario_id: scenarioId }),
      }),
    listRuns: () => request("/api/runs"),
    getRun: (runId) => request(`/api/runs/${encodeURIComponent(runId)}`),
    getReport: async (runId) => {
      try {
        return await request(`/api/runs/${encodeURIComponent(runId)}/report`);
      } catch (err) {
        if (err instanceof ApiError && err.status === 404) return null;
        throw err;
      }
    },
    getMappings: (runId) => request(`/api/runs/${encodeURIComponent(runId)}/mappings`),
    subscribeEvents,
  };
}
