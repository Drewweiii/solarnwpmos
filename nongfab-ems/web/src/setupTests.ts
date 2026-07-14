import '@testing-library/jest-dom/vitest'

// jsdom has no ResizeObserver; Recharts' <ResponsiveContainer> needs one to
// measure its box and render children at all.
class ResizeObserverStub {
  observe() {}
  unobserve() {}
  disconnect() {}
}
globalThis.ResizeObserver = ResizeObserverStub
