"""Machine fingerprints (XLS-R + AASIST): is the waveform synthetic. Owner: ML lead A.

AASIST-L (~85K params) runs on CPU. Returns MachineFingerprintSignal.

The check layer and the model are separate. MachineFingerprintCheck owns status,
evidence and the contract; a SyntheticScorer owns the model. Status transitions:

| Condition | CheckStatus |
|---|---|
| window below min_window_ms | skipped, no signal, insufficient_audio |
| no scorer configured | failed, no signal |
| scorer raised, or returned a value outside [0, 1] | failed, no signal |
| window below degraded_window_ms | degraded, signal present |
| otherwise | ok, signal present |

Two scorers exist. `SslAasistScorer` (XLS-R + AASIST) is the architecture the deck
describes and the one to use; `AasistScorer` (AASIST alone) is kept as a lightweight
CPU comparison. Neither is imported here, so this package stays importable without
torch; import them from their own modules.
"""

from .check import (
    DEFAULT_DEGRADED_WINDOW_MS,
    DEFAULT_EVIDENCE_THRESHOLD,
    DEFAULT_MIN_WINDOW_MS,
    MachineFingerprintCheck,
)
from .scorer import SyntheticScorer

__all__ = [
    "DEFAULT_DEGRADED_WINDOW_MS",
    "DEFAULT_EVIDENCE_THRESHOLD",
    "DEFAULT_MIN_WINDOW_MS",
    "MachineFingerprintCheck",
    "SyntheticScorer",
]
