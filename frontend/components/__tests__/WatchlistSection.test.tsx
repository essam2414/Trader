import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { WatchlistSection } from "../WatchlistSection";

describe("WatchlistSection search", () => {
  afterEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
    Reflect.deleteProperty(document, "elementFromPoint");
    Reflect.deleteProperty(HTMLElement.prototype, "animate");
  });

  it("closes an open search panel when the user clicks away", () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({ ok: true, json: async () => [] }),
    );
    render(<WatchlistSection />);

    fireEvent.change(screen.getByRole("combobox", { name: /search us equities/i }), {
      target: { value: "AAPL" },
    });
    expect(screen.getByText("Searching…")).toBeInTheDocument();

    fireEvent.pointerDown(document.body);

    expect(screen.queryByText("Searching…")).not.toBeInTheDocument();
  });

  it("renders watchlist quotes as a compact list rather than a table", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        json: async () => [
          {
            assetId: "asset-1",
            symbol: "NOW",
            name: "ServiceNow Inc Common Stock",
            exchange: "NASDAQ",
            sortOrder: 0,
            addedAt: "2026-09-18T13:30:00Z",
            logoUrl: "/api/watchlist/asset-1/logo",
            quote: {
              price: 136.01,
              previousClose: 135.47,
              dollarChange: 0.54,
              percentChange: 0.4,
              sparkline: [
                { timestamp: "2026-09-18T13:30:00Z", close: 135.47 },
                { timestamp: "2026-09-18T13:35:00Z", close: 136.01 },
              ],
              feed: "iex",
              sourceTimestamp: "2026-09-18T13:35:00Z",
              sourceType: "trade",
              freshness: "fresh",
              isExtendedHours: false,
            },
          },
        ],
      }),
    );

    const { container } = render(<WatchlistSection />);

    expect(await screen.findByText("ServiceNow")).toBeInTheDocument();
    expect(screen.getByText("↗ 0.40%")).toBeInTheDocument();
    expect(screen.getByText("$136.01")).toBeInTheDocument();
    expect(container.querySelector("table")).not.toBeInTheDocument();
    expect(screen.queryByText("Regular session")).not.toBeInTheDocument();
    expect(screen.getByLabelText("Watchlist entries")).toHaveClass("mt-2", "overflow-y-auto");
    expect(screen.getByText("ServiceNow").closest(".space-y-1")).toHaveClass("mt-2");
    expect(screen.getByLabelText("Watchlist")).toHaveClass("flex-col");
    expect(screen.getByRole("heading", { name: "Watchlist" }).parentElement?.parentElement).toHaveClass("flex-nowrap");
    expect(screen.getByRole("heading", { name: "Watchlist" }).parentElement?.parentElement).toHaveClass("gap-x-8");
    expect(screen.getByRole("heading", { name: "Watchlist" }).parentElement).toHaveClass("relative");
    expect(screen.getByText("US market schedule unavailable").parentElement).toHaveClass("top-10", "text-sm");
    expect(screen.getByRole("combobox", { name: /search us equities/i }).parentElement).toHaveClass(
      "w-32",
    );
    expect(screen.getByRole("combobox", { name: /search us equities/i }).parentElement).not.toHaveClass(
      "ml-auto",
    );
    expect(screen.getByRole("heading", { name: "Watchlist" }).parentElement?.nextElementSibling)
      .toContainElement(screen.getByRole("combobox", { name: /search us equities/i }));
    expect(screen.getByRole("heading", { name: "Watchlist" }).parentElement?.nextElementSibling).toHaveClass(
      "gap-5",
    );
    expect(screen.getByRole("combobox", { name: /search us equities/i })).toHaveClass("h-8");
  });

  it("patches a watchlist price from an incoming IEX stream trade", async () => {
    const sources: FakeEventSource[] = [];
    class FakeEventSource {
      onerror: (() => void) | null = null;
      private listeners = new Map<string, Array<(event: MessageEvent<string>) => void>>();

      constructor(readonly url: string) {
        sources.push(this);
      }

      addEventListener(type: string, listener: (event: MessageEvent<string>) => void) {
        this.listeners.set(type, [...(this.listeners.get(type) ?? []), listener]);
      }

      close() {}

      emit(type: string, data: unknown) {
        for (const listener of this.listeners.get(type) ?? []) {
          listener({ data: JSON.stringify(data) } as MessageEvent<string>);
        }
      }
    }
    vi.stubGlobal("EventSource", FakeEventSource);
    vi.stubGlobal(
      "fetch",
      vi.fn((input: string) => Promise.resolve({
        ok: true,
        json: async () => input === "/api/market-session" ? { phase: "closed" } : watchlistEntries(),
      })),
    );

    render(<WatchlistSection />);
    await screen.findByText("$188.25");
    expect(sources).toHaveLength(1);
    expect(sources[0].url).toBe("/api/watchlist/stream");

    sources[0].emit("quote", {
      symbol: "AAPL",
      price: 189.5,
      sourceTimestamp: "2026-09-22T14:00:00Z",
      sourceType: "iex_trade_stream",
      freshness: "fresh",
      isExtendedHours: false,
    });

    expect(await screen.findByText("$189.50")).toBeInTheDocument();
    expect(screen.getByText(/1\.20%/)).toBeInTheDocument();
  });

  it("does not treat a scroll between IEX quote events as a row reorder", async () => {
    const sources: FakeEventSource[] = [];
    class FakeEventSource {
      onerror: (() => void) | null = null;
      private listeners = new Map<string, Array<(event: MessageEvent<string>) => void>>();

      constructor() {
        sources.push(this);
      }

      addEventListener(type: string, listener: (event: MessageEvent<string>) => void) {
        this.listeners.set(type, [...(this.listeners.get(type) ?? []), listener]);
      }

      close() {}

      emit(type: string, data: unknown) {
        for (const listener of this.listeners.get(type) ?? []) {
          listener({ data: JSON.stringify(data) } as MessageEvent<string>);
        }
      }
    }
    let scrollOffset = 0;
    const animate = vi.fn(() => ({ cancel: vi.fn() }) as unknown as Animation);
    Object.defineProperty(HTMLElement.prototype, "animate", { configurable: true, value: animate });
    vi.spyOn(HTMLElement.prototype, "getBoundingClientRect").mockImplementation(function (this: HTMLElement) {
      const index = this.dataset.watchlistEntry === "aapl" ? 0 : this.dataset.watchlistEntry === "msft" ? 1 : -1;
      return {
        left: 0,
        top: index < 0 ? 0 : 100 + index * 68 - scrollOffset,
        width: 320,
        height: index < 0 ? 0 : 68,
      } as DOMRect;
    });
    vi.stubGlobal("EventSource", FakeEventSource);
    vi.stubGlobal(
      "fetch",
      vi.fn((input: string) => Promise.resolve({
        ok: true,
        json: async () => input === "/api/market-session" ? { phase: "closed" } : watchlistEntries(),
      })),
    );

    render(<WatchlistSection />);
    await screen.findByText("$188.25");
    animate.mockClear();
    scrollOffset = 60;

    sources[0].emit("quote", {
      symbol: "AAPL",
      price: 189.5,
      sourceTimestamp: "2026-09-22T14:00:00Z",
      sourceType: "iex_trade_stream",
      freshness: "fresh",
      isExtendedHours: false,
    });

    await screen.findByText("$189.50");
    expect(animate).not.toHaveBeenCalled();
  });

  it("shows the current US market session beneath the watchlist heading in one line", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn((input: string) => Promise.resolve({
        ok: true,
        json: async () => input === "/api/market-session"
          ? {
              phase: "regular",
              asOf: "2026-09-18T14:00:00Z",
              endsAt: "2026-09-18T20:00:00Z",
              nextPhase: "after_hours",
              nextPhaseStartsAt: "2026-09-18T20:00:00Z",
              isEarlyClose: false,
            }
          : [],
      })),
    );

    render(<WatchlistSection />);

    const reminder = await screen.findByText("US regular hours · closes 21:00 UK");
    expect(reminder.parentElement).toHaveClass("whitespace-nowrap");
  });

  it.each([
    ["pre_market", "pre-market", "bg-orange-400", "text-orange-300"],
    ["regular", "regular hours", "bg-green-400", "text-green-300"],
    ["after_hours", "after-hours", "bg-pink-400", "text-pink-300"],
    ["overnight", "overnight", "bg-blue-400", "text-blue-300"],
  ])("uses the requested colour for %s session", async (phase, label, dotColour, textColour) => {
    vi.stubGlobal(
      "fetch",
      vi.fn((input: string) => Promise.resolve({
        ok: true,
        json: async () => input === "/api/market-session"
          ? {
              phase,
              asOf: "2026-09-18T14:00:00Z",
              endsAt: "2026-09-18T20:00:00Z",
              nextPhase: "after_hours",
              nextPhaseStartsAt: "2026-09-18T20:00:00Z",
              isEarlyClose: false,
            }
          : [],
      })),
    );

    render(<WatchlistSection />);

    const reminder = await screen.findByText(new RegExp(`US ${label}`));
    expect(reminder.parentElement).toHaveClass(textColour);
    expect(reminder.parentElement?.querySelector("[aria-hidden='true']")).toHaveClass(dotColour);
  });

  it("moves the dragged row itself while the other rows reorder", async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => watchlistEntries() });
    vi.stubGlobal("fetch", fetchMock);
    render(<WatchlistSection />);

    await screen.findByText("Apple");
    fireEvent.click(screen.getByRole("button", { name: "Move" }));

    const apple = screen.getByText("Apple").closest("[data-watchlist-entry]");
    const microsoft = screen.getByText("Microsoft").closest("[data-watchlist-entry]");
    expect(apple).not.toBeNull();
    expect(microsoft).not.toBeNull();

    vi.spyOn(apple!, "getBoundingClientRect").mockReturnValue({
      left: 0,
      top: 0,
      width: 320,
      height: 68,
    } as DOMRect);
    Object.defineProperty(apple!, "setPointerCapture", { configurable: true, value: vi.fn() });
    Object.defineProperty(document, "elementFromPoint", {
      configurable: true,
      value: () => microsoft,
    });

    fireEvent.pointerDown(apple!, { pointerId: 1, clientX: 20, clientY: 10 });
    await waitFor(() => expect(apple).toHaveStyle({ position: "fixed" }));
    expect(apple).toHaveAttribute("draggable", "false");

    fireEvent.pointerMove(apple!, { pointerId: 1, clientX: 40, clientY: 100 });

    await waitFor(() => expect(entryIds()).toEqual(["msft", "aapl"]));
    expect(apple).toHaveStyle({ left: "0px" });

    fireEvent.pointerUp(window, { pointerId: 1 });
    await waitFor(() => expect(apple).not.toHaveStyle({ position: "fixed" }));
    expect(fetchMock).toHaveBeenLastCalledWith("/api/watchlist/order", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ assetIds: ["msft", "aapl"] }),
    });
  });
});

function entryIds() {
  return [...document.querySelectorAll<HTMLElement>("[data-watchlist-entry]")]
    .map((entry) => entry.dataset.watchlistEntry);
}

function watchlistEntries() {
  return [
    watchlistEntry("aapl", "AAPL", "Apple Inc Common Stock", 188.25),
    watchlistEntry("msft", "MSFT", "Microsoft Corp Common Stock", 420.34),
  ];
}

function watchlistEntry(assetId: string, symbol: string, name: string, price: number) {
  return {
    assetId,
    symbol,
    name,
    exchange: "NASDAQ",
    sortOrder: 0,
    addedAt: "2026-09-18T13:30:00Z",
    logoUrl: `/api/watchlist/${assetId}/logo`,
    quote: {
      price,
      previousClose: price - 1,
      dollarChange: 1,
      percentChange: 0.5,
      sparkline: [],
      feed: "iex",
      sourceTimestamp: "2026-09-18T13:35:00Z",
      sourceType: "trade",
      freshness: "fresh",
      isExtendedHours: false,
    },
  };
}
