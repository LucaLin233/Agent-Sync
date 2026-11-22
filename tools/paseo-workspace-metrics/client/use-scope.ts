import { useRpc } from "@getpaseo/plugin/client";
import { useQuery } from "@tanstack/react-query";
import { workspaceScopeRpc } from "../shared/scope";

export function useWorkspaceScope() {
  const run = useRpc(workspaceScopeRpc);
  return useQuery({
    queryKey: ["workspace-metrics-scope"],
    retry: false,
    staleTime: Number.POSITIVE_INFINITY,
    refetchOnWindowFocus: false,
    refetchOnReconnect: false,
    queryFn: () => run({}),
  });
}
