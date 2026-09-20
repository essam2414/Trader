import { describe, expect, it } from "vitest";
import { conciseStockName } from "../WatchlistSection";

describe("conciseStockName", () => {
  it("removes share-class and corporate suffix clutter from a table name", () => {
    expect(conciseStockName("Vertiv Holdings Co Class A Common Stock")).toBe("Vertiv");
  });

  it("keeps the meaningful company name", () => {
    expect(conciseStockName("Berkshire Hathaway Inc Class B")).toBe("Berkshire Hathaway");
  });

  it("removes commas from the display name", () => {
    expect(conciseStockName("Hershey, The Common Stock")).toBe("Hershey The");
  });
});
