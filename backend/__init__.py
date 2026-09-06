"""SATYACHECK backend, stages 02 to 07 (owner: WebSocket/backend lead; evidence by Flex F).

The backend is transport-agnostic. Only backend.app.ingestion may import
acquisitions; everything below it consumes contracts.pipeline canonical audio.
"""