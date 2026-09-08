"""Exotel adapter: telephony stream to AudioChunk (owner: telephony lead).

Part of the acquisition layer only. Never imported below stage 02.
"""

from acquisitions.exotel.ws_adapter import ExotelWebSocketAdapter

__all__ = ["ExotelWebSocketAdapter"]