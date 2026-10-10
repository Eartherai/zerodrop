// Compact, human-readable facts extracted from an event's data for the timeline.

import type { JsonValue, RunEvent } from "../api/types";
import type { Tone } from "./tones";

export interface Detail {
  label: string;
  value: string;
  tone?: Tone;
}

function isRecord(v: JsonValue | undefined): v is { [key: string]: JsonValue } {
  return typeof v === "object" && v !== null && !Array.isArray(v);
}

function n(v: JsonValue | undefined): number | null {
  return typeof v === "number" ? v : null;
}

function s(v: JsonValue | undefined): string | null {
  return typeof v === "string" ? v : null;
}

function strings(v: JsonValue | undefined): string[] {
  return Array.isArray(v) ? v.filter((x): x is string => typeof x === "string") : [];
}

function seconds(v: number): string {
  return `${Number(v.toFixed(2))}s`;
}

/** {"subscriptions": {"added_fields": ["price_id"], "removed_fields": ["plan_code"]}} -> "subscriptions +price_id −plan_code". */
export function summarizeSchemaChanges(v: JsonValue | undefined): string | null {
  if (!isRecord(v)) return null;
  const parts = Object.entries(v).map(([entity, change]) => {
    if (!isRecord(change)) return entity;
    const marks = [
      ...strings(change.added_fields).map((f) => `+${f}`),
      ...strings(change.removed_fields).map((f) => `−${f}`),
      ...strings(change.changed_fields).map((f) => `~${f}`),
    ];
    return `${entity} ${marks.join(" ")}`.trim();
  });
  return parts.length ? parts.join("; ") : null;
}

/** {"added": ["price_id"], "removed": ["plan_code"], "changed": []} -> "+price_id −plan_code". */
export function summarizeMappingChanges(v: JsonValue | undefined): string | null {
  if (!isRecord(v)) return null;
  const marks = [
    ...strings(v.added).map((f) => `+${f}`),
    ...strings(v.removed).map((f) => `−${f}`),
    ...strings(v.changed).map((f) => `~${f}`),
  ];
  return marks.length ? marks.join(" ") : "fields unchanged";
}

function versions(v: JsonValue | undefined): string | null {
  if (!isRecord(v)) return null;
  const parts = Object.entries(v)
    .filter(([, x]) => typeof x === "number")
    .map(([entity, x]) => `${entity} v${String(x)}`);
  return parts.length ? parts.join(", ") : null;
}

function batchDetails(e: RunEvent, out: Detail[]): void {
  const d = e.data;
  const size = n(d.size);
  const written = n(d.written);
  if (written !== null && size !== null)
    out.push({ label: "written", value: `${written}/${size}`, tone: written === size ? "success" : "warning" });
  const extras: Array<[string, Tone]> = [
    ["replayed", "observe"],
    ["already_present", "observe"],
    ["quarantined", "warning"],
    ["contract_rejected", "danger"],
    ["held_for_revalidation", "warning"],
    ["retry", "warning"],
    ["failed", "danger"],
  ];
  for (const [key, tone] of extras) {
    const value = n(d[key]);
    if (value) out.push({ label: key.replaceAll("_", " "), value: String(value), tone });
  }
  const api = s(d.api_version);
  if (api) out.push({ label: "API", value: api });
}

