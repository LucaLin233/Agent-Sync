import {
  type PluginPopoverProps,
  type PluginSidebarItemProps,
  useHosts,
  useRpc,
  useSettings,
} from "@getpaseo/plugin/client";
import { Icon } from "@getpaseo/plugin/client/ui";
import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { AppState, Pressable, Text, View, useWindowDimensions } from "react-native";
import { hostResourcesRpc, type HostResources } from "../shared/contract.ts";
import { buildSeries, drawnPoints, type SeriesRun } from "../shared/history.ts";
import { chooseFooterPlan, FOOTER_HEIGHT } from "../shared/layout.ts";
import { DEFAULT_SETTINGS, monitorSettings } from "../shared/settings.ts";
import { bytesText, loadText, percentText, rateText, shortRate, timeText, uptimeText } from "./format.ts";

type Colors = PluginPopoverProps["theme"]["colors"];
type Status = "loading" | "live" | "stale" | "failed";

const hostStatusLabels: Record<string, string> = {
  idle: "未连接",
  connecting: "连接中",
  online: "已连接",
  offline: "离线",
  error: "连接异常",
};

/**
 * One shared reading per daemon: the footer and the popover both poll, but the
 * daemon serves the same cached sample, so they never double-sample. Polling
 * runs only while a surface is mounted and the app is in the foreground.
 */
function useSample(hostId: string, intervalMs: number) {
  const sample = useRpc(hostResourcesRpc);
  const [state, setState] = useState<{ hostId: string; value: HostResources } | null>(null);
  const [status, setStatus] = useState<Status>("loading");
  const [failing, setFailing] = useState(false);
  const [tick, setTick] = useState(0);
  const [awake, setAwake] = useState(AppState.currentState === "active");
  const mounted = useRef(true);

  useEffect(() => {
    mounted.current = true;
    const subscription = AppState.addEventListener("change", (next) => setAwake(next === "active"));
    setAwake(AppState.currentState === "active");
    return () => {
      mounted.current = false;
      subscription.remove();
    };
  }, []);

  useEffect(() => {
    if (!awake) return;
    let cancelled = false;
    let reportedFailure = false;
    let timer: ReturnType<typeof setTimeout> | undefined;

    const run = async () => {
      try {
        const value = await sample({});
        if (cancelled || !mounted.current) return;
        reportedFailure = false;
        const age = Date.now() - Date.parse(value.sampledAt);
        // Same three-interval tolerance the daemon uses to drop a stale payload.
        const old = Number.isFinite(age) && age > intervalMs * 3;
        setState({ hostId, value });
        setStatus(old ? "stale" : "live");
        setFailing(old);
      } catch (error) {
        if (cancelled || !mounted.current) return;
        // One line per failure streak, never per poll: enough to tell a schema
        // rejection from a transport drop without leaking payloads or hosts.
        if (!reportedFailure) {
          reportedFailure = true;
          console.warn("[daemon-monitor] host-resources.sample failed:", error instanceof Error ? error.name : "unknown");
        }
        setFailing(true);
        setStatus("failed");
      } finally {
        if (!cancelled) timer = setTimeout(run, intervalMs);
      }
    };

    void run();
    return () => {
      cancelled = true;
      if (timer) clearTimeout(timer);
    };
  }, [awake, hostId, sample, tick, intervalMs]);

  const value = state?.hostId === hostId ? state.value : null;
  return {
    value,
    status: value ? status : status === "live" ? "loading" : status,
    failing,
    refresh: () => {
      setStatus("loading");
      setTick((count) => count + 1);
    },
  };
}

/** A disconnected host keeps its last reading only as an explicitly old sample. */
function effectiveStatus(status: Status, value: HostResources | null, connection: string): Status {
  if (status === "failed" && value) return "stale";
  if (status === "live" && (connection === "offline" || connection === "error" || connection === "idle")) {
    return value ? "stale" : "failed";
  }
  return status;
}

