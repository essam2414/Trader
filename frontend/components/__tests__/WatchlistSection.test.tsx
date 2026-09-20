import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { WatchlistSection } from "../WatchlistSection";

describe("WatchlistSection search", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
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
});
