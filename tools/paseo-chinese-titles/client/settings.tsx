import { useSettings, type PluginSurfaceProps } from "@getpaseo/plugin/client";
import { SettingsAction, SettingsCard, SettingsInput, SettingsSection, SettingsSwitch } from "@getpaseo/plugin/client/ui";
import { useState } from "react";
import { Text, View } from "react-native";
import { CHINESE_TITLES_SETTINGS, type ChineseTitlesSettings } from "../shared/settings";

export function ChineseTitlesSettingsScreen({ theme }: PluginSurfaceProps) {
  const settings = useSettings(CHINESE_TITLES_SETTINGS);
  const [draft, setDraft] = useState<{ values: ChineseTitlesSettings; revision: string } | null>(null);
  const [error, setError] = useState<string | null>(null);

  if (settings.status === "loading") {
    return <Text style={{ color: theme.colors.foregroundMuted }}>正在读取设置…</Text>;
  }
  if (settings.status !== "ready") {
    return <Text style={{ color: theme.colors.statusDanger }}>{settings.error}</Text>;
  }

  const values = draft?.values ?? settings.values;
  const revision = draft?.revision ?? settings.revision;
  const update = (patch: Partial<ChineseTitlesSettings>) => {
    setError(null);
    setDraft((current) => ({
      values: { ...(current?.values ?? settings.values), ...patch },
      revision: current?.revision ?? settings.revision,
    }));
  };
  const save = () => {
    if (!draft || settings.saving) return;
    setError(null);
    const { values: next, revision: baseRevision } = draft;
    void settings.save(next, baseRevision).then((ok) => {
      if (ok) setDraft(null);
      else setError("保存失败；设置可能已被其他客户端更新，请重试。");
    });
  };

  return (
    <View style={{ gap: 20 }}>
      <SettingsSection title="自动命名">
        <SettingsCard>
          <SettingsSwitch
            label="新项目侧栏名称"
            hint="只写项目显示覆盖，不改目录。"
            value={values.autoNameProjects}
            disabled={settings.saving}
            onValueChange={(autoNameProjects) => update({ autoNameProjects })}
          />
          <SettingsSwitch
            label="新工作区标题"
            hint="首个真实任务到达时生成一次。"
            value={values.autoNameWorkspaces}
            disabled={settings.saving}
            onValueChange={(autoNameWorkspaces) => update({ autoNameWorkspaces })}
          />
          <SettingsSwitch
            label="新会话标题"
            hint="默认关闭；开启前先关闭 Better Paseo「自动优化新任务标题」。"
            value={values.autoNameSessions}
            disabled={settings.saving}
            onValueChange={(autoNameSessions) => update({ autoNameSessions })}
          />
        </SettingsCard>
      </SettingsSection>
      <SettingsSection title="Codex provider 与模型">
        <SettingsCard>
          <SettingsInput
            key={`provider-${revision}`}
            label="Provider"
            hint="留空自动选择已就绪的 Codex provider 或别名；示例：cchp"
            initialValue={values.provider}
            placeholder="cchp"
            disabled={settings.saving}
            onChangeText={(provider) => update({ provider })}
          />
          <SettingsInput
            key={`model-${revision}`}
            label="Model"
            hint="留空使用默认模型；示例：deepseek-flash"
            initialValue={values.model}
            placeholder="deepseek-flash"
            disabled={settings.saving}
            onChangeText={(model) => update({ model })}
          />
          <SettingsInput
            key={`thinking-${revision}`}
            label="Thinking 档位"
            hint="可留空，使用模型默认档。"
            initialValue={values.thinkingOptionId}
            placeholder="low"
            disabled={settings.saving}
            onChangeText={(thinkingOptionId) => update({ thinkingOptionId })}
          />
        </SettingsCard>
      </SettingsSection>
      {draft ? <SettingsAction label="保存设置" hint="修改会保留在本页，点击后按当前 revision 写入。" actionLabel="保存" onPress={save} disabled={settings.saving} /> : null}
      {settings.saving ? <Text style={{ color: theme.colors.foregroundMuted }}>正在保存…</Text> : null}
      {error ? <Text style={{ color: theme.colors.statusDanger }}>{error}</Text> : null}
    </View>
  );
}
