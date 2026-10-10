import type { RunDetail } from "../api/types";

function isUrl(value: string): boolean {
  return /^https?:\/\//i.test(value);
}

function LinkOrText({ value, label }: { value: string; label: string }) {
  if (isUrl(value)) {
    return (
      <a
        href={value}
        target="_blank"
        rel="noreferrer noopener"
        className="font-semibold text-accent underline underline-offset-2 hover:opacity-80"
      >
        {label}
      </a>
    );
  }
  return <code className="font-mono text-fg">{value}</code>;
}

export function Footer({ detail, mock }: { detail: RunDetail | null; mock: boolean }) {
  const trace = detail?.trace_url ?? null;
  const commit = detail?.commit ?? null;
  return (
    <footer className="mt-6 border-t border-line bg-surface">
      <div className="mx-auto flex max-w-[1880px] flex-wrap items-center gap-x-8 gap-y-2 px-4 py-4 text-sm lg:px-6">
        <div className="flex items-center gap-2">
          <span className="text-muted">Neatlogs trace:</span>
          {trace ? (
            <LinkOrText value={trace} label="Open trace ↗" />
          ) : (
            <span className="text-muted">not available for this run</span>
          )}
        </div>
        <div className="flex items-center gap-2">
          <span className="text-muted">Entire checkpoint:</span>
          {commit ? (
            <LinkOrText value={commit} label={commit} />
          ) : (
            <span className="text-muted">not available for this run</span>
          )}
        </div>
        <p className="text-xs text-muted lg:ml-auto">
          LegacyBill and NovaBill are sandbox services; their failures are injected by a seeded fault plan.
          {mock ? " Mock mode: recorded runs bundled with the UI." : ""}
        </p>
      </div>
    </footer>
  );
}
