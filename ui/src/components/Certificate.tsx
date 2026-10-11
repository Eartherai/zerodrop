import { useState } from "react";
import type { CheckResult, ReconciliationReport, RunStatus } from "../api/types";
import { compactValue, formatMinor, minorUnitDigits } from "../lib/format";
import { isTerminal, type RunModel } from "../lib/runModel";
import { TONES } from "../lib/tones";
import { EmptyNote, Panel, Pill } from "./ui";

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
      <div className="text-xs text-muted">Report fingerprint (SHA-256 of the checks)</div>
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

/** Plain names for the checks the verifier runs; unknown ones fall back to their own name. */
const CHECK_LABELS: Record<string, string> = {
  count: "Record count matches",
  no_duplicate_external_ids: "No duplicate ids",
  missing_records_quarantined: "Nothing missing without a reason",
  no_unexpected_records: "No records that were not in the source",
  unique_emails: "E-mails are unique",
  source_fidelity: "Every field matches the source",
  referential_integrity: "References point to real records",
  money_by_currency: "Money totals match, per currency",
  golden_records: "Matches the expected records",
  quarantine_accounting: "Set-aside records are accounted for",
  golden_quarantine: "The right records were set aside",
  quarantine_reasons: "Each set-aside record has a valid reason",
};

function checkLabel(name: string): string {
  return CHECK_LABELS[name] ?? name.replaceAll("_", " ");
}

