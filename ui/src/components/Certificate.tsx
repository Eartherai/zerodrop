import { useState } from "react";
import type { CheckResult, ReconciliationReport, RunStatus } from "../api/types";
import { compactValue, formatInt, formatMinor, minorUnitDigits } from "../lib/format";
import { isTerminal, type RunModel } from "../lib/runModel";
import { TONES } from "../lib/tones";
import { EmptyNote, Panel, Pill, StatusBadge } from "./ui";

function ClaimComparison({ verdict, claim }: { verdict: RunStatus; claim: RunStatus | null }) {
  if (!claim) return <p className="text-sm text-muted">The agent did not record a claim.</p>;
  if (claim === verdict) {
    return <p className={`text-sm font-semibold ${TONES.success.text}`}>The agent's own claim matches the verifier.</p>;
  }
  const falseSuccess = claim === "SUCCESS";
  return (
    <p
      role="alert"
      className={`rounded-lg px-3 py-2 text-sm font-semibold ${falseSuccess ? `${TONES.danger.soft} ${TONES.danger.text}` : `${TONES.warning.soft} ${TONES.warning.text}`}`}
    >
      {falseSuccess
        ? `False-success claim caught: the agent believed SUCCESS, the independent verifier says ${verdict.replaceAll("_", " ")}.`
        : `The agent claimed ${claim.replaceAll("_", " ")}; the verifier decided ${verdict.replaceAll("_", " ")}.`}
    </p>
  );
}

function CopyHash({ hash }: { hash: string }) {
  const [copied, setCopied] = useState(false);
  const copy = () => {
    void navigator.clipboard?.writeText(hash).then(
      () => {
        setCopied(true);
        setTimeout(() => setCopied(false), 1500);
      },
      () => setCopied(false),
    );
  };
  return (
    <div className="min-w-0">
      <div className="text-[0.7rem] font-semibold tracking-wide text-muted uppercase">
        Report hash (SHA-256 of the checks)
      </div>
      <div className="mt-0.5 flex items-center gap-2">
        <code className="min-w-0 truncate font-mono text-sm text-fg" title={hash}>
          {hash || "—"}
        </code>
        {hash ? (
          <button
            type="button"
            onClick={copy}
            className="shrink-0 rounded-md border border-line px-2 py-0.5 text-xs font-semibold text-muted hover:text-fg"
          >
            {copied ? "Copied" : "Copy"}
          </button>
        ) : null}
      </div>
    </div>
  );
}

function sortChecks(checks: readonly CheckResult[]): CheckResult[] {
  return [...checks].sort((a, b) => Number(a.passed) - Number(b.passed));
}

