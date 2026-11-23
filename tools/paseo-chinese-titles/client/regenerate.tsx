import {
  type PluginWorkspacePanelProps,
  useRpc,
  useWorkspace,
} from "@getpaseo/plugin/client";
import { useEffect, useMemo, useState } from "react";
import { Pressable, Text, View } from "react-native";
import { listWorkspaceSessionsRpc, regenerateWorkspaceTitleRpc } from "../shared/rpc";

type Scope = "both" | "workspace" | "session";

type Phase =
  | { kind: "idle" }
  | { kind: "running" }
  | { kind: "done"; title: string; workspace: boolean; session: boolean }
  | { kind: "partial"; title: string; workspace: boolean; session: boolean; message: string }
  | { kind: "busy" }
  | { kind: "error"; message: string };

type SessionList =
  | { kind: "loading" }
  | { kind: "ready"; sessions: Array<{ id: string; title: string | null; lastActivityAt: string | null }> }
  | { kind: "error" };

const SCOPES: ReadonlyArray<{ value: Scope; label: string; hint: string }> = [
  { value: "both", label: "工作区和所选会话", hint: "两处使用同一个中文摘要标题。" },
  { value: "workspace", label: "仅工作区", hint: "不改所选会话标题。" },
  { value: "session", label: "仅所选会话", hint: "不改工作区标题和自动命名状态。" },
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
  empty_conversation: "所选会话没有可概括的用户或助手文本，未修改原标题。",
  conversation_unavailable: "读取所选会话失败，未修改原标题；可以重试。",
  no_session: "这个工作区还没有可选的普通会话，未修改原标题。",
  choose_session: "请先选择要概括的会话。",
  session_not_selectable: "所选会话不在这个工作区或不可选，请重新选择。",
};

function sessionLabel(session: { id: string; title: string | null }): string {
  const title = session.title?.trim();
  return title ? title : `未命名会话 ${session.id.slice(0, 8)}`;
}

function writtenTargets(workspace: boolean, session: boolean): string {
  if (workspace && session) return "工作区和所选会话";
  if (workspace) return "工作区";
  return "所选会话";
}

