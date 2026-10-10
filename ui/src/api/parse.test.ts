import { describe, expect, it } from "vitest";
import { eventsUrl } from "./http";
import { parseEventData, toRunEvent } from "./parse";

const valid = {
  run_id: "run_1",
  seq: 3,
  ts: 1791630958.67,
  kind: "batch",
  message: "customers batch (attempt 1): 50/50 written",
  state: "EXECUTING",
  entity: "customers",
  data: { written: 50, size: 50 },
};

describe("RunEvent parsing", () => {
  it("accepts a contract-shaped event", () => {
    expect(parseEventData(JSON.stringify(valid))).toEqual(valid);
  });

  it("defaults optional fields", () => {
    const { state: _s, entity: _e, data: _d, ...bare } = valid;
    expect(toRunEvent(bare)).toMatchObject({ state: null, entity: null, data: {} });
  });

  it("rejects malformed or drifted events", () => {
    expect(parseEventData("not json")).toBeNull();
    expect(toRunEvent({ ...valid, kind: "unknown" })).toBeNull();
    expect(toRunEvent({ ...valid, state: "DONE" })).toBeNull();
    expect(toRunEvent({ ...valid, entity: "payments" })).toBeNull();
    expect(toRunEvent({ ...valid, seq: "3" })).toBeNull();
    expect(toRunEvent([valid])).toBeNull();
  });
});

describe("eventsUrl", () => {
  it("encodes the run id and clamps after_seq", () => {
    expect(eventsUrl("", "run 1", 12)).toBe("/api/runs/run%201/events?after_seq=12");
    expect(eventsUrl("http://h", "r", -5)).toBe("http://h/api/runs/r/events?after_seq=0");
  });
});
