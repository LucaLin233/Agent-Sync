import { createContext, useContext } from "react";
import type { CumulativeHub } from "./cumulative-hub";

export type { CumulativeHub };

/**
 * The hub this client's pill runtime and panels share. `contribute` creates one
 * per loaded client bundle and provides it to every surface, so a reading either
 * entry point obtains is visible to both without crossing into another client.
 */
export const CumulativeHubContext = createContext<CumulativeHub | null>(null);

export function useCumulativeHub(): CumulativeHub {
  const hub = useContext(CumulativeHubContext);
  if (!hub) throw new Error("A workspace-metrics surface needs its client's cumulative hub");
  return hub;
}
