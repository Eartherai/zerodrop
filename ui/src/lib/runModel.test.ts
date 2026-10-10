import { describe, expect, it } from "vitest";
import type { RunEvent } from "../api/types";
import { RECORDINGS, type Recording } from "../mock/recordings";
import {
  applyEvent,
  applyEvents,
  emptyRunModel,
  excludedRecords,
  expectedRecords,
  pendingRecords,
  stagesForEvent,
} from "./runModel";

function recording(id: string): Recording {
  const r = RECORDINGS.find((x) => x.scenario.id === id);
  if (!r) throw new Error(`missing recording ${id}`);
  return r;
}

function finalModel(id: string) {
  const r = recording(id);
  return { r, model: applyEvents(emptyRunModel(r.summary.run_id), r.events) };
}

function event(partial: Partial<RunEvent> & Pick<RunEvent, "seq" | "kind">): RunEvent {
  return { run_id: "run_x", ts: partial.seq, message: "", state: null, entity: null, data: {}, ...partial };
}

describe("runModel on the recorded demo run (v2 flip, 429 storm, crash and resume)", () => {
  const { r, model } = finalModel("demo-v2-flip");

  it("ends in the verifier's status with matching claim", () => {
    expect(model.status).toBe("SUCCESS");
    expect(model.verification).toBe("success");
    expect(model.verify?.status).toBe("SUCCESS");
    expect(model.agentClaim).toBe("SUCCESS");
    expect(model.verify?.reportHash).toBe(r.report?.report_hash);
  });

  it("derives per-entity counts equal to the ledger summary", () => {
    for (const [entity, counts] of Object.entries(r.summary.counts)) {
      const p = model.entities[entity as keyof typeof model.entities];
      expect(p.written).toBe(counts.written);
      expect(p.quarantined).toBe(counts.quarantined);
      expect(p.total).toBe(counts.total);
      expect(pendingRecords(p)).toBe(0);
    }
  });

  it("knows soft-deleted customers were excluded and replays were idempotent", () => {
    expect(excludedRecords(model.entities.customers)).toBe(8);
    expect(model.entities.invoices.replayed).toBe(50);
    expect(model.resumes).toBe(1);
  });

  it("tracks mapping versions and the target API change", () => {
    expect(model.mappingVersions).toEqual(r.summary.mapping_versions);
    expect(model.apiVersionHistory).toEqual(["v1", "v2"]);
    expect(model.targetApiVersion).toBe("v2");
  });

  it("lights every pipeline stage and classifies failures and recoveries", () => {
    for (const stage of Object.values(model.stages)) expect(stage.hits).toBeGreaterThan(0);
    expect(model.stages.failure.tags.TRANSIENT).toBeGreaterThan(0);
    expect(model.stages.failure.tags.CONTRACT).toBeGreaterThan(0);
    expect(model.stages.failure.tags.AMBIGUOUS_WRITE).toBe(1);
    expect(model.stages.recovery.tags.backoff).toBeGreaterThan(0);
    expect(model.stages.recovery.tags.lookup).toBe(1);
    expect(model.stages.recovery.tags["new mapping"]).toBe(2);
    expect(model.stages.recovery.tags.resume).toBe(1);
  });

  it("reads the goal from the first event", () => {
    expect(model.goal).toBe(r.summary.goal);
    expect(model.scenario).toBe("demo-v2-flip");
  });
});

describe("runModel on the other recordings", () => {
  it("catches the false-success claim of the naive planner", () => {
    const { model } = finalModel("naive-planner");
    expect(model.status).toBe("FAILED");
    expect(model.agentClaim).toBe("SUCCESS");
    expect(model.verify?.falseSuccess).toBe(true);
    expect(model.verify?.failedChecks).toContain("money_by_currency");
    expect(model.verification).toBe("failed");
    expect(model.mappingVersions.customers).toBe(2);
  });

  it("counts quarantined records of the messy-data run", () => {
    const { r, model } = finalModel("messy-data");
    expect(model.status).toBe("PARTIAL_SUCCESS");
    expect(model.verification).toBe("partial");
    expect(model.entities.customers.quarantined).toBe(r.summary.counts.customers?.quarantined);
    expect(model.entities.invoices.quarantined).toBe(r.summary.counts.invoices?.quarantined);
    expect(model.stages.recovery.tags.quarantine).toBe(3);
  });
});

describe("runModel reducer mechanics", () => {
  it("ignores duplicate and stale events (SSE reconnects)", () => {
    const first = event({ seq: 1, kind: "state", state: "CREATED", message: "run created: Move it" });
    const m1 = applyEvent(emptyRunModel(), first);
    expect(applyEvent(m1, first)).toBe(m1);
    expect(applyEvent(m1, { ...first, seq: 0 })).toBe(m1);
    expect(m1.goal).toBe("Move it");
    expect(m1.runId).toBe("run_x");
  });

  it("ignores events of another run", () => {
    const m = emptyRunModel("run_a");
    expect(applyEvent(m, event({ seq: 1, kind: "info" }))).toBe(m);
  });

  it("estimates pending work before an entity completes", () => {
    let m = applyEvent(emptyRunModel(), event({ seq: 1, kind: "info", data: { records_loaded: { invoices: 120 } } }));
    m = applyEvent(m, event({ seq: 2, kind: "batch", entity: "invoices", data: { written: 30, size: 50, retry: 20 } }));
    m = applyEvent(
      m,
      event({
        seq: 3,
        kind: "decision",
        entity: "invoices",
        message: "quarantined 2 invoices record(s) (mapping); continuing",
        data: { failure_class: "DATA", items: [] },
      }),
    );
    const p = m.entities.invoices;
    expect(expectedRecords(p)).toBe(120);
    expect(pendingRecords(p)).toBe(88);
    expect(p.quarantined).toBe(2);
  });

  it("maps events to pipeline stages", () => {
    expect(stagesForEvent(event({ seq: 1, kind: "batch" }))).toEqual(["observation", "action"]);
    expect(stagesForEvent(event({ seq: 1, kind: "failure" }))).toEqual(["failure"]);
    expect(stagesForEvent(event({ seq: 1, kind: "plan", state: "RECOVERING" }))).toEqual(["recovery", "plan"]);
    expect(stagesForEvent(event({ seq: 1, kind: "state", state: "VERIFYING" }))).toEqual(["verification"]);
    expect(stagesForEvent(event({ seq: 1, kind: "decision", data: { failure_class: "BUDGET" } }))).toEqual(["failure"]);
    expect(stagesForEvent(event({ seq: 1, kind: "info", message: "resuming run from EXECUTING" }))).toEqual([
      "recovery",
    ]);
  });

  it("marks a halted run without a verifier report as failed", () => {
    const m = applyEvents(emptyRunModel(), [
      event({ seq: 1, kind: "failure", data: { failure_class: "BUDGET" } }),
      event({ seq: 2, kind: "state", state: "FAILED" }),
    ]);
    expect(m.verification).toBe("failed");
    expect(m.verify).toBeNull();
  });
});
