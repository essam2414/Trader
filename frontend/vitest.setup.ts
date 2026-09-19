import { cleanup } from "@testing-library/react";
import { afterEach } from "vitest";

import "@testing-library/jest-dom/vitest";

// Unmount and clean up the DOM after every test. Without this, each test's
// rendered output stays in the DOM for subsequent tests in the same file,
// which silently breaks any query that expects a single match (e.g.
// getByRole) once more than one test in a file renders similar markup.
afterEach(() => {
  cleanup();
});

// Mock ResizeObserver for recharts compatibility in jsdom
global.ResizeObserver = class ResizeObserver {
  constructor(callback: ResizeObserverCallback) {}
  observe() {}
  unobserve() {}
  disconnect() {}
};
