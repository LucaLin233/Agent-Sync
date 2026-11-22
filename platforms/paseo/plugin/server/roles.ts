import type { AgentSessionConfig } from "@getpaseo/protocol/agent-types";
import type { ProviderOptions } from "@getpaseo/protocol/agent-types";

export const ROLE_METADATA_KEY = "shared-role-providers.binding";
export const ROLE_OPTION = "paseo_role";
export const UPSTREAM_OPTION = "paseo_upstream";
export const SHARED_PROVIDERS = ["cchp", "gdr"] as const;

export type Role = "LUNO" | "LENS" | "FORGE";
export type Upstream = "cchp" | "gdr";

export interface RoleBinding {
  v: 1;
  role: Role;
  upstream: Upstream;
}

export interface RoleLaunch {
  codexHome: string;
  roleSource: string;
  upstream: Upstream;
  disableSubagents: boolean;
}

/**
 * Deployment values live in one table: a deployment changes paths here, never in the hook
 * logic. The LUNO entries share the main Codex home; `lens-codex` and the other role names
 * are directory names, not provider IDs.
 */
export const ROLE_TABLE: Record<
  Role,
  Record<Upstream, { codexHome: string; roleSource: string; disableSubagents: boolean }>
> = {
  LUNO: {
    cchp: {
      codexHome: "/home/example/codex-home",
      roleSource: "/home/example/.luno/agent-sync/prompt/LUNO.md",
      disableSubagents: false,
    },
    gdr: {
      codexHome: "/home/example/codex-home",
      roleSource: "/home/example/.luno/agent-sync/prompt/LUNO.md",
      disableSubagents: false,
    },
  },
  LENS: {
    cchp: {
      codexHome: "/home/example/.luno/homes/lens-codex",
      roleSource: "/home/example/.luno/agent-sync/subagents/LENS.md",
      disableSubagents: true,
    },
    gdr: {
      codexHome: "/home/example/.luno/homes/lens-gdr",
      roleSource: "/home/example/.luno/agent-sync/subagents/LENS.md",
      disableSubagents: true,
    },
  },
  FORGE: {
    cchp: {
      codexHome: "/home/example/.luno/homes/forge-codex",
      roleSource: "/home/example/.luno/agent-sync/subagents/FORGE.md",
      disableSubagents: true,
    },
    gdr: {
      codexHome: "/home/example/.luno/homes/forge-gdr",
      roleSource: "/home/example/.luno/agent-sync/subagents/FORGE.md",
      disableSubagents: true,
    },
  },
};

export function upstreamOfProvider(provider: string): Upstream | null {
  if (provider === "cchp") return "cchp";
  if (provider === "gdr") return "gdr";
  return null;
}

export function isRole(value: unknown): value is Role {
  return value === "LUNO" || value === "LENS" || value === "FORGE";
}

export function isUpstream(value: unknown): value is Upstream {
  return value === "cchp" || value === "gdr";
}

export type BindingRead =
  | { kind: "absent" }
  | { kind: "invalid" }
  | { kind: "valid"; binding: RoleBinding };

export function readBinding(metadata: Record<string, unknown> | undefined): BindingRead {
  const raw = metadata?.[ROLE_METADATA_KEY];
  if (raw === undefined) return { kind: "absent" };
  if (!raw || typeof raw !== "object" || Array.isArray(raw)) return { kind: "invalid" };
  const { v, role, upstream } = raw as Record<string, unknown>;
  if (v !== 1 || !isRole(role) || !isUpstream(upstream)) return { kind: "invalid" };
  return { kind: "valid", binding: { v: 1, role, upstream } };
}

/** Deployment-injected allowlist; only these pre-switch LUNO agents may resume without binding. */
export function legacyAgentAllowed(agentId: string, provider: string): boolean {
  const raw = process.env.PASEO_ROLE_LEGACY_AGENT_IDS?.trim();
  if (!raw) return false;
  return raw
    .split(",")
    .map((entry) => entry.trim())
    .filter(Boolean)
    .some((entry) => {
      const separator = entry.lastIndexOf(":");
      return (
        separator > 0 &&
        entry.slice(0, separator) === agentId &&
        entry.slice(separator + 1) === provider
      );
    });
}

/** A stored LUNO agent that predates role metadata continues as LUNO on its own upstream. */
export function legacyLunoBinding(provider: string): RoleBinding | null {
  const upstream = upstreamOfProvider(provider);
  return upstream ? { v: 1, role: "LUNO", upstream } : null;
}

export function launchFor(binding: RoleBinding): RoleLaunch {
  const entry = ROLE_TABLE[binding.role][binding.upstream];
  return {
    codexHome: entry.codexHome,
    roleSource: entry.roleSource,
    upstream: binding.upstream,
    disableSubagents: entry.disableSubagents,
  };
}

export function optionValue(options: ProviderOptions | undefined, key: string): unknown {
  return options?.[key];
}

/**
 * New agents carry the role in profile options. A stored binding is re-checked, so a create
 * that revives a record cannot be pointed at a different role by options.
 */
export function selectCreateBinding(input: {
  provider: string;
  options: ProviderOptions | undefined;
}): RoleBinding {
  const upstream = upstreamOfProvider(input.provider);
  if (!upstream) {
    throw new Error(
      `shared-role-providers: provider '${input.provider}' is not a shared role provider`,
    );
  }
  const role = optionValue(input.options, ROLE_OPTION);
  const optionUpstream = optionValue(input.options, UPSTREAM_OPTION);
  if (role === undefined && optionUpstream === undefined) {
    throw new Error(
      `shared-role-providers: '${input.provider}' requires profile options ${ROLE_OPTION} and ${UPSTREAM_OPTION}`,
    );
  }
  if (!isRole(role) || !isUpstream(optionUpstream)) {
    throw new Error(
      `shared-role-providers: invalid role binding (${String(role)} / ${String(optionUpstream)})`,
    );
  }
  if (optionUpstream !== upstream) {
    throw new Error(
      `shared-role-providers: option upstream '${optionUpstream}' does not match provider '${input.provider}'`,
    );
  }
  return { v: 1, role, upstream: optionUpstream };
}

/** Remove role routing from provider options so the Codex adapter only sees real options. */
export function stripRoleOptions(config: AgentSessionConfig): AgentSessionConfig {
  const providerOptions = config.providerOptions;
  const featureValues = (config as { featureValues?: Record<string, unknown> }).featureValues;
  const clean = <T extends Record<string, unknown> | undefined>(value: T): T => {
    if (!value) return value;
    const { [ROLE_OPTION]: _role, [UPSTREAM_OPTION]: _upstream, ...rest } = value;
    return rest as T;
  };
  return {
    ...config,
    ...(providerOptions ? { providerOptions: clean(providerOptions) } : {}),
    ...(featureValues ? { featureValues: clean(featureValues) } : {}),
  } as AgentSessionConfig;
}
