import { describe, expect, it } from "vitest";
import type { RunEvent } from "../api/types";
import { RECORDINGS } from "../mock/recordings";
import { eventDetails, isCleanBatch, summarizeMappingChanges, summarizeSchemaChanges } from "./eventDetails";
import { buildRows } from "./timeline";

const demo = RECORDINGS.find((r) => r.scenario.id === "demo-v2-flip")!.events;

function find(predicate: (e: RunEvent) => boolean): RunEvent {
  const e = demo.find(predicate);
  if (!e) throw new Error("event not found");
  return e;
}

function detail(e: RunEvent, label: string): string | undefined {
  return eventDetails(e).find((d) => d.label === label)?.value;
}

describe("eventDetails", () => {
  it("shows attempt, HTTP status and retry-after for a 429", () => {
    const e = find((x) => x.kind === "failure" && x.data.status === 429);
    expect(detail(e, "HTTP")).toBe("429");
    expect(detail(e, "attempt")).toBe("1");
    expect(detail(e, "class")).toBe("TRANSIENT");
    const backoff = find((x) => x.kind === "recovery" && x.data.retry_after === 0.4);
    expect(detail(backoff, "retry-after")).toBe("0.4s");
  });

  it("shows the mapping version bump and field changes", () => {
    const e = find((x) => x.kind === "plan" && x.entity === "subscriptions" && x.data.version_to === 2);
    expect(detail(e, "mapping")).toBe("v1 → v2");
    expect(detail(e, "fields")).toBe("+price_id −plan_code");
  });

  it("shows the API version change and error code of the contract failure", () => {
    expect(
      detail(
        find((x) => x.kind === "failure" && x.data.version_to === "v2"),
        "API",
      ),
    ).toBe("v1 → v2");
    expect(
      detail(
        find((x) => x.kind === "failure" && x.data.dominant_code === "unknown_field"),
        "error code",
      ),
    ).toBe("unknown_field");
  });

  it("shows idempotent replays after the resume", () => {
    expect(
      detail(
        find((x) => x.kind === "batch" && x.data.replayed === 50),
        "replayed",
      ),
    ).toBe("50");
  });

  it("summarizes schema and mapping changes", () => {
    expect(
      summarizeSchemaChanges({
        subscriptions: { added_fields: ["price_id"], removed_fields: ["plan_code"], changed_fields: [] },
      }),
    ).toBe("subscriptions +price_id −plan_code");
    expect(summarizeMappingChanges({ added: [], removed: [], changed: [] })).toBe("fields unchanged");
  });
});

describe("timeline rows", () => {
  it("are newest first and fold consecutive clean batches", () => {
    const rows = buildRows(demo, true);
    const first = rows[0];
    expect(first?.type === "event" && first.event.seq).toBe(demo.at(-1)!.seq);
    const groups = rows.filter((r) => r.type === "group");
    expect(groups.length).toBeGreaterThan(0);
    const folded = groups.reduce((n, g) => n + (g.type === "group" ? g.events.length : 0), 0);
    expect(rows.length + folded - groups.length).toBe(demo.length);
    expect(buildRows(demo, false)).toHaveLength(demo.length);
  });

  it("never fold a batch that needed a retry or replayed records", () => {
    expect(isCleanBatch(find((x) => x.kind === "batch" && x.data.attempt === 3))).toBe(false);
    expect(isCleanBatch(find((x) => x.kind === "batch" && x.data.replayed === 50))).toBe(false);
    expect(isCleanBatch(find((x) => x.kind === "batch" && x.data.written !== x.data.size))).toBe(false);
  });
});
