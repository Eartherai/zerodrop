import {
  ENTITIES,
  EVENT_KINDS,
  RUN_STATUSES,
  type Entity,
  type EventKind,
  type JsonObject,
  type RunEvent,
  type RunStatus,
} from "./types";

const KINDS: ReadonlySet<string> = new Set(EVENT_KINDS);
const STATUSES: ReadonlySet<string> = new Set(RUN_STATUSES);
const ENTITY_SET: ReadonlySet<string> = new Set(ENTITIES);

function isObject(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

export function isRunStatus(value: unknown): value is RunStatus {
  return typeof value === "string" && STATUSES.has(value);
}

export function isEntity(value: unknown): value is Entity {
  return typeof value === "string" && ENTITY_SET.has(value);
}

/**
 * Validate one decoded RunEvent. Unknown kinds/states/entities are rejected so a
 * contract drift shows up as a visible parse error instead of a silently wrong UI.
 */
export function toRunEvent(raw: unknown): RunEvent | null {
  if (!isObject(raw)) return null;
  const { run_id, seq, ts, kind, message, state, entity, data } = raw;
  if (typeof run_id !== "string" || typeof seq !== "number" || typeof ts !== "number") return null;
  if (typeof kind !== "string" || !KINDS.has(kind) || typeof message !== "string") return null;
  if (state !== null && state !== undefined && !isRunStatus(state)) return null;
  if (entity !== null && entity !== undefined && !isEntity(entity)) return null;
  return {
    run_id,
    seq,
    ts,
    kind: kind as EventKind,
    message,
    state: (state ?? null) as RunStatus | null,
    entity: (entity ?? null) as Entity | null,
    data: isObject(data) ? (data as JsonObject) : {},
  };
}

/** Parse the `data:` payload of one Server-Sent Event. */
export function parseEventData(text: string): RunEvent | null {
  try {
    return toRunEvent(JSON.parse(text));
  } catch {
    return null;
  }
}
