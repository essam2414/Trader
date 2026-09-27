import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { Sidebar } from "../Sidebar";

vi.mock("next/navigation", () => ({ usePathname: () => "/dashboard" }));

const event = {
  id: "earnings:acme:2026-10-21",
  title: "Acme earnings report",
  category: "earnings",
  scope: "watchlist" as const,
  eventDate: "2026-10-21",
  previousEventDate: null,
  startsAt: null,
  timePrecision: "date_only" as const,
  dateStatus: "confirmed" as const,
  watchlistSymbols: ["ACME"],
  sourceUrl: "https://example.com/calendar",
  lastVerifiedAt: "2026-09-25T06:00:00Z",
};

describe("Sidebar", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("shows the soonest upcoming event in the sidebar card", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => ({
      ok: true,
      json: async () => [
        { ...event, id: "earnings:later", title: "Later earnings", eventDate: "2026-11-05" },
        event,
      ],
    })));

    render(<Sidebar />);

    const card = await screen.findByRole("region", { name: "Next event" });
    expect(card).toHaveClass("bg-orange-900/60");
    expect(card).toHaveTextContent("21 Oct 2026");
    expect(card).not.toHaveTextContent("ACME");
    expect(screen.queryByRole("link", { name: /Acme earnings report/i })).not.toBeInTheDocument();
    await waitFor(() => expect(fetch).toHaveBeenCalledWith("/api/events", expect.objectContaining({ cache: "no-store" })));
  });

  it("handles an empty event list without leaving stale event content", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => ({ ok: true, json: async () => [] })));

    render(<Sidebar />);

    expect(await screen.findByText("No upcoming events")).toBeInTheDocument();
  });
});
