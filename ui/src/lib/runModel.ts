// Pure reducer: folds the RunEvent stream into the view model every panel reads.
// It only relies on documented event kinds/states and on the data keys the engine
// emits (see docs/UI.md, "Event data keys"); unknown keys are ignored.

import { isEntity, isRunStatus } from "../api/parse";
import { ENTITIES, TERMINAL_STATUSES, type Entity, type JsonValue, type RunEvent, type RunStatus } from "../api/types";

export const STAGES = ["goal", "plan", "action", "observation", "failure", "recovery", "verification"] as const;
export type StageId = (typeof STAGES)[number];

export const STAGE_LABELS: Record<StageId, string> = {
  goal: "Goal",
  plan: "Plan",
  action: "Action",
  observation: "Observation",
  failure: "Failure",
  recovery: "Recovery",
  verification: "Verification",
};

export type VerificationResult = "success" | "partial" | "failed";

export interface StageState {
  hits: number;
  lastSeq: number | null;
  lastMessage: string | null;
  /** Labelled counters shown under the stage (failure classes, recovery tactics...). */
  tags: Record<string, number>;
}

export interface EntityProgress {
  entity: Entity;
  /** Source records loaded at discovery (includes rows a mapping later excludes). */
  loaded: number | null;
  /** Final record total reported when the entity completed (excludes excluded rows). */
  total: number | null;
  written: number;
  quarantined: number;
  failed: number;
  replayed: number;
  batches: number;
  done: boolean;
}

export interface VerifySummary {
  status: RunStatus;
  agentClaim: RunStatus | null;
  falseSuccess: boolean;
  reportHash: string | null;
  failedChecks: string[];
}

export interface RunModel {
  runId: string | null;
  lastSeq: number;
  events: RunEvent[];
  status: RunStatus | null;
  goal: string | null;
  scenario: string | null;
  timezone: string | null;
  targetApiVersion: string | null;
  apiVersionHistory: string[];
  stages: Record<StageId, StageState>;
  activeStages: StageId[];
  verification: VerificationResult | null;
  entities: Record<Entity, EntityProgress>;
  mappingVersions: Partial<Record<Entity, number>>;
  llm: { calls: number; costUsd: number };
  agentClaim: RunStatus | null;
  verify: VerifySummary | null;
  resumes: number;
  firstTs: number | null;
  lastTs: number | null;
}

function emptyStage(): StageState {
  return { hits: 0, lastSeq: null, lastMessage: null, tags: {} };
}

function emptyEntity(entity: Entity): EntityProgress {
  return {
    entity,
    loaded: null,
    total: null,
    written: 0,
    quarantined: 0,
    failed: 0,
    replayed: 0,
    batches: 0,
    done: false,
  };
}

export function emptyRunModel(runId: string | null = null): RunModel {
  return {
    runId,
    lastSeq: 0,
    events: [],
    status: null,
    goal: null,
    scenario: null,
    timezone: null,
    targetApiVersion: null,
    apiVersionHistory: [],
    stages: Object.fromEntries(STAGES.map((s) => [s, emptyStage()])) as Record<StageId, StageState>,
    activeStages: [],
    verification: null,
    entities: Object.fromEntries(ENTITIES.map((e) => [e, emptyEntity(e)])) as Record<Entity, EntityProgress>,
    mappingVersions: {},
    llm: { calls: 0, costUsd: 0 },
    agentClaim: null,
    verify: null,
    resumes: 0,
    firstTs: null,
    lastTs: null,
  };
}

// ---------------------------------------------------------------------------
// Data accessors (event.data is untyped JSON)
// ---------------------------------------------------------------------------

function num(value: JsonValue | undefined): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function str(value: JsonValue | undefined): string | null {
  return typeof value === "string" ? value : null;
}

function has(event: RunEvent, key: string): boolean {
  return Object.prototype.hasOwnProperty.call(event.data, key);
}

export function failureClassOf(event: RunEvent): string | null {
  return str(event.data.failure_class);
}

/** "quarantined 2 customers record(s)" -> 2; falls back to the listed items. */
function quarantinedCount(event: RunEvent): number {
  const match = /quarantined (\d+)/.exec(event.message);
  if (match?.[1]) return Number(match[1]);
  const items = event.data.items;
  return Array.isArray(items) ? items.length : 0;
}

function claimFromMessage(message: string): RunStatus | null {
  const match = /engine believes the run is ([A-Z_]+)/.exec(message);
  return match?.[1] && isRunStatus(match[1]) ? match[1] : null;
}

// ---------------------------------------------------------------------------
// Event -> pipeline stages
// ---------------------------------------------------------------------------

const PLAN_STATES: ReadonlySet<RunStatus> = new Set<RunStatus>(["DISCOVERING", "PLANNING", "DRY_RUN"]);

