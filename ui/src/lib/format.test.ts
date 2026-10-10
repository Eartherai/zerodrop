import { describe, expect, it } from "vitest";
import { compactValue, formatDuration, formatMinor, formatMoney, minorUnitDigits, toDate } from "./format";

describe("money formatting from minor units", () => {
  it("uses ISO-4217 exponents", () => {
    expect(minorUnitDigits("JPY")).toBe(0);
    expect(minorUnitDigits("usd")).toBe(2);
    expect(minorUnitDigits("KWD")).toBe(3);
  });

  it("is exact for large totals", () => {
    expect(formatMinor(2120696895, "INR")).toBe("21,206,968.95");
    expect(formatMinor(12059665, "JPY")).toBe("12,059,665");
    expect(formatMinor(5, "USD")).toBe("0.05");
    expect(formatMinor(-9960000, "INR")).toBe("-99,600.00");
    expect(formatMinor(1234, "KWD")).toBe("1.234");
    expect(formatMoney(12900, "usd")).toBe("USD 129.00");
  });
});

describe("dates and durations", () => {
  it("accepts epoch seconds, epoch milliseconds and ISO strings", () => {
    expect(toDate(1_700_000_000)?.toISOString()).toBe("2023-11-14T22:13:20.000Z");
    expect(toDate(1_700_000_000_000)?.toISOString()).toBe("2023-11-14T22:13:20.000Z");
    expect(toDate("2024-02-01T00:00:00Z")?.toISOString()).toBe("2024-02-01T00:00:00.000Z");
    expect(toDate("not a date")).toBeNull();
    expect(toDate(null)).toBeNull();
  });

  it("formats durations", () => {
    expect(formatDuration(4.21)).toBe("4.2s");
    expect(formatDuration(65)).toBe("1:05");
    expect(formatDuration(3723)).toBe("1:02:03");
  });
});

describe("compactValue", () => {
  it("renders check expectations", () => {
    expect(compactValue({ EUR: 472052, JPY: 4492710 })).toBe("EUR 472,052 · JPY 4,492,710");
    expect(compactValue(null)).toBe("—");
    expect(compactValue(["a", 1])).toBe("a, 1");
  });
});
