import { act, render } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const refresh = vi.fn();

vi.mock("next/navigation", () => ({
  useRouter: () => ({ refresh }),
}));

import { PortfolioAutoRefresh } from "../PortfolioAutoRefresh";

describe("PortfolioAutoRefresh", () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    Object.defineProperty(document, "visibilityState", { configurable: true, value: "visible" });
    vi.useRealTimers();
    refresh.mockReset();
  });

  it("refreshes the visible portfolio overview every five seconds", () => {
    render(<PortfolioAutoRefresh />);

    act(() => {
      vi.advanceTimersByTime(5_000);
    });

    expect(refresh).toHaveBeenCalledTimes(1);
  });

  it("does not refresh while the portfolio overview tab is hidden", () => {
    Object.defineProperty(document, "visibilityState", { configurable: true, value: "hidden" });
    render(<PortfolioAutoRefresh />);

    act(() => {
      vi.advanceTimersByTime(5_000);
    });

    expect(refresh).not.toHaveBeenCalled();
  });
});
