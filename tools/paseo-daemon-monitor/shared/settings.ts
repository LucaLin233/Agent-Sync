import { defineSettings } from "@getpaseo/plugin";
import { z } from "zod";

/**
 * Host-scoped settings: they live in the selected daemon's plugin settings,
 * affect only this installation, and every client connected to that daemon
 * sees the same values.
 */
export const monitorSettings = defineSettings({
  id: "daemon-monitor",
  scope: "host",
  version: 1,
  schema: z.object({
    /** Sampling cadence for CPU, memory and network. */
    intervalMs: z.union([z.literal(2000), z.literal(5000), z.literal(10000)]).default(2000),
    /** Footer only; the detail popover always shows network figures. */
    showNetworkInFooter: z.boolean().default(true),
  }),
});

export type MonitorSettings = z.infer<typeof monitorSettings.schema>;

export const DEFAULT_SETTINGS: MonitorSettings = { intervalMs: 2000, showNetworkInFooter: true };

export type IntervalValue = "2000" | "5000" | "10000";

/** Options for the native SettingsSelect; values are the persisted milliseconds. */
export const INTERVAL_OPTIONS: readonly { label: string; value: IntervalValue }[] = [
  { label: "2 秒", value: "2000" },
  { label: "5 秒", value: "5000" },
  { label: "10 秒", value: "10000" },
];

export function parseInterval(value: string | number | undefined): MonitorSettings["intervalMs"] {
  const n = Number(value);
  return n === 5000 || n === 10000 ? n : 2000;
}
