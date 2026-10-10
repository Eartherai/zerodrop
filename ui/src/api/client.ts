import type { MappingVersion, ReconciliationReport, RunDetail, RunEvent, RunListItem, Scenario } from "./types";

export type ConnectionState = "connecting" | "open" | "reconnecting" | "closed";

export interface EventHandlers {
  onEvent: (event: RunEvent) => void;
  onConnection?: (state: ConnectionState, detail?: string) => void;
}

export interface EventSubscription {
  close: () => void;
}

/** Everything the UI needs from the ZeroDrop backend (or the bundled mock). */
export interface ZeroDropApi {
  readonly mode: "live" | "mock";
  listScenarios: () => Promise<Scenario[]>;
  startRun: (scenarioId: string) => Promise<{ run_id: string }>;
  listRuns: () => Promise<RunListItem[]>;
  getRun: (runId: string) => Promise<RunDetail>;
  /** Resolves to null while the report does not exist yet (HTTP 404). */
  getReport: (runId: string) => Promise<ReconciliationReport | null>;
  getMappings: (runId: string) => Promise<MappingVersion[]>;
  /** Streams events with seq > afterSeq, in order, until closed or the run ends. */
  subscribeEvents: (runId: string, afterSeq: number, handlers: EventHandlers) => EventSubscription;
}

export class ApiError extends Error {
  readonly status: number;

  constructor(status: number, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

export function isMockMode(): boolean {
  return import.meta.env.VITE_MOCK === "1";
}

export async function createApi(): Promise<ZeroDropApi> {
  if (isMockMode()) {
    const { createMockApi } = await import("../mock/mockApi");
    return createMockApi();
  }
  const { createHttpApi } = await import("./http");
  return createHttpApi("");
}
