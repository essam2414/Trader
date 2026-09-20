import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { WatchlistSparkline } from "../WatchlistSparkline";

describe("WatchlistSparkline", () => {
  it("renders the regular-session direction for multiple data points", () => {
    render(
      <WatchlistSparkline
        trend="positive"
        points={[
          { timestamp: "2026-09-18T13:30:00Z", close: 100 },
          { timestamp: "2026-09-18T13:35:00Z", close: 102 },
        ]}
      />,
    );

    const sparkline = screen.getByRole("img", { name: /regular-session price direction/i });
    expect(sparkline).toBeInTheDocument();
    expect(sparkline.querySelectorAll("polyline")).toHaveLength(2);
    expect(sparkline.querySelector("polyline")?.getAttribute("stroke")).toBe("#263238");
  });

  it("uses an explicit unavailable state for insufficient data", () => {
    render(<WatchlistSparkline trend="neutral" points={[]} />);

    expect(screen.getByText("No session data")).toBeInTheDocument();
  });

  it("keeps a neutral chart fully muted", () => {
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

    expect(screen.getByRole("img").querySelectorAll("polyline")).toHaveLength(1);
  });
});
