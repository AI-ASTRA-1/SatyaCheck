"""The transport invariant, mechanically enforced.

Nothing below stage 02 (backend.app.ingestion) may know which transport delivered
the audio: no import of acquisitions / exotel / webrtc, no use of the
acquisition-boundary types (AudioChunk, StreamOpen, StreamClose, Transport, Codec),
no `.transport` or `.codec` attribute access. contracts/ imports only pydantic and
stdlib. Adding a third acquisition layer requires no change below ingestion.

A code change that makes the Exotel path behave differently from the WebRTC path is
a bug; this test is the tripwire.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONTRACTS_DIR = ROOT / "contracts"
INGESTION_DIR = ROOT / "backend" / "app" / "ingestion"
INVARIANT_DIRS = [ROOT / "backend", ROOT / "ml"]

TRANSPORT_MODULES = {"acquisitions", "exotel", "webrtc"}
ACQUISITION_TYPES = {"AudioChunk", "StreamOpen", "StreamClose", "Transport", "Codec"}
ACQUISITION_ATTRS = {"transport", "codec"}


def _py_files(directory: Path) -> list[Path]:
    return sorted(path for path in directory.rglob("*.py") if path.is_file())


def _is_in_ingestion(path: Path) -> bool:
    return path.resolve().is_relative_to(INGESTION_DIR.resolve())


def _stdlib() -> set[str]:
    return set(sys.stdlib_module_names)


def test_contracts_imports_only_pydantic_and_stdlib() -> None:
    stdlib = _stdlib()
    for path in _py_files(CONTRACTS_DIR):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    top = alias.name.split(".")[0]
                    assert top in stdlib or top == "pydantic", (
                        f"{path}: imports {alias.name}"
                    )
            elif isinstance(node, ast.ImportFrom):
                if node.level > 0 or node.module is None:
                    continue  # intra-package relative import
                top = node.module.split(".")[0]
                assert top in stdlib or top == "pydantic", (
                    f"{path}: imports {node.module}"
                )


def test_no_transport_leak_below_ingestion() -> None:
    for directory in INVARIANT_DIRS:
        for path in _py_files(directory):
            in_ingestion = _is_in_ingestion(path)
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        if alias.name.split(".")[0] in TRANSPORT_MODULES:
                            assert in_ingestion, f"{path}: imports {alias.name}"
                elif isinstance(node, ast.ImportFrom):
                    if node.module is not None and node.module.split(".")[0] in TRANSPORT_MODULES:
                        assert in_ingestion, f"{path}: imports {node.module}"
                    for alias in node.names:
                        if alias.name in ACQUISITION_TYPES:
                            assert in_ingestion, f"{path}: imports {alias.name}"
                elif isinstance(node, ast.Attribute):
                    if node.attr in ACQUISITION_ATTRS or node.attr in ACQUISITION_TYPES:
                        assert in_ingestion, f"{path}: .{node.attr} access"