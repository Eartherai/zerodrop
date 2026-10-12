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
        className="font-medium text-accent underline underline-offset-2 hover:opacity-80"
      >
        {label}
      </a>
    );
  }
  return <code className="font-mono text-fg">{value}</code>;
}

export function Footer({ detail, mock }: { detail: RunDetail | null; mock: boolean }) {
  const trace = detail?.trace_url ?? detail?.trace_id ?? null;
  const commit = detail?.commit ?? null;
  return (
    <footer className="mt-10 border-t border-line">
      <div className="mx-auto flex max-w-[1480px] flex-wrap items-baseline gap-x-8 gap-y-2 px-5 py-5 text-sm text-muted lg:px-10">
        {detail ? (
          <>
            <span>
              Run <code className="font-mono text-fg">{detail.run_id}</code>
            </span>
            <span>
              Trace in Neatlogs:{" "}
              {trace ? <LinkOrText value={trace} label="open the trace" /> : "this run was not traced"}
            </span>
            <span>Agent version: {commit ? <LinkOrText value={commit} label={commit} /> : "unknown"}</span>
          </>
        ) : null}
        <p className="max-w-[70ch] lg:ml-auto">
          LegacyBill and NovaBill are sandbox services built for this project. Their failures are injected from a seeded
          plan the agent never sees.
          {mock ? " This page replays recorded runs bundled with it; nothing here calls a model." : ""}
        </p>
      </div>
    </footer>
  );
}