/** Track spans the free width of its column; the fill stays a true percentage. */
/**
 * The column is a fixed third of the row, so `flexGrow` here means "everything
 * the icon and number did not need" — the bar elongates with the sidebar.
 * `width` is only the reserved length for the widest label, used as a floor.
 */
function Meter({ percent, tone, colors, width }: { percent: number | null; tone: string; colors: Colors; width: number }) {
  const fill = percent === null ? 0 : Math.min(100, Math.max(0, percent));
  return (
    <View
      accessibilityElementsHidden
      importantForAccessibility="no-hide-descendants"
      style={{ flexGrow: 1, flexShrink: 1, flexBasis: 0, minWidth: Math.min(width, 14), height: 4, borderRadius: 4, backgroundColor: colors.border, overflow: "hidden" }}
    >
      <View style={{ width: `${fill}%`, height: "100%", borderRadius: 4, backgroundColor: tone }} />
    </View>
  );
}

interface ReadingProps {
  icon: string;
  percent: number | null | undefined;
  tone: string;
  showIcon: boolean;
  /** Drawn meter length in DP; 0 hides the meter. */
  meterWidth: number;
  /** Equal column width in DP; null before the first measurement (flex share). */
  columnWidth: number | null;
  stacked: boolean;
  iconSize: number;
  iconGap: number;
  padX: number;
  colors: Colors;
  onTextWidth: (width: number) => void;
}

/**
 * Icon, then a non-shrinking number slot, then the meter eating the rest. The
 * number never shrinks or ellipsizes; only the meter gives up width.
 */
function Reading({ icon, percent, tone, showIcon, meterWidth, columnWidth, stacked, iconSize, iconGap, padX, colors, onTextWidth }: ReadingProps) {
  return (
    <View
      accessibilityElementsHidden
      importantForAccessibility="no-hide-descendants"
      style={{
        ...(columnWidth === null
          ? { flexGrow: 1, flexShrink: 1, flexBasis: 0 }
          : { width: columnWidth, flexGrow: 0, flexShrink: 0 }),
        minWidth: 0,
        flexDirection: stacked ? "column" : "row",
        alignItems: "center",
        justifyContent: stacked ? "center" : "flex-start",
        gap: iconGap,
        paddingHorizontal: padX,
      }}
    >
      {showIcon ? <Icon name={icon} size={iconSize} color={tone} /> : null}
      <Text
        numberOfLines={1}
        onLayout={(event) => onTextWidth(event.nativeEvent.layout.width)}
        style={{ color: colors.foreground, fontSize: 11, fontWeight: "700", fontVariant: ["tabular-nums"], flexShrink: 0 }}
      >
        {percentText(percent)}
      </Text>
      {meterWidth > 0 ? <Meter percent={percent ?? null} tone={tone} colors={colors} width={meterWidth} /> : null}
    </View>
  );
}

/** A HH:MM:SS clock barely fits a 48 DP track; shorter tracks keep HH:MM. */
function clockText(iso: string, trackWidth: number): string {
  const full = timeText(iso);
  if (trackWidth >= 60 || full.length <= 5) return full;
  return full.slice(0, 5);
}

