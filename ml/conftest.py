"""Make the repo-root packages importable when the ML tests run from the repo root.

ML tests live under `ml/` because `tests/` belongs to R2. Run them with
`.venv\\Scripts\\python.exe -m pytest ml -q`.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