/** Recovery tactic label for the RECOVERY stage counters. */
export function recoveryTactic(event: RunEvent): string | null {
  if (event.kind === "info" && event.message.startsWith("resuming")) return "resume";
  if (event.kind === "decision" && failureClassOf(event) === "DATA") return "quarantine";
  if (event.kind === "plan" && event.state === "RECOVERING") return "new mapping";
  if (event.kind !== "recovery") return null;
  if (failureClassOf(event) === "TRANSIENT") return "backoff";
  if (has(event, "found") || has(event, "resend")) return "lookup";
  if (has(event, "schema_changes")) return "schema refetch";
  if (has(event, "mapping_versions")) return "resume writes";
  if (event.message.startsWith("credentials")) return "re-auth";
  return "other";
}

function stagesForState(state: RunStatus): StageId[] {
  switch (state) {
    case "CREATED":
      return ["goal"];
    case "DISCOVERING":
    case "PLANNING":
    case "DRY_RUN":
      return ["plan"];
    case "EXECUTING":
      return ["action"];
    case "RECOVERING":
      return ["recovery"];
    case "VERIFYING":
    case "SUCCESS":
    case "PARTIAL_SUCCESS":
    case "FAILED":
      return ["verification"];
    case "WAITING_FOR_APPROVAL":
      return ["failure"];
  }
}

/** Stages an event lights up; the first entry is the primary stage. */
export function stagesForEvent(event: RunEvent): StageId[] {
  const recovering = event.state === "RECOVERING";
  switch (event.kind) {
    case "state":
      return event.state ? stagesForState(event.state) : [];
    case "info":
      return event.message.startsWith("resuming") ? ["recovery"] : ["observation"];
    case "plan":
      return recovering ? ["recovery", "plan"] : ["plan"];
    case "llm":
      return recovering ? ["recovery"] : ["plan"];
    case "batch":
      return ["observation", "action"];
    case "failure":
      return ["failure"];
    case "recovery":
      return ["recovery"];
    case "verify":
      return ["verification"];
    case "decision": {
      const cls = failureClassOf(event);
      if (cls === "DATA") return ["recovery"];
      if (cls !== null) return ["failure"];
      if (has(event, "checked")) return recovering ? ["recovery"] : ["observation", "action"]; // dry run
      if (has(event, "codes")) return recovering ? ["recovery"] : ["plan"]; // repair request
      if (event.state !== null && PLAN_STATES.has(event.state)) return ["plan"];
      return recovering ? ["recovery"] : ["observation"];
    }
  }
}

function stageTag(stage: StageId, event: RunEvent): string | null {
  if (stage === "failure") return failureClassOf(event) ?? (event.state === "WAITING_FOR_APPROVAL" ? "APPROVAL" : null);
  if (stage === "recovery") return recoveryTactic(event);
  return null;
}

function verificationResult(status: RunStatus): VerificationResult | null {
  if (status === "SUCCESS") return "success";
  if (status === "PARTIAL_SUCCESS") return "partial";
  if (status === "FAILED") return "failed";
  return null;
}

// ---------------------------------------------------------------------------
// Reducer
// ---------------------------------------------------------------------------

function updateEntities(model: RunModel, event: RunEvent): Record<Entity, EntityProgress> {
  const entities = { ...model.entities };
  const loaded = event.data.records_loaded;
  if (event.kind === "info" && loaded && typeof loaded === "object" && !Array.isArray(loaded)) {
    for (const [name, value] of Object.entries(loaded)) {
      const n = num(value);
      if (isEntity(name) && n !== null) entities[name] = { ...entities[name], loaded: n };
    }
  }
  const entity = event.entity;
  if (!entity) return entities;
  const current = entities[entity];
  if (event.kind === "batch") {
    entities[entity] = {
      ...current,
      written: current.written + (num(event.data.written) ?? 0),
      replayed: current.replayed + (num(event.data.replayed) ?? 0),
      batches: current.batches + 1,
    };
  } else if (event.kind === "recovery" && has(event, "found")) {
    entities[entity] = { ...current, written: current.written + (num(event.data.found) ?? 0) };
  } else if (event.kind === "decision" && failureClassOf(event) === "DATA") {
    entities[entity] = { ...current, quarantined: current.quarantined + quarantinedCount(event) };
  } else if (event.kind === "decision" && has(event, "total") && has(event, "written")) {
    // "<entity> complete": authoritative ledger counts for the entity.
    entities[entity] = {
      ...current,
      total: num(event.data.total),
      written: num(event.data.written) ?? current.written,
      quarantined: num(event.data.quarantined) ?? current.quarantined,
      failed: num(event.data.failed) ?? current.failed,
      done: true,
    };
  }
  return entities;
}

