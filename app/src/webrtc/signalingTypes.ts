/**
 * signalingTypes.ts
 *
 * TypeScript mirror of the signalling WebSocket contract (port 8766).
 * Both the React Native lead and the WebRTC lead sign off on these types.
 * Do not add, rename, or drop fields without telling both parties.
 *
 * Direction legend:
 *   App  -> Server  (caller sends)
 *   Server -> App   (server pushes to caller or receiver)
 */

// ---- Messages the APP sends to the server --------------------------------

/** Caller dials -- sends SDP offer and a self-generated call_id. */
export interface DialMessage {
  type: "dial";
  call_id: string;
  sdp: string;
}

/** Receiver accepts an incoming call -- sends SDP answer. */
export interface AcceptMessage {
  type: "accept";
  call_id: string;
  sdp: string;
}

/** Either side ends the call. */
export interface HangupMessage {
  type: "hangup";
  call_id: string;
}

/** Either side sends an ICE candidate. */
export interface IceMessage {
  type: "ice";
  call_id: string;
  candidate: RTCIceCandidateInit;
}

export type AppToServerMessage = DialMessage | AcceptMessage | HangupMessage | IceMessage;

// ---- Messages the SERVER sends to the APP --------------------------------

/** Server confirms offer received; waiting for receiver. */
export interface RingingMessage {
  type: "ringing";
  call_id: string;
}

/** Server delivers SDP answer to the caller once receiver accepts. */
export interface AnswerMessage {
  type: "answer";
  sdp: string;
}

/** Server notifies receiver of an incoming call with caller's offer SDP. */
export interface IncomingCallMessage {
  type: "incoming_call";
  call_id: string;
  sdp: string;
}

/** Server relays ICE candidate from the other peer. */
export interface RemoteIceMessage {
  type: "ice";
  call_id: string;
  candidate: RTCIceCandidateInit;
}

/** Server notifies both sides the call is over. */
export interface CallEndedMessage {
  type: "call_ended";
  call_id: string;
}

/** Server signals an error. */
export interface SignalErrorMessage {
  type: "error";
  reason: string;
}

export type ServerToAppMessage =
  | RingingMessage
  | AnswerMessage
  | IncomingCallMessage
  | RemoteIceMessage
  | CallEndedMessage
  | SignalErrorMessage;
