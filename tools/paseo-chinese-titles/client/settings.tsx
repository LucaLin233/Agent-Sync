import { useRpc, useSettings, type PluginSurfaceProps } from "@getpaseo/plugin/client";
import { SettingsAction, SettingsCard, SettingsSection, SettingsSelect, SettingsSwitch } from "@getpaseo/plugin/client/ui";
import { useEffect, useState } from "react";
import { Text, View } from "react-native";
import { CHINESE_TITLES_SETTINGS, type ChineseTitlesSettings } from "../shared/settings";
import { titleCatalogRpc } from "../shared/rpc";

interface CatalogModel {
  id: string;
  label: string;
  isDefault: boolean;
  defaultThinkingOptionId?: string;
  thinkingOptions: Array<{ id: string; label: string; isDefault: boolean }>;
}
interface CatalogProvider {
  id: string;
  label: string;
  models: CatalogModel[];
}
interface Catalog {
  providers: CatalogProvider[];
}

export function ChineseTitlesSettingsScreen({ theme }: PluginSurfaceProps) {
  const settings = useSettings(CHINESE_TITLES_SETTINGS);
  const loadCatalog = useRpc(titleCatalogRpc);
  const [catalog, setCatalog] = useState<Catalog | null>(null);
  const [catalogState, setCatalogState] = useState<"loading" | "ready" | "error">("loading");
  const [draft, setDraft] = useState<{ values: ChineseTitlesSettings; revision: string } | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    setCatalogState("loading");
    void loadCatalog({}).then(
      (result) => {
        if (!alive) return;
        setCatalog(result);
        setCatalogState("ready");
      },
      () => {
        if (!alive) return;
        setCatalogState("error");
      },
    );
    return () => { alive = false; };
  }, [loadCatalog]);

  if (settings.status === "loading") {
    return <Text style={{ color: theme.colors.foregroundMuted }}>正在读取设置…</Text>;
  }
  if (settings.status !== "ready") {
    return <Text style={{ color: theme.colors.statusDanger }}>{settings.error}</Text>;
  }

  const values = draft?.values ?? settings.values;
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

  const providerOptions = [
    { value: "", label: "自动选择就绪的 Codex provider" },
    ...(catalog?.providers ?? []).map((provider) => ({ value: provider.id, label: provider.label })),
  ];
  if (values.provider && !providerOptions.some((option) => option.value === values.provider)) {
    providerOptions.push({ value: values.provider, label: `不可用：${values.provider}` });
  }
  const selectedProvider = catalog?.providers.find((provider) => provider.id === values.provider);
  const modelOptions = values.provider
    ? [
        { value: "", label: "模型默认" },
        ...(selectedProvider?.models ?? []).map((model) => ({ value: model.id, label: model.label })),
      ]
    : [{ value: "", label: "自动模型" }];
  if (values.model && !modelOptions.some((option) => option.value === values.model)) {
    modelOptions.push({ value: values.model, label: `不可用：${values.model}` });
  }
  const selectedModel = selectedProvider?.models.find((model) => model.id === values.model);
  const thinkingOptions = [
    { value: "", label: "默认思考档" },
    ...(selectedModel?.thinkingOptions ?? []).map((option) => ({ value: option.id, label: option.label })),
  ];
  if (values.thinkingOptionId && !thinkingOptions.some((option) => option.value === values.thinkingOptionId)) {
    thinkingOptions.push({ value: values.thinkingOptionId, label: `不可用：${values.thinkingOptionId}` });
  }
  const catalogHint =
    catalogState === "loading"
      ? "正在读取 daemon 的 Codex provider 目录…"
      : catalogState === "error"
        ? "Provider 目录读取失败；保留已保存值，重新打开设置页可重试。"
        : (catalog?.providers.length ?? 0) === 0
          ? "当前没有就绪的 Codex provider 或 Codex 别名。"
          : undefined;

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
          <SettingsSelect
            label="Provider"
            hint={catalogHint ?? "只列就绪的 Codex 内置或 extends codex 别名。"}
            value={values.provider}
            options={providerOptions}
            disabled={settings.saving || catalogState === "loading"}
            onValueChange={(provider) => update({ provider, model: "", thinkingOptionId: "" })}
          />
          <SettingsSelect
            label="Model"
            hint={values.provider ? "只列该 provider 的可选模型。" : "先选择 Provider 才能限定模型。"}
            value={values.model}
            options={modelOptions}
            disabled={settings.saving || catalogState === "loading" || !values.provider}
            onValueChange={(model) => update({ model, thinkingOptionId: "" })}
          />
          <SettingsSelect
            label="Thinking 档位"
            hint={selectedModel ? "使用该模型提供的思考档位。" : "选择模型后可选。"}
            value={values.thinkingOptionId}
            options={thinkingOptions}
            disabled={settings.saving || catalogState === "loading" || !selectedModel}
            onValueChange={(thinkingOptionId) => update({ thinkingOptionId })}
          />
        </SettingsCard>
      </SettingsSection>
      {draft ? <SettingsAction label="保存设置" hint="修改会保留在本页，点击后按当前 revision 写入。" actionLabel="保存" onPress={save} disabled={settings.saving} /> : null}
      {settings.saving ? <Text style={{ color: theme.colors.foregroundMuted }}>正在保存…</Text> : null}
      {error ? <Text style={{ color: theme.colors.statusDanger }}>{error}</Text> : null}
    </View>
  );
}
