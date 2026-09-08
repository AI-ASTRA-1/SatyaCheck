/**
 * useSignalling.ts
 *
 * WebSocket hook for the signalling server (port 8766).
 * Completely separate from useRiskSocket (port 8765) -- these are two
 * independent connections and must never be confused.
 *
 * Exposes:
 *   send(msg)     -- send any AppToServerMessage to the signalling server
 *   sigState      -- current connection state
 *   lastMessage   -- most recent ServerToAppMessage received (null if none)
 *
 * The hook does NOT do any WebRTC logic. It only handles the WebSocket
 * transport for the signalling protocol.
 */

import { useCallback, useEffect, useRef, useState } from "react";
import {
  AppToServerMessage,
  ServerToAppMessage,
} from "./signalingTypes";
import { SIGNALLING_URL } from "../config";

export type SignalState =
  | "disconnected"
  | "connecting"
  | "connected"
  | "error";

export function useSignalling() {
  const [sigState, setSigState] = useState<SignalState>("disconnected");
  const [lastMessage, setLastMessage] = useState<ServerToAppMessage | null>(
    null
  );
  const wsRef = useRef<WebSocket | null>(null);

  const connect = useCallback(() => {
    if (wsRef.current) {
      wsRef.current.close();
    }
    setSigState("connecting");

    const ws = new WebSocket(SIGNALLING_URL);
    wsRef.current = ws;

    ws.onopen = () => setSigState("connected");

    ws.onmessage = (event: MessageEvent) => {
      let msg: ServerToAppMessage;
      try {
        msg = JSON.parse(event.data as string) as ServerToAppMessage;
      } catch {
        return; // malformed frame -- ignore
      }
      setLastMessage(msg);
    };

    ws.onerror = () => setSigState("error");
    ws.onclose = () => {
      setSigState("disconnected");
      wsRef.current = null;
    };
  }, []);

  const send = useCallback((msg: AppToServerMessage) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify(msg));
    }
  }, []);

  const disconnect = useCallback(() => {
    wsRef.current?.close();
    wsRef.current = null;
    setSigState("disconnected");
    setLastMessage(null);
  }, []);

  useEffect(() => {
    return () => {
      wsRef.current?.close();
    };
  }, []);

  return { sigState, lastMessage, connect, send, disconnect };
}
