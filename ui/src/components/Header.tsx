import type { RunListItem, Scenario } from "../api/types";
import { formatDateTime } from "../lib/format";

export function Logo() {
  return (
    <svg aria-hidden viewBox="0 0 32 32" className="size-9 shrink-0">
      <rect width="32" height="32" rx="8" className="fill-accent" />
      <path d="M16 6c-4 5.2-7 9-7 12.6A7 7 0 0 0 23 18.6C23 15 20 11.2 16 6Z" className="fill-on-accent" />
      <path
        d="m12.6 18.4 2.4 2.4 4.6-4.8"
        fill="none"
        strokeWidth="2.2"
        strokeLinecap="round"
        strokeLinejoin="round"
        className="stroke-accent"
      />
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
    "h-10 min-w-0 rounded-lg border border-line bg-surface px-3 text-sm text-fg shadow-sm focus:border-accent";
  return (
    <header className="border-b border-line bg-surface">
      <div className="mx-auto flex max-w-[1880px] flex-wrap items-center gap-x-6 gap-y-3 px-4 py-3 lg:px-6">
        <div className="flex min-w-0 items-center gap-3">
          <Logo />
          <div className="min-w-0">
            <div className="flex items-center gap-2">
              <h1 className="text-2xl leading-none font-extrabold tracking-tight text-fg">ZeroDrop</h1>
              {mock ? (
                <span className="rounded-md border-2 border-warning bg-warning-soft px-2 py-0.5 text-xs font-extrabold tracking-widest text-warning">
                  MOCK DATA
                </span>
              ) : null}
            </div>
            <p className="mt-1 text-sm text-muted">The migration agent that proves nothing was lost</p>
          </div>
        </div>

        <div className="ml-auto flex flex-wrap items-center gap-2">
          <label htmlFor="scenario" className="text-sm font-medium text-muted">
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
            className="h-10 rounded-lg bg-accent px-5 text-sm font-bold text-on-accent shadow-sm transition-opacity hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {starting ? "Starting…" : "Start migration"}
          </button>
          <span className="mx-1 hidden h-6 w-px bg-line sm:block" aria-hidden />
          <label htmlFor="history" className="text-sm font-medium text-muted">
            Runs
          </label>
          <select
            id="history"
            className={`${selectClass} max-w-[20rem]`}
            value={runId ?? ""}
            onChange={(e) => onSelectRun(e.target.value || null)}
          >
            <option value="">{runs.length ? "Select a run…" : "No runs yet"}</option>
            {runs.map((r) => (
              <option key={r.run_id} value={r.run_id}>
                {r.status} · {r.scenario_id} · {formatDateTime(r.created_at)}
              </option>
            ))}
          </select>
        </div>
      </div>
    </header>
  );
}
