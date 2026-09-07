"""WebRTC acquisition package for real-time audio streaming.

Conforms to AudioStreamAdapter interface defined in contracts/acquisition.py.
"""
from __future__ import annotations

# Initialize contracts shim if not in repo context
try:
    from contracts.acquisition import (
        AudioChunk,
        AudioStreamAdapter,
        AudioStreamConsumer,
        CallDirection,
        Codec,
        StreamClose,
        StreamOpen,
        Transport,
    )
except ImportError:
    from .contracts_shim import (
        AudioChunk,
        AudioStreamAdapter,
        AudioStreamConsumer,
        CallDirection,
        Codec,
        StreamClose,
        StreamOpen,
        Transport,
    )

from .adapter import WebRTCAdapter, WebRTCSession
from .signalling import SignallingServer

__all__ = [
    "WebRTCAdapter",
    "SignallingServer",
    "WebRTCSession",
    "AudioStreamAdapter",
    "AudioStreamConsumer",
    "StreamOpen",
    "AudioChunk",
    "StreamClose",
    "Transport",
    "Codec",
    "CallDirection",
]
