import { usePaseo, type AgentRef } from "@getpaseo/plugin/client";
import { useEffect, useRef, useState } from "react";
import { metricFirstTokenMs, observeTurn, tokenCount, type TurnObservation, type TurnSignal } from "../shared/metrics";

/**
 * `claude` says whether the agent runs on Claude Code by its adapter marker;
 * custom providers such as claude-cchp report their own ID on the event.
 */
export function useLiveTurn(agentRef: AgentRef, claude = false) {
  const claudeRef = useRef(claude);
  claudeRef.current = claude;
  const paseo = usePaseo();
  const [status, setStatus] = useState<"connecting" | "live" | "unavailable">("connecting");
  const [observation, setObservation] = useState<TurnObservation>({ active: null, last: null });

  useEffect(() => {
    let disposed = false;
    const receive = (signal: TurnSignal) => setObservation((current) => observeTurn(current, signal));
    const unavailable = () => {
      if (disposed) return;
      receive({ kind: "gap" });
      setStatus("unavailable");
    };
    const release = paseo.agents.ref(agentRef).timeline.subscribe((update) => {
      if (disposed) return;
      const { event } = update;
      switch (event.type) {
        case "error":
          unavailable();
          return;
        case "subscription_restored":
          receive({ kind: "gap" });
          setStatus("live");
          return;
        case "replacement":
          receive({ kind: "replacement" });
          return;
      }
      if (!("timestamp" in update) || !("turnId" in event) || !event.turnId) return;
      const stamp = { turnId: event.turnId, timestamp: Date.parse(update.timestamp) };
      switch (event.type) {
        case "turn_started":
          receive({ kind: "start", ...stamp });
          break;
        case "timeline":
          if (event.item.type === "assistant_message") {
            receive({
              kind: "assistant",
              ...stamp,
              visible: event.item.text.trim().length > 0,
            });
          }
          break;
        case "turn_completed":
          receive({
            kind: "completed",
            ...stamp,
            // Claude's streaming result reports the main agent loop's output for this turn.
            outputTokens: event.provider === "claude" || claudeRef.current
              ? tokenCount(event.usage?.outputTokens)
              : null,
            providerFirstTokenMs: event.provider === "claude" || claudeRef.current
              ? metricFirstTokenMs((event as { metrics?: unknown }).metrics)
              : null,
          });
          break;
        case "turn_failed":
          receive({ kind: "failed", ...stamp });
          break;
        case "turn_canceled":
          receive({ kind: "canceled", ...stamp });
          break;
      }
    });
    void release.ready.then(() => {
      if (!disposed) setStatus("live");
    }, unavailable);
    return () => {
      disposed = true;
      release();
    };
  }, [agentRef, paseo]);

  return { status, measurement: observation.last, observingTurn: observation.active !== null };
}
