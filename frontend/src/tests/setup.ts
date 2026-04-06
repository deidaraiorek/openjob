import "@testing-library/jest-dom/vitest";

Object.defineProperty(window, "AbortSignal", {
  value: globalThis.AbortSignal,
  configurable: true,
});

Object.defineProperty(window, "Request", {
  value: globalThis.Request,
  configurable: true,
});

Object.defineProperty(window, "Response", {
  value: globalThis.Response,
  configurable: true,
});

Object.defineProperty(window, "Headers", {
  value: globalThis.Headers,
  configurable: true,
});