export function HostMonitorItem({ theme, host, layout, openPopover }: PluginSidebarItemProps) {
  const colors = theme.colors;
  const hosts = useHosts();
  const connection = hosts.find((entry) => entry.serverId === host.id)?.status ?? "offline";
  const settings = useSettings(monitorSettings);
  const intervalMs = settings.status === "ready" ? settings.values.intervalMs : DEFAULT_SETTINGS.intervalMs;
  const networkEnabled = settings.status === "ready" ? settings.values.showNetworkInFooter : DEFAULT_SETTINGS.showNetworkInFooter;
  const { value, status } = useSample(host.id, intervalMs);
  const shown = effectiveStatus(status, value, connection);
  const cpu = percentText(value?.cpuPercent);
  const memory = percentText(value?.memoryPercent);
  const disk = percentText(value?.diskTotal?.percent ?? value?.disk?.percent);
  const anomaly = shown === "stale" ? "旧样本" : shown === "failed" ? "读取失败" : null;
  const { fontScale } = useWindowDimensions();
  const [width, setWidth] = useState<number | null>(null);
  const [textWidths, setTextWidths] = useState<(number | null)[]>([null, null, null]);
  // A real 0 B/s is a measurement, not a missing sample: only null disables it.
  const networkAvailable = Boolean(
    value?.network && (value.network.rxBytesPerSecond !== null || value.network.txBytesPerSecond !== null),
  );

  // Before the first measurement, reserve for the widest plausible label at the
  // user's own font scale so the tier choice is not optimistic.
  const fallbackText = Math.ceil(40 * fontScale);
  const plan = chooseFooterPlan({
    width,
    textWidths: textWidths.map((value) => value ?? fallbackText),
    // The plan decides from the measured percentages plus a font-scaled rate
    // budget: if the fourth group would squeeze a percentage out of one line it
    // is not drawn at all, and its space returns to the three columns.
    networkAvailable,
    showNetworkSetting: networkEnabled,
    compact: layout.compact,
    fontScale,
  });

  const recordTextWidth = (index: number, measured: number) => {
    setTextWidths((previous) => {
      if (Math.abs((previous[index] ?? -1) - measured) < 0.5) return previous;
      const next = previous.slice();
      next[index] = measured;
      return next;
    });
  };

  const rateLabel = networkAvailable
    ? `，下行 ${rateText(value?.network?.rxBytesPerSecond)}，上行 ${rateText(value?.network?.txBytesPerSecond)}`
    : "";

  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={`宿主机资源：CPU ${cpu}，内存 ${memory}，硬盘 ${disk}${rateLabel}，${hostStatusLabels[connection] ?? connection}${anomaly ? `，${anomaly}` : ""}`}
      accessibilityHint="打开宿主机资源详情"
      onPress={() => openPopover(Popover)}
      onLayout={(event) => {
        const next = Math.max(0, event.nativeEvent.layout.width);
        setWidth((previous) => (previous !== null && Math.abs(previous - next) < 0.5 ? previous : next));
      }}
      style={({ pressed }) => ({
        height: FOOTER_HEIGHT,
        flexDirection: "row",
        alignItems: "center",
        paddingHorizontal: 8,
        borderRadius: 9,
        borderWidth: 1,
        borderColor: pressed ? colors.accent : colors.border,
        backgroundColor: pressed ? colors.surface2 : colors.surface1,
        overflow: "hidden",
      })}
    >
      {plan.mode === "content" ? (
        <View style={{ flexDirection: "row", alignItems: "center", justifyContent: "center", flex: 1, gap: 4, paddingHorizontal: 4 }}>
          {[cpu, memory, disk].map((label, index) => (
            <Text
              key={index}
              numberOfLines={1}
              onLayout={(event) => recordTextWidth(index, event.nativeEvent.layout.width)}
              style={{ color: colors.foreground, fontSize: 11, fontWeight: "700", fontVariant: ["tabular-nums"], flexShrink: 0 }}
            >
              {label}
            </Text>
          ))}
        </View>
      ) : (
        <>
          <Reading
            icon="Cpu"
            percent={value?.cpuPercent}
            tone={colors.accent}
            showIcon={plan.showIcons}
            meterWidth={plan.meterWidth}
            columnWidth={plan.measured ? plan.columnWidth : null}
            stacked={plan.stacked}
            iconSize={plan.iconSize}
            iconGap={plan.iconGap}
            padX={plan.columnPadX}
            colors={colors}
            onTextWidth={(measured) => recordTextWidth(0, measured)}
          />
          <Reading
            icon="MemoryStick"
            percent={value?.memoryPercent}
            tone={colors.statusSuccess}
            showIcon={plan.showIcons}
            meterWidth={plan.meterWidth}
            columnWidth={plan.measured ? plan.columnWidth : null}
            stacked={plan.stacked}
            iconSize={plan.iconSize}
            iconGap={plan.iconGap}
            padX={plan.columnPadX}
            colors={colors}
            onTextWidth={(measured) => recordTextWidth(1, measured)}
          />
          <Reading
            icon="HardDrive"
            percent={value?.diskTotal?.percent ?? value?.disk?.percent}
            tone={colors.statusWarning}
            showIcon={plan.showIcons}
            meterWidth={plan.meterWidth}
            columnWidth={plan.measured ? plan.columnWidth : null}
            stacked={plan.stacked}
            iconSize={plan.iconSize}
            iconGap={plan.iconGap}
            padX={plan.columnPadX}
            colors={colors}
            onTextWidth={(measured) => recordTextWidth(2, measured)}
          />
        </>
      )}
      {plan.showTail ? (
        <View
          accessibilityElementsHidden
          importantForAccessibility="no-hide-descendants"
          style={{
            width: plan.tailWidth,
            flexShrink: 0,
            flexDirection: "row",
            alignItems: "center",
            justifyContent: "flex-end",
            paddingLeft: 8,
            borderLeftWidth: 1,
            borderLeftColor: colors.border,
            overflow: "hidden",
          }}
        >
          {plan.tail === "network" ? (
            <View
              style={{
                flexDirection: plan.tailStacked ? "column" : "row",
                alignItems: plan.tailStacked ? "flex-end" : "center",
                justifyContent: "flex-end",
                gap: plan.tailStacked ? 1 : 6,
              }}
            >
              <Text
                numberOfLines={1}
                style={{ color: colors.foregroundMuted, fontSize: 9, fontVariant: ["tabular-nums"], flexShrink: 0 }}
              >
                ↓{shortRate(value?.network?.rxBytesPerSecond)}
              </Text>
              <Text
                numberOfLines={1}
                style={{ color: colors.foregroundMuted, fontSize: 9, fontVariant: ["tabular-nums"], flexShrink: 0 }}
              >
                ↑{shortRate(value?.network?.txBytesPerSecond)}
              </Text>
            </View>
          ) : (
            <Text numberOfLines={1} style={{ color: colors.foregroundMuted, fontSize: 10, fontVariant: ["tabular-nums"] }}>
              {value ? clockText(value.sampledAt, plan.tailWidth) : "—"}
            </Text>
          )}
        </View>
      ) : null}
      {anomaly ? (
        <View
          style={{
            position: "absolute",
            top: 4,
            right: plan.tailWidth + 4,
            width: 6,
            height: 6,
            borderRadius: 3,
            backgroundColor: shown === "failed" ? colors.statusDanger : colors.statusWarning,
          }}
        />
      ) : null}
    </Pressable>
  );
}

