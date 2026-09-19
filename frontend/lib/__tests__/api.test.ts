import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { getPortfolioCurrent, getPortfolioHistory } from "../api";

describe("portfolio API client", () => {
  beforeEach(() => {
    process.env.BACKEND_URL = "https://backend.example.com";
    process.env.DASHBOARD_API_KEY = "test-key";
  });

  afterEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  it("fetches current portfolio from the backend with the bearer token", async () => {
    const mockResponse = {
      account: {
        id: 1,
        currency: "USD",
        totalValue: 100,
        cash: { availableToTrade: 0, inPies: 0, reservedForOrders: 0 },
        unrealizedProfitLoss: 0,
        realizedProfitLoss: 0,
      },
      positions: [],
    };
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => mockResponse,
    });
    vi.stubGlobal("fetch", fetchMock);

    const result = await getPortfolioCurrent();

    expect(fetchMock).toHaveBeenCalledWith(
      "https://backend.example.com/api/portfolio/current",
      expect.objectContaining({ headers: { Authorization: "Bearer test-key" } })
    );
    expect(result).toEqual(mockResponse);
  });

  it("throws when the backend responds with an error status", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({ ok: false, status: 500, json: async () => ({}) })
    );

    await expect(getPortfolioCurrent()).rejects.toThrow("Failed to fetch current portfolio: 500");
  });

  it("fetches portfolio history from the backend", async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, status: 200, json: async () => [] });
    vi.stubGlobal("fetch", fetchMock);

    await getPortfolioHistory();

    expect(fetchMock).toHaveBeenCalledWith(
      "https://backend.example.com/api/portfolio/history",
      expect.objectContaining({ headers: { Authorization: "Bearer test-key" } })
    );
  });
});
