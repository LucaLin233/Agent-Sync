/**
 * TanStack reads `isServer` once, when query-core is first imported, and then
 * disables `refetchInterval` (and window focus handling) in that mode. Node's
 * test runner has no `window`, but the real clients — the desktop/mobile web
 * UI and React Native, where `window === global` — are not servers. This module
 * runs first (import order), so the module under test sees the same condition
 * the app has.
 */
if (typeof globalThis.window === "undefined") globalThis.window = globalThis;
