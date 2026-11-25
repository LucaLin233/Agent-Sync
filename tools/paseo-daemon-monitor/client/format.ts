export function percentText(value: number | null | undefined): string {
  if (value === null || value === undefined) return "—";
  // A real 0 stays "0%" so it can never be read as a missing sample.
  if (value === 0) return "0%";
  return `${value.toFixed(value >= 10 ? 0 : 1)}%`;
}

export function bytesText(value: number | null | undefined): string {
  if (value === null || value === undefined) return "—";
  const gib = value / 1024 ** 3;
  if (gib >= 1) return `${gib.toFixed(1)} GiB`;
  return `${(value / 1024 ** 2).toFixed(0)} MiB`;
}

/**
 * Short footer rate in binary units, matching the detail card: `2.4M` / `640K`
 * / `12K`. Unknown stays an em dash so a missing sample never reads as 0 B/s.
 */
export function shortRate(value: number | null | undefined): string {
  if (value === null || value === undefined) return "—";
  const kib = value / 1024;
  const mib = kib / 1024;
  // A gigabyte tier keeps the label short and bounded: at most `9990G`, so the
  // widest label stays arrow + 5 characters and the footer budget can rely on it.
  if (mib >= 1024) return `${Math.min(9990, Math.round(mib / 1024))}G`;
  if (kib >= 1024) return `${mib.toFixed(mib >= 10 ? 0 : 1)}M`;
  if (kib >= 10) return `${kib.toFixed(0)}K`;
  if (kib >= 0.1) return `${kib.toFixed(1)}K`;
  return `${Math.round(value)}B`;
}

/** Detail rate keeps the unit explicit: `2.4 MiB/s`. */
export function rateText(value: number | null | undefined): string {
  if (value === null || value === undefined) return "—";
  const kib = value / 1024;
  if (kib >= 1024) return `${(kib / 1024).toFixed(1)} MiB/s`;
  if (kib >= 1) return `${kib.toFixed(kib >= 100 ? 0 : 1)} KiB/s`;
  return `${Math.round(value)} B/s`;
}

export function timeText(iso: string | null | undefined): string {
  if (!iso) return "—";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "—";
  return date.toLocaleTimeString("zh-CN", { hour12: false });
}

/** `6 天 04:22` style uptime; null stays an em dash. */
export function uptimeText(seconds: number | null | undefined): string {
  if (seconds === null || seconds === undefined) return "—";
  const total = Math.max(0, Math.floor(seconds));
  const days = Math.floor(total / 86400);
  const hours = Math.floor((total % 86400) / 3600);
  const minutes = Math.floor((total % 3600) / 60);
  if (days > 0) return `${days} 天 ${String(hours).padStart(2, "0")}:${String(minutes).padStart(2, "0")}`;
  return `${String(hours).padStart(2, "0")}:${String(minutes).padStart(2, "0")}`;
}

export function loadText(load: { one: number; five: number; fifteen: number } | null | undefined): string {
  if (!load) return "—";
  const part = (value: number) => value.toFixed(2);
  return `${part(load.one)} / ${part(load.five)} / ${part(load.fifteen)}`;
}
