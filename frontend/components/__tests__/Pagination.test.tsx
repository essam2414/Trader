// Tests for Pagination: verifies the range label renders, buttons disable
// at the bounds, and clicking Prev/Next invokes the provided handlers.

import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { Pagination } from "../Pagination";

describe("Pagination", () => {
  it("renders the range label", () => {
    render(
      <Pagination
        rangeStart={11}
        rangeEnd={20}
        totalCount={1791}
        canGoPrev={true}
        canGoNext={true}
        onPrev={() => {}}
        onNext={() => {}}
      />
    );

    expect(screen.getByText("11–20 of 1,791")).toBeInTheDocument();
  });

  it("disables Prev on the first page and calls onNext when Next is clicked", () => {
    const onNext = vi.fn();
    render(
      <Pagination
        rangeStart={1}
        rangeEnd={10}
        totalCount={25}
        canGoPrev={false}
        canGoNext={true}
        onPrev={() => {}}
        onNext={onNext}
      />
    );

    expect(screen.getByRole("button", { name: "Previous" })).toBeDisabled();
    fireEvent.click(screen.getByRole("button", { name: "Next" }));
    expect(onNext).toHaveBeenCalledOnce();
  });

  it("disables Next on the last page and calls onPrev when Prev is clicked", () => {
    const onPrev = vi.fn();
    render(
      <Pagination
        rangeStart={21}
        rangeEnd={25}
        totalCount={25}
        canGoPrev={true}
        canGoNext={false}
        onPrev={onPrev}
        onNext={() => {}}
      />
    );

    expect(screen.getByRole("button", { name: "Next" })).toBeDisabled();
    fireEvent.click(screen.getByRole("button", { name: "Previous" }));
    expect(onPrev).toHaveBeenCalledOnce();
  });
});
