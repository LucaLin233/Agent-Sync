import {
  type PluginWorkspacePanelProps,
  useRpc,
  useWorkspace,
} from "@getpaseo/plugin/client";
import { useEffect, useMemo, useState } from "react";
import { Pressable, ScrollView, Text, View } from "react-native";
import { listWorkspaceSessionsRpc, regenerateWorkspaceTitleRpc } from "../shared/rpc";
import { panelPalette } from "../shared/palette";

type Scope = "both" | "workspace" | "session";

type Phase =
  | { kind: "idle" }
  | { kind: "running" }
  | { kind: "done"; title: string; workspace: boolean; session: boolean; coverage?: string }
  | { kind: "partial"; title: string; workspace: boolean; session: boolean; message: string }
  | { kind: "busy" }
  | { kind: "error"; message: string };

const COVERAGE_REASONS: Record<string, string> = {
  page_cap: "会话过长，超过单次读取页数上限",
  entry_cap: "会话条目过多，超过单次读取条目上限",
  char_cap: "会话文本过长，达到单次读取字数上限",
  deadline: "读取会话已接近本次请求时限",
  cursor_missing: "分页游标缺失，没能读完整个会话",
  read_error: "读取会话中途失败，只用了已读到的部分",
  segment_cap: "会话超过本次可分段提炼的分段上限",
  reset: "会话历史游标已重置，只用了重置前读到的部分",
  gap: "会话历史出现断层，只用了断层前读到的部分",
};

function coverageNote(coverage: { reason?: string; turns: number }): string {
  const why = coverage.reason ? COVERAGE_REASONS[coverage.reason] ?? "会话未能完整读取" : "会话未能完整读取";
  return `${why}；标题只概括了已读取的 ${coverage.turns} 轮，可重试。`;
}

type SessionList =
  | { kind: "loading" }
  | { kind: "ready"; sessions: Array<{ id: string; title: string | null; lastActivityAt: string | null }> }
  | { kind: "error" };

const SCOPES: ReadonlyArray<{ value: Scope; label: string; hint: string }> = [
  { value: "both", label: "工作区和所选会话", hint: "两处使用同一个中文标题。" },
  { value: "workspace", label: "仅工作区", hint: "保留会话标题。" },
  { value: "session", label: "仅所选会话", hint: "保留工作区标题和工作区自动命名状态。" },
];

const MESSAGES: Record<string, string> = {
  timeout: "生成超时，未写入标题；可以重试。",
  manual_change: "生成期间工作区标题已被手动修改，本次未覆盖。",
  session_manual_change: "生成期间所选会话标题已被手动修改，本次未覆盖。",
  not_found: "工作区不存在或已归档。",
  excluded: "后台或插件辅助工作区不参与重命名。",
  verification_failed: "写入后回读不一致，请重试。",
  workspace_write_failed: "工作区标题写入失败。",
  workspace_verification_failed: "工作区标题写入后回读不一致。",
  session_write_failed: "会话标题写入失败。",
  session_verification_failed: "会话标题写入后回读不一致。",
  session_not_found: "所选会话已不存在或不可读。",
  session_archived: "所选会话已归档，未修改任何标题。",
  session_moved: "所选会话已移到其他工作区，未修改任何标题。",
  settings_unavailable: "设置不可用，请检查插件设置后重试。",
  internal_failed: "生成失败，请重试。",
  provider_unavailable: "标题模型不可用，未修改原标题；检查插件设置里的 provider 后重试。",
  model_failed: "标题模型未返回可用结果，未修改原标题；可以重试。",
  invalid_title: "模型结果不是合格的中文标题，未修改原标题；可以重试。",
  rewrite_failed: "模型标题过长或断句不完整，缩写后仍不合格，未修改原标题；可以重试。",
  empty_conversation: "所选会话没有可概括的用户或助手文本，未修改原标题。",
  conversation_unavailable: "读取所选会话失败，未修改原标题；可以重试。",
  no_session: "这个工作区还没有可选的普通会话，未修改原标题。",
  choose_session: "请先选择要概括的会话。",
  session_not_selectable: "所选会话不在这个工作区或不可选，请重新选择。",
};

