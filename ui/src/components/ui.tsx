import type { ReactNode } from "react";
import type { RunStatus } from "../api/types";
import { titleCase } from "../lib/format";
import { statusTone, TONES, type Tone } from "../lib/tones";

export function Panel({
  title,
  subtitle,
  actions,
  children,
  className = "",
  id,
}: {
  title: ReactNode;
  subtitle?: ReactNode;
  actions?: ReactNode;
  children: ReactNode;
  className?: string;
  id?: string;
}) {
  const headingId = id ? `${id}-title` : undefined;
  return (
    <section
      id={id}
      aria-labelledby={headingId}
      className={`flex min-w-0 flex-col rounded-lg border border-line bg-surface ${className}`}
    >
      <header className="flex flex-wrap items-end justify-between gap-x-4 gap-y-2 border-b border-line px-5 py-4">
        <div className="min-w-0">
          <h2 id={headingId} className="font-display text-xl leading-tight font-semibold text-fg">
            {title}
          </h2>
          {subtitle ? <p className="mt-1 text-sm text-muted">{subtitle}</p> : null}
        </div>
        {actions ? <div className="flex flex-wrap items-center gap-2">{actions}</div> : null}
      </header>
      <div className="min-h-0 flex-1">{children}</div>
    </section>
  );
}

export function Pill({
  tone = "neutral",
  children,
  className = "",
  title,
}: {
  tone?: Tone;
  children: ReactNode;
  className?: string;
  title?: string;
}) {
  const t = TONES[tone];
  return (
    <span
      title={title}
      className={`inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-xs font-medium whitespace-nowrap ${t.soft} ${t.text} ${className}`}
    >
      {children}
    </span>
  );
}

export function Dot({ tone, pulse = false }: { tone: Tone; pulse?: boolean }) {
  return (
    <span
      aria-hidden
      className={`inline-block size-2.5 shrink-0 rounded-full ${TONES[tone].dot} ${pulse ? "zd-pulse" : ""}`}
    />
  );
}

export function StatusBadge({
  status,
  size = "md",
  live = false,
}: {
  status: RunStatus | null;
  size?: "md" | "lg";
  live?: boolean;
}) {
  const tone = statusTone(status);
  const t = TONES[tone];
  const sizing = size === "lg" ? "px-4 py-1.5 text-lg" : "px-2.5 py-1 text-sm";
  return (
    <span className={`inline-flex items-center gap-2 rounded-md font-semibold ${sizing} ${t.soft} ${t.text}`}>
      <Dot tone={tone} pulse={live} />
      {statusLabel(status)}
    </span>
  );
}

export function statusLabel(status: RunStatus | null): string {
  if (!status) return "Idle";
  const words = titleCase(status).toLowerCase();
  return words.charAt(0).toUpperCase() + words.slice(1);
}

export function Kbd({ children }: { children: ReactNode }) {
  return <code className="rounded bg-surface-2 px-1.5 py-0.5 font-mono text-[0.8em] text-fg">{children}</code>;
}

export function EmptyNote({ children }: { children: ReactNode }) {
  return <p className="max-w-[60ch] px-5 py-6 text-sm leading-relaxed text-muted">{children}</p>;
}
