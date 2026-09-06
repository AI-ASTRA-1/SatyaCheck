"""ML workstream, stage 04.

Owner: ML lead A (machine_fingerprint, speaker_identity), ML lead B (prosody,
stt_llm, runner). All inference is local, no external API. Models emit evidence
(contracts.checks.CheckResult); the risk engine owns the decision.
"""