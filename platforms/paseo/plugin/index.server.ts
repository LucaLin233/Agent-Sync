import type { PluginServerContext } from "@getpaseo/plugin/server";

const HOST_LUNO_INSTRUCTION =
  "本 daemon 的共享 Codex 通道使用 cchp 和 gdr 两个 provider。按 get_agent_status 中同一活线程的 codexRoleVerification 核对 role、upstream、resolvedModel 及三项核验标志。每次派发用 list_profiles 按 options.paseo_role、options.paseo_upstream 选同上游唯一 profile。沿用 luno-core 的权限与工作区门禁，将选中 profile 的 options、modeId、thinkingOptionId 传给 create_agent，正式任务只用一次 initialPrompt 投递，宿主在首轮请求前验证角色与模型。证据缺失或不符时按原规则停依赖步骤。未采用共享启动的端仍按既有规则。";
import {
  ROLE_METADATA_KEY,
  launchFor,
  legacyAgentAllowed,
  legacyLunoBinding,
  readBinding,
  selectCreateBinding,
  stripRoleOptions,
  upstreamOfProvider,
} from "./server/roles.js";

export default function contribute(server: PluginServerContext) {
  server.addHook("agent.create.before", async ({ request }) => {
    if (!upstreamOfProvider(request.config.provider)) return request;
    const options = {
      ...(request.config as { featureValues?: Record<string, unknown> }).featureValues,
      ...request.config.providerOptions,
    };
    // Explicit profile options are the only source for a new binding. Metadata sent by a
    // public create/import is not trusted, and a stored binding is not reused as a create.
    const binding = selectCreateBinding({ provider: request.config.provider, options });
    return {
      ...request,
      metadata: { ...request.metadata, [ROLE_METADATA_KEY]: binding },
      config: stripRoleOptions(request.config),
    };
  });

  server.addHook("agent.open.before", async ({ request }) => {
    if (!upstreamOfProvider(request.provider)) return request;
    if (request.reason === "import") {
      throw new Error(
        "shared-role-providers: importing into a shared role provider is not allowed",
      );
    }
    const read = readBinding(request.metadata);
    if (read.kind === "invalid") {
      throw new Error(
        `shared-role-providers: agent '${request.agentId}' has an invalid role binding`,
      );
    }
    const binding =
      read.kind === "valid"
        ? read.binding
        : request.reason !== "create" &&
          legacyAgentAllowed(request.agentId, request.provider) &&
          legacyLunoBinding(request.provider);
    if (!binding) {
      throw new Error(
        `shared-role-providers: refusing to open '${request.provider}' without a role binding`,
      );
    }
    const launch = launchFor(binding);
    const next = {
      ...request,
      env: {
        ...request.env,
        CODEX_HOME: launch.codexHome,
        PASEO_CODEX_ROLE_SOURCE: launch.roleSource,
        PASEO_CODEX_ROLE_MODEL_PROVIDER: launch.upstream,
        PASEO_CODEX_ROLE: binding.role,
      },
    };
    if (binding.role === "LUNO" && request.purpose === "interactive") {
      return {
        ...next,
        appendSystemPrompt: [...(request.appendSystemPrompt ?? []), HOST_LUNO_INSTRUCTION],
      };
    }
    return next;
  });
  return () => {};
}
