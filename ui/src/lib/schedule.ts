// Pacing for replays and the mock stream: a recorded run finishes in seconds,
// so each event gets a minimum on-screen dwell (longer for the moments a viewer
// must notice: failures, recoveries, new mappings, the verdict).

import type { EventKind, RunEvent } from "../api/types";

export const DWELL_MS: Record<EventKind, number> = {
  state: 450,
  info: 700,
  plan: 1500,
  llm: 300,
  batch: 240,
  failure: 1200,
  recovery: 1200,
  decision: 500,
  verify: 1800,
};

/** Longest pause kept from the original recording (e.g. a client timeout). */
export const MAX_GAP_MS = 2500;
const RESUME_DWELL_MS = 2200;

export const SPEEDS = [0.5, 1, 2, 4] as const;

export function dwellFor(event: RunEvent): number {
  if (event.kind === "info" && event.message.startsWith("resuming")) return RESUME_DWELL_MS;
  if (event.kind === "batch" && event.data.written !== event.data.size) return DWELL_MS.failure;
  return DWELL_MS[event.kind];
}

/**
 * Offsets (ms from replay start) at which each event is released. Event i stays
 * "newest" for max(its dwell, the real gap to event i+1 capped at MAX_GAP_MS).
 */
export function buildSchedule(events: readonly RunEvent[], speed = 1): number[] {
  const factor = speed > 0 ? speed : 1;
  const offsets: number[] = [];
  let t = 0;
  events.forEach((event, i) => {
    offsets.push(Math.round(t));
    const next = events[i + 1];
    if (!next) return;
    const realGap = Math.max(0, (next.ts - event.ts) * 1000);
    t += Math.max(dwellFor(event), Math.min(realGap, MAX_GAP_MS)) / factor;
  });
  return offsets;
}

export function parseSpeed(value: string | null | undefined, fallback = 1): number {
  const n = Number(value);
  return Number.isFinite(n) && n > 0 && n <= 16 ? n : fallback;
}
