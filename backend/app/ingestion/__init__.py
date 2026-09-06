"""Stage 02: ingest and normalize AudioChunk to CanonicalAudioChunk.

The ONLY backend layer allowed to import acquisitions. The decoder owns Opus, G.711
and AMR; its contract is one CanonicalAudioChunk per 20 ms, exact frame size, order
preserved, gaps recorded in StreamClose.dropped_frames.
"""