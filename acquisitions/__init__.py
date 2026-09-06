"""Acquisition layer: Exotel and WebRTC adapters (owner: telephony lead).

Transport-specific handling stops here. Nothing below stage 02 (backend.app.ingestion)
imports these packages; tests/test_transport_invariant.py enforces that.
"""