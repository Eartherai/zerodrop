// Recorded runs bundled for mock mode (VITE_MOCK=1), which is what the public static site
// serves. The `real-*` files and `early-check-stop` were exported from run ledgers with
// scripts/export_recording.py (real engine, sandbox and verifier; `real-*` were planned by a
// Gemini model). The three older files are scripted-planner runs from Oct 10, kept as test
// fixtures; see docs/UI.md, "Mock mode".

import type { MappingVersion, ReconciliationReport, RunDetail, RunEvent, Scenario } from "../api/types";

export interface Recording {
  scenario: Scenario;
  fault_plan: unknown;
  summary: RunDetail & { created_at: number };
  events: RunEvent[];
  mappings: MappingVersion[];
  report: ReconciliationReport | null;
}

const files = import.meta.glob<Recording>("./recordings/*.json", { eager: true, import: "default" });

/** Display order: the full demo first. */
const ORDER = [
  "real-chaos",
  "real-false-success",
  "early-check-stop",
  "real-messy-data",
  "demo-v2-flip",
  "messy-data",
  "naive-planner",
];

export const RECORDINGS: readonly Recording[] = Object.values(files).sort(
  (a, b) => rank(a.scenario.id) - rank(b.scenario.id) || a.scenario.id.localeCompare(b.scenario.id),
);

function rank(id: string): number {
  const i = ORDER.indexOf(id);
  return i === -1 ? ORDER.length : i;
}
