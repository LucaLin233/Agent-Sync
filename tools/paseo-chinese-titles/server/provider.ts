import type { PaseoApi } from "./paseo-types";
import type { ChineseTitlesSettings } from "../shared/settings";

interface ProviderOverride {
  extends?: string;
  enabled?: boolean;
  label?: string;
}

interface ProviderModel {
  id: string;
  label?: string;
  isDefault?: boolean;
  isSelectable?: boolean;
  defaultThinkingOptionId?: string;
  thinkingOptions?: readonly { id: string; label?: string; isDefault?: boolean }[];
}

interface ProviderEntry {
  provider: string;
  status: string;
  enabled?: boolean;
  label?: string;
  models?: readonly ProviderModel[];
}

export interface TitleProviderCatalog {
  providers: Array<{
    id: string;
    label: string;
    models: Array<{
      id: string;
      label: string;
      isDefault: boolean;
      defaultThinkingOptionId?: string;
      thinkingOptions: Array<{ id: string; label: string; isDefault: boolean }>;
    }>;
  }>;
}

export interface ResolvedTitleProvider {
  provider: string;
  model: string;
  thinkingOptionId?: string;
  /** `codex` or the alias whose `extends` chain reaches codex. */
  family: string;
}

function isCodexFamily(provider: string, overrides: Record<string, ProviderOverride>): boolean {
  if (provider === "pi") return false;
  let current = provider;
  for (let depth = 0; depth < 6; depth += 1) {
    if (current === "codex") return true;
    const next = overrides[current]?.extends?.trim();
    if (!next) return false;
    current = next;
  }
  return false;
}

function selectModel(models: readonly ProviderModel[], configured: string): ProviderModel | null {
  if (configured) return models.find((model) => model.id === configured) ?? null;
  return models.find((model) => model.isDefault) ?? models.find((model) => model.isSelectable !== false) ?? models[0] ?? null;
}

function thinkingFor(model: ProviderModel, configured: string): string | undefined {
  if (configured && model.thinkingOptions?.some((option) => option.id === configured)) return configured;
  return model.defaultThinkingOptionId;
}

async function modelsFor(paseo: PaseoApi, provider: string, entry?: ProviderEntry): Promise<readonly ProviderModel[]> {
  if (entry?.models && entry.models.length > 0) return entry.models;
  const catalog = await paseo.providers.listModels(provider);
  return (catalog.models ?? []) as unknown as readonly ProviderModel[];
}

/**
 * Only Codex providers and aliases whose config override `extends: "codex"`.
 * The daemon's provider snapshot does not expose that family, so the config
 * override record is the authoritative source for aliases such as cchp/gdr.
 */
export async function resolveTitleProvider(
  paseo: PaseoApi,
  settings: ChineseTitlesSettings,
): Promise<ResolvedTitleProvider> {
  const config = await paseo.config.get();
  const overrides = ((config.config.providers ?? {}) as Record<string, ProviderOverride>);
  const snapshot = await paseo.providers.snapshot();
  const entries = (snapshot.entries ?? []) as unknown as ProviderEntry[];
  const ready = entries.filter((entry) => entry.enabled !== false && entry.status === "ready");

  if (settings.provider) {
    const entry = ready.find((candidate) => candidate.provider === settings.provider);
    if (!entry) throw new Error(`Codex provider ${settings.provider} is not configured or ready.`);
    if (!isCodexFamily(entry.provider, overrides)) {
      throw new Error(`Provider ${entry.provider} is not a Codex provider or Codex alias.`);
    }
    const models = await modelsFor(paseo, entry.provider, entry);
    const model = selectModel(models, settings.model);
    if (!model) throw new Error(`Provider ${entry.provider} has no usable model.`);
    return {
      provider: entry.provider,
      model: model.id,
      thinkingOptionId: thinkingFor(model, settings.thinkingOptionId),
      family: "codex",
    };
  }

  const configOrder = Object.keys(overrides);
  const ordered = [...ready].sort((left, right) => {
    const leftIndex = configOrder.indexOf(left.provider);
    const rightIndex = configOrder.indexOf(right.provider);
    return (leftIndex === -1 ? Number.MAX_SAFE_INTEGER : leftIndex) -
      (rightIndex === -1 ? Number.MAX_SAFE_INTEGER : rightIndex);
  });

  for (const entry of ordered) {
    if (!isCodexFamily(entry.provider, overrides)) continue;
    const models = await modelsFor(paseo, entry.provider, entry).catch(() => []);
    const model = selectModel(models, settings.model);
    if (!model) continue;
    return {
      provider: entry.provider,
      model: model.id,
      thinkingOptionId: thinkingFor(model, settings.thinkingOptionId),
      family: "codex",
    };
  }
  throw new Error("No ready Codex provider (or Codex alias) with a usable model is configured.");
}

/** Non-secret catalog for the settings screen: ready Codex providers and aliases only. */
export async function listTitleProviderOptions(paseo: PaseoApi): Promise<TitleProviderCatalog> {
  const config = await paseo.config.get();
  const overrides = (config.config.providers ?? {}) as Record<string, ProviderOverride>;
  const snapshot = await paseo.providers.snapshot();
  const entries = (snapshot.entries ?? []) as unknown as ProviderEntry[];
  const ready = entries.filter((entry) => entry.enabled !== false && entry.status === "ready");
  const configOrder = Object.keys(overrides);
  ready.sort((left, right) => {
    const leftIndex = configOrder.indexOf(left.provider);
    const rightIndex = configOrder.indexOf(right.provider);
    return (leftIndex === -1 ? Number.MAX_SAFE_INTEGER : leftIndex) -
      (rightIndex === -1 ? Number.MAX_SAFE_INTEGER : rightIndex);
  });
  const providers: TitleProviderCatalog["providers"] = [];
  for (const entry of ready) {
    if (!isCodexFamily(entry.provider, overrides)) continue;
    const models = await modelsFor(paseo, entry.provider, entry).catch(() => []);
    const selectable = models.filter((model) => model.isSelectable !== false);
    if (selectable.length === 0) continue;
    providers.push({
      id: entry.provider,
      label: entry.label?.trim() || overrides[entry.provider]?.label?.trim() || entry.provider,
      models: selectable.map((model) => ({
        id: model.id,
        label: model.label?.trim() || model.id,
        isDefault: model.isDefault === true,
        ...(model.defaultThinkingOptionId ? { defaultThinkingOptionId: model.defaultThinkingOptionId } : {}),
        thinkingOptions: (model.thinkingOptions ?? []).map((option) => ({
          id: option.id,
          label: option.label?.trim() || option.id,
          isDefault: option.isDefault === true,
        })),
      })),
    });
  }
  return { providers };
}
