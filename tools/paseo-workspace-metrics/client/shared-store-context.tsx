import { createContext, useContext, type ReactNode } from "react";
import type { SharedStore } from "./shared-store";

/** The scope, refresh revision and surface ownership one client shares. */
export const SharedStoreContext = createContext<SharedStore | null>(null);

export function useSharedStore(): SharedStore {
  const store = useContext(SharedStoreContext);
  if (!store) throw new Error("A workspace-metrics surface needs its client's shared store");
  return store;
}

export function SharedStoreProvider({ store, children }: { store: SharedStore; children: ReactNode }) {
  return <SharedStoreContext.Provider value={store}>{children}</SharedStoreContext.Provider>;
}