function ChecksTable({ checks }: { checks: readonly CheckResult[] }) {
  return (
    <div className="max-h-[30rem] overflow-auto">
      <table className="w-full border-collapse text-left text-sm">
        <thead className="sticky top-0 bg-surface-2">
          <tr>
            {["Result", "Check", "Entity", "Expected", "Actual", "Detail"].map((h) => (
              <th key={h} scope="col" className="px-3 py-2 text-xs font-semibold text-muted uppercase">
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {sortChecks(checks).map((c, i) => (
            <tr
              key={`${c.name}:${c.entity ?? ""}:${i}`}
              className={`border-t border-line ${c.passed ? "" : TONES.danger.soft}`}
            >
              <td className="px-3 py-1.5">
                <Pill tone={c.passed ? "success" : "danger"}>{c.passed ? "✓ PASS" : "✗ FAIL"}</Pill>
              </td>
              <td className="px-3 py-1.5 font-mono text-[0.8rem] text-fg">{c.name}</td>
              <td className="px-3 py-1.5 text-muted">{c.entity ?? "all"}</td>
              <td
                className="max-w-[12rem] truncate px-3 py-1.5 font-mono text-[0.8rem] tabular text-fg"
                title={compactValue(c.expected)}
              >
                {compactValue(c.expected)}
              </td>
              <td
                className={`max-w-[12rem] truncate px-3 py-1.5 font-mono text-[0.8rem] tabular ${c.passed ? "text-fg" : `font-bold ${TONES.danger.text}`}`}
                title={compactValue(c.actual)}
              >
                {compactValue(c.actual)}
              </td>
              <td className="max-w-[18rem] truncate px-3 py-1.5 text-xs text-muted" title={c.detail}>
                {c.detail || "—"}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/** A non-zero delta is only an error when the verifier's money check failed; otherwise quarantine explains it. */
function deltaClass(delta: number, checkPassed: boolean | undefined): string {
  if (delta === 0) return TONES.success.text;
  return checkPassed ? `font-semibold ${TONES.warning.text}` : `font-bold ${TONES.danger.text}`;
}

function MoneyTable({ report }: { report: ReconciliationReport }) {
  const currencies = [
    ...new Set([...Object.keys(report.money_source_minor), ...Object.keys(report.money_target_minor)]),
  ].sort();
  const moneyCheck = report.checks.find((c) => c.name === "money_by_currency");
  if (!currencies.length) return <EmptyNote>No invoice money in this run.</EmptyNote>;
  return (
    <div className="overflow-x-auto">
      <table className="w-full border-collapse text-left text-sm">
        <thead className="bg-surface-2">
          <tr>
            {["Currency", "Source", "Target", "Δ"].map((h) => (
              <th
                key={h}
                scope="col"
                className={`px-3 py-2 text-xs font-semibold text-muted uppercase ${h === "Currency" ? "" : "text-right"}`}
              >
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {currencies.map((cur) => {
            const src = report.money_source_minor[cur] ?? 0;
            const tgt = report.money_target_minor[cur] ?? 0;
            const delta = tgt - src;
            return (
              <tr key={cur} className="border-t border-line">
                <th scope="row" className="px-3 py-1.5 text-left font-semibold text-fg">
                  {cur.toUpperCase()}
                  <span className="ml-1 text-[0.7rem] font-normal text-muted">{minorUnitDigits(cur)} dp</span>
                </th>
                <td className="px-3 py-1.5 text-right font-mono tabular text-fg">{formatMinor(src, cur)}</td>
                <td className="px-3 py-1.5 text-right font-mono tabular text-fg">{formatMinor(tgt, cur)}</td>
                <td className={`px-3 py-1.5 text-right font-mono tabular ${deltaClass(delta, moneyCheck?.passed)}`}>
                  {delta === 0 ? "0" : `${delta > 0 ? "+" : ""}${formatMinor(delta, cur)}`}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
      {moneyCheck ? (
        <p className="border-t border-line px-3 py-2 text-xs text-muted">
          Check <code className="font-mono">money_by_currency</code> (target vs. source minus quarantined invoices,
          exact minor units):{" "}
          <span className={`font-bold ${moneyCheck.passed ? TONES.success.text : TONES.danger.text}`}>
            {moneyCheck.passed ? "PASS" : "FAIL"}
          </span>
          {moneyCheck.detail ? ` · ${moneyCheck.detail}` : ""}
          {moneyCheck.passed &&
          currencies.some((c) => (report.money_target_minor[c] ?? 0) !== (report.money_source_minor[c] ?? 0))
            ? ". Non-zero Δ equals the value of quarantined invoices."
            : ""}
        </p>
      ) : null}
    </div>
  );
}

function CountsTable({ report }: { report: ReconciliationReport }) {
  const entities = Object.keys(report.source_counts);
  return (
    <div className="overflow-x-auto">
      <table className="w-full border-collapse text-left text-sm">
        <thead className="bg-surface-2">
          <tr>
            {["Entity", "Source", "Target", "Quarantined"].map((h) => (
              <th
                key={h}
                scope="col"
                className={`px-3 py-2 text-xs font-semibold text-muted uppercase ${h === "Entity" ? "" : "text-right"}`}
              >
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {entities.map((e) => (
            <tr key={e} className="border-t border-line">
              <th scope="row" className="px-3 py-1.5 text-left font-semibold text-fg">
                {e}
              </th>
              <td className="px-3 py-1.5 text-right font-mono tabular">{formatInt(report.source_counts[e] ?? 0)}</td>
              <td className="px-3 py-1.5 text-right font-mono tabular">{formatInt(report.target_counts[e] ?? 0)}</td>
              <td className="px-3 py-1.5 text-right font-mono tabular">
                {formatInt(report.quarantined.filter((q) => q.entity === e).length)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function reasonCode(reason: string): [string, string] {
  const i = reason.indexOf(":");
  return i > 0 ? [reason.slice(0, i), reason.slice(i + 1).trim()] : [reason, ""];
}

function SubHeading({ children }: { children: string }) {
  return (
    <h3 className="border-b border-line px-3 py-2 text-xs font-bold tracking-wider text-muted uppercase">{children}</h3>
  );
}

function placeholder(model: RunModel): string {
  if (model.status === "VERIFYING") return "The independent verifier is re-reading LegacyBill and NovaBill…";
  if (model.status === "WAITING_FOR_APPROVAL")
    return "The run is waiting for human approval; the verifier runs once it can finish.";
  if (isTerminal(model.status))
    return `No verification report: the run stopped (${model.status}) before the verifier produced one.`;
  return "Appears when the run finishes. The verifier re-reads both systems and checks counts, money per currency, referential integrity, duplicates and golden records.";
}

export function Certificate({ report, model }: { report: ReconciliationReport | null; model: RunModel }) {
  const verified = model.verify !== null;
  if (!report || !verified) {
    return (
      <Panel
        id="certificate"
        title="Verification certificate"
        subtitle="Decided by the independent verifier, not by the agent"
      >
        <EmptyNote>{placeholder(model)}</EmptyNote>
      </Panel>
    );
  }
  const claim = model.verify?.agentClaim ?? model.agentClaim;
  const passed = report.checks.filter((c) => c.passed).length;
  return (
    <Panel
      id="certificate"
      title="Verification certificate"
      subtitle="Decided by the independent verifier, not by the agent"
      className="zd-enter"
    >
      <div className="grid gap-4 border-b border-line px-4 py-4 lg:grid-cols-[auto_auto_1fr] lg:items-center">
        <div>
          <div className="text-[0.7rem] font-semibold tracking-wide text-muted uppercase">Verifier verdict</div>
          <div className="mt-1">
            <StatusBadge status={report.status} size="lg" />
          </div>
        </div>
        <div>
          <div className="text-[0.7rem] font-semibold tracking-wide text-muted uppercase">Agent's own claim</div>
          <div className="mt-1">
            <StatusBadge status={claim} />
          </div>
        </div>
        <div className="flex min-w-0 flex-col gap-2">
          <ClaimComparison verdict={report.status} claim={claim} />
          <div className="flex flex-wrap items-end gap-x-6 gap-y-2">
            <div>
              <div className="text-[0.7rem] font-semibold tracking-wide text-muted uppercase">Checks</div>
              <div
                className={`text-lg font-bold tabular ${passed === report.checks.length ? TONES.success.text : TONES.danger.text}`}
              >
                {passed}/{report.checks.length} passed
              </div>
            </div>
            <div>
              <div className="text-[0.7rem] font-semibold tracking-wide text-muted uppercase">Quarantined</div>
              <div className="text-lg font-bold tabular text-fg">{report.quarantined.length}</div>
            </div>
            <CopyHash hash={report.report_hash} />
          </div>
        </div>
      </div>
      <div className="grid gap-0 xl:grid-cols-[minmax(0,7fr)_minmax(0,5fr)]">
        <div className="min-w-0 border-line xl:border-r">
          <SubHeading>Checks</SubHeading>
          <ChecksTable checks={report.checks} />
        </div>
        <div className="min-w-0">
          <SubHeading>Money totals per currency</SubHeading>
          <MoneyTable report={report} />
          <SubHeading>Record counts</SubHeading>
          <CountsTable report={report} />
          <SubHeading>{`Quarantined items (${report.quarantined.length})`}</SubHeading>
          {report.quarantined.length ? (
            <ul className="max-h-48 divide-y divide-line overflow-y-auto">
              {report.quarantined.map((q) => {
                const [code, rest] = reasonCode(q.reason);
                return (
                  <li key={`${q.entity}:${q.source_id}`} className="px-3 py-1.5 text-sm">
                    <span className="font-mono font-semibold text-fg">{q.source_id}</span>
                    <span className="ml-1.5 text-muted">{q.entity}</span>
                    <Pill tone="warning" className="ml-2">
                      {code}
                    </Pill>
                    {rest ? <p className="mt-0.5 text-xs break-words text-muted">{rest}</p> : null}
                  </li>
                );
              })}
            </ul>
          ) : (
            <EmptyNote>Nothing quarantined: every source record is accounted for in NovaBill.</EmptyNote>
          )}
        </div>
      </div>
    </Panel>
  );
}
