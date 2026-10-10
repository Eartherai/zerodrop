// Formatting helpers. Money is formatted from integer minor units with string
// arithmetic so totals are exact to the last minor unit.

const ZERO_DECIMAL = new Set([
  "BIF",
  "CLP",
  "DJF",
  "GNF",
  "ISK",
  "JPY",
  "KMF",
  "KRW",
  "PYG",
  "RWF",
  "UGX",
  "VND",
  "VUV",
  "XAF",
  "XOF",
  "XPF",
]);
const THREE_DECIMAL = new Set(["BHD", "IQD", "JOD", "KWD", "LYD", "OMR", "TND"]);

/** ISO-4217 minor-unit exponent (JPY 0, USD 2, KWD 3). */
export function minorUnitDigits(currency: string): number {
  const code = currency.toUpperCase();
  if (ZERO_DECIMAL.has(code)) return 0;
  if (THREE_DECIMAL.has(code)) return 3;
  return 2;
}

const GROUPED = new Intl.NumberFormat("en-US", { maximumFractionDigits: 0 });

export function formatInt(value: number): string {
  return GROUPED.format(value);
}

/** 1234567 USD -> "12,345.67"; 1500 JPY -> "1,500". */
export function formatMinor(minor: number, currency: string): string {
  const digits = minorUnitDigits(currency);
  const negative = minor < 0;
  const abs = Math.abs(Math.trunc(minor));
  const scale = 10 ** digits;
  const whole = Math.floor(abs / scale);
  const frac = digits === 0 ? "" : `.${String(abs % scale).padStart(digits, "0")}`;
  return `${negative ? "-" : ""}${GROUPED.format(whole)}${frac}`;
}

export function formatMoney(minor: number, currency: string): string {
  return `${currency.toUpperCase()} ${formatMinor(minor, currency)}`;
}

/** Accepts epoch seconds, epoch milliseconds or an ISO-8601 string. */
export function toDate(value: number | string | null | undefined): Date | null {
  if (value === null || value === undefined || value === "") return null;
  if (typeof value === "number") return new Date(value < 1e12 ? value * 1000 : value);
  const parsed = Date.parse(value);
  return Number.isNaN(parsed) ? null : new Date(parsed);
}

export function formatDateTime(value: number | string | null | undefined): string {
  const date = toDate(value);
  if (!date) return "—";
  return date.toLocaleString("en-GB", {
    day: "2-digit",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
  });
}

/** Seconds -> "4.2s" / "1:05" / "12:03:09". */
export function formatDuration(seconds: number): string {
  const s = Math.max(0, seconds);
  if (s < 60) return `${s.toFixed(1)}s`;
  const total = Math.floor(s);
  const h = Math.floor(total / 3600);
  const m = Math.floor((total % 3600) / 60);
  const sec = String(total % 60).padStart(2, "0");
  return h > 0 ? `${h}:${String(m).padStart(2, "0")}:${sec}` : `${m}:${sec}`;
}

/** Offset of an event from the run start: "+12.4s". */
export function formatOffset(seconds: number): string {
  return `+${formatDuration(seconds)}`;
}

export function formatUsd(value: number): string {
  return `$${value.toFixed(value < 1 ? 4 : 2)}`;
}

export function shortHash(hash: string, length = 12): string {
  return hash.length > length ? `${hash.slice(0, length)}…` : hash;
}

export function titleCase(status: string): string {
  return status
    .toLowerCase()
    .split("_")
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
    .join(" ");
}

/** Compact rendering of a JSON value for table cells. */
export function compactValue(value: unknown): string {
  if (value === null || value === undefined) return "—";
  if (typeof value === "number") return formatInt(value);
  if (typeof value === "string") return value;
  if (typeof value === "boolean") return value ? "true" : "false";
  if (Array.isArray(value)) return value.map(compactValue).join(", ");
  return Object.entries(value as Record<string, unknown>)
    .map(([k, v]) => `${k} ${compactValue(v)}`)
    .join(" · ");
}
