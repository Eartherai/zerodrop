import { describe, expect, it } from "vitest";
import { RECORDINGS } from "../mock/recordings";
import { buildSchedule, DWELL_MS, MAX_GAP_MS, parseSpeed } from "./schedule";

describe("buildSchedule", () => {
  const demo = RECORDINGS.find((r) => r.scenario.id === "demo-v2-flip")!.events;

  it("starts at zero and never goes backwards", () => {
    const offsets = buildSchedule(demo);
    expect(offsets[0]).toBe(0);
    for (let i = 1; i < offsets.length; i++) expect(offsets[i]!).toBeGreaterThanOrEqual(offsets[i - 1]!);
  });

  it("paces the demo run to a watchable length", () => {
    const total = buildSchedule(demo).at(-1)!;
    expect(total).toBeGreaterThan(30_000);
    expect(total).toBeLessThan(90_000);
  });

  it("gives failures more dwell than routine batches and caps long gaps", () => {
    expect(DWELL_MS.failure).toBeGreaterThan(DWELL_MS.batch);
    const events = [0, 100].map((ts, i) => ({ ...demo[0]!, seq: i + 1, ts, kind: "info" as const, message: "x" }));
    expect(buildSchedule(events)[1]).toBe(MAX_GAP_MS);
  });

  it("scales with speed", () => {
    const one = buildSchedule(demo, 1).at(-1)!;
    const four = buildSchedule(demo, 4).at(-1)!;
    expect(Math.abs(four - one / 4)).toBeLessThan(demo.length);
  });
});

describe("parseSpeed", () => {
  it("accepts sane positive numbers only", () => {
    expect(parseSpeed("2")).toBe(2);
    expect(parseSpeed("0")).toBe(1);
    expect(parseSpeed("abc")).toBe(1);
    expect(parseSpeed(null, 0.5)).toBe(0.5);
    expect(parseSpeed("100")).toBe(1);
  });
});