function updateMappingVersions(model: RunModel, event: RunEvent): Partial<Record<Entity, number>> {
  const versions = { ...model.mappingVersions };
  const mappings = event.data.mappings;
  if (event.kind === "plan" && mappings && typeof mappings === "object" && !Array.isArray(mappings)) {
    for (const [name, summary] of Object.entries(mappings)) {
      if (!isEntity(name) || !summary || typeof summary !== "object" || Array.isArray(summary)) continue;
      const v = num(summary.version);
      if (v !== null) versions[name] = v;
    }
  }
  const to = num(event.data.version_to);
  if (event.kind === "plan" && event.entity && to !== null) versions[event.entity] = to;
  const current = event.data.mapping_versions;
  if (current && typeof current === "object" && !Array.isArray(current)) {
    for (const [name, value] of Object.entries(current)) {
      const v = num(value);
      if (isEntity(name) && v !== null) versions[name] = v;
    }
  }
  return versions;
}

function observedApiVersion(event: RunEvent): string | null {
  return str(event.data.version_to) ?? str(event.data.target_api_version) ?? str(event.data.api_version);
}

function updateStages(model: RunModel, event: RunEvent, stages: StageId[]): Record<StageId, StageState> {
  const next = { ...model.stages };
  for (const stage of stages) {
    const prev = next[stage];
    const tag = stageTag(stage, event);
    next[stage] = {
      hits: prev.hits + 1,
      lastSeq: event.seq,
      lastMessage: event.message,
      tags: tag ? { ...prev.tags, [tag]: (prev.tags[tag] ?? 0) + 1 } : prev.tags,
    };
  }
  return next;
}

function updateVerify(model: RunModel, event: RunEvent): VerifySummary | null {
  if (event.kind !== "verify") return model.verify;
  const status = event.data.status;
  if (!isRunStatus(status)) return model.verify; // e.g. "verifier error" events carry no status
  const claim = event.data.agent_claimed_status;
  const failed = event.data.failed_checks;
  return {
    status,
    agentClaim: isRunStatus(claim) ? claim : model.agentClaim,
    falseSuccess: event.data.false_success_claim === true,
    reportHash: str(event.data.report_hash),
    failedChecks: Array.isArray(failed) ? failed.filter((f): f is string => typeof f === "string") : [],
  };
}

export function applyEvent(model: RunModel, event: RunEvent): RunModel {
  if (event.seq <= model.lastSeq) return model; // duplicate after a reconnect
  if (model.runId !== null && event.run_id !== model.runId) return model;

  const stages = stagesForEvent(event);
  const status = event.state ?? model.status;
  const apiVersion = observedApiVersion(event);
  const history = model.apiVersionHistory;
  const calls = num(event.data.calls);
  const cost = num(event.data.cost_usd);
  const verify = updateVerify(model, event);
  const claim =
    (event.kind === "decision" ? claimFromMessage(event.message) : null) ?? verify?.agentClaim ?? model.agentClaim;

  let verification = model.verification;
  if (event.kind === "verify" && verify) verification = verificationResult(verify.status);
  if (
    event.kind === "state" &&
    event.state &&
    TERMINAL_STATUSES.has(event.state) &&
    event.state !== "WAITING_FOR_APPROVAL"
  ) {
    verification = verify ? verificationResult(verify.status) : verificationResult(event.state);
  }

  return {
    ...model,
    runId: model.runId ?? event.run_id,
    lastSeq: event.seq,
    events: [...model.events, event],
    status,
    goal:
      model.goal ?? (event.message.startsWith("run created: ") ? event.message.slice("run created: ".length) : null),
    scenario: model.scenario ?? str(event.data.scenario),
    timezone: str(event.data.timezone) ?? model.timezone,
    targetApiVersion: apiVersion ?? model.targetApiVersion,
    apiVersionHistory: apiVersion && history[history.length - 1] !== apiVersion ? [...history, apiVersion] : history,
    stages: updateStages(model, event, stages),
    activeStages: stages.length > 0 ? stages : model.activeStages,
    verification,
    entities: updateEntities(model, event),
    mappingVersions: updateMappingVersions(model, event),
    llm: event.kind === "llm" ? { calls: calls ?? model.llm.calls, costUsd: cost ?? model.llm.costUsd } : model.llm,
    agentClaim: claim,
    verify,
    resumes: model.resumes + (event.kind === "info" && event.message.startsWith("resuming") ? 1 : 0),
    firstTs: model.firstTs ?? event.ts,
    lastTs: event.ts,
  };
}

export function applyEvents(model: RunModel, events: readonly RunEvent[]): RunModel {
  let next = model;
  for (const event of events) next = applyEvent(next, event);
  return next;
}

export function isTerminal(status: RunStatus | null): boolean {
  return status !== null && TERMINAL_STATUSES.has(status);
}

/** Records not yet resolved: the best known denominator minus everything resolved so far. */
export function expectedRecords(p: EntityProgress): number {
  return p.total ?? Math.max(p.loaded ?? 0, p.written + p.quarantined + p.failed);
}

export function pendingRecords(p: EntityProgress): number {
  return Math.max(0, expectedRecords(p) - p.written - p.quarantined - p.failed);
}

/** Rows a mapping rule excluded (soft-deleted customers), known once the entity completes. */
export function excludedRecords(p: EntityProgress): number | null {
  if (p.total === null || p.loaded === null) return null;
  return Math.max(0, p.loaded - p.total);
}