export function eventDetails(e: RunEvent): Detail[] {
  const d = e.data;
  const out: Detail[] = [];
  const cls = s(d.failure_class);
  if (cls)
    out.push({
      label: "class",
      value: cls,
      tone: cls === "DATA" ? "warning" : e.kind === "recovery" ? "warning" : "danger",
    });
  const status = n(d.status);
  if (status !== null) out.push({ label: "HTTP", value: String(status), tone: "danger" });
  const attempt = n(d.attempt);
  if (attempt !== null) out.push({ label: "attempt", value: String(attempt) });
  const retryAfter = n(d.retry_after);
  if (retryAfter !== null) out.push({ label: "retry-after", value: seconds(retryAfter) });
  const delay = n(d.delay_s);
  if (delay !== null) out.push({ label: "backoff", value: seconds(delay) });
  const code = s(d.dominant_code);
  if (code) out.push({ label: "error code", value: code, tone: "danger" });
  const codes = strings(d.codes);
  if (codes.length) out.push({ label: "codes", value: codes.join(", "), tone: "danger" });
  if (e.kind === "batch") batchDetails(e, out);

  const from = d.version_from;
  const to = d.version_to;
  if ((typeof from === "number" || typeof from === "string") && (typeof to === "number" || typeof to === "string")) {
    const prefix = typeof from === "number" ? "v" : "";
    out.push({
      label: e.kind === "plan" ? "mapping" : "API",
      value: `${prefix}${from} → ${prefix}${to}`,
      tone: "plan",
    });
  }
  const mv = n(d.mapping_version);
  const checked = n(d.checked);
  const passed = n(d.passed);
  if (mv !== null)
    out.push({ label: "mapping", value: `v${mv}${s(d.target_api_version) ? ` on ${s(d.target_api_version)}` : ""}` });
  if (checked !== null && passed !== null)
    out.push({
      label: "samples valid",
      value: `${passed}/${checked}`,
      tone: passed === checked ? "success" : "danger",
    });

  const schema = summarizeSchemaChanges(d.schema_changes);
  if (schema) out.push({ label: "schema", value: schema, tone: "plan" });
  const changes = summarizeMappingChanges(d.changes);
  if (changes) out.push({ label: "fields", value: changes, tone: "plan" });
  const resumed = versions(d.mapping_versions);
  if (resumed) out.push({ label: "mappings", value: resumed, tone: "plan" });

  const found = n(d.found);
  const resend = n(d.resend);
  if (found !== null) out.push({ label: "found committed", value: String(found), tone: "success" });
  if (resend !== null) out.push({ label: "re-send", value: String(resend) });

  if (e.kind === "llm") {
    const calls = n(d.calls);
    const cost = n(d.cost_usd);
    if (calls !== null) out.push({ label: "LLM calls", value: String(calls) });
    if (cost !== null) out.push({ label: "cost", value: `$${cost.toFixed(4)}` });
  }
  const loaded = d.records_loaded;
  if (isRecord(loaded)) {
    out.push({
      label: "source records",
      value: Object.entries(loaded)
        .map(([k, v]) => `${k} ${String(v)}`)
        .join(", "),
    });
  }
  const api = e.kind === "batch" ? null : s(d.target_api_version);
  if (api && mv === null) out.push({ label: "target API", value: api });
  const tz = s(d.timezone);
  if (tz) out.push({ label: "timezone", value: tz });

  if (Array.isArray(d.items)) {
    const ids = d.items
      .map((item) => (isRecord(item) ? s(item.source_id) : null))
      .filter((x): x is string => x !== null);
    if (ids.length)
      out.push({
        label: "records",
        value: ids.slice(0, 4).join(", ") + (ids.length > 4 ? ` +${ids.length - 4}` : ""),
        tone: "warning",
      });
  }
  if (e.kind === "verify") {
    const claim = s(d.agent_claimed_status);
    if (claim)
      out.push({ label: "agent claimed", value: claim, tone: d.false_success_claim === true ? "danger" : "neutral" });
    const failed = strings(d.failed_checks);
    if (failed.length) out.push({ label: "failed checks", value: failed.join(", "), tone: "danger" });
    const hash = s(d.report_hash);
    if (hash) out.push({ label: "hash", value: hash.slice(0, 12) });
  }
  if (e.kind === "decision" && n(d.total) !== null) {
    out.push({ label: "total", value: String(n(d.total)) });
  }
  return out;
}

/** A batch that wrote everything on the first attempt: routine, collapsible. */
export function isCleanBatch(e: RunEvent): boolean {
  if (e.kind !== "batch") return false;
  const d = e.data;
  return d.written === d.size && (n(d.attempt) ?? 1) === 1 && !n(d.replayed) && !n(d.quarantined);
}
