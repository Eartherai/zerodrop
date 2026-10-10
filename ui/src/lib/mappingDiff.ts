// Field-level diff of two MappingSpec versions for the side-by-side panel.

import type { Condition, FieldMapping, MappingSpec, TransformOp } from "../api/types";

export type RowChange = "same" | "changed" | "added" | "removed" | "replaced";

export interface DiffRow {
  key: string;
  change: RowChange;
  left: FieldMapping | null;
  right: FieldMapping | null;
  /** For "changed": which parts differ ("source", "ops", "required"). */
  parts: string[];
  /** For "changed": indexes of ops that differ on each side. */
  leftOps: number[];
  rightOps: number[];
}

export interface MetaRow {
  label: string;
  left: string;
  right: string;
  changed: boolean;
}

export interface SpecDiff {
  rows: DiffRow[];
  meta: MetaRow[];
  counts: Record<RowChange, number>;
}

function stable(value: unknown): string {
  // Key order and null-vs-missing parameters must not create spurious diffs.
  if (Array.isArray(value)) return `[${value.map(stable).join(",")}]`;
  if (value && typeof value === "object") {
    const entries = Object.entries(value as Record<string, unknown>)
      .filter(([, v]) => v !== null && v !== undefined)
      .sort(([a], [b]) => a.localeCompare(b));
    return `{${entries.map(([k, v]) => `${JSON.stringify(k)}:${stable(v)}`).join(",")}}`;
  }
  return JSON.stringify(value ?? null);
}

export function sameOp(a: TransformOp | undefined, b: TransformOp | undefined): boolean {
  return stable(a) === stable(b);
}

function changedOpIndexes(a: TransformOp[], b: TransformOp[]): [number[], number[]] {
  const left: number[] = [];
  const right: number[] = [];
  const n = Math.max(a.length, b.length);
  for (let i = 0; i < n; i++) {
    if (sameOp(a[i], b[i])) continue;
    if (i < a.length) left.push(i);
    if (i < b.length) right.push(i);
  }
  return [left, right];
}

function compareFields(left: FieldMapping, right: FieldMapping): DiffRow {
  const parts: string[] = [];
  if ((left.source ?? null) !== (right.source ?? null)) parts.push("source");
  if (stable(left.ops) !== stable(right.ops)) parts.push("ops");
  if (left.required !== right.required) parts.push("required");
  const [leftOps, rightOps] = changedOpIndexes(left.ops, right.ops);
  return { key: left.target, change: parts.length ? "changed" : "same", left, right, parts, leftOps, rightOps };
}

/** Longest common subsequence of target names, as index pairs. */
function lcsPairs(a: string[], b: string[]): Array<[number, number]> {
  const dp: number[][] = Array.from({ length: a.length + 1 }, () => new Array<number>(b.length + 1).fill(0));
  for (let i = a.length - 1; i >= 0; i--) {
    for (let j = b.length - 1; j >= 0; j--) {
      dp[i]![j] = a[i] === b[j] ? dp[i + 1]![j + 1]! + 1 : Math.max(dp[i + 1]![j]!, dp[i]![j + 1]!);
    }
  }
  const pairs: Array<[number, number]> = [];
  let i = 0;
  let j = 0;
  while (i < a.length && j < b.length) {
    if (a[i] === b[j]) {
      pairs.push([i, j]);
      i++;
      j++;
    } else if (dp[i + 1]![j]! >= dp[i]![j + 1]!) i++;
    else j++;
  }
  return pairs;
}

function gapRows(removed: FieldMapping[], added: FieldMapping[]): DiffRow[] {
  // Pair removals with additions in the same gap: plan_code -> price_id reads as one replacement.
  const rows: DiffRow[] = [];
  const n = Math.max(removed.length, added.length);
  for (let k = 0; k < n; k++) {
    const left = removed[k] ?? null;
    const right = added[k] ?? null;
    const change: RowChange = left && right ? "replaced" : left ? "removed" : "added";
    const key = left && right ? `${left.target}->${right.target}` : (left ?? right)!.target;
    rows.push({ key, change, left, right, parts: [], leftOps: [], rightOps: [] });
  }
  return rows;
}

export function formatCondition(c: Condition): string {
  return `${c.field} = ${JSON.stringify(c.equals)}`;
}

export function diffMappings(left: MappingSpec, right: MappingSpec): SpecDiff {
  const a = left.fields;
  const b = right.fields;
  const pairs = lcsPairs(
    a.map((f) => f.target),
    b.map((f) => f.target),
  );
  const rows: DiffRow[] = [];
  let i = 0;
  let j = 0;
  for (const [pi, pj] of [...pairs, [a.length, b.length] as [number, number]]) {
    rows.push(...gapRows(a.slice(i, pi), b.slice(j, pj)));
    if (pi < a.length && pj < b.length) rows.push(compareFields(a[pi]!, b[pj]!));
    i = pi + 1;
    j = pj + 1;
  }
  const exclusions = (s: MappingSpec) => (s.exclude_if.length ? s.exclude_if.map(formatCondition).join("; ") : "none");
  const meta: MetaRow[] = [
    {
      label: "Mapping version",
      left: `v${left.version}`,
      right: `v${right.version}`,
      changed: left.version !== right.version,
    },
    {
      label: "Target API",
      left: left.target_api_version,
      right: right.target_api_version,
      changed: left.target_api_version !== right.target_api_version,
    },
    {
      label: "Exclude if",
      left: exclusions(left),
      right: exclusions(right),
      changed: exclusions(left) !== exclusions(right),
    },
  ];
  const counts: Record<RowChange, number> = { same: 0, changed: 0, added: 0, removed: 0, replaced: 0 };
  for (const row of rows) counts[row.change] += 1;
  return { rows, meta, counts };
}

// ---------------------------------------------------------------------------
// Compact op rendering
// ---------------------------------------------------------------------------

function list(values: readonly string[] | null | undefined): string {
  return (values ?? []).join(", ");
}

export function formatOp(op: TransformOp): string {
  switch (op.op) {
    case "split_name":
      return `split_name(${op.part ?? "first"})`;
    case "parse_datetime": {
      const args = [list(op.formats)];
      if (op.assume_tz) args.push(`tz=${op.assume_tz}`);
      return `parse_datetime(${args.filter(Boolean).join(", ")})`;
    }
    case "decimal_to_minor":
      if (op.currency_field) return `decimal_to_minor(by ${op.currency_field})`;
      return `decimal_to_minor(${op.decimals ?? 2} dp)`;
    case "enum_map": {
      const pairs = (op.mapping ?? []).map((p) => `${p.source}→${p.target}`).join(", ");
      return `enum_map(${pairs}${op.default ? `; default ${op.default}` : ""})`;
    }
    case "ref":
      return `ref(${op.entity ?? "?"})`;
    case "lookup":
      return `lookup(${op.table ?? "?"}.${op.match_field ?? "?"} → ${op.return_field ?? "?"})`;
    case "bool_map":
      return `bool_map(${list(op.true_values)})`;
    case "const":
      return `const(${JSON.stringify(op.value ?? null)})`;
    default:
      return op.op;
  }
}

/** Mapping versions available for an entity, oldest first. */
export function versionsFor<T extends { entity: string; version: number }>(rows: readonly T[], entity: string): T[] {
  return rows.filter((r) => r.entity === entity).sort((x, y) => x.version - y.version);
}
