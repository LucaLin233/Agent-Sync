import {
  type PluginPopoverProps,
  type PluginSidebarItemProps,
  useHosts,
  useRpc,
} from "@getpaseo/plugin/client";
import { Icon } from "@getpaseo/plugin/client/ui";
import { useEffect, useRef, useState, type ReactNode } from "react";
import { AppState, Pressable, ScrollView, Text, View, useWindowDimensions } from "react-native";
import { hostResourcesRpc, type HostResources } from "../shared/contract.ts";
import { chooseFooterLayout, FOOTER_ROW_GAP, FOOTER_ROW_GAP_TIGHT } from "../shared/layout.ts";

type Colors = PluginPopoverProps["theme"]["colors"];
type Status = "loading" | "live" | "stale" | "failed";

const POLL_MS = 5_000;

const hostStatusLabels: Record<string, string> = {
  idle: "未连接",
  connecting: "连接中",
  online: "已连接",
  offline: "离线",
  error: "连接异常",
};

function percentText(value: number | null | undefined): string {
  return value === null || value === undefined ? "—" : `${value.toFixed(value >= 100 ? 0 : 1)}%`;
}

function bytesText(value: number | null | undefined): string {
  if (value === null || value === undefined) return "—";
  const gib = value / 1024 ** 3;
  if (gib >= 1) return `${gib.toFixed(1)} GiB`;
  return `${(value / 1024 ** 2).toFixed(0)} MiB`;
}

function timeText(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "—";
  return date.toLocaleTimeString("zh-CN", { hour12: false });
}

/**
 * The reading is tagged with the host it came from, so a host switch never
 * paints the previous host's numbers even for one frame. Polling runs only while
 * the surface is mounted and the app is in the foreground.
 */
function useSample(hostId: string) {
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
    let timer: ReturnType<typeof setTimeout> | undefined;
    setStatus("loading");

    const run = async () => {
      try {
        const value = await sample({});
        if (cancelled || !mounted.current) return;
        setState({ hostId, value });
        setStatus("live");
        setFailing(false);
      } catch {
        if (cancelled || !mounted.current) return;
        setFailing(true);
        setStatus("failed");
      } finally {
        if (!cancelled) timer = setTimeout(run, POLL_MS);
      }
    };

    void run();
    return () => {
      cancelled = true;
      if (timer) clearTimeout(timer);
    };
  }, [awake, hostId, sample, tick]);

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

function Meter({ percent, tone, colors }: { percent: number | null; tone: string; colors: Colors }) {
  const width = percent === null ? 0 : Math.min(100, Math.max(0, percent));
  return (
    <View
      accessibilityElementsHidden
      importantForAccessibility="no-hide-descendants"
      style={{ height: 3, width: 22, borderRadius: 3, backgroundColor: colors.border, overflow: "hidden" }}
    >
      <View style={{ width: `${width}%`, height: "100%", borderRadius: 3, backgroundColor: tone }} />
    </View>
  );
}

/** Rough advance width of one CJK glyph at the 10 px badge size. */
const ANOMALY_CHAR_WIDTH = 10;

function Reading({ icon, percent, tone, showMeter, showIcon, colors, onTextWidth }: {
  icon: string;
  percent: number | null | undefined;
  tone: string;
  showMeter: boolean;
  showIcon: boolean;
  colors: Colors;
  onTextWidth: (width: number) => void;
}) {
  return (
    <View
      accessibilityElementsHidden
      importantForAccessibility="no-hide-descendants"
      style={{ flexDirection: "row", alignItems: "center", gap: 4, flexShrink: 0 }}
    >
      {showIcon ? <Icon name={icon} size={12} color={tone} /> : null}
      <Text
        numberOfLines={1}
        onLayout={(event) => onTextWidth(event.nativeEvent.layout.width)}
        style={{
          color: colors.foreground,
          fontSize: 11,
          fontWeight: "700",
          fontVariant: ["tabular-nums"],
          flexShrink: 0,
        }}
      >
        {percentText(percent)}
      </Text>
      {showMeter ? <Meter percent={percent ?? null} tone={tone} colors={colors} /> : null}
    </View>
  );
}

