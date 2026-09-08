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
import { setSpeakerphoneOn } from "satyacheck-overlay";

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
  const incomingOfferRef = useRef<string>("");
  const callIdRef = useRef<string>("");
  const roleRef = useRef<CallRole | null>(null);
  const pendingRemoteIceRef = useRef<RTCIceCandidate[]>([]);

  // ---- Helpers -----------------------------------------------------------

  function flushPendingRemoteIce(pc: RTCPeerConnection) {
    while (pendingRemoteIceRef.current.length > 0) {
      const cand = pendingRemoteIceRef.current.shift();
      if (cand) {
        console.log("[useWebRTCCall] Flushing buffered remote ICE candidate");
        pc.addIceCandidate(cand).catch((e) =>
          console.warn("[useWebRTCCall] Failed to add buffered ICE candidate:", e)
        );
      }
    }
  }

  function makePeerConnection() {
    const pc = new RTCPeerConnection(RTC_CONFIG);

    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    pc.onicecandidate = (event: any) => {
      if (event.candidate && callIdRef.current) {
        console.log("[useWebRTCCall] Local ICE candidate generated for", callIdRef.current);
        send({
          type: "ice",
          call_id: callIdRef.current,
          candidate: event.candidate.toJSON(),
        });
      }
    };

    pc.oniceconnectionstatechange = () => {
      console.log("[useWebRTCCall] ICE connection state:", pc.iceConnectionState);
    };

    pc.onconnectionstatechange = () => {
      console.log("[useWebRTCCall] Connection state:", pc.connectionState);
    };

    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    pc.ontrack = (event: any) => {
      console.log("[useWebRTCCall] Remote track received, kind:", event.track?.kind);
      if (event.track) {
        event.track.enabled = true;
        try {
          // eslint-disable-next-line @typescript-eslint/no-explicit-any
          (event.track as any)._setVolume(10.0);
          console.log("[useWebRTCCall] Audio track volume set to 10.0 (max gain)");
        } catch (e) {
          console.log("[useWebRTCCall] _setVolume note:", e);
        }
      }
      // Receiver only: remote track = caller's voice. Tap it to backend.
      if (roleRef.current === "receiver") {
        forwardAudioToBackend();
      }
    };

    return pc;
  }

  /**
   * Opens a WebSocket to AUDIO_INGEST_URL and sends the handshake JSON.
   * Subsequent binary frames (raw Opus) are sent by the native WebRTC stack
   * automatically once the track is attached -- this connection is the
   * channel the backend adapter listens on.
   */
  function forwardAudioToBackend() {
    const callId = callIdRef.current;
    if (!callId) return;

    console.log("[useWebRTCCall] Connecting to Audio Ingest WS at:", AUDIO_INGEST_URL);
    const ws = new WebSocket(AUDIO_INGEST_URL);
    ingestWsRef.current = ws;

    ws.onopen = () => {
      console.log("[useWebRTCCall] Audio Ingest WS connected. Sending JSON handshake...");
      ws.send(
        JSON.stringify({
          call_id: callId,
          codec: "opus",
          sample_rate: 48000,
          channels: 1,
        })
      );
    };

    ws.onerror = (e) => {
      console.warn("[useWebRTCCall] Audio Ingest WS error:", e);
      ingestWsRef.current = null;
    };
  }

  function cleanup() {
    setSpeakerphoneOn(false);
    pendingRemoteIceRef.current = [];
    localStreamRef.current?.getTracks().forEach((t) => t.stop());
    localStreamRef.current = null;
    pcRef.current?.close();
    pcRef.current = null;
    ingestWsRef.current?.close();
    ingestWsRef.current = null;
    callIdRef.current = "";
    roleRef.current = null;
  }

  // ---- Caller: dial() ----------------------------------------------------

  const dial = useCallback(
    async (callId: string) => {
      if (callState.status !== "idle") return;
      roleRef.current = "caller";
      callIdRef.current = callId;
      setRole("caller");
      setCallState({ status: "dialling", callId });

      try {
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
      } catch (err) {
        console.error("dial error:", err);
        cleanup();
        setCallState({ status: "ended", callId, reason: "dial failed: " + String(err) });
        setRole(null);
      }
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [callState.status, connectSignalling, send]
  );

  // ---- Receiver: accept() ------------------------------------------------

  const accept = useCallback(
    async (callId: string, offerSdp?: string) => {
      const sdp = offerSdp || incomingOfferRef.current;
      roleRef.current = "receiver";
      callIdRef.current = callId;
      setRole("receiver");
      setCallState({ status: "active", callId });

      try {
        const stream = await mediaDevices.getUserMedia({ audio: true, video: false });
        localStreamRef.current = stream as MediaStream;

        const pc = makePeerConnection();
        pcRef.current = pc;
        (stream as MediaStream).getTracks().forEach((track) =>
          pc.addTrack(track, stream as MediaStream)
        );

        await pc.setRemoteDescription(
          new RTCSessionDescription({ type: "offer", sdp })
        );
        flushPendingRemoteIce(pc);

        const answer = await pc.createAnswer();
        await pc.setLocalDescription(answer as RTCSessionDescription);

        send({
          type: "accept",
          call_id: callId,
          sdp: (answer as RTCSessionDescription).sdp ?? "",
        });
        setSpeakerphoneOn(true);
      } catch (err) {
        console.error("accept error:", err);
        cleanup();
        setCallState({ status: "ended", callId, reason: "accept failed: " + String(err) });
        setRole(null);
      }
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
        callIdRef.current = lastMessage.call_id;
        setCallState({ status: "ringing", callId: lastMessage.call_id });
        break;

      case "incoming_call":
        // Receiver: show incoming call UI. Accept is triggered by the user pressing Accept.
        incomingOfferRef.current = lastMessage.sdp;
        roleRef.current = "receiver";
        callIdRef.current = lastMessage.call_id;
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
              if (pcRef.current) {
                flushPendingRemoteIce(pcRef.current);
              }
              setCallState({ status: "active", callId: callIdRef.current });
              setSpeakerphoneOn(true);
            })
            .catch((e) => {
              console.warn("[useWebRTCCall] setRemoteDescription error:", e);
            });
        }
        break;

      case "ice":
        if (lastMessage.candidate) {
          const cand = new RTCIceCandidate(lastMessage.candidate);
          // eslint-disable-next-line @typescript-eslint/no-explicit-any
          const hasRemoteDesc = Boolean((pcRef.current as any)?.remoteDescription);
          if (pcRef.current && hasRemoteDesc) {
            pcRef.current
              .addIceCandidate(cand)
              .catch((e) => console.warn("[useWebRTCCall] addIceCandidate error:", e));
          } else {
            console.log("[useWebRTCCall] Buffering remote ICE candidate before remoteDescription");
            pendingRemoteIceRef.current.push(cand);
          }
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
    accept: (callId: string, offerSdp?: string) => accept(callId, offerSdp),
    hangup,
    connectSignalling,
  };
}
