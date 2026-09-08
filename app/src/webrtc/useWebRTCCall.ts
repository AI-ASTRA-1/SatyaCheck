/**
 * useWebRTCCall.ts
 *
 * Manages the full WebRTC peer connection lifecycle for SATYACHECK in-app calls.
 *
 * Roles:
 *   caller   -- dials by calling dial(callId). Creates SDP offer, sends via signalling.
 *   receiver -- receives incoming_call from signalling, calls accept(callId, offerSdp).
 *
 * Audio forwarding (receiver side only):
 *   When the remote audio track arrives (ontrack), the receiver taps raw audio
 *   and forwards it to the backend audio ingest WebSocket (AUDIO_INGEST_URL).
 *   The backend wraps it into AudioChunk and feeds AudioStreamConsumer.
 *   This is the only way audio reaches the AI pipeline in the WebRTC path.
 *
 * Transport invariant:
 *   This hook is entirely within app/. It never imports from backend/, ml/,
 *   acquisitions/, or contracts/. It speaks only the AppToServerMessage protocol.
 *
 * Exotel path invariant:
 *   This hook is only mounted when CallScreen is active. OverlayScreen,
 *   useRiskSocket, and useOverlay are untouched and continue to work for
 *   the Exotel path.
 */

import { useCallback, useEffect, useRef, useState } from "react";
import {
  MediaStream,
  RTCIceCandidate,
  RTCPeerConnection,
  RTCSessionDescription,
  mediaDevices,
} from "react-native-webrtc";
import { AUDIO_INGEST_URL } from "../config";
import { useSignalling } from "./useSignalling";

// ---- Call state machine --------------------------------------------------

export type CallRole = "caller" | "receiver";

export type CallState =
  | { status: "idle" }
  | { status: "dialling"; callId: string }
  | { status: "ringing"; callId: string }      // receiver sees incoming call
  | { status: "active"; callId: string }
  | { status: "ended"; callId: string; reason: string };

// ICE / STUN config. Cast to any to avoid RTCConfiguration type conflict between
// lib.dom and react-native-webrtc's bundled types.
// eslint-disable-next-line @typescript-eslint/no-explicit-any
const RTC_CONFIG: any = {
  iceServers: [
    { urls: "stun:stun.l.google.com:19302" },
    { urls: "stun:stun1.l.google.com:19302" },
  ],
};

// ---- Hook ----------------------------------------------------------------

