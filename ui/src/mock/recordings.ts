// Recorded runs bundled for mock mode (VITE_MOCK=1). Each JSON file was produced
// by the real engine + sandbox + verifier with the deterministic FakePlanner
// (no LLM calls); see docs/UI.md, "Mock mode".

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
const ORDER = ["demo-v2-flip", "messy-data", "naive-planner"];

export const RECORDINGS: readonly Recording[] = Object.values(files).sort(
  (a, b) => rank(a.scenario.id) - rank(b.scenario.id) || a.scenario.id.localeCompare(b.scenario.id),
);

function rank(id: string): number {
  const i = ORDER.indexOf(id);
  return i === -1 ? ORDER.length : i;
}