export function HostMonitorItem({ theme, host, layout, openPopover }: PluginSidebarItemProps) {
  const colors = theme.colors;
  const hosts = useHosts();
  const connection = hosts.find((entry) => entry.serverId === host.id)?.status ?? "offline";
  const { value, status } = useSample(host.id);
  const shown = effectiveStatus(status, value, connection);
  const cpu = percentText(value?.cpuPercent);
  const memory = percentText(value?.memoryPercent);
  const disk = percentText(value?.disk?.percent);
  const anomaly = shown === "stale" ? "旧样本" : shown === "failed" ? "读取失败" : null;
  const { fontScale } = useWindowDimensions();
  const [availableWidth, setAvailableWidth] = useState<number | null>(null);
  const [textWidths, setTextWidths] = useState<(number | null)[]>([null, null, null]);

  // The percentages are the only content that must survive at any width, so the
  // row fits itself to real measurements instead of trusting the layout flag.
  const plan = chooseFooterLayout({
    availableWidth,
    compact: layout.compact,
    textWidths,
    anomaly: anomaly !== null,
    anomalyTextWidth: anomaly ? anomaly.length * ANOMALY_CHAR_WIDTH * fontScale : 0,
  });

  const recordTextWidth = (index: number, width: number) => {
    setTextWidths((previous) => {
      if (Math.abs((previous[index] ?? -1) - width) < 0.5) return previous;
      const next = previous.slice();
      next[index] = width;
      return next;
    });
  };

  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={`宿主机资源：CPU ${cpu}，内存 ${memory}，硬盘 ${disk}，${hostStatusLabels[connection] ?? connection}${anomaly ? `，${anomaly}` : ""}`}
      accessibilityHint="打开宿主机资源详情"
      onPress={() => openPopover(Popover)}
      onLayout={(event) => {
        const width = Math.max(0, event.nativeEvent.layout.width);
        setAvailableWidth((previous) => (previous !== null && Math.abs(previous - width) < 0.5 ? previous : width));
      }}
      style={({ pressed }) => ({
        flexDirection: "row",
        alignItems: "center",
        gap: plan.tightGap ? FOOTER_ROW_GAP_TIGHT : FOOTER_ROW_GAP,
        minHeight: 32,
        paddingVertical: 6,
        paddingHorizontal: 9,
        borderRadius: 8,
        borderWidth: 1,
        borderColor: pressed ? colors.accent : colors.border,
        backgroundColor: pressed ? colors.surface2 : colors.surface1,
      })}
    >
      <Reading
        icon="Cpu"
        percent={value?.cpuPercent}
        tone={colors.accent}
        showMeter={plan.showMeters}
        showIcon={plan.showIcons}
        colors={colors}
        onTextWidth={(width) => recordTextWidth(0, width)}
      />
      <Reading
        icon="MemoryStick"
        percent={value?.memoryPercent}
        tone={colors.statusSuccess}
        showMeter={plan.showMeters}
        showIcon={plan.showIcons}
        colors={colors}
        onTextWidth={(width) => recordTextWidth(1, width)}
      />
      <Reading
        icon="HardDrive"
        percent={value?.disk?.percent}
        tone={colors.statusWarning}
        showMeter={plan.showMeters}
        showIcon={plan.showIcons}
        colors={colors}
        onTextWidth={(width) => recordTextWidth(2, width)}
      />
      {anomaly && plan.showAnomalyText ? (
        <Text
          numberOfLines={1}
          style={{ marginLeft: "auto", flexShrink: 0, color: shown === "failed" ? colors.statusDanger : colors.statusWarning, fontSize: 10 }}
        >
          {anomaly}
        </Text>
      ) : null}
      {anomaly && !plan.showAnomalyText && plan.showAnomalyMark ? (
        <View
          accessibilityElementsHidden
          importantForAccessibility="no-hide-descendants"
          style={{ marginLeft: "auto", width: 8, height: 8, borderRadius: 4, backgroundColor: shown === "failed" ? colors.statusDanger : colors.statusWarning }}
        />
      ) : null}
    </Pressable>
  );
}

