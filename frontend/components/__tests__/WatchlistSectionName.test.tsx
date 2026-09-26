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

  it("shortens Credo Technology Group Holdings to Credo Technology", () => {
    expect(conciseStockName("Credo Technology Group Holdings")).toBe("Credo Technology");
  });

  it("shortens Credo Technology Group Holding to Credo Technology", () => {
    expect(conciseStockName("Credo Technology Group Holding")).toBe("Credo Technology");
    expect(conciseStockName("Credo Technology Group Holding Ltd")).toBe("Credo Technology");
  });
});
