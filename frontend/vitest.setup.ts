import "@testing-library/jest-dom/vitest";

// Mock ResizeObserver for recharts compatibility in jsdom
global.ResizeObserver = class ResizeObserver {
  constructor(callback: ResizeObserverCallback) {}
  observe() {}
  unobserve() {}
  disconnect() {}
};
