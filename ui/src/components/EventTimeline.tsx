import { useMemo, useState } from "react";
import { EVENT_KINDS, type EventKind, type RunEvent } from "../api/types";
import { eventDetails } from "../lib/eventDetails";
import { buildRows, type TimelineRow } from "../lib/timeline";
import { formatDateTime, formatInt, formatOffset } from "../lib/format";
import { KIND_TONE, TONES } from "../lib/tones";
import { EmptyNote, Panel } from "./ui";

const MAX_ROWS = 400;

/** Plain words for the event kinds: what a person watching would call them. */
const KIND_LABEL: Record<EventKind, string> = {
  state: "step",
  plan: "plan",
  batch: "batch",
  failure: "failure",
  recovery: "recovery",
  decision: "decision",
  verify: "verdict",
  llm: "model",
  info: "note",
};

/** Only the kinds that change the outcome get color; the rest stay ink on paper. */
const LOUD: ReadonlySet<EventKind> = new Set(["failure", "recovery", "verify"]);

/** A filled row is reserved for the two things a reader must not miss: something broke, and the verdict. */
const FILLED: ReadonlySet<EventKind> = new Set(["failure", "verify"]);

function Kind({ kind }: { kind: EventKind }) {
  const loud = LOUD.has(kind);
  return (
    <span
      className={`w-16 shrink-0 pt-px text-xs ${loud ? `font-semibold ${TONES[KIND_TONE[kind]].text}` : "text-muted"}`}
    >
      {KIND_LABEL[kind]}
    </span>
  );
}

function EventRow({ event, t0, fresh }: { event: RunEvent; t0: number; fresh: boolean }) {
  const loud = LOUD.has(event.kind);
  const tone = TONES[KIND_TONE[event.kind]];
  const details = eventDetails(event);
  return (
    <li
      className={`flex items-start gap-3 px-5 py-2.5 ${FILLED.has(event.kind) ? tone.soft : ""} ${fresh ? "zd-enter" : ""}`}
    >
      <time
        className="w-12 shrink-0 pt-px font-mono text-xs text-muted tabular"
        title={`#${event.seq} · ${formatDateTime(event.ts)}`}
      >
        {formatOffset(event.ts - t0)}
      </time>
      <Kind kind={event.kind} />
      <div className="min-w-0 flex-1">
        <p className={`text-sm leading-snug break-words ${loud ? "font-medium text-fg" : "text-fg"}`}>
          {event.entity ? <span className="mr-1.5 text-muted">{event.entity}:</span> : null}
          {event.message}
        </p>
        {details.length ? (
          <p className="mt-1 font-mono text-xs leading-relaxed text-muted">
            {details.map((d, i) => (
              <span key={`${d.label}:${d.value}`}>
                {i > 0 ? <span aria-hidden>{"  "}</span> : null}
                <span className="whitespace-nowrap">
                  {d.label} <span className={d.tone ? TONES[d.tone].text : "text-fg"}>{d.value}</span>
                </span>{" "}
              </span>
            ))}
          </p>
        ) : null}
      </div>
    </li>
  );
}

function GroupRow({ row, t0 }: { row: Extract<TimelineRow, { type: "group" }>; t0: number }) {
  const oldest = row.events[row.events.length - 1]!;
  return (
    <li className="flex items-start gap-3 px-5 py-2">
      <span className="w-12 shrink-0 pt-px font-mono text-xs text-muted tabular">{formatOffset(oldest.ts - t0)}</span>
      <Kind kind="batch" />
      <p className="min-w-0 flex-1 text-sm text-muted">
        {row.entity}: {formatInt(row.written)} written in {row.events.length} clean batches
      </p>
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
      <label className="flex cursor-pointer items-center gap-1.5 text-xs text-muted">
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
      title="What happened"
      subtitle={`${formatInt(events.length)} events, newest first`}
      actions={filters}
      className={className}
    >
      <div
        className="flex flex-wrap gap-x-3 gap-y-1 border-b border-line px-5 py-2.5 text-xs"
        role="group"
        aria-label="Show or hide kinds of event"
      >
        {EVENT_KINDS.filter((k) => counts[k]).map((kind) => {
          const on = !hidden.has(kind);
          return (
            <button
              key={kind}
              type="button"
              aria-pressed={on}
              onClick={() => toggle(kind)}
              className={`rounded px-1 py-0.5 transition-colors hover:bg-surface-2 ${on ? (LOUD.has(kind) ? `font-semibold ${TONES[KIND_TONE[kind]].text}` : "text-fg") : "text-muted line-through"}`}
            >
              {KIND_LABEL[kind]} <span className="tabular text-muted">{counts[kind]}</span>
            </button>
          );
        })}
      </div>
      {rows.length ? (
        <ol
          aria-label="Run events, newest first"
          className="h-full max-h-[44rem] min-h-[16rem] divide-y divide-line overflow-y-auto"
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
        <EmptyNote>Nothing yet. Start a migration and each step the agent takes will appear here.</EmptyNote>
      )}
    </Panel>
  );
}
