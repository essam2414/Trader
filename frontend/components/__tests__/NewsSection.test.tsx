import { fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { NewsSection } from "../NewsSection";

describe("NewsSection", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("orders unique cards by last update and keeps card content compact", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        json: async () => [
          newsArticle(2, "Later headline", "2026-09-21T11:00:00Z"),
          newsArticle(1, "Earlier headline", "2026-09-21T09:00:00Z"),
          { ...newsArticle(1, "Earlier revision", "2026-09-21T09:00:00Z"), updatedAt: "2026-09-21T10:00:00Z" },
        ],
      }),
    );

    render(<NewsSection />);

    const earlierCard = await screen.findByRole("button", { name: /earlier revision/i });
    const laterCard = screen.getByRole("button", { name: /later headline/i });
    expect(laterCard.compareDocumentPosition(earlierCard) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(screen.queryByRole("button", { name: /earlier headline/i })).not.toBeInTheDocument();
    expect(within(laterCard).queryByText("A concise summary")).not.toBeInTheDocument();
    expect(within(laterCard).queryByText(/Created/)).not.toBeInTheDocument();
    expect(within(laterCard).getByText(/Last updated/)).toBeInTheDocument();

    fireEvent.click(laterCard);

    const dialog = screen.getByRole("dialog");
    expect(within(dialog).getByText("Benzinga")).toBeInTheDocument();
    expect(within(dialog).getByText("Full Alpaca content")).toBeInTheDocument();
    expect(within(dialog).getByText(/\[\s*"AAPL"\s*\]/)).toBeInTheDocument();
  });

  it("keeps its header outside a scrollable pane that contains every article", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        json: async () => Array.from({ length: 7 }, (_, index) => {
          const id = index + 1;
          return newsArticle(id, `Headline ${id}`, `2026-09-21T0${id}:00:00Z`);
        }),
      }),
    );

    render(<NewsSection />);

    expect(await screen.findByRole("button", { name: /headline 7/i })).toBeInTheDocument();
    expect(screen.queryByText("Watchlist only")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: /headline 2/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /headline 1/i })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Next news page" })).not.toBeInTheDocument();
    expect(screen.getByLabelText("News articles")).toHaveClass("overflow-y-auto");
    expect(screen.getByLabelText("News")).toHaveClass("flex-col");
  });
});

function newsArticle(id: number, headline: string, createdAt: string) {
  return {
    id,
    headline,
    summary: "A concise summary",
    createdAt,
    updatedAt: createdAt,
    watchlistSymbols: ["AAPL"],
    rawData: {
      id,
      headline,
      source: "Benzinga",
      content: "Full Alpaca content",
      symbols: ["AAPL"],
    },
  };
}
