"""Where model weights live.

Outside the repo, deliberately. The repo sits inside a synced OneDrive folder and
the checkpoints are gigabytes. Override with the SATYACHECK_MODEL_DIR environment
variable; the default is %LOCALAPPDATA%\\satyacheck\\models on Windows and
~/.local/share/satyacheck/models elsewhere.
"""

from __future__ import annotations

import os
from pathlib import Path

ENV_VAR = "SATYACHECK_MODEL_DIR"


def model_root() -> Path:
    """Root directory holding the downloaded checkpoints."""
    override = os.environ.get(ENV_VAR)
    if override:
        return Path(override)
    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        return Path(local_app_data) / "satyacheck" / "models"
    return Path.home() / ".local" / "share" / "satyacheck" / "models"


def require(*parts: str) -> Path:
    """Resolve a path under the model root, raising if it is not there.

    The message names the missing path and the override variable, because "file not
    found" three frames inside a model loader is not actionable.
    """
    path = model_root().joinpath(*parts)
    if not path.exists():
        raise FileNotFoundError(
            f"missing model file: {path}. Download it, or point {ENV_VAR} at the "
            f"directory that has it."
        )
    return path
