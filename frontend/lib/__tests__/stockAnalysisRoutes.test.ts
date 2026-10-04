import { afterEach, describe, expect, it, vi } from "vitest";
import { watchlistBackendRequest } from "../watchlistRoute";
import { GET as news } from "../../app/api/news/route";
import { GET as analysis } from "../../app/api/watchlist/[assetId]/analysis/route";

vi.mock("../watchlistRoute", () => ({ watchlistBackendRequest: vi.fn().mockResolvedValue(new Response("{}")) }));
afterEach(() => vi.clearAllMocks());

describe("authenticated stock pane proxies", () => {
  it("forwards stock filtering and pagination without forwarding arbitrary parameters", async () => {
    await news(new Request("http://localhost/api/news?assetId=asset-sndk&limit=21&offset=20&token=unrelated"));
    expect(watchlistBackendRequest).toHaveBeenCalledWith("/api/news?assetId=asset-sndk&limit=21&offset=20");
  });
  it("preserves the existing dashboard news request", async () => {
    await news(new Request("http://localhost/api/news"));
    expect(watchlistBackendRequest).toHaveBeenCalledWith("/api/news");
  });
  it("encodes the asset in the analysis route", async () => {
    await analysis(new Request("http://localhost/api/watchlist/asset/analysis"), { params: Promise.resolve({ assetId: "asset/?" }) });
    expect(watchlistBackendRequest).toHaveBeenCalledWith("/api/watchlist/asset%2F%3F/analysis");
  });
});
