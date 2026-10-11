import { useEffect, useMemo, useRef, useState } from "react";
import { ENTITIES, type Entity, type FieldMapping, type MappingVersion } from "../api/types";
import { diffMappings, formatOp, versionsFor, type DiffRow, type RowChange } from "../lib/mappingDiff";
import type { RunModel } from "../lib/runModel";
import { TONES, type Tone } from "../lib/tones";
import { EmptyNote, Panel, Pill } from "./ui";

const CHANGE_TONE: Record<RowChange, Tone | null> = {
  same: null,
  changed: "warning",
  added: "success",
  removed: "danger",
  replaced: "plan",
};

const CHANGE_LABEL: Record<RowChange, string> = {
  same: "unchanged",
  changed: "changed",
  added: "added",
  removed: "removed",
  replaced: "replaced",
};

function FieldCell({
  field,
  highlightOps,
  side,
  change,
}: {
  field: FieldMapping | null;
  highlightOps: number[];
  side: "left" | "right";
  change: RowChange;
}) {
  if (!field) return <td className="px-3 py-2 align-top text-sm text-muted italic">—</td>;
  const removedSide = side === "left" && (change === "removed" || change === "replaced");
  const addedSide = side === "right" && (change === "added" || change === "replaced");
  const bg = removedSide
    ? TONES.danger.soft
    : addedSide
      ? TONES.success.soft
      : change === "changed"
        ? TONES.warning.soft
        : "";
  return (
    <td className={`px-3 py-2 align-top ${bg}`}>
      <div
        className={`font-mono text-[0.8rem] leading-snug ${removedSide ? "line-through decoration-2 opacity-90" : ""}`}
      >
        <span className={`font-bold ${removedSide ? TONES.danger.text : addedSide ? TONES.success.text : "text-fg"}`}>
          {field.target}
        </span>
        <span className="text-muted"> ← </span>
        <span className="text-fg">{field.source ?? "∅"}</span>
        {!field.required ? <span className="ml-1 text-muted">(optional)</span> : null}
      </div>
      {field.ops.length ? (
        <ol className="mt-1 flex flex-wrap items-center gap-1">
          {field.ops.map((op, i) => (
            <li
              key={i}
              className={`rounded px-1.5 py-px font-mono text-[0.72rem] ${
                highlightOps.includes(i) ? `${TONES.warning.solid} font-bold` : "bg-surface-2 text-fg ring-1 ring-line"
              }`}
            >
              {formatOp(op)}
            </li>
          ))}
        </ol>
      ) : null}
    </td>
  );
}

function DiffTableRow({ row }: { row: DiffRow }) {
  const tone = CHANGE_TONE[row.change];
  return (
    <tr className="border-t border-line">
      <th scope="row" className="w-28 px-3 py-2 text-left align-top">
        {tone ? (
          <Pill tone={tone}>{CHANGE_LABEL[row.change]}</Pill>
        ) : (
          <span className="text-xs text-muted">{CHANGE_LABEL[row.change]}</span>
        )}
        {row.parts.length ? <div className="mt-1 text-[0.7rem] text-muted">{row.parts.join(", ")}</div> : null}
      </th>
      <FieldCell field={row.left} highlightOps={row.leftOps} side="left" change={row.change} />
      <FieldCell field={row.right} highlightOps={row.rightOps} side="right" change={row.change} />
    </tr>
  );
}

function hasFieldChanges(changes: unknown): boolean {
  if (!changes || typeof changes !== "object") return false;
  return ["added", "removed", "changed"].some((k) => {
    const list = (changes as Record<string, unknown>)[k];
    return Array.isArray(list) && list.length > 0;
  });
}

/**
 * Entity whose mapping changed most recently, so a fresh repair is shown at once.
 * A version bump that changed fields wins over one that only re-targeted the API.
 */
export function latestChangedEntity(model: Pick<RunModel, "events">): Entity | null {
  let fallback: Entity | null = null;
  for (let i = model.events.length - 1; i >= 0; i--) {
    const e = model.events[i]!;
    if (e.kind !== "plan" || !e.entity || typeof e.data.version_to !== "number") continue;
    if (hasFieldChanges(e.data.changes)) return e.entity;
    fallback ??= e.entity;
  }
  return fallback;
}

