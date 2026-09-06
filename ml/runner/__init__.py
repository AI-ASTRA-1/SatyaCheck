"""Stage 04 runner (owner: ML lead B).

Implements contracts.checks.CheckRunner: parallel fan-out to all four checks on a
COPY of CanonicalAudioBatch, shared 180 ms deadline, stragglers marked FAILED or
SKIPPED, returns one ChecksBatchResult.
"""