export function ChineseTitlePanel({ theme, layout, workspaceId }: PluginWorkspacePanelProps) {
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

  const styles = useMemo(
    () => ({
      screen: {
        flex: 1,
        padding: layout.compact ? 16 : 24,
        gap: layout.compact ? 8 : 12,
        backgroundColor: theme.colors.surface0,
      },
      title: {
        color: theme.colors.foreground,
        fontSize: layout.compact ? 18 : 20,
        fontWeight: "600" as const,
      },
      current: { color: theme.colors.foregroundMuted },
      label: { color: theme.colors.foreground, fontWeight: "600" as const },
      hint: { color: theme.colors.foregroundMuted, fontSize: 12 },
      option: {
        paddingVertical: 10,
        paddingHorizontal: 12,
        borderRadius: 8,
        borderWidth: 1,
        borderColor: theme.colors.border,
        backgroundColor: theme.colors.surface1,
        opacity: running ? 0.6 : 1,
      },
      optionSelected: { borderColor: theme.colors.accent, backgroundColor: theme.colors.surface2 },
      optionText: { color: theme.colors.foreground },
      optionMeta: { color: theme.colors.foregroundMuted, fontSize: 12 },
      button: {
        paddingVertical: 12,
        paddingHorizontal: 16,
        borderRadius: 10,
        backgroundColor: theme.colors.accent,
        opacity: running || !selectedId ? 0.5 : 1,
      },
      buttonText: {
        color: theme.colors.accentForeground,
        textAlign: "center" as const,
        fontWeight: "600" as const,
      },
      running: { color: theme.colors.foregroundMuted },
      done: { color: theme.colors.statusSuccess },
      busy: { color: theme.colors.statusWarning },
      error: { color: theme.colors.statusDanger },
    }),
    [theme, layout.compact, running, selectedId],
  );

  const press = () => {
    if (running || !selectedId) return;
    setPhase({ kind: "running" });
    void regenerate({ workspaceId, agentId: selectedId, scope }).then(
      (result) => {
        const title = result.title ?? "";
        const workspace = result.workspaceUpdated;
        const session = result.sessionUpdated;
        if (result.status === "done") {
          setPhase({ kind: "done", title, workspace, session });
        } else if (result.status === "partial") {
          setPhase({
            kind: "partial",
            title,
            workspace,
            session,
            message: `只更新了${writtenTargets(workspace, session)}；${MESSAGES[result.reason ?? ""] ?? "另一处未写入。"}可以重试。`,
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

  return (
    <View style={styles.screen}>
      <Text style={styles.title}>工作区中文标题</Text>
      <Text style={styles.current}>当前标题：{currentTitle ?? "（未命名）"}</Text>
      <Text style={styles.hint}>
        只修改显示标题，不改目录、仓库或分支。手动生成会读取所选会话的用户与助手可见文本，发送到设置中指定的标题模型，概括这个会话实际讨论的主题。
      </Text>

      <Text style={styles.label}>{multiple ? "选择要概括的会话" : "用于概括的会话"}</Text>
      {sessions.kind === "loading" ? <Text style={styles.hint}>正在读取本工作区的会话…</Text> : null}
      {sessions.kind === "error" ? (
        <Text style={styles.error}>会话列表读取失败，未修改标题；重新打开面板可重试。</Text>
      ) : null}
      {sessions.kind === "ready" && readySessions.length === 0 ? (
        <Text style={styles.hint}>这个工作区还没有可选的普通会话，无法生成可选范围的摘要。</Text>
      ) : null}
      {readySessions.map((session) => {
        const selected = session.id === selectedId;
        return (
          <Pressable
            key={session.id}
            accessibilityRole="button"
            accessibilityState={{ selected, disabled: running }}
            accessibilityLabel={`选择会话 ${sessionLabel(session)}`}
            disabled={running}
            onPress={() => {
              setSelectedId(session.id);
              setPhase({ kind: "idle" });
            }}
            style={[styles.option, selected ? styles.optionSelected : null]}
          >
            <Text style={styles.optionText}>{sessionLabel(session)}{selected ? "（已选择）" : ""}</Text>
            {session.lastActivityAt ? (
              <Text style={styles.optionMeta}>最近活动：{session.lastActivityAt.slice(0, 16).replace("T", " ")}</Text>
            ) : null}
          </Pressable>
        );
      })}

      <Text style={styles.label}>更新范围</Text>
      {SCOPES.map((option) => {
        const selected = option.value === scope;
        return (
          <Pressable
            key={option.value}
            accessibilityRole="button"
            accessibilityState={{ selected, disabled: running }}
            accessibilityLabel={`更新范围：${option.label}`}
            disabled={running}
            onPress={() => {
              setScope(option.value);
              setPhase({ kind: "idle" });
            }}
            style={[styles.option, selected ? styles.optionSelected : null]}
          >
            <Text style={styles.optionText}>{option.label}{selected ? "（当前）" : ""}</Text>
            <Text style={styles.optionMeta}>{option.hint}</Text>
          </Pressable>
        );
      })}
      {multiple ? (
        <Text style={styles.hint}>其它会话不参与本次生成或改名。</Text>
      ) : null}

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
      {phase.kind === "running" ? <Text style={styles.running}>正在读取所选会话并生成中文标题…</Text> : null}
      {phase.kind === "done" ? (
        <Text style={styles.done}>已更新{writtenTargets(phase.workspace, phase.session)}为「{phase.title}」。</Text>
      ) : null}
      {phase.kind === "partial" ? (
        <Text style={styles.error}>{phase.message}</Text>
      ) : null}
      {phase.kind === "busy" ? <Text style={styles.busy}>另一个生成正在进行，请稍后重试。</Text> : null}
      {phase.kind === "error" ? <Text style={styles.error}>{phase.message}</Text> : null}
    </View>
  );
}
