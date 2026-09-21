import { describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({ redirect: vi.fn() }));

vi.mock("next/navigation", () => ({ redirect: mocks.redirect }));

import HomePage from "./page";

describe("HomePage", () => {
  it("opens the dashboard by default", () => {
    HomePage();

    expect(mocks.redirect).toHaveBeenCalledWith("/dashboard");
  });
});
