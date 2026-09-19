// Tests for the dashboard route's error boundary (app/error.tsx).
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import DashboardError from "../error";

describe("DashboardError", () => {
  it("shows a Trading212-specific message when the backend returned a 502", () => {
    render(<DashboardError error={new Error("Failed to fetch current portfolio: 502")} reset={() => {}} />);

    expect(screen.getByText(/couldn't connect to trading212/i)).toBeInTheDocument();
  });

  it("shows a generic message for other errors", () => {
    render(<DashboardError error={new Error("Failed to fetch current portfolio: 500")} reset={() => {}} />);

    expect(screen.getByText(/something went wrong loading your data/i)).toBeInTheDocument();
  });

  it("calls reset when the Try again button is clicked", () => {
    const reset = vi.fn();
    render(<DashboardError error={new Error("boom")} reset={reset} />);

    screen.getByRole("button", { name: /try again/i }).click();

    expect(reset).toHaveBeenCalledOnce();
  });
});