const activityParts = new Intl.DateTimeFormat("zh-CN", {
  month: "numeric",
  day: "numeric",
  hour: "2-digit",
  minute: "2-digit",
  hour12: false,
});

/** Matches the artboard's "11 月 26 日 14:24"; falls back to the raw value if unparsable. */
function formatActivity(timestamp: number): string {
  const parts = activityParts.formatToParts(timestamp);
  const part = (type: string) => parts.find((entry) => entry.type === type)?.value ?? "";
  return `${part("month")} 月 ${part("day")} 日 ${part("hour")}:${part("minute")}`;
}

function sessionLabel(session: { id: string; title: string | null }): string {
  const title = session.title?.trim();
  return title ? title : `未命名会话 ${session.id.slice(0, 8)}`;
}

function activityText(value: string | null): string | null {
  if (!value) return null;
  const parsed = Date.parse(value);
  return Number.isFinite(parsed) ? formatActivity(parsed) : value.slice(0, 16).replace("T", " ");
}

function writtenTargets(workspace: boolean, session: boolean): string {
  if (workspace && session) return "工作区和所选会话";
  if (workspace) return "工作区";
  return "所选会话";
}

export function ChineseTitlePanel({ theme, layout, workspaceId }: PluginWorkspacePanelProps) {
  const compact = layout.compact;
  const accent = panelPalette(theme.colors);
  const currentTitle = useWorkspace(workspaceId, (workspace) => workspace.title);
  // A new prompt in this workspace means a session may have joined or moved;
  // re-read the picker without touching any saved selection.
  const lastPromptAt = useWorkspace(workspaceId, (workspace) => workspace.lastPromptAt);
  const regenerate = useRpc(regenerateWorkspaceTitleRpc);
  const loadSessions = useRpc(listWorkspaceSessionsRpc);
  const [sessions, setSessions] = useState<SessionList>({ kind: "loading" });
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [scope, setScope] = useState<Scope>("both");
  const [phase, setPhase] = useState<Phase>({ kind: "idle" });
  const [refreshKey, setRefreshKey] = useState(0);
  const running = phase.kind === "running";

  // A selection belongs to one workspace only.
  useEffect(() => {
    setSelectedId(null);
    setPhase({ kind: "idle" });
  }, [workspaceId]);

  useEffect(() => {
    let alive = true;
    setSessions({ kind: "loading" });
    void loadSessions({ workspaceId }).then(
      (result) => {
        if (!alive) return;
        setSessions({ kind: "ready", sessions: result.sessions });
        // One session is the only choice there is; several need an explicit pick.
        setSelectedId((current) => {
          if (current && result.sessions.some((session) => session.id === current)) return current;
          return result.sessions.length === 1 ? result.sessions[0]?.id ?? null : null;
        });
      },
      () => {
        if (alive) setSessions({ kind: "error" });
      },
    );
    return () => { alive = false; };
  }, [loadSessions, workspaceId, lastPromptAt, refreshKey]);

  const styles = useMemo(() => {
    const colors = theme.colors;
    return {
      screen: {
        flex: 1,
        backgroundColor: colors.surface0,
      },
      content: {
        paddingHorizontal: compact ? 14 : 32,
        paddingTop: compact ? 16 : 24,
        paddingBottom: compact ? 24 : 32,
        gap: compact ? 14 : 20,
      },
      header: { flexDirection: "row" as const, alignItems: "center" as const, gap: compact ? 10 : 13 },
      headerCopy: { flexShrink: 1, minWidth: 0 },
      badge: {
        width: compact ? 32 : 38,
        height: compact ? 32 : 38,
        borderRadius: 10,
        borderWidth: 1,
        borderColor: accent.iconBorder,
        backgroundColor: accent.iconPlate,
        alignItems: "center" as const,
        justifyContent: "center" as const,
      },
      badgeText: { color: accent.mark, fontSize: 17, fontWeight: "700" as const },
      badgeSub: { color: accent.mark, fontSize: 9, marginLeft: 1 },
      heading: {
        color: colors.foreground,
        fontSize: compact ? 20 : 22,
        lineHeight: compact ? 27 : 29,
        fontWeight: "700" as const,
      },
      context: {
        marginTop: 3,
        color: colors.foregroundMuted,
        fontSize: 14,
        lineHeight: 20,
      },
      card: {
        paddingVertical: compact ? 12 : 17,
        paddingHorizontal: compact ? 14 : 20,
        borderWidth: 1,
        borderColor: colors.border,
        borderRadius: 12,
        backgroundColor: colors.surface1,
      },
      cardLabel: { color: colors.foregroundMuted, fontSize: 14, lineHeight: 20 },
      cardValue: {
        marginTop: 4,
        color: colors.foreground,
        fontSize: compact ? 16 : 18,
        lineHeight: compact ? 23 : 25,
        fontWeight: "600" as const,
      },
      columns: {
        flexDirection: compact ? ("column" as const) : ("row" as const),
        alignItems: "stretch" as const,
        gap: compact ? 14 : 24,
      },
      column: { flex: 1, minWidth: 0, gap: 4 },
      sectionTitle: {
        color: colors.foreground,
        fontSize: 16,
        lineHeight: 22,
        fontWeight: "600" as const,
      },
      helper: {
        color: colors.foregroundMuted,
        fontSize: 14,
        lineHeight: 20,
      },
      options: { marginTop: compact ? 7 : 11, gap: compact ? 5 : 7 },
      option: {
        minHeight: compact ? 44 : undefined,
        flexDirection: "row" as const,
        alignItems: "flex-start" as const,
        gap: 11,
        paddingVertical: compact ? 7 : 10,
        paddingHorizontal: compact ? 10 : 12,
        borderWidth: 1,
        borderColor: colors.border,
        borderRadius: 9,
        backgroundColor: colors.surface1,
        opacity: running ? 0.6 : 1,
      },
      optionSelected: { borderColor: accent.selectedEdge, backgroundColor: accent.selectedPlate },
      radio: {
        marginTop: 4,
        width: 16,
        height: 16,
        flexGrow: 0,
        flexShrink: 0,
        borderRadius: 8,
        borderWidth: 1,
        borderColor: colors.border,
        alignItems: "center" as const,
        justifyContent: "center" as const,
      },
      radioDot: { width: 8, height: 8, borderRadius: 4, backgroundColor: accent.mark },
      optionCopy: { flex: 1, minWidth: 0, gap: 2 },
      optionLabel: {
        color: colors.foreground,
        fontSize: 15,
        lineHeight: 21,
        fontWeight: "600" as const,
      },
      optionMeta: { color: colors.foregroundMuted, fontSize: 14, lineHeight: 20 },
      footer: {
        flexDirection: compact ? ("column" as const) : ("row" as const),
        alignItems: compact ? ("stretch" as const) : ("center" as const),
        flexWrap: "wrap" as const,
        gap: compact ? 9 : 16,
        marginTop: compact ? 2 : 2,
        paddingTop: compact ? 11 : 16,
        borderTopWidth: 1,
        borderTopColor: colors.border,
      },
      disclosure: {
        flexGrow: 1,
        flexBasis: compact ? undefined : 260,
        color: colors.foregroundMuted,
        fontSize: 14,
        lineHeight: 20,
      },
      button: {
        minHeight: 44,
        paddingVertical: 9,
        paddingHorizontal: 16,
        borderRadius: 9,
        backgroundColor: accent.action,
        opacity: running || !selectedId ? 0.6 : 1,
        alignItems: "center" as const,
        justifyContent: "center" as const,
      },
      buttonText: {
        color: accent.actionText,
        fontSize: 15,
        lineHeight: 21,
        fontWeight: "700" as const,
        textAlign: "center" as const,
      },
      notice: {
        width: compact ? undefined : ("100%" as const),
        paddingVertical: 11,
        paddingHorizontal: 12,
        borderWidth: 1,
        borderColor: colors.border,
        borderLeftWidth: 3,
        borderRadius: 9,
        backgroundColor: colors.surface1,
      },
      noticeTitle: { fontSize: 16, lineHeight: 22, fontWeight: "600" as const },
      noticeBody: { marginTop: 3, color: colors.foregroundMuted, fontSize: 14, lineHeight: 20 },
      muted: { color: colors.foregroundMuted, fontSize: 14, lineHeight: 20 },
      error: { color: colors.statusDanger, fontSize: 14, lineHeight: 20 },
    };
  }, [theme, compact, running, selectedId]);

  const press = () => {
    if (running || !selectedId) return;
    setPhase({ kind: "running" });
    void regenerate({ workspaceId, agentId: selectedId, scope }).then(
      (result) => {
        const title = result.title ?? "";
        const workspace = result.workspaceUpdated;
        const session = result.sessionUpdated;
        if (result.status === "done") {
          setPhase({
            kind: "done",
            title,
            workspace,
            session,
            ...(result.coverage ? { coverage: coverageNote(result.coverage) } : {}),
          });
        } else if (result.status === "partial") {
          setPhase({
            kind: "partial",
            title,
            workspace,
            session,
            message: `新标题为「${title}」。${MESSAGES[result.reason ?? ""] ?? "另一处未写入。"}可选择范围后重试。` +
              (result.coverage ? ` ${coverageNote(result.coverage)}` : ""),
          });
        } else if (result.status === "busy") {
          setPhase({ kind: "busy" });
        } else if (result.status === "needs_selection") {
          setPhase({ kind: "error", message: MESSAGES[result.reason ?? ""] ?? "请先选择要概括的会话。" });
        } else if (result.status === "skipped") {
          setPhase({ kind: "error", message: MESSAGES[result.reason ?? ""] ?? "本次未写入标题。" });
        } else {
          setPhase({ kind: "error", message: MESSAGES[result.reason ?? ""] ?? "生成失败，请重试。" });
        }
      },
      () => setPhase({ kind: "error", message: "请求失败，请重试。" }),
    ).finally(() => {
      // Sessions may have appeared or gone while the request ran; refresh the
      // picker without changing the explicit selection.
      setRefreshKey((value) => value + 1);
    });
  };

  const readySessions = sessions.kind === "ready" ? sessions.sessions : [];
  const multiple = readySessions.length > 1;
  const selectedScope = SCOPES.find((option) => option.value === scope) ?? SCOPES[0];
  const notice =
    phase.kind === "running"
      ? { tone: accent.mark, title: "正在生成中文标题", body: "正在读取所选会话的可见文本。" }
      : phase.kind === "done"
        ? {
            tone: theme.colors.statusSuccess,
            title: `已更新${writtenTargets(phase.workspace, phase.session)}`,
            body: `新标题为「${phase.title}」。` + (phase.coverage ? ` ${phase.coverage}` : ""),
          }
        : phase.kind === "partial"
          ? { tone: theme.colors.statusWarning, title: `只更新了${writtenTargets(phase.workspace, phase.session)}标题`, body: phase.message }
          : phase.kind === "busy"
            ? { tone: theme.colors.statusWarning, title: "另一个生成正在进行", body: "请稍后重试。" }
            : phase.kind === "error"
              ? { tone: theme.colors.statusDanger, title: "未更新标题", body: phase.message }
              : null;

  return (
    <ScrollView style={styles.screen} contentContainerStyle={styles.content}>
      <View style={styles.header}>
        <View style={styles.badge}>
          <Text style={styles.badgeText}>
            文<Text style={styles.badgeSub}>A</Text>
          </Text>
        </View>
        <View style={styles.headerCopy}>
          <Text style={styles.heading}>工作区中文标题</Text>
          <Text style={styles.context}>概括所选会话，生成新的中文显示标题</Text>
        </View>
      </View>

      <View style={styles.card}>
        <Text style={styles.cardLabel}>当前工作区标题</Text>
        <Text style={styles.cardValue}>{currentTitle ?? "（未命名）"}</Text>
      </View>

      <View style={styles.columns}>
        <View style={styles.column}>
          <Text style={styles.sectionTitle}>{multiple ? "选择要概括的会话" : "用于概括的会话"}</Text>
          <Text style={styles.helper}>只读取所选会话的用户和助手可见文本。</Text>
          {sessions.kind === "loading" ? <Text style={styles.muted}>正在读取本工作区的会话…</Text> : null}
          {sessions.kind === "error" ? (
            <Text style={styles.error}>
              会话列表读取失败，未修改标题；重新打开面板可重试。
            </Text>
          ) : null}
          {sessions.kind === "ready" && readySessions.length === 0 ? (
            <Text style={styles.muted}>这个工作区还没有可选的普通会话，无法生成可选范围的摘要。</Text>
          ) : null}
          <View style={styles.options}>
            {readySessions.map((session) => {
              const selected = session.id === selectedId;
              const activity = activityText(session.lastActivityAt);
              return (
                <Pressable
                  key={session.id}
                  accessibilityRole="radio"
                  accessibilityState={{ selected, disabled: running }}
                  accessibilityLabel={`选择会话 ${sessionLabel(session)}`}
                  disabled={running}
                  onPress={() => {
                    setSelectedId(session.id);
                    setPhase({ kind: "idle" });
                  }}
                  style={[styles.option, selected ? styles.optionSelected : null]}
                >
                  <View style={styles.radio}>{selected ? <View style={styles.radioDot} /> : null}</View>
                  <View style={styles.optionCopy}>
                    <Text style={styles.optionLabel}>{sessionLabel(session)}</Text>
                    {activity ? <Text style={styles.optionMeta}>最近活动 · {activity}</Text> : null}
                  </View>
                </Pressable>
              );
            })}
          </View>
        </View>

        <View style={styles.column}>
          <Text style={styles.sectionTitle}>更新范围</Text>
          <Text style={styles.helper}>只改显示标题，目录、仓库和分支保持原样。</Text>
          <View style={styles.options}>
            {SCOPES.map((option) => {
              const selected = option.value === scope;
              return (
                <Pressable
                  key={option.value}
                  accessibilityRole="radio"
                  accessibilityState={{ selected, disabled: running }}
                  accessibilityLabel={`更新范围：${option.label}`}
                  disabled={running}
                  onPress={() => {
                    setScope(option.value);
                    setPhase({ kind: "idle" });
                  }}
                  style={[styles.option, selected ? styles.optionSelected : null]}
                >
                  <View style={styles.radio}>{selected ? <View style={styles.radioDot} /> : null}</View>
                  <View style={styles.optionCopy}>
                    <Text style={styles.optionLabel}>{option.label}</Text>
                    <Text style={styles.optionMeta}>{option.hint}</Text>
                  </View>
                </Pressable>
              );
            })}
          </View>
          {multiple ? <Text style={styles.helper}>其它会话不参与本次生成或改名。</Text> : null}
        </View>
      </View>

      <View style={styles.footer}>
        <Text style={styles.disclosure}>所选会话的可见文本会发送到插件设置中的标题模型。</Text>
        <Pressable
          accessibilityRole="button"
          accessibilityLabel={`生成中文标题并更新${selectedScope.label}`}
          accessibilityState={{ disabled: running || !selectedId }}
          disabled={running || !selectedId}
          onPress={press}
          style={styles.button}
        >
          <Text style={styles.buttonText}>{running ? "正在生成…" : `生成并更新${selectedScope.label}`}</Text>
        </Pressable>
        {notice ? (
          <View
            accessibilityRole="alert"
            accessibilityLiveRegion="polite"
            style={[styles.notice, { borderLeftColor: notice.tone }]}
          >
            <Text style={[styles.noticeTitle, { color: notice.tone }]}>{notice.title}</Text>
            <Text style={styles.noticeBody}>{notice.body}</Text>
          </View>
        ) : null}
      </View>
    </ScrollView>
  );
}
