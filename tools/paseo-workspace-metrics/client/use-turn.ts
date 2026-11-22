import { usePaseo, type AgentRef } from "@getpaseo/plugin/client";
import { useEffect, useState } from "react";
import { observeTurn, tokenCount, type TurnObservation, type TurnSignal } from "../shared/metrics";

export function useLiveTurn(agentRef: AgentRef) {
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
          if (event.item.type === "assistant_message") receive({ kind: "assistant", ...stamp });
          break;
        case "turn_completed":
          receive({
            kind: "completed",
            ...stamp,
            // Claude's streaming result reports the main agent loop's output for this turn.
            outputTokens: event.provider === "claude" ? tokenCount(event.usage?.outputTokens) : null,
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