function Fact({ label, value, colors, strong = false }: { label: string; value: string; colors: Colors; strong?: boolean }) {
  return (
    <View style={{ gap: 3, flexGrow: 1, flexShrink: 1, flexBasis: 92, minWidth: 0 }}>
      <Text style={{ color: colors.foregroundMuted, fontSize: 11 }}>{label}</Text>
      <Text numberOfLines={2} style={{ color: colors.foreground, fontSize: strong ? 20 : 13, fontWeight: strong ? "700" : "600", fontVariant: ["tabular-nums"] }}>
        {value}
      </Text>
    </View>
  );
}

function Card({ title, icon, tone, children, colors }: { title: string; icon: string; tone: string; children: ReactNode; colors: Colors }) {
  return (
    <View style={{ gap: 8, padding: 12, borderRadius: 10, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surface1 }}>
      <View style={{ flexDirection: "row", alignItems: "center", gap: 7 }}>
        <Icon name={icon} size={13} color={tone} />
        <Text style={{ color: colors.foreground, fontSize: 13, fontWeight: "700" }}>{title}</Text>
      </View>
      {children}
    </View>
  );
}

const CHART_BUCKETS = 60;

function bucketize(runs: readonly SeriesRun[], buckets: number): (number | null)[] {
  const out: (number | null)[] = Array.from({ length: buckets }, () => null);
  for (const run of runs) {
    for (const point of run) {
      const index = Math.max(0, Math.min(buckets - 1, Math.floor(point.x * buckets)));
      out[index] = point.v;
    }
  }
  return out;
}

