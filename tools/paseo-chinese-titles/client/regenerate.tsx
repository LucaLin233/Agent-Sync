import {
  type PluginWorkspacePanelProps,
  useRpc,
  useWorkspace,
} from "@getpaseo/plugin/client";
import { useMemo, useState } from "react";
import { Pressable, Text, View } from "react-native";
import { regenerateWorkspaceTitleRpc } from "../shared/rpc";

type Phase =
  | { kind: "idle" }
  | { kind: "running" }
  | { kind: "done"; title: string }
  | { kind: "busy" }
  | { kind: "error"; message: string };

const MESSAGES: Record<string, string> = {
  timeout: "生成超时，未写入标题；可以重试。",
  manual_change: "生成期间标题已被手动修改，本次未覆盖。",
  not_found: "工作区不存在或已归档。",
  excluded: "后台或插件辅助工作区不参与重命名。",
  verification_failed: "写入后回读不一致，请重试。",
  settings_unavailable: "设置不可用，请检查插件设置后重试。",
  internal_failed: "生成失败，请重试。",
};

export function ChineseTitlePanel({ theme, layout, workspaceId }: PluginWorkspacePanelProps) {
  const currentTitle = useWorkspace(workspaceId, (workspace) => workspace.title);
  const regenerate = useRpc(regenerateWorkspaceTitleRpc);
  const [phase, setPhase] = useState<Phase>({ kind: "idle" });
  const running = phase.kind === "running";

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
      hint: { color: theme.colors.foregroundMuted, fontSize: 12 },
      button: {
        paddingVertical: 12,
        paddingHorizontal: 16,
        borderRadius: 10,
        backgroundColor: theme.colors.accent,
        opacity: running ? 0.6 : 1,
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
    [theme, layout.compact, running],
  );

  const press = () => {
    if (running) return;
    setPhase({ kind: "running" });
    void regenerate({ workspaceId }).then(
      (result) => {
        if (result.status === "done") {
          setPhase({ kind: "done", title: result.title ?? "" });
        } else if (result.status === "busy") {
          setPhase({ kind: "busy" });
        } else if (result.status === "skipped") {
          setPhase({ kind: "error", message: MESSAGES[result.reason ?? ""] ?? "本次未写入标题。" });
        } else {
          setPhase({ kind: "error", message: MESSAGES[result.reason ?? ""] ?? "生成失败，请重试。" });
        }
      },
      () => setPhase({ kind: "error", message: "请求失败，请重试。" }),
    );
  };

  return (
    <View style={styles.screen}>
      <Text style={styles.title}>工作区中文标题</Text>
      <Text style={styles.current}>当前标题：{currentTitle ?? "（未命名）"}</Text>
      <Text style={styles.hint}>只修改显示标题，不改目录、仓库或分支；旧英文工作区也可使用。每次点击只处理一次，完成后可再次点击。</Text>
      <Pressable
        accessibilityRole="button"
        accessibilityLabel="重新生成中文标题"
        accessibilityState={{ disabled: running }}
        disabled={running}
        onPress={press}
        style={styles.button}
      >
        <Text style={styles.buttonText}>{running ? "正在生成…" : "重新生成中文标题"}</Text>
      </Pressable>
      {phase.kind === "running" ? <Text style={styles.running}>正在读取首个真实任务并生成中文标题…</Text> : null}
      {phase.kind === "done" ? <Text style={styles.done}>已更新为「{phase.title}」。</Text> : null}
      {phase.kind === "busy" ? <Text style={styles.busy}>另一个生成正在进行，请稍后重试。</Text> : null}
      {phase.kind === "error" ? <Text style={styles.error}>{phase.message}</Text> : null}
    </View>
  );
}
