import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { WatchlistSparkline } from "../WatchlistSparkline";

describe("WatchlistSparkline", () => {
  it("renders the regular-session direction for multiple data points", () => {
    render(
      <WatchlistSparkline
        positive
        points={[
          { timestamp: "2026-09-18T13:30:00Z", close: 100 },
          { timestamp: "2026-09-18T13:35:00Z", close: 102 },
        ]}
      />,
    );

    expect(screen.getByRole("img", { name: /regular-session price direction/i })).toBeInTheDocument();
  });

  it("uses an explicit unavailable state for insufficient data", () => {
    render(<WatchlistSparkline positive points={[]} />);

    expect(screen.getByText("No session data")).toBeInTheDocument();
  });
});
