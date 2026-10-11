import type { RunListItem, Scenario } from "../api/types";
import { formatDateTime } from "../lib/format";
import { statusLabel } from "./ui";

export function Logo() {
  // Two columns of a ledger with the totals line under them: the same shape as the page's centerpiece.
  return (
    <svg aria-hidden viewBox="0 0 32 32" className="size-8 shrink-0">
      <rect width="32" height="32" rx="6" className="fill-fg" />
      <path d="M8 9h6M8 14h6M18 9h6M18 14h6" strokeWidth="2.4" strokeLinecap="round" className="stroke-bg" />
      <path d="M8 20h16" strokeWidth="1.6" strokeLinecap="round" className="stroke-bg" opacity="0.55" />
      <path d="M9 24.2h5M19 24.2h5" strokeWidth="2.4" strokeLinecap="round" className="stroke-success" />
    </svg>
  );
}

interface HeaderProps {
  mock: boolean;
  scenarios: Scenario[];
  scenarioId: string;
  onScenario: (id: string) => void;
  onStart: () => void;
  starting: boolean;
  runs: RunListItem[];
  runId: string | null;
  onSelectRun: (id: string | null) => void;
}

export function Header(props: HeaderProps) {
  const { mock, scenarios, scenarioId, onScenario, onStart, starting, runs, runId, onSelectRun } = props;
  const selectClass =
    "h-10 min-w-0 rounded-md border border-line-strong bg-surface px-3 text-sm text-fg focus:border-accent";
  return (
    <header className="border-b border-line">
      <div className="mx-auto flex max-w-[1480px] flex-wrap items-center gap-x-6 gap-y-3 px-5 py-4 lg:px-10">
        <div className="flex min-w-0 items-center gap-3">
          <Logo />
          <h1 className="font-display text-2xl leading-none font-semibold tracking-tight text-fg">ZeroDrop</h1>
          <p className="hidden text-sm text-muted md:block">The migration agent that proves nothing was lost</p>
          {mock ? (
            <span className="rounded border border-warning bg-warning-soft px-2 py-0.5 text-xs font-semibold text-warning">
              Mock data
            </span>
          ) : null}
        </div>

        <div className="ml-auto flex flex-wrap items-center gap-2">
          <label htmlFor="scenario" className="sr-only">
            Scenario
          </label>
          <select
            id="scenario"
            className={`${selectClass} max-w-[22rem]`}
            value={scenarioId}
            onChange={(e) => onScenario(e.target.value)}
          >
            {scenarios.length === 0 ? <option value="">No scenarios</option> : null}
            {scenarios.map((s) => (
              <option key={s.id} value={s.id} title={s.description}>
                {s.title}
              </option>
            ))}
          </select>
          <button
            type="button"
            onClick={onStart}
            disabled={!scenarioId || starting}
            className="h-10 rounded-md bg-accent px-5 text-sm font-semibold text-on-accent transition-opacity hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {starting ? "Starting…" : "Start migration"}
          </button>
          <span className="mx-2 hidden h-6 w-px bg-line sm:block" aria-hidden />
          <label htmlFor="history" className="text-sm text-muted">
            Past runs
          </label>
          <select
            id="history"
            className={`${selectClass} max-w-[20rem]`}
            value={runId ?? ""}
            onChange={(e) => onSelectRun(e.target.value || null)}
          >
            <option value="">{runs.length ? "Choose a run" : "No runs yet"}</option>
            {runs.map((r) => (
              <option key={r.run_id} value={r.run_id}>
                {statusLabel(r.status)}, {r.scenario_id}, {formatDateTime(r.created_at)}
              </option>
            ))}
          </select>
        </div>
      </div>
    </header>
  );
}
