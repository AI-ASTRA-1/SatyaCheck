/**
 * useRiskSocket: connects to the SATYACHECK backend WebSocket and drives
 * a state machine over the AppMessage discriminated union.
 *
 * State machine:
 *   disconnected -> connecting -> session -> live -> ended -> disconnected
 *
 * On disconnect (or error) the state immediately resets to "disconnected"
 * so the UI shows nothing rather than a stale score.
 *
 * Uses the browser/React Native built-in WebSocket global -- NOT the ws
 * npm package (that is Node.js only, for the fake server).
 */

import { useCallback, useEffect, useRef, useState } from "react";
import { AppMessage, CallEnded, RiskUpdate, SessionStart } from "./types";

// ---- State machine types ------------------------------------------------

export type SocketStatus =
  | { status: "disconnected" }
  | { status: "connecting" }
  | { status: "session"; session: SessionStart }
  | { status: "live"; session: SessionStart; latest: RiskUpdate }
  | { status: "ended"; session: SessionStart; summary: CallEnded };

export type AlertHistoryEntry = {
  session: SessionStart;
  summary: CallEnded;
};

// ---- Hook ---------------------------------------------------------------

export function useRiskSocket(url: string) {
  const [state, setState] = useState<SocketStatus>({ status: "disconnected" });
  const [alertHistory, setAlertHistory] = useState<AlertHistoryEntry[]>([]);
  const wsRef = useRef<WebSocket | null>(null);

  const connect = useCallback(() => {
    if (wsRef.current) {
      wsRef.current.close();
    }

    setState({ status: "connecting" });

    const ws = new WebSocket(url);
    wsRef.current = ws;

    ws.onopen = () => {
      // session_start arrives in the first message; nothing to do here.
    };

    ws.onmessage = (event: MessageEvent) => {
      let msg: AppMessage;
      try {
        msg = JSON.parse(event.data as string) as AppMessage;
      } catch {
        return; // malformed frame -- ignore
      }

      switch (msg.kind) {
        case "session_start":
          setState({ status: "session", session: msg });
          break;

        case "risk_update":
          setState((prev) => {
            if (prev.status !== "session" && prev.status !== "live") return prev;
            return { status: "live", session: prev.session, latest: msg };
          });
          break;

        case "call_ended":
          setState((prev) => {
            if (prev.status !== "session" && prev.status !== "live") return prev;
            const entry: AlertHistoryEntry = {
              session: prev.session,
              summary: msg,
            };
            setAlertHistory((h) => [entry, ...h].slice(0, 50));
            return { status: "ended", session: prev.session, summary: msg };
          });
          break;
      }
    };

    // Go blank on error or close -- never show a stale score.
    ws.onerror = () => setState({ status: "disconnected" });
    ws.onclose = () => setState({ status: "disconnected" });
  }, [url]);

  useEffect(() => {
    connect();
    return () => {
      wsRef.current?.close();
      setState({ status: "disconnected" });
    };
  }, [connect]);

  return { state, alertHistory, reconnect: connect };
}