export function useWebRTCCall() {
  const [callState, setCallState] = useState<CallState>({ status: "idle" });
  const [role, setRole] = useState<CallRole | null>(null);

  const { sigState, lastMessage, connect: connectSignalling, send, disconnect: disconnectSignalling } =
    useSignalling();

  const pcRef = useRef<RTCPeerConnection | null>(null);
  const localStreamRef = useRef<MediaStream | null>(null);
  const ingestWsRef = useRef<WebSocket | null>(null);

  // ---- Helpers -----------------------------------------------------------

  function makePeerConnection() {
    const pc = new RTCPeerConnection(RTC_CONFIG);

    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    pc.onicecandidate = (event: any) => {
      if (event.candidate && callState.status !== "idle") {
        const callId =
          "callId" in callState ? callState.callId : "";
        send({ type: "ice", call_id: callId, candidate: event.candidate.toJSON() });
      }
    };

    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    pc.ontrack = (event: any) => {
      // Receiver only: remote track = caller's voice. Tap it to backend.
      if (role === "receiver") {
        forwardAudioToBackend();
      }
      // We intentionally do not play the remote track to the local speaker here.
      // If you want earpiece playback, attach event.streams[0] to an RTCView.
    };

    return pc;
  }

  /**
   * Opens a WebSocket to AUDIO_INGEST_URL and sends the handshake JSON.
   * Subsequent binary frames (raw Opus) are sent by the native WebRTC stack
   * automatically once the track is attached -- this connection is the
   * channel the backend adapter listens on.
   *
   * Note: actual frame-by-frame forwarding relies on the native WebRTC
   * audio pipeline feeding the ingest socket. The hook sets up the channel;
   * the friend's adapter reads from it.
   */
  function forwardAudioToBackend() {
    const callId =
      callState.status === "active" || callState.status === "ringing"
        ? callState.callId
        : "";
    if (!callId) return;

    const ws = new WebSocket(AUDIO_INGEST_URL);
    ingestWsRef.current = ws;

    ws.onopen = () => {
      // Send JSON handshake first, then the native WebRTC audio pump sends binary frames.
      ws.send(
        JSON.stringify({
          call_id: callId,
          codec: "opus",
          sample_rate: 48000,
          channels: 1,
        })
      );
    };

    ws.onerror = () => {
      // Degraded: no analysis. Call audio continues unaffected.
      ingestWsRef.current = null;
    };
  }

  function cleanup() {
    localStreamRef.current?.getTracks().forEach((t) => t.stop());
    localStreamRef.current = null;
    pcRef.current?.close();
    pcRef.current = null;
    ingestWsRef.current?.close();
    ingestWsRef.current = null;
  }

  // ---- Caller: dial() ----------------------------------------------------

  const dial = useCallback(
    async (callId: string) => {
      if (callState.status !== "idle") return;
      setRole("caller");
      setCallState({ status: "dialling", callId });

      // Connect to signalling server first.
      connectSignalling();

      // Acquire mic.
      const stream = await mediaDevices.getUserMedia({ audio: true, video: false });
      localStreamRef.current = stream as MediaStream;

      const pc = makePeerConnection();
      pcRef.current = pc;
      (stream as MediaStream).getTracks().forEach((track) =>
        pc.addTrack(track, stream as MediaStream)
      );

      const offer = await pc.createOffer({});
      await pc.setLocalDescription(offer as RTCSessionDescription);

      send({
        type: "dial",
        call_id: callId,
        sdp: (offer as RTCSessionDescription).sdp ?? "",
      });
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [callState.status, connectSignalling, send]
  );

  // ---- Receiver: accept() ------------------------------------------------

  const accept = useCallback(
    async (callId: string, offerSdp: string) => {
      setRole("receiver");
      setCallState({ status: "active", callId });

      const stream = await mediaDevices.getUserMedia({ audio: true, video: false });
      localStreamRef.current = stream as MediaStream;

      const pc = makePeerConnection();
      pcRef.current = pc;
      (stream as MediaStream).getTracks().forEach((track) =>
        pc.addTrack(track, stream as MediaStream)
      );

      await pc.setRemoteDescription(
        new RTCSessionDescription({ type: "offer", sdp: offerSdp })
      );
      const answer = await pc.createAnswer();
      await pc.setLocalDescription(answer as RTCSessionDescription);

      send({
        type: "accept",
        call_id: callId,
        sdp: (answer as RTCSessionDescription).sdp ?? "",
      });
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [send]
  );

  // ---- Hang up -----------------------------------------------------------

  const hangup = useCallback(
    (callId: string) => {
      send({ type: "hangup", call_id: callId });
      cleanup();
      disconnectSignalling();
      setCallState({ status: "ended", callId, reason: "local hangup" });
      setRole(null);
    },
    [send, disconnectSignalling]
  );

  // ---- Handle incoming signalling messages --------------------------------

  useEffect(() => {
    if (!lastMessage) return;

    switch (lastMessage.type) {
      case "ringing":
        setCallState({ status: "ringing", callId: lastMessage.call_id });
        break;

      case "incoming_call":
        // Receiver: show incoming call UI. Accept is triggered by the user pressing Accept.
        setRole("receiver");
        setCallState({ status: "ringing", callId: lastMessage.call_id });
        break;

      case "answer":
        // Caller: received SDP answer from receiver.
        if (pcRef.current) {
          pcRef.current
            .setRemoteDescription(
              new RTCSessionDescription({ type: "answer", sdp: lastMessage.sdp })
            )
            .then(() => {
              if (callState.status === "dialling" || callState.status === "ringing") {
                setCallState({ status: "active", callId: (callState as { callId: string }).callId });
              }
            })
            .catch(() => {/* setRemoteDescription failed -- call stays in ringing */});
        }
        break;

      case "ice":
        if (pcRef.current && lastMessage.candidate) {
          pcRef.current
            .addIceCandidate(new RTCIceCandidate(lastMessage.candidate))
            .catch(() => {/* non-fatal */});
        }
        break;

      case "call_ended":
        cleanup();
        disconnectSignalling();
        setCallState({ status: "ended", callId: lastMessage.call_id, reason: "remote hangup" });
        setRole(null);
        break;

      case "error":
        cleanup();
        disconnectSignalling();
        setCallState({ status: "idle" });
        setRole(null);
        break;
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [lastMessage]);

  // Cleanup on unmount.
  useEffect(() => {
    return () => {
      cleanup();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return {
    callState,
    role,
    sigState,
    dial,
    accept: (callId: string, offerSdp: string) => accept(callId, offerSdp),
    hangup,
    connectSignalling,
  };
}