/**
 * React Native has no canvas; thin bars over the same 3-minute window are the
 * cross-platform primitive here. Missing buckets stay blank, so null values and
 * idle gaps read as holes rather than a flattened line.
 */
function Chart({ runs, max, colors, second }: { runs: readonly SeriesRun[]; max: number; colors: Colors; second?: { runs: readonly SeriesRun[]; color: string } }) {
  const [width, setWidth] = useState(0);
  const primary = useMemo(() => bucketize(runs, CHART_BUCKETS), [runs]);
  const secondary = useMemo(() => second ? bucketize(second.runs, CHART_BUCKETS) : null, [second]);
  const peak = Math.max(1, max);
  const points = drawnPoints(runs) + (second ? drawnPoints(second.runs) : 0);
  const barWidth = width > 0 ? Math.max(1, width / CHART_BUCKETS - 1) : 2;

  return (
    <View style={{ gap: 4 }}>
      <View
        onLayout={(event) => setWidth(Math.max(0, event.nativeEvent.layout.width))}
        style={{ height: 44, flexDirection: "row", alignItems: "flex-end", borderBottomWidth: 1, borderBottomColor: colors.border }}
      >
        {width > 0
          ? primary.map((value, index) => {
              const other = secondary?.[index] ?? null;
              const primaryHeight = value === null ? 0 : Math.max(1, (Math.min(value / peak, 1) * 100));
              const otherHeight = other === null ? 0 : Math.max(1, Math.min(other / peak, 1) * 100);
              const empty = value === null && other === null;
              return (
                <View key={index} style={{ width: barWidth, height: "100%", justifyContent: "flex-end", marginRight: 1 }}>
                  {empty ? null : (
                    <View style={{ flexDirection: "row", alignItems: "flex-end", height: "100%" }}>
                      <View style={{ width: secondary ? barWidth / 2 : barWidth, height: `${primaryHeight}%`, backgroundColor: colors.accent, borderRadius: 1 }} />
                      {secondary ? <View style={{ width: barWidth / 2, height: `${otherHeight}%`, backgroundColor: second?.color, borderRadius: 1 }} /> : null}
                    </View>
                  )}
                </View>
              );
            })
          : null}
      </View>
      <View style={{ flexDirection: "row", justifyContent: "space-between" }}>
        <Text style={{ color: colors.foregroundMuted, fontSize: 10 }}>−3 分钟</Text>
        <Text style={{ color: colors.foregroundMuted, fontSize: 10 }}>{points > 1 ? "最新" : points === 1 ? "等待下一次采样" : "暂无历史"}</Text>
      </View>
    </View>
  );
}

