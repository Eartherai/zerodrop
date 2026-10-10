// The bundled recordings must stay contract-accurate (src/zerodrop/models.py):
// every event parses as a RunEvent, seqs are contiguous, and the summary,
// mappings and report agree with the stream.

import { describe, expect, it } from "vitest";
import { toRunEvent } from "../api/parse";
import { ENTITIES, RUN_STATUSES } from "../api/types";
import { RECORDINGS } from "./recordings";

const MAPPING_KEYS = ["entity", "version", "target_api_version", "fields", "exclude_if", "rationale"].sort();
const REPORT_KEYS = [
  "run_id",
  "status",
  "checks",
  "quarantined",
  "source_counts",
  "target_counts",
  "money_source_minor",
  "money_target_minor",
  "report_hash",
].sort();

describe.each(RECORDINGS.map((r) => [r.scenario.id, r] as const))("recording %s", (_id, r) => {
  it("has valid, contiguous RunEvents for one run", () => {
    expect(r.events.length).toBeGreaterThan(10);
    r.events.forEach((raw, i) => {
      const parsed = toRunEvent(raw);
      expect(parsed, `event ${i}`).not.toBeNull();
      expect(Object.keys(raw).sort()).toEqual(["data", "entity", "kind", "message", "run_id", "seq", "state", "ts"]);
      expect(raw.seq).toBe(i + 1);
      expect(raw.run_id).toBe(r.summary.run_id);
      if (i > 0) expect(raw.ts).toBeGreaterThanOrEqual(r.events[i - 1]!.ts);
    });
  });

  it("starts at CREATED and ends in the summary status", () => {
    expect(r.events[0]?.state).toBe("CREATED");
    const last = r.events.at(-1)!;
    expect(last.kind).toBe("state");
    expect(last.state).toBe(r.summary.status);
    expect(RUN_STATUSES).toContain(r.summary.status);
  });

  it("has a summary in the GET /api/runs/{id} shape", () => {
    expect(Object.keys(r.summary.counts).sort()).toEqual([...ENTITIES].sort());
    for (const c of Object.values(r.summary.counts))
      expect(Object.keys(c).sort()).toEqual(["pending", "quarantined", "total", "written"]);
    expect(typeof r.summary.llm.calls).toBe("number");
    expect(typeof r.summary.llm.cost_usd).toBe("number");
  });

  it("has mapping rows in the GET /api/runs/{id}/mappings shape", () => {
    for (const m of r.mappings) {
      expect(m.spec.entity).toBe(m.entity);
      expect(m.spec.version).toBe(m.version);
      expect(Object.keys(m.spec).sort()).toEqual(MAPPING_KEYS);
    }
    for (const e of ENTITIES) expect(r.mappings.some((m) => m.entity === e && m.version === 1)).toBe(true);
  });

  it("has a ReconciliationReport matching the verify event", () => {
    const report = r.report!;
    expect(Object.keys(report).sort()).toEqual(REPORT_KEYS);
    expect(report.status).toBe(r.summary.status);
    const verify = r.events.find((e) => e.kind === "verify")!;
    expect(verify.data.report_hash).toBe(report.report_hash);
    expect(verify.data.status).toBe(report.status);
  });
});
