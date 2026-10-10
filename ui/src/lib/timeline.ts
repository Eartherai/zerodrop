// Timeline rows: newest first, with routine batches folded together.

import type { RunEvent } from "../api/types";
import { isCleanBatch } from "./eventDetails";

export type TimelineRow =
  | { type: "event"; event: RunEvent }
  | { type: "group"; key: string; entity: string; events: RunEvent[]; written: number };

/** Newest first; consecutive clean batches of one entity fold into a single row. */
export function buildRows(events: readonly RunEvent[], fold: boolean): TimelineRow[] {
  const rows: TimelineRow[] = [];
  for (let i = events.length - 1; i >= 0; i--) {
    const event = events[i]!;
    const last = rows[rows.length - 1];
    if (fold && isCleanBatch(event)) {
      if (last?.type === "group" && last.entity === event.entity) {
        last.events.push(event);
        last.written += typeof event.data.written === "number" ? event.data.written : 0;
        continue;
      }
      rows.push({
        type: "group",
        key: "",
        entity: event.entity ?? "",
        events: [event],
        written: typeof event.data.written === "number" ? event.data.written : 0,
      });
      continue;
    }
    rows.push({ type: "event", event });
  }
  // A "group" of one is just an event; a group is keyed by its oldest event so it stays mounted as it grows.
  return rows.map((r) => {
    if (r.type !== "group") return r;
    if (r.events.length === 1) return { type: "event", event: r.events[0]! };
    return { ...r, key: `g${r.events[r.events.length - 1]!.seq}` };
  });
}
