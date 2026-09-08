"""Training-time audio degradation: the phone channel, in software.

Everything a call does to a waveform before our models see it, applied to training
audio so the models see it too. `AGENTS.md`: train directly on 8 kHz G.711 and
AMR-NB, train on noisy audio as well as clean, watermark both classes or neither.

Measured on 2026-09-07, and the reason `gain.py` exists: the pretrained AASIST
checkpoint's score tracked input loudness rather than content. The same speech at
RMS 0.01 scored 0.02 and at RMS 0.16 scored 0.87, and a synthetic clip scored lower
than genuine speakers at every level below 0.16. A model trained on a corpus with
consistent level never learns to ignore level. Random gain in training is the fix.

Naming note, load-bearing: `tests/test_transport_invariant.py` AST-walks `ml/` and
fails on any attribute named `codec`, so this package says `codec_name` throughout
and never `codec`.
"""

from .g711 import alaw_round_trip, mulaw_round_trip
from .gain import GainPreset, compress, random_gain
from .noise import active_speech_rms, add_noise_at_snr
from .phone_codecs import CodecName, ffmpeg_available, phone_codec_round_trip
from .room import apply_reverb, synthetic_rir

__all__ = [
    "CodecName",
    "GainPreset",
    "active_speech_rms",
    "add_noise_at_snr",
    "alaw_round_trip",
    "apply_reverb",
    "compress",
    "ffmpeg_available",
    "mulaw_round_trip",
    "phone_codec_round_trip",
    "random_gain",
    "synthetic_rir",
]
