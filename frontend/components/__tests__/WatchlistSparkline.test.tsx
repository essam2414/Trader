import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { WatchlistSparkline } from "../WatchlistSparkline";
import { createSparklinePath, mergeLiveSparklinePrice } from "../../lib/watchlistSparkline";

describe("WatchlistSparkline", () => {
  afterEach(() => {
    vi.useRealTimers();
  });

  it("renders the regular-session direction for multiple data points", () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-09-18T14:00:00Z"));
    render(
      <WatchlistSparkline
        trend="positive"
        points={[
          { timestamp: "2026-09-18T13:30:00Z", close: 100 },
          { timestamp: "2026-09-18T13:35:00Z", close: 102 },
        ]}
      />,
    );

    const sparkline = screen.getByRole("img", { name: /24-hour price direction/i });
    expect(sparkline).toBeInTheDocument();
    expect(sparkline.querySelectorAll("path")).toHaveLength(1);
    expect(sparkline.querySelector("path")).toHaveAttribute("stroke", "#42d95a");
    expect(sparkline.querySelector("path")).toHaveAttribute("stroke-width", "2.25");
    expect(sparkline.querySelector("path")).toHaveAttribute("stroke-linejoin", "round");
  });

  it("uses an explicit unavailable state for insufficient data", () => {
    render(<WatchlistSparkline trend="neutral" points={[]} />);

    expect(screen.getByText("No session data")).toBeInTheDocument();
  });

  it("keeps a neutral chart fully muted", () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-09-18T14:00:00Z"));
    render(
      <WatchlistSparkline
        trend="neutral"
        points={[
          { timestamp: "2026-09-18T13:30:00Z", close: 100 },
          { timestamp: "2026-09-18T13:35:00Z", close: 100 },
          { timestamp: "2026-09-18T13:40:00Z", close: 100 },
        ]}
      />,
    );

    expect(screen.getByRole("img").querySelector("path")).toHaveAttribute("stroke", "#78838a");
  });

  it("uses the full chart width for the available 24-hour price samples", () => {
    const path = createSparklinePath(
      [
        { timestamp: "2026-09-18T00:00:00Z", close: 100 },
        { timestamp: "2026-09-18T01:00:00Z", close: 101 },
        { timestamp: "2026-09-19T00:00:00Z", close: 102 },
      ],
      Date.parse("2026-09-19T00:00:00Z"),
    );

    expect(path).toBe("M 3 33 L 52 18 L 101 3");
  });

  it("replaces the active 15-minute point when a live quote arrives", () => {
    expect(
      mergeLiveSparklinePrice(
        [
          { timestamp: "2026-09-18T13:30:00Z", close: 100 },
          { timestamp: "2026-09-18T13:45:00Z", close: 101 },
        ],
        { timestamp: "2026-09-18T13:37:12Z", close: 102 },
        Date.parse("2026-09-18T14:00:00Z"),
      ),
    ).toEqual([
      { timestamp: "2026-09-18T13:30:00.000Z", close: 102 },
      { timestamp: "2026-09-18T13:45:00Z", close: 101 },
    ]);
  });
});