export function MappingDiff({ mappings, model }: { mappings: readonly MappingVersion[]; model: RunModel }) {
  // Only show versions the stream has announced (keeps replays honest).
  const known = useMemo(
    () => mappings.filter((m) => m.version <= (model.mappingVersions[m.entity] ?? 0)),
    [mappings, model.mappingVersions],
  );
  const autoEntity = latestChangedEntity(model);
  const [entity, setEntity] = useState<Entity>("customers");
  const [pairIndex, setPairIndex] = useState<number | null>(null);
  const followed = useRef<Entity | null>(null);

  useEffect(() => {
    // Follow the agent: jump to the entity that was just repaired.
    if (autoEntity && autoEntity !== followed.current) {
      followed.current = autoEntity;
      setEntity(autoEntity);
      setPairIndex(null);
    }
  }, [autoEntity]);

  const versions = versionsFor(known, entity);
  const pairs = versions.slice(1).map((right, i) => [versions[i]!, right] as const);
  const index = pairIndex === null || pairIndex >= pairs.length ? pairs.length - 1 : pairIndex;
  const pair = index >= 0 ? pairs[index] : undefined;
  const diff = useMemo(() => (pair ? diffMappings(pair[0].spec, pair[1].spec) : null), [pair]);
  const single = !pair && versions.length ? versions[versions.length - 1] : undefined;

  const tabs = (
    <div role="tablist" aria-label="Entity" className="flex rounded-lg bg-surface-2 p-0.5 ring-1 ring-line">
      {ENTITIES.map((e) => {
        const count = versionsFor(known, e).length;
        const selected = e === entity;
        return (
          <button
            key={e}
            role="tab"
            type="button"
            aria-selected={selected}
            onClick={() => {
              setEntity(e);
              setPairIndex(null);
            }}
            className={`rounded-md px-2.5 py-1 text-xs font-semibold transition-colors ${selected ? "bg-surface text-fg shadow-sm ring-1 ring-line" : "text-muted hover:text-fg"}`}
          >
            {e}
            {count > 1 ? <span className={`ml-1 ${TONES.plan.text}`}>v{count}</span> : null}
          </button>
        );
      })}
    </div>
  );

  return (
    <Panel
      id="mapping"
      title="Mapping diff"
      subtitle="How the agent rewrote its mapping after the target schema changed"
      actions={tabs}
    >
      {pairs.length > 1 ? (
        <div className="flex items-center gap-2 border-b border-line px-4 py-2 text-sm">
          <label htmlFor="pair" className="text-muted">
            Compare
          </label>
          <select
            id="pair"
            value={index}
            onChange={(e) => setPairIndex(Number(e.target.value))}
            className="rounded-md border border-line bg-surface px-2 py-1 text-sm text-fg"
          >
            {pairs.map(([a, b], i) => (
              <option key={b.version} value={i}>
                v{a.version} → v{b.version}
              </option>
            ))}
          </select>
        </div>
      ) : null}
      {diff && pair ? (
        <div className="overflow-x-auto">
          <table className="w-full min-w-[36rem] border-collapse text-left">
            <thead>
              <tr className="bg-surface-2">
                <th scope="col" className="px-5 py-2 text-xs font-normal text-muted">
                  Change
                </th>
                <th scope="col" className="px-5 py-2 text-xs font-normal text-muted">
                  v{pair[0].version}{" "}
                  <span className="font-normal normal-case">for API {pair[0].spec.target_api_version}</span>
                </th>
                <th scope="col" className="px-5 py-2 text-xs font-normal text-muted">
                  v{pair[1].version}{" "}
                  <span className="font-normal normal-case">for API {pair[1].spec.target_api_version}</span>
                </th>
              </tr>
            </thead>
            <tbody>
              {diff.meta
                .filter((m) => m.changed || m.label === "Target API")
                .map((m) => (
                  <tr key={m.label} className="border-t border-line text-sm">
                    <th scope="row" className="px-3 py-1.5 text-left text-xs font-semibold text-muted">
                      {m.label}
                    </th>
                    <td className={`px-3 py-1.5 font-mono text-[0.8rem] ${m.changed ? TONES.danger.text : "text-fg"}`}>
                      {m.left}
                    </td>
                    <td
                      className={`px-3 py-1.5 font-mono text-[0.8rem] font-semibold ${m.changed ? TONES.success.text : "text-fg"}`}
                    >
                      {m.right}
                    </td>
                  </tr>
                ))}
              {[...diff.rows]
                .sort((a, b) => Number(a.change === "same") - Number(b.change === "same"))
                .map((row) => (
                  <DiffTableRow key={row.key} row={row} />
                ))}
            </tbody>
          </table>
          {pair[1].spec.rationale ? (
            <p className="border-t border-line px-4 py-2.5 text-sm text-fg">
              <span className={`font-semibold ${TONES.plan.text}`}>Agent rationale (v{pair[1].version}): </span>
              {pair[1].spec.rationale}
            </p>
          ) : null}
        </div>
      ) : single ? (
        <div className="px-4 py-3">
          <p className="text-sm text-muted">
            Only <span className="font-semibold text-fg">v{single.version}</span> exists for {entity} (target API{" "}
            {single.spec.target_api_version}). A side-by-side diff appears here when the agent has to repair this
            mapping.
          </p>
          <ul className="mt-2 flex flex-wrap gap-1">
            {single.spec.fields.map((f) => (
              <li
                key={f.target}
                className="rounded bg-surface-2 px-1.5 py-0.5 font-mono text-xs text-fg ring-1 ring-line"
              >
                {f.target} ← {f.source ?? "∅"}
              </li>
            ))}
          </ul>
        </div>
      ) : (
        <EmptyNote>No mapping yet. The planner proposes one after discovery.</EmptyNote>
      )}
    </Panel>
  );
}
