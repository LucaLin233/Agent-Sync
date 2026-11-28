import { useRpc, type PluginButtonIconProps } from "@getpaseo/plugin/client";
import { Icon } from "@getpaseo/plugin/client/ui";
import { useEffect } from "react";
import { workspaceScopeRpc, type WorkspaceScope } from "../shared/scope";
import { readFirstScope } from "./first-scope-read";

/**
 * The composer pill's icon also owns its first scope read. A button icon renders
 * inside the host's plugin surface providers, so its `useRpc` reaches the same
 * host-scoped RPC the popover already proved, on cold starts where the
 * bundle-level runtime never sees a settings event. It only hands the scope to
 * that one runtime, which keeps members, single-flight reads, and the shared
 * label as they are.
 */
export function createPillIcon(runtime: {
  adoptScope(scope: WorkspaceScope): boolean;
  hasScope(): boolean;
}) {
  return function PillIcon({ size, color }: PluginButtonIconProps) {
    const readScope = useRpc(workspaceScopeRpc);
    useEffect(() => readFirstScope({
      read: () => readScope({}),
      adopt: (scope) => runtime.adoptScope(scope),
      settled: () => runtime.hasScope(),
      schedule(callback, delayMs) {
        const timer = setTimeout(callback, delayMs);
        return { cancel: () => clearTimeout(timer) };
      },
    }), [readScope, runtime]);
    return <Icon name="Activity" size={size} color={color} />;
  };
}
