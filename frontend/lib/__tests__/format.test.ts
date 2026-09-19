// Tests for the formatCurrency helper's locale-aware currency formatting.

import { describe, expect, it } from "vitest";
import { formatCurrency } from "../format";

describe("formatCurrency", () => {
  it("matches Intl.NumberFormat output for the given currency", () => {
    const expected = new Intl.NumberFormat("en-GB", { style: "currency", currency: "USD" }).format(1352);
    expect(formatCurrency(1352, "USD")).toBe(expected);
  });

  it("rounds to two decimal places", () => {
    expect(formatCurrency(1352, "USD")).toContain("1,352.00");
  });
});
