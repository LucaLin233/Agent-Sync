import { useCallback, useMemo, useState } from "react";
import { Text, View } from "react-native";
import {
  type PluginSurfaceProps,
  type SettingsState,
  useSettings,
} from "@getpaseo/plugin/client";
import {
  SettingsAction,
  SettingsCard,
  SettingsInput,
  SettingsSection,
  SettingsSwitch,
} from "@getpaseo/plugin/client/ui";
import { effectiveWorkspaceScope, type EffectiveWorkspaceScope } from "../shared/scope";
import { metricsSettings } from "../shared/settings";

type ReadySettings = Extract<SettingsState<typeof metricsSettings.schema>, { status: "ready" }>;

function splitIds(text: string): string[] {
  return [...new Set(text.split(/[\s,]+/).map((id) => id.trim()).filter(Boolean))];
}

function initialRestricted(settings: ReadySettings["values"]): boolean {
  return settings.allWorkspaces === false ||
    (settings.allWorkspaces !== true && (settings.workspaceIds?.length ?? 0) > 0);
}

function AdvancedSettings({
  settings,
  scope,
  onClose,
  style,
}: {
  settings: ReadySettings;
  scope: EffectiveWorkspaceScope;
  onClose(): void;
  style: { color: string };
}) {
  const [restricted, setRestricted] = useState(() => initialRestricted(settings.values));
  const [idsText, setIdsText] = useState(() => (settings.values.workspaceIds ?? []).join("\n"));
  const [codexHome, setCodexHome] = useState(() => settings.values.codexHome ?? "");
  const [error, setError] = useState<string | null>(null);
  // Keep the revision this draft was opened with so another client's save conflicts.
  const [revision] = useState(settings.revision);

  const save = useCallback(async () => {
    const ids = splitIds(idsText);
    if (restricted && ids.length === 0) {
      setError("至少填写一个 workspace ID");
      return;
    }
    const home = codexHome.trim();
    if (home && !home.startsWith("/") && !/^[A-Za-z]:[\\/]/.test(home)) {
      setError("Codex home 必须是绝对路径");
      return;
    }
    setError(null);
    const saved = await settings.save({
      ...settings.values,
      cumulativeEnabled: settings.values.cumulativeEnabled ?? scope.enabled,
      allWorkspaces: !restricted,
      workspaceIds: restricted ? ids : [],
      codexHome: home || undefined,
    }, revision);
    if (saved) onClose();
  }, [codexHome, idsText, onClose, restricted, revision, scope.enabled, settings]);

  return (
    <SettingsCard>
      <SettingsSwitch
        label="仅限指定 workspace"
        hint="关闭时为此主机所有 workspace 各自汇总；打开后只查询列出的 ID。"
        value={restricted}
        disabled={settings.saving}
        onValueChange={setRestricted}
      />
      {restricted && (
        <SettingsInput
          label="Workspace IDs"
          hint="每行一个，也可用逗号或空格分隔。"
          initialValue={idsText}
          onChangeText={setIdsText}
          error={error ?? undefined}
          placeholder="wks_..."
          disabled={settings.saving}
        />
      )}
      <SettingsInput
        label="Codex home"
        hint="留空时自动发现 CODEX_HOME 或 ~/.codex；填写时作为显式覆盖。"
        initialValue={codexHome}
        onChangeText={setCodexHome}
        placeholder="留空自动发现"
        disabled={settings.saving}
      />
      {error && !restricted && (
        <Text accessibilityRole="alert" style={style}>{error}</Text>
      )}
      {settings.saveError && (
        <Text accessibilityRole="alert" style={style}>{settings.saveError}</Text>
      )}
      <SettingsAction
        label="保存高级设置"
        actionLabel={settings.saving ? "保存中…" : "保存"}
        disabled={settings.saving}
        onPress={save}
      />
    </SettingsCard>
  );
}

function SettingsControls({ settings, theme }: { settings: ReadySettings; theme: PluginSurfaceProps["theme"] }) {
  const [advanced, setAdvanced] = useState(false);
  const style = useMemo(() => ({ color: theme.colors.foreground }), [theme]);
  const scope = effectiveWorkspaceScope(settings.values);
  const enabled = settings.values.cumulativeEnabled ?? scope.enabled;

  const changeCumulative = useCallback((value: boolean) => {
    const next = { ...settings.values, cumulativeEnabled: value };
    if (value && !initialRestricted(settings.values)) {
      next.allWorkspaces = true;
      next.workspaceIds = [];
    }
    void settings.save(next, settings.revision);
  }, [settings]);

  return (
    <SettingsSection title="工作区用量">
      <SettingsCard>
        <SettingsSwitch
          label="累计统计"
          hint="开启后按 workspace 汇总 Codex 累计缓存率；默认只显示最近样本。"
          value={enabled}
          disabled={settings.saving}
          onValueChange={changeCumulative}
        />
        <SettingsAction
          label="高级设置"
          actionLabel={advanced ? "收起" : "展开"}
          disabled={settings.saving}
          onPress={() => setAdvanced((value) => !value)}
        />
      </SettingsCard>
      {settings.saveError && !advanced && (
        <Text accessibilityRole="alert" style={style}>{settings.saveError}</Text>
      )}
      {advanced && (
        <AdvancedSettings
          settings={settings}
          scope={scope}
          onClose={() => setAdvanced(false)}
          style={style}
        />
      )}
      <View>
        <Text style={style}>
          当前：{enabled ? (scope.allWorkspaces ? "累计统计，全部 workspace" : "累计统计，" + scope.workspaceIds.length + " 个 workspace") : "仅最近样本"}
        </Text>
      </View>
    </SettingsSection>
  );
}

export function WorkspaceMetricsSettings({ theme }: PluginSurfaceProps) {
  const settings = useSettings(metricsSettings);
  const style = useMemo(() => ({ color: theme.colors.foreground }), [theme]);
  if (settings.status === "loading") return <Text style={style}>正在读取设置…</Text>;
  if (settings.status !== "ready") {
    return (
      <SettingsSection title="工作区用量">
        <Text style={style}>{settings.error}</Text>
        <SettingsAction label="重新读取" actionLabel="重试" onPress={settings.reload} />
        {settings.status === "invalid" ? (
          <SettingsAction label="恢复默认设置" actionLabel="重置" onPress={settings.reset} />
        ) : null}
      </SettingsSection>
    );
  }
  return <SettingsControls settings={settings} theme={theme} />;
}