/** One row per kind of check, one column per entity: 24 checks read as a small grid, not a long list. */
function CheckMatrix({ checks }: { checks: readonly CheckResult[] }) {
  const names = [...new Set(checks.map((c) => c.name))];
  const columns = [...new Set(checks.map((c) => c.entity ?? "all"))];
  const cell = (name: string, column: string) => checks.find((c) => c.name === name && (c.entity ?? "all") === column);
  return (
    <div className="overflow-x-auto">
      <table className="w-full border-collapse text-left text-sm">
        <thead>
          <tr>
            <th scope="col" className="px-5 py-2 text-xs font-normal text-muted">
              Check
            </th>
            {columns.map((column) => (
              <th key={column} scope="col" className="px-3 py-2 text-center text-xs font-normal text-muted">
                {column === "all" ? "whole run" : column}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {names.map((name) => (
            <tr key={name} className="border-t border-line">
              <th scope="row" className="px-5 py-2 text-left font-normal text-fg" title={name}>
                {checkLabel(name)}
              </th>
              {columns.map((column) => {
                const c = cell(name, column);
                if (!c) {
                  return (
                    <td key={column} className="px-3 py-2 text-center text-muted" aria-label="not applicable">
                      ·
                    </td>
                  );
                }
                return (
                  <td
                    key={column}
                    className={`px-3 py-2 text-center text-base leading-none ${c.passed ? TONES.success.text : `font-semibold ${TONES.danger.soft} ${TONES.danger.text}`}`}
                    title={`expected ${compactValue(c.expected)}, found ${compactValue(c.actual)}`}
                  >
                    {c.passed ? "✓" : "✗"}
                    <span className="sr-only">{c.passed ? " passed" : " failed"}</span>
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/** What exactly failed, in full: the detail is the useful part and must not be cut off. */
function FailedChecks({ checks }: { checks: readonly CheckResult[] }) {
  const failed = checks.filter((c) => !c.passed);
  if (!failed.length) return null;
  return (
    <ul className="divide-y divide-line border-t border-line">
      {failed.map((c, i) => (
        <li key={`${c.name}:${c.entity ?? ""}:${i}`} className="px-5 py-3 text-sm">
          <p className="font-medium text-fg">
            <span className={TONES.danger.text}>✗</span> {checkLabel(c.name)}
            <span className="text-muted">, {c.entity ?? "whole run"}</span>
          </p>
          <p className="mt-1 font-mono text-xs text-muted">
            expected <span className="text-fg">{compactValue(c.expected)}</span>, found{" "}
            <span className={`font-semibold ${TONES.danger.text}`}>{compactValue(c.actual)}</span>
          </p>
          {c.detail ? (
            <p className="mt-1 max-w-[90ch] text-xs leading-relaxed break-words text-muted">{c.detail}</p>
          ) : null}
        </li>
      ))}
    </ul>
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
        <thead>
          <tr>
            {["Currency", "Source", "Target", "Δ"].map((h) => (
              <th
                key={h}
                scope="col"
                className={`px-5 py-2 text-xs font-normal text-muted ${h === "Currency" ? "" : "text-right"}`}
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
                <th scope="row" className="px-5 py-2 text-left font-semibold text-fg">
                  {cur.toUpperCase()}
                  <span className="ml-1 text-[0.7rem] font-normal text-muted">{minorUnitDigits(cur)} dp</span>
                </th>
                <td className="px-5 py-2 text-right font-mono tabular text-fg">{formatMinor(src, cur)}</td>
                <td className="px-5 py-2 text-right font-mono tabular text-fg">{formatMinor(tgt, cur)}</td>
                <td className={`px-5 py-2 text-right font-mono tabular ${deltaClass(delta, moneyCheck?.passed)}`}>
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
            {moneyCheck.passed ? "pass" : "fail"}
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

function reasonCode(reason: string): [string, string] {
  const i = reason.indexOf(":");
  return i > 0 ? [reason.slice(0, i), reason.slice(i + 1).trim()] : [reason, ""];
}

function SubHeading({ children }: { children: string }) {
  return <h3 className="border-b border-line px-5 pt-5 pb-2 text-base font-semibold text-fg">{children}</h3>;
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
        title="The proof"
        subtitle="What the independent checker found when it re-read both systems. The agent cannot edit this."
      >
        <EmptyNote>{placeholder(model)}</EmptyNote>
      </Panel>
    );
  }
  const claim = model.verify?.agentClaim ?? model.agentClaim;
  const passed = report.checks.filter((c) => c.passed).length;
  const allPassed = passed === report.checks.length;
  const disagree = claim !== null && claim !== report.status;
  return (
    <Panel
      id="certificate"
      title="The proof"
      subtitle="What the independent checker found when it re-read both systems. The agent cannot edit this."
      className="zd-enter"
    >
      {disagree ? (
        <div className="border-b border-line px-5 py-4">
          <ClaimComparison verdict={report.status} claim={claim} />
        </div>
      ) : null}
      <div className="grid gap-0 xl:grid-cols-[minmax(0,7fr)_minmax(0,5fr)]">
        <div className="min-w-0 border-line xl:border-r">
          <h3 className="flex flex-wrap items-baseline gap-x-3 px-5 pt-5 pb-2 text-base font-semibold text-fg">
            <span className={allPassed ? TONES.success.text : TONES.danger.text}>
              {passed} of {report.checks.length} checks passed
            </span>
            <span className="text-sm font-normal text-muted">
              {allPassed
                ? "every cell below was compared against the source"
                : "the failures are listed under the grid"}
            </span>
          </h3>
          <CheckMatrix checks={report.checks} />
          <FailedChecks checks={report.checks} />
        </div>
        <div className="min-w-0">
          <SubHeading>Money, per currency</SubHeading>
          <MoneyTable report={report} />
          <SubHeading>{`Set aside (${report.quarantined.length})`}</SubHeading>
          {report.quarantined.length ? (
            <ul className="max-h-56 divide-y divide-line overflow-y-auto">
              {report.quarantined.map((q) => {
                const [code, rest] = reasonCode(q.reason);
                return (
                  <li key={`${q.entity}:${q.source_id}`} className="px-5 py-2 text-sm">
                    <span className="font-mono font-medium text-fg">{q.source_id}</span>
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
            <EmptyNote>Nothing was set aside. Every source record is accounted for in NovaBill.</EmptyNote>
          )}
          <div className="border-t border-line px-5 py-4">
            <CopyHash hash={report.report_hash} />
          </div>
        </div>
      </div>
    </Panel>
  );
}
