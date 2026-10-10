import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { ConnectionState } from "../api/client";
import type { RunEvent } from "../api/types";
import { buildSchedule } from "../lib/schedule";
import { createMockApi } from "./mockApi";
import { RECORDINGS } from "./recordings";

const demo = RECORDINGS.find((r) => r.scenario.id === "demo-v2-flip")!;

describe("mock API", () => {
  let clock = 1_000_000;
  const now = () => clock;

  beforeEach(() => {
    vi.useFakeTimers();
    clock = 1_000_000;
  });
  afterEach(() => vi.useRealTimers());

  async function advance(ms: number) {
    clock += ms;
    await vi.advanceTimersByTimeAsync(ms);
  }

  it("lists scenarios and finished history runs", async () => {
    const api = createMockApi({ now, speed: 1 });
    expect(api.mode).toBe("mock");
    expect((await api.listScenarios()).map((s) => s.id)).toEqual(RECORDINGS.map((r) => r.scenario.id));
    const runs = await api.listRuns();
    expect(runs).toHaveLength(RECORDINGS.length);
    for (const run of runs) expect(["SUCCESS", "PARTIAL_SUCCESS", "FAILED"]).toContain(run.status);
    const detail = await api.getRun(demo.summary.run_id);
    expect(detail.counts).toEqual(demo.summary.counts);
    expect(detail.mapping_versions).toEqual(demo.summary.mapping_versions);
    expect(await api.getReport(demo.summary.run_id)).toEqual(demo.report);
  });

  it("streams a started run in order, gating report and mappings on the events", async () => {
    const api = createMockApi({ now, speed: 1 });
    const { run_id } = await api.startRun("demo-v2-flip");
    expect(run_id).toBe("run_mock001");
    const received: RunEvent[] = [];
    const states: ConnectionState[] = [];
    api.subscribeEvents(run_id, 0, { onEvent: (e) => received.push(e), onConnection: (s) => states.push(s) });

    await advance(1);
    expect(states).toContain("open");
    expect(received[0]?.run_id).toBe(run_id);
    expect(await api.getReport(run_id)).toBeNull();
    expect((await api.getRun(run_id)).status).not.toBe("SUCCESS");

    const schedule = buildSchedule(demo.events, 1);
    await advance(schedule.at(-1)! + 10);
    expect(received.map((e) => e.seq)).toEqual(demo.events.map((e) => e.seq));
    expect(states.at(-1)).toBe("closed");
    const detail = await api.getRun(run_id);
    expect(detail.status).toBe("SUCCESS");
    expect(detail.agent_claimed_status).toBe("SUCCESS");
    expect((await api.getReport(run_id))?.run_id).toBe(run_id);
    expect((await api.getMappings(run_id)).length).toBe(demo.mappings.length);
  });

  it("only exposes mapping versions announced so far", async () => {
    const api = createMockApi({ now, speed: 1 });
    const { run_id } = await api.startRun("demo-v2-flip");
    const schedule = buildSchedule(demo.events, 1);
    const planIndex = demo.events.findIndex((e) => e.kind === "plan");
    await advance(schedule[planIndex]!);
    const early = await api.getMappings(run_id);
    expect(early.every((m) => m.version === 1)).toBe(true);
    expect(early).toHaveLength(3);
  });

  it("resumes a stream after a given seq", async () => {
    const api = createMockApi({ now, speed: 1 });
    const received: number[] = [];
    api.subscribeEvents(demo.summary.run_id, 90, { onEvent: (e) => received.push(e.seq) });
    await advance(1);
    expect(received).toEqual(demo.events.filter((e) => e.seq > 90).map((e) => e.seq));
  });

  it("rejects unknown scenarios and runs", async () => {
    const api = createMockApi({ now });
    await expect(api.startRun("nope")).rejects.toMatchObject({ status: 404 });
    await expect(api.getRun("nope")).rejects.toMatchObject({ status: 404 });
    const states: ConnectionState[] = [];
    api.subscribeEvents("nope", 0, { onEvent: () => undefined, onConnection: (s) => states.push(s) });
    await advance(1);
    expect(states).toEqual(["closed"]);
  });

  it("stops delivering after close", async () => {
    const api = createMockApi({ now, speed: 1 });
    const { run_id } = await api.startRun("messy-data");
    const received: number[] = [];
    const sub = api.subscribeEvents(run_id, 0, { onEvent: (e) => received.push(e.seq) });
    await advance(1);
    const count = received.length;
    sub.close();
    await advance(60_000);
    expect(received.length).toBe(count);
  });
});
