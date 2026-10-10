import { describe, expect, it } from "vitest";
import type { FieldMapping, MappingSpec } from "../api/types";
import { RECORDINGS } from "../mock/recordings";
import { diffMappings, formatOp, versionsFor } from "./mappingDiff";

function specs(scenario: string, entity: string): MappingSpec[] {
  const r = RECORDINGS.find((x) => x.scenario.id === scenario);
  if (!r) throw new Error(scenario);
  return versionsFor(r.mappings, entity).map((m) => m.spec);
}

function field(target: string, source: string | null, ops: FieldMapping["ops"] = []): FieldMapping {
  return { target, source, ops, required: true };
}

function spec(fields: FieldMapping[], version = 1, api = "v1"): MappingSpec {
  return { entity: "subscriptions", version, target_api_version: api, fields, exclude_if: [], rationale: "" };
}

describe("diffMappings", () => {
  it("shows the v2 schema change as plan_code replaced by price_id", () => {
    const [v1, v2] = specs("demo-v2-flip", "subscriptions");
    const diff = diffMappings(v1!, v2!);
    const replaced = diff.rows.filter((r) => r.change === "replaced");
    expect(replaced).toHaveLength(1);
    expect(replaced[0]?.left?.target).toBe("plan_code");
    expect(replaced[0]?.right?.target).toBe("price_id");
    expect(formatOp(replaced[0]!.right!.ops[0]!)).toBe("lookup(prices.lookup_key → id)");
    expect(diff.meta.find((m) => m.label === "Target API")).toMatchObject({ left: "v1", right: "v2", changed: true });
  });

  it("flags an op-level change and the op index that changed", () => {
    const [v1, v2] = specs("naive-planner", "customers");
    const diff = diffMappings(v1!, v2!);
    const email = diff.rows.find((r) => r.key === "email");
    expect(email?.change).toBe("changed");
    expect(email?.parts).toEqual(["ops"]);
    expect(email?.rightOps).toEqual([1]);
    expect(diff.counts.changed).toBe(1);
  });

  it("reports a re-targeted mapping with identical fields", () => {
    const [v1, v2] = specs("demo-v2-flip", "invoices");
    const diff = diffMappings(v1!, v2!);
    expect(diff.counts.same).toBe(diff.rows.length);
    expect(diff.meta.find((m) => m.label === "Target API")?.changed).toBe(true);
  });

  it("keeps unmatched fields as additions and removals in order", () => {
    const a = spec([field("a", "x"), field("b", "y"), field("c", "z")]);
    const b = spec([field("a", "x"), field("c", "z"), field("d", "w"), field("e", "v")], 2);
    const diff = diffMappings(a, b);
    expect(diff.rows.map((r) => [r.change, r.key])).toEqual([
      ["same", "a"],
      ["removed", "b"],
      ["same", "c"],
      ["added", "d"],
      ["added", "e"],
    ]);
  });

  it("ignores null-vs-missing op parameters and key order", () => {
    const a = spec([field("s", "state", [{ op: "lower", part: null }])]);
    const b = spec([field("s", "state", [{ op: "lower" }])], 2);
    expect(diffMappings(a, b).rows[0]?.change).toBe("same");
  });
});

describe("formatOp", () => {
  it("renders the DSL compactly", () => {
    expect(formatOp({ op: "parse_datetime", formats: ["%m/%d/%Y"], assume_tz: "Asia/Kolkata" })).toBe(
      "parse_datetime(%m/%d/%Y, tz=Asia/Kolkata)",
    );
    expect(formatOp({ op: "decimal_to_minor", currency_field: "currency" })).toBe("decimal_to_minor(by currency)");
    expect(formatOp({ op: "decimal_to_minor", decimals: 2 })).toBe("decimal_to_minor(2 dp)");
    expect(formatOp({ op: "enum_map", mapping: [{ source: "Y", target: "paid" }], default: "open" })).toBe(
      "enum_map(Y→paid; default open)",
    );
    expect(formatOp({ op: "ref", entity: "customers" })).toBe("ref(customers)");
    expect(formatOp({ op: "const", value: 1 })).toBe("const(1)");
    expect(formatOp({ op: "lower" })).toBe("lower");
  });
});