function Fact({ label, value, colors, strong = false }: { label: string; value: string; colors: Colors; strong?: boolean }) {
  return (
    <View style={{ gap: 3, flexGrow: 1, flexShrink: 1, flexBasis: 92, minWidth: 0 }}>
      <Text style={{ color: colors.foregroundMuted, fontSize: 11 }}>{label}</Text>
      <Text
        numberOfLines={2}
        style={{ color: colors.foreground, fontSize: strong ? 20 : 13, fontWeight: strong ? "700" : "600", fontVariant: ["tabular-nums"] }}
      >
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

function Popover({ theme, host, close }: PluginPopoverProps) {
  const colors = theme.colors;
  const hosts = useHosts();
  const connection = hosts.find((entry) => entry.serverId === host.id)?.status ?? "offline";
  const { value, status, failing, refresh } = useSample(host.id);
  const shown = effectiveStatus(status, value, connection);
  const isLinux = value?.platform === "linux";
  const process = value?.process ?? null;
  const statusText =
    shown === "live" ? "采样成功" : shown === "stale" ? "本次采样未更新，显示旧样本" : shown === "failed" ? "无法读取主机资源" : "正在采样…";
  const statusTone =
    shown === "live" ? colors.statusSuccess : shown === "stale" ? colors.statusWarning : shown === "failed" ? colors.statusDanger : colors.foregroundMuted;

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
        <Text style={{ color: colors.foreground, fontSize: 12, fontWeight: "600", flex: 1 }}>{statusText}</Text>
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

      <Text style={{ color: colors.foregroundMuted, fontSize: 11 }}>
        最近成功采样 {value ? timeText(value.sampledAt) : "—"}
        {value && value.cpuWindowMs > 0 ? ` · CPU 窗口 ${(value.cpuWindowMs / 1000).toFixed(1)} 秒` : ""}
      </Text>

      {shown === "stale" && failing ? (
        <Text style={{ color: colors.statusWarning, fontSize: 11 }}>本次采样失败，读数保持上一次成功结果。</Text>
      ) : null}
      {shown === "failed" ? (
        <Text style={{ color: colors.statusDanger, fontSize: 11 }}>暂时无法读取此主机资源，请确认连接后重试。</Text>
      ) : null}

      <ScrollView style={{ maxHeight: 420 }} contentContainerStyle={{ gap: 8 }}>
        <Card title="宿主机 CPU" icon="Cpu" tone={colors.accent} colors={colors}>
          <View style={{ flexDirection: "row", gap: 12 }}>
            <Fact label="使用率" value={percentText(value?.cpuPercent)} colors={colors} strong />
            <Fact label="逻辑核心" value={value ? String(value.cpuCores) : "—"} colors={colors} />
          </View>
          <Text style={{ color: colors.foregroundMuted, fontSize: 11 }}>
            {isLinux && value?.cpuSource === "proc"
              ? "取自 daemon 宿主 /proc/stat 相邻两次计数，100% 代表全部逻辑核心满载。"
              : "取自 daemon 宿主 os.cpus() 相邻两次计数，100% 代表全部逻辑核心满载。"}
          </Text>
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
        </Card>

        <Card title="系统盘" icon="HardDrive" tone={colors.statusWarning} colors={colors}>
          {value?.disk ? (
            <>
              <View style={{ flexDirection: "row", gap: 12 }}>
                <Fact label="使用率" value={percentText(value.disk.percent)} colors={colors} strong />
                <Fact label="已用 / 总量" value={`${bytesText(value.disk.usedBytes)} / ${bytesText(value.disk.totalBytes)}`} colors={colors} />
              </View>
              <Text style={{ color: colors.foregroundMuted, fontSize: 11 }}>
                可用 {bytesText(value.disk.availableBytes)}；仅统计 daemon 宿主系统根所在文件系统，不枚举其他磁盘。
              </Text>
            </>
          ) : (
            <Text style={{ color: colors.foregroundMuted, fontSize: 11 }}>系统盘容量暂不可读，CPU 与内存读数不受影响。</Text>
          )}
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
      </ScrollView>
    </View>
  );
}