function Popover({ theme, host, close }: PluginPopoverProps) {
  const colors = theme.colors;
  const hosts = useHosts();
  const connection = hosts.find((entry) => entry.serverId === host.id)?.status ?? "offline";
  const settings = useSettings(monitorSettings);
  const settingsInterval = settings.status === "ready" ? settings.values.intervalMs : DEFAULT_SETTINGS.intervalMs;
  const { value, status, refresh } = useSample(host.id, settingsInterval);
  const shown = effectiveStatus(status, value, connection);
  const isLinux = value?.platform === "linux";
  const process = value?.process ?? null;
  const statusText =
    shown === "live" ? "采样成功" : shown === "stale" ? "本次采样未更新，显示旧样本" : shown === "failed" ? "无法读取主机资源" : "正在采样…";
  const statusTone =
    shown === "live" ? colors.statusSuccess : shown === "stale" ? colors.statusWarning : shown === "failed" ? colors.statusDanger : colors.foregroundMuted;

  const history = value?.history;
  const interval = history?.intervalMs ?? settingsInterval;
  // Anchor the window to the snapshot itself, so a stale sample still draws its
  // own last three minutes instead of falling outside a wall-clock window.
  const endMs = value && Number.isFinite(Date.parse(value.sampledAt)) ? Date.parse(value.sampledAt) : Date.now();
  const maxGap = Math.max(6000, interval * 3);
  const samples = history?.samples ?? [];
  const cpuRuns = buildSeries(samples, (point) => point.cpuPercent, endMs, undefined, maxGap);
  const memoryRuns = buildSeries(samples, (point) => point.memoryPercent, endMs, undefined, maxGap);
  const diskRuns = buildSeries(samples, (point) => point.diskPercent, endMs, undefined, 45_000);
  const rxRuns = buildSeries(samples, (point) => point.rxBytesPerSecond, endMs, undefined, maxGap);
  const txRuns = buildSeries(samples, (point) => point.txBytesPerSecond, endMs, undefined, maxGap);
  const networkPeak = Math.max(
    1024,
    ...rxRuns.flat().map((point) => point.v),
    ...txRuns.flat().map((point) => point.v),
  );

  const diskTotal = value?.diskTotal ?? null;
  const diskScopeText = diskTotal
    ? diskTotal.scope === "local-disks"
      ? "本地磁盘汇总：逐个去重后，已用与可用分别求和再算百分比（df 口径）。"
      : "仅能读取系统根盘，以下为根盘口径。"
    : "磁盘容量暂不可用。";

  return (
    <View style={{ gap: 12, minWidth: 260 }}>
      <View style={{ flexDirection: "row", alignItems: "flex-start", gap: 10 }}>
        <View style={{ flex: 1, minWidth: 0, gap: 2 }}>
          <Text style={{ color: colors.foreground, fontSize: 16, fontWeight: "700" }}>宿主机资源</Text>
          <Text numberOfLines={1} style={{ color: colors.foregroundMuted, fontSize: 12 }}>
            {host.label} · {hostStatusLabels[connection] ?? connection}
          </Text>
        </View>
        <Pressable accessibilityRole="button" accessibilityLabel="关闭宿主机资源详情" onPress={close} hitSlop={8} style={{ paddingHorizontal: 8, paddingVertical: 4, borderRadius: 6 }}>
          <Text style={{ color: colors.foregroundMuted, fontSize: 16 }}>×</Text>
        </Pressable>
      </View>

      <View style={{ flexDirection: "row", alignItems: "center", gap: 8 }}>
        <View style={{ width: 7, height: 7, borderRadius: 4, backgroundColor: statusTone }} />
        <View style={{ flex: 1, minWidth: 0, gap: 2 }}>
          <Text style={{ color: colors.foreground, fontSize: 12, fontWeight: "600" }}>{statusText}</Text>
          <Text style={{ color: colors.foregroundMuted, fontSize: 11, fontVariant: ["tabular-nums"] }}>
            每 {(interval / 1000).toFixed(0)} 秒 · 最近成功 {value ? timeText(value.sampledAt) : "—"}
          </Text>
        </View>
        <Pressable
          accessibilityRole="button"
          accessibilityLabel="重新采样"
          onPress={refresh}
          disabled={status === "loading"}
          style={({ pressed }) => ({
            paddingHorizontal: 9,
            paddingVertical: 5,
            borderRadius: 6,
            borderWidth: 1,
            borderColor: colors.border,
            backgroundColor: pressed ? colors.surface2 : colors.surface1,
            opacity: status === "loading" ? 0.6 : 1,
          })}
        >
          <Text style={{ color: colors.foreground, fontSize: 11, fontWeight: "600" }}>刷新</Text>
        </Pressable>
      </View>

      {shown === "stale" ? (
        <View style={{ padding: 9, borderRadius: 9, borderWidth: 1, borderColor: colors.statusWarning, backgroundColor: colors.surface1 }}>
          <Text style={{ color: colors.statusWarning, fontSize: 12, fontWeight: "700" }}>正在显示旧样本</Text>
          <Text style={{ color: colors.foregroundMuted, fontSize: 11 }}>本次采样失败。下方读数来自此主机最近一次成功采样。</Text>
        </View>
      ) : null}
      {shown === "failed" ? (
        <View style={{ padding: 9, borderRadius: 9, borderWidth: 1, borderColor: colors.statusDanger, backgroundColor: colors.surface1 }}>
          <Text style={{ color: colors.statusDanger, fontSize: 12, fontWeight: "700" }}>无法读取主机资源</Text>
          <Text style={{ color: colors.foregroundMuted, fontSize: 11 }}>此主机暂无可用样本，请确认连接后重试。</Text>
        </View>
      ) : null}

      {/*
        The host owns the only scroll area here: on desktop the sidebar popover
        is rendered by PluginPopoverSurface -> MenuSurface(scrollable) ->
        FloatingScrollView with a height capped by maxHeight; on compact the
        bottom sheet wraps its content in BottomSheetScrollView. A nested
        ScrollView would add a second scrollbar and clip the daemon process row.
      */}
      <View style={{ gap: 8 }}>
        <View style={{ flexDirection: "row", gap: 8, paddingBottom: 9, borderBottomWidth: 1, borderBottomColor: colors.border }}>
          <Fact label="主机运行时长" value={uptimeText(value?.uptimeSeconds)} colors={colors} />
          <Fact label="系统负载 1 / 5 / 15 分钟" value={loadText(value?.loadAverage)} colors={colors} />
        </View>

        <Card title="宿主机 CPU" icon="Cpu" tone={colors.accent} colors={colors}>
          <View style={{ flexDirection: "row", gap: 12 }}>
            <Fact label="使用率" value={percentText(value?.cpuPercent)} colors={colors} strong />
            <Fact label="逻辑核心" value={value ? String(value.cpuCores) : "—"} colors={colors} />
          </View>
          <Text style={{ color: colors.foregroundMuted, fontSize: 11 }}>
            {isLinux && value?.cpuSource === "proc"
              ? "取自宿主 /proc/stat 相邻两次计数；100% 代表全部逻辑核心满载。"
              : "取自宿主 os.cpus() 相邻两次计数；100% 代表全部逻辑核心满载。"}
          </Text>
          <Chart runs={cpuRuns} max={100} colors={colors} />
        </Card>

        <Card title="宿主机内存" icon="MemoryStick" tone={colors.statusSuccess} colors={colors}>
          <View style={{ flexDirection: "row", gap: 12 }}>
            <Fact label="使用率" value={percentText(value?.memoryPercent)} colors={colors} strong />
            <Fact label="已用 / 总量" value={value ? `${bytesText(value.memoryUsedBytes)} / ${bytesText(value.memoryTotalBytes)}` : "—"} colors={colors} />
          </View>
          <Text style={{ color: colors.foregroundMuted, fontSize: 11 }}>
            {isLinux && value?.memoryBasis === "available"
              ? "已用 = 总量 − /proc/meminfo MemAvailable。"
              : "已用 = 总量 − 系统空闲内存；此平台没有 MemAvailable。"}
          </Text>
          {value?.memoryPressure || value?.memoryBreakdown ? (
            <Text style={{ color: colors.foregroundMuted, fontSize: 11 }}>
              {value.memoryPressure
                ? `内存压力：${{ normal: "正常", warning: "偏高", critical: "严重" }[value.memoryPressure]}`
                : null}
              {value.memoryBreakdown ? `${value.memoryPressure ? " · " : ""}缓存 ${bytesText(value.memoryBreakdown.cachedBytes)}${value.memoryBreakdown.buffersBytes !== null ? `, 缓冲 ${bytesText(value.memoryBreakdown.buffersBytes)}` : ""}` : null}
            </Text>
          ) : null}
          <Chart runs={memoryRuns} max={100} colors={colors} />
        </Card>

        <Card title={diskTotal?.scope === "root-disk" ? "系统盘" : "本地磁盘"} icon="HardDrive" tone={colors.statusWarning} colors={colors}>
          <View style={{ flexDirection: "row", gap: 12 }}>
            <Fact label="使用率" value={percentText(diskTotal?.percent)} colors={colors} strong />
            <Fact label="已用 / 可用" value={diskTotal ? `${bytesText(diskTotal.usedBytes)} / ${bytesText(diskTotal.availableBytes)}` : "—"} colors={colors} />
          </View>
          <Text style={{ color: colors.foregroundMuted, fontSize: 11 }}>{diskScopeText}</Text>
          <Chart runs={diskRuns} max={100} colors={colors} />
          {value?.disks && value.disks.length > 0 ? (
            <View style={{ gap: 5 }}>
              {value.disks.map((entry) => (
                <View key={`${entry.mountPoint}:${entry.source}`} style={{ flexDirection: "row", justifyContent: "space-between", gap: 8, borderTopWidth: 1, borderTopColor: colors.border, paddingTop: 5 }}>
                  <Text numberOfLines={1} style={{ color: colors.foreground, fontSize: 11, flexShrink: 1 }}>
                    {entry.mountPoint === "/" ? "系统盘 /" : entry.mountPoint} · {entry.fstype}
                  </Text>
                  <Text style={{ color: colors.foregroundMuted, fontSize: 11, fontVariant: ["tabular-nums"], flexShrink: 0 }}>
                    {bytesText(entry.usedBytes)} / {bytesText(entry.totalBytes)} · 可用 {bytesText(entry.availableBytes)} · {percentText(entry.percent)}
                  </Text>
                </View>
              ))}
            </View>
          ) : null}
        </Card>

        <Card title="宿主机网络" icon="Network" tone={colors.accent} colors={colors}>
          <View style={{ flexDirection: "row", gap: 12 }}>
            <Fact label="↓ 下行" value={rateText(value?.network?.rxBytesPerSecond)} colors={colors} strong />
            <Fact label="↑ 上行" value={rateText(value?.network?.txBytesPerSecond)} colors={colors} strong />
          </View>
          <Text style={{ color: colors.foregroundMuted, fontSize: 11 }}>
            {isLinux
              ? "取自宿主 /proc/net/dev 累计字节的差值；已跳过 loopback 与 veth、docker、bridge 等虚拟接口，不产生流量。"
              : "此平台没有可用的 /proc/net/dev，网络速率不可用。"}
          </Text>
          <Chart runs={rxRuns} second={{ runs: txRuns, color: colors.statusSuccess }} max={networkPeak} colors={colors} />
        </Card>

        <Card title="Paseo daemon 主进程" icon="Terminal" tone={colors.foregroundMuted} colors={colors}>
          {process ? (
            <>
              <View style={{ flexDirection: "row", gap: 12 }}>
                <Fact label="进程 CPU" value={process.cpuPercent === null ? "待采样" : `${process.cpuPercent.toFixed(1)}%`} colors={colors} />
                <Fact label="常驻内存 RSS" value={bytesText(process.rssBytes)} colors={colors} />
                <Fact label="PID" value={String(process.pid)} colors={colors} />
              </View>
              <Text style={{ color: colors.foregroundMuted, fontSize: 11 }}>
                进程 CPU 为 daemon 进程 ticks ÷ 宿主全部逻辑核心 ticks；与上方宿主 CPU 同一口径，不是单核百分比。
              </Text>
            </>
          ) : (
            <Text style={{ color: colors.foregroundMuted, fontSize: 11 }}>
              {value && value.platform !== "linux"
                ? "此平台未提供 daemon 主进程读数，已省略；不会用插件子进程代替。"
                : "暂未读到可靠的 daemon 主进程读数，已省略。"}
            </Text>
          )}
        </Card>
      </View>
    </View>
  );
}
