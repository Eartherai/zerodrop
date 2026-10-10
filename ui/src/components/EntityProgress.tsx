import { ENTITIES, type Entity, type EntityCounts } from "../api/types";
import { formatInt } from "../lib/format";
import {
  excludedRecords,
  expectedRecords,
  pendingRecords,
  type EntityProgress as Progress,
  type RunModel,
} from "../lib/runModel";
import { Panel, Pill } from "./ui";

const LABELS: Record<Entity, string> = { customers: "Customers", subscriptions: "Subscriptions", invoices: "Invoices" };

function withFallback(p: Progress, counts: EntityCounts | undefined): Progress {
  // The event stream is the source of truth; polled ledger counts are passed only while no event has arrived.
  if (!counts) return p;
  return { ...p, written: counts.written, quarantined: counts.quarantined, total: counts.total || p.total };
}

function Segment({
  value,
  total,
  className,
  label,
}: {
  value: number;
  total: number;
  className: string;
  label: string;
}) {
  if (value <= 0 || total <= 0) return null;
  return (
    <div
      className={`h-full transition-[width] duration-500 ease-out ${className}`}
      style={{ width: `${(value / total) * 100}%` }}
      title={label}
    />
  );
}

function Stat({ label, value, className }: { label: string; value: number; className: string }) {
  return (
    <div className="min-w-0">
      <dt className="text-[0.7rem] font-semibold tracking-wide text-muted uppercase">{label}</dt>
      <dd className={`text-xl leading-tight font-bold tabular ${className}`}>{formatInt(value)}</dd>
    </div>
  );
}

function Row({ p, version }: { p: Progress; version: number | undefined }) {
  const expected = expectedRecords(p);
  const pending = pendingRecords(p);
  const excluded = excludedRecords(p);
  const resolved = p.written + p.quarantined + p.failed;
  const pct = expected > 0 ? Math.round((resolved / expected) * 100) : 0;
  return (
    <li className="px-4 py-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <h3 className="text-base font-semibold text-fg">{LABELS[p.entity]}</h3>
          {version !== undefined ? (
            <Pill tone={version > 1 ? "plan" : "neutral"} title="Mapping version in use">
              mapping v{version}
            </Pill>
          ) : null}
          {p.done ? <Pill tone="success">✓ complete</Pill> : null}
        </div>
        <span className="text-sm text-muted tabular">
          {formatInt(resolved)} / {expected ? formatInt(expected) : "—"} · {pct}%
        </span>
      </div>
      <div
        className="mt-2 flex h-3 w-full overflow-hidden rounded-full bg-surface-2 ring-1 ring-line"
        role="progressbar"
        aria-label={`${LABELS[p.entity]} progress`}
        aria-valuemin={0}
        aria-valuemax={expected || 1}
        aria-valuenow={resolved}
      >
        <Segment value={p.written} total={expected} className="bg-success" label={`${p.written} written`} />
        <Segment value={p.quarantined} total={expected} className="bg-warning" label={`${p.quarantined} quarantined`} />
        <Segment value={p.failed} total={expected} className="bg-danger" label={`${p.failed} failed`} />
      </div>
      <dl className="mt-2 grid grid-cols-3 gap-2 sm:grid-cols-4">
        <Stat label="Written" value={p.written} className="text-success" />
        <Stat label="Quarantined" value={p.quarantined} className={p.quarantined ? "text-warning" : "text-muted"} />
        <Stat label="Pending" value={pending} className="text-fg" />
        {p.failed ? <Stat label="Failed" value={p.failed} className="text-danger" /> : null}
      </dl>
      <p className="mt-1 text-xs text-muted">
        {p.loaded !== null ? `${formatInt(p.loaded)} source rows` : "waiting for discovery"}
        {excluded ? ` · ${formatInt(excluded)} excluded by mapping rule (soft-deleted)` : ""}
        {p.replayed ? ` · ${formatInt(p.replayed)} idempotent replays (no duplicates)` : ""}
        {p.batches ? ` · ${formatInt(p.batches)} batch responses` : ""}
      </p>
    </li>
  );
}

export function EntityProgress({
  model,
  counts,
}: {
  model: RunModel;
  counts: Partial<Record<Entity, EntityCounts>> | undefined;
}) {
  return (
    <Panel id="progress" title="Migration progress" subtitle="Records resolved per entity, live from the event stream">
      <ul className="divide-y divide-line">
        {ENTITIES.map((e) => (
          <Row key={e} p={withFallback(model.entities[e], counts?.[e])} version={model.mappingVersions[e]} />
        ))}
      </ul>
    </Panel>
  );
}
