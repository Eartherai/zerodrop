// TypeScript mirror of the frozen contracts in src/zerodrop/models.py and the
// HTTP API documented in docs/UI.md. Keep the two in sync.

export const ENTITIES = ["customers", "subscriptions", "invoices"] as const;
export type Entity = (typeof ENTITIES)[number];

export const RUN_STATUSES = [
  "CREATED",
  "DISCOVERING",
  "PLANNING",
  "DRY_RUN",
  "EXECUTING",
  "RECOVERING",
  "VERIFYING",
  "SUCCESS",
  "PARTIAL_SUCCESS",
  "FAILED",
  "WAITING_FOR_APPROVAL",
] as const;
export type RunStatus = (typeof RUN_STATUSES)[number];

export const TERMINAL_STATUSES: ReadonlySet<RunStatus> = new Set<RunStatus>([
  "SUCCESS",
  "PARTIAL_SUCCESS",
  "FAILED",
  "WAITING_FOR_APPROVAL",
]);

export const EVENT_KINDS = [
  "state",
  "plan",
  "batch",
  "failure",
  "recovery",
  "decision",
  "verify",
  "llm",
  "info",
] as const;
export type EventKind = (typeof EVENT_KINDS)[number];

export type FailureClass =
  "TRANSIENT" | "AMBIGUOUS_WRITE" | "CONTRACT" | "DATA" | "AUTH" | "DESTRUCTIVE" | "BUDGET" | "UNKNOWN";

export type JsonValue = string | number | boolean | null | JsonValue[] | { [key: string]: JsonValue };
export type JsonObject = { [key: string]: JsonValue };

/** One persisted, streamed event (models.RunEvent). `ts` is epoch seconds. */
export interface RunEvent {
  run_id: string;
  seq: number;
  ts: number;
  kind: EventKind;
  message: string;
  state: RunStatus | null;
  entity: Entity | null;
  data: JsonObject;
}

// ---------------------------------------------------------------------------
// Mapping DSL (models.MappingSpec)
// ---------------------------------------------------------------------------

export interface EnumPair {
  source: string;
  target: string;
}

export interface Condition {
  field: string;
  equals: string | number | boolean | null;
}

export interface TransformOp {
  op: string;
  part?: "first" | "last" | null;
  formats?: string[] | null;
  assume_tz?: string | null;
  decimals?: number | null;
  currency_field?: string | null;
  mapping?: EnumPair[] | null;
  default?: string | null;
  entity?: Entity | null;
  table?: string | null;
  match_field?: string | null;
  return_field?: string | null;
  true_values?: string[] | null;
  value?: string | number | boolean | null;
}

export interface FieldMapping {
  target: string;
  source: string | null;
  ops: TransformOp[];
  required: boolean;
}

export interface MappingSpec {
  entity: Entity;
  version: number;
  target_api_version: string;
  fields: FieldMapping[];
  exclude_if: Condition[];
  rationale: string;
}

/** One row of GET /api/runs/{id}/mappings. */
export interface MappingVersion {
  entity: Entity;
  version: number;
  spec: MappingSpec;
}

// ---------------------------------------------------------------------------
// Verification (models.ReconciliationReport)
// ---------------------------------------------------------------------------

export interface CheckResult {
  name: string;
  passed: boolean;
  entity: Entity | null;
  expected: JsonValue;
  actual: JsonValue;
  detail: string;
}

export interface QuarantineItem {
  entity: Entity;
  source_id: string;
  reason: string;
}

export interface ReconciliationReport {
  run_id: string;
  status: RunStatus;
  checks: CheckResult[];
  quarantined: QuarantineItem[];
  source_counts: Record<string, number>;
  target_counts: Record<string, number>;
  money_source_minor: Record<string, number>;
  money_target_minor: Record<string, number>;
  report_hash: string;
}

// ---------------------------------------------------------------------------
// HTTP API payloads
// ---------------------------------------------------------------------------

export interface Scenario {
  id: string;
  title: string;
  description: string;
}

/** `created_at` may be epoch seconds or an ISO-8601 string; both are accepted. */
export interface RunListItem {
  run_id: string;
  status: RunStatus;
  scenario_id: string;
  created_at: number | string;
}

export interface EntityCounts {
  total: number;
  written: number;
  quarantined: number;
  pending: number;
}

export interface RunDetail {
  run_id: string;
  status: RunStatus;
  agent_claimed_status: RunStatus | null;
  goal: string;
  scenario_id: string;
  counts: Partial<Record<Entity, EntityCounts>>;
  mapping_versions: Partial<Record<Entity, number>>;
  llm: { calls: number; cost_usd: number };
  trace_url?: string | null;
  trace_id?: string | null;
  commit?: string | null;
}
