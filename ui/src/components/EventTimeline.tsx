import { useMemo, useState } from "react";
import { EVENT_KINDS, type EventKind, type RunEvent } from "../api/types";
import { eventDetails } from "../lib/eventDetails";
import { buildRows, type TimelineRow } from "../lib/timeline";
import { formatDateTime, formatInt, formatOffset } from "../lib/format";
import { KIND_TONE, TONES } from "../lib/tones";
import { EmptyNote, Panel } from "./ui";

const MAX_ROWS = 400;

function KindTag({ kind }: { kind: EventKind }) {
  const t = TONES[KIND_TONE[kind]];
  return (
    <span
      className={`inline-block w-[5.5rem] shrink-0 rounded-md px-1.5 py-0.5 text-center text-[0.7rem] font-bold tracking-wider uppercase ${t.soft} ${t.text}`}
    >
      {kind}
    </span>
  );
}

function EventRow({ event, t0, fresh }: { event: RunEvent; t0: number; fresh: boolean }) {
  const tone = TONES[KIND_TONE[event.kind]];
  const details = eventDetails(event);
  return (
    <li className={`relative border-l-4 py-2 pr-3 pl-3 ${tone.border} ${fresh ? "zd-enter" : ""}`}>
      <div className="flex items-start gap-2">
        <KindTag kind={event.kind} />
        <div className="min-w-0 flex-1">
          <p className="text-sm leading-snug break-words text-fg">
            {event.entity ? <span className="mr-1.5 font-semibold text-muted">{event.entity}</span> : null}
            {event.message}
          </p>
          {details.length ? (
            <ul className="mt-1 flex flex-wrap gap-1">
              {details.map((d) => (
                <li
                  key={`${d.label}:${d.value}`}
                  className={`rounded border px-1.5 py-px font-mono text-[0.72rem] ${d.tone ? `${TONES[d.tone].border} ${TONES[d.tone].text}` : "border-line text-muted"}`}
                >
                  <span className="opacity-80">{d.label}</span> <span className="font-semibold">{d.value}</span>
                </li>
              ))}
            </ul>
          ) : null}
        </div>
        <time
          className="shrink-0 pt-0.5 font-mono text-xs text-muted tabular"
          title={`#${event.seq} · ${formatDateTime(event.ts)}`}
        >
          {formatOffset(event.ts - t0)}
        </time>
      </div>
    </li>
  );
}

function GroupRow({ row, t0 }: { row: Extract<TimelineRow, { type: "group" }>; t0: number }) {
  const newest = row.events[0]!;
  const oldest = row.events[row.events.length - 1]!;
  return (
    <li className={`border-l-4 py-1.5 pr-3 pl-3 ${TONES.info.border}`}>
      <div className="flex items-center gap-2">
        <KindTag kind="batch" />
        <p className="min-w-0 flex-1 text-sm text-muted">
          <span className="mr-1.5 font-semibold">{row.entity}</span>
          {row.events.length} clean batches · {formatInt(row.written)} written on the first attempt
        </p>
        <span className="shrink-0 font-mono text-xs text-muted tabular">
          {formatOffset(oldest.ts - t0)}–{formatOffset(newest.ts - t0).slice(1)}
        </span>
      </div>
    </li>
  );
}

export function EventTimeline({ events, className = "" }: { events: readonly RunEvent[]; className?: string }) {
  const [hidden, setHidden] = useState<ReadonlySet<EventKind>>(new Set());
  const [fold, setFold] = useState(true);
  const counts = useMemo(() => {
    const c: Partial<Record<EventKind, number>> = {};
    for (const e of events) c[e.kind] = (c[e.kind] ?? 0) + 1;
    return c;
  }, [events]);
  const visible = useMemo(() => events.filter((e) => !hidden.has(e.kind)), [events, hidden]);
  const rows = useMemo(() => buildRows(visible, fold).slice(0, MAX_ROWS), [visible, fold]);
  const t0 = events[0]?.ts ?? 0;
  const newestSeq = events[events.length - 1]?.seq;

  const toggle = (kind: EventKind) =>
    setHidden((prev) => {
      const next = new Set(prev);
      if (next.has(kind)) next.delete(kind);
      else next.add(kind);
      return next;
    });

  const filters = (
    <>
      <label className="flex cursor-pointer items-center gap-1.5 text-xs font-medium text-muted">
        <input
          type="checkbox"
          className="accent-[var(--zd-accent)]"
          checked={fold}
          onChange={(e) => setFold(e.target.checked)}
        />
        Fold clean batches
      </label>
    </>
  );

  return (
    <Panel
      id="timeline"
      title="Event timeline"
      subtitle={`${formatInt(events.length)} events · newest first`}
      actions={filters}
      className={className}
    >
      <div className="flex flex-wrap gap-1 border-b border-line px-3 py-2" role="group" aria-label="Filter event kinds">
        {EVENT_KINDS.filter((k) => counts[k]).map((kind) => {
          const t = TONES[KIND_TONE[kind]];
          const on = !hidden.has(kind);
          return (
            <button
              key={kind}
              type="button"
              aria-pressed={on}
              onClick={() => toggle(kind)}
              className={`rounded-md border px-2 py-0.5 text-xs font-semibold transition-colors ${on ? `${t.border} ${t.soft} ${t.text}` : "border-line text-muted line-through"}`}
            >
              {kind} {counts[kind]}
            </button>
          );
        })}
      </div>
      {rows.length ? (
        <ol
          aria-label="Run events, newest first"
          className="h-full max-h-[38rem] min-h-[16rem] divide-y divide-line overflow-y-auto"
        >
          {rows.map((row) =>
            row.type === "event" ? (
              <EventRow key={row.event.seq} event={row.event} t0={t0} fresh={row.event.seq === newestSeq} />
            ) : (
              <GroupRow key={row.key} row={row} t0={t0} />
            ),
          )}
        </ol>
      ) : (
        <EmptyNote>No events yet. Start a run to watch the agent work.</EmptyNote>
      )}
    </Panel>
  );
}
