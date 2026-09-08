"""One CSV schema for every diagnostic, so the slides come from a groupby.

Every number produced during the H+0 to H+4 diagnosis goes into a row here, never
into a chat message or a hand-typed spreadsheet. `baseline`, `ood` and `transplant`
all write this schema, which is what makes them joinable.

Three properties this module exists to guarantee:

**No NaN, ever.** `score` is a float or `None`. `None` writes as an empty cell and
must arrive with `vad_status == "FAIL"`. A missing score and a high score are
different facts; `nan` is neither, and a `nan` in a five-row table reads as a broken
tool and gets the row silently dropped rather than counted.

**Byte-identical on a re-run.** Rows sort on a stable key and floats format to a
fixed number of decimals before writing. A diagnostic whose output moves between
identical runs cannot be used to detect that something else moved.

**Provenance travels with the number.** `checkpoint` and `frozen_commit` are
required on every row. A row from a different config is not comparable to one from
this config, and the only way to know is to have recorded it.
"""

from __future__ import annotations

import csv
from dataclasses import asdict, dataclass, fields
from pathlib import Path

#: The column order, fixed. Readers index by name, but a stable order keeps the diff
#: of a regenerated CSV readable.
FIELDS = [
    "run_id",
    "filename",
    "speaker",
    "label",
    "dataset",
    "channel",
    "duration_s",
    "sample_rate",
    "vad_status",
    "speech_s",
    "score",
    "checkpoint",
    "frozen_commit",
    "notes",
]

VAD_PASS = "PASS"
VAD_FAIL = "FAIL"

#: Scores and durations are written to this many decimals. Six is far past the
#: model's meaningful precision and well inside float64 round-trip, so it makes a
#: re-run byte-identical without inventing significance.
DECIMALS = 6

LABELS = {"genuine", "spoof", "non_speech"}


@dataclass(frozen=True)
class Row:
    """One scored item. `score` is None exactly when `vad_status` is FAIL."""

    run_id: str
    filename: str
    label: str
    dataset: str
    channel: str
    duration_s: float
    vad_status: str
    speech_s: float
    score: float | None
    checkpoint: str
    frozen_commit: str
    speaker: str = "n/a"
    sample_rate: int = 16000
    notes: str = ""

    def __post_init__(self) -> None:
        if self.label not in LABELS:
            raise ValueError(f"label {self.label!r} is not one of {sorted(LABELS)}")
        if self.vad_status not in {VAD_PASS, VAD_FAIL}:
            raise ValueError(f"vad_status {self.vad_status!r} is not PASS or FAIL")
        if self.score is None and self.vad_status != VAD_FAIL:
            raise ValueError(f"{self.filename}: no score but vad_status is not FAIL")
        if self.score is not None:
            if self.vad_status != VAD_PASS:
                raise ValueError(f"{self.filename}: a score with vad_status FAIL")
            # A NaN would survive every check above and then poison a mean, so it is
            # rejected at the boundary rather than found in a slide.
            if not (0.0 <= self.score <= 1.0):
                raise ValueError(
                    f"{self.filename}: score {self.score!r} is not a probability"
                )
        if not self.frozen_commit:
            raise ValueError(f"{self.filename}: frozen_commit is required")

    def as_cells(self) -> dict[str, str]:
        """The row as it is written. Floats fixed-width, None as an empty cell."""
        raw = asdict(self)
        cells: dict[str, str] = {}
        for name in FIELDS:
            value = raw[name]
            if value is None:
                cells[name] = ""
            elif isinstance(value, float):
                cells[name] = f"{value:.{DECIMALS}f}"
            else:
                cells[name] = str(value)
        return cells


def sort_key(row: Row) -> tuple[str, str, str]:
    return (row.run_id, row.dataset, row.filename)


def write(rows: list[Row], path: Path) -> Path:
    """Write rows to `path`, sorted, with a trailing newline and LF endings.

    `newline=""` plus `lineterminator="\n"` rather than the csv default, because
    the default writes CRLF on Windows and the file would then differ from one
    written anywhere else for no reason a reader could see.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS, lineterminator="\n")
        writer.writeheader()
        for row in sorted(rows, key=sort_key):
            writer.writerow(row.as_cells())
    return path


def read(path: Path) -> list[dict[str, str]]:
    """Read a run log back. Cells stay strings; an empty score stays empty."""
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def scores(rows: list[dict[str, str]]) -> list[float]:
    """The scores that exist. Rows with an empty score are skipped, not zeroed."""
    return [float(r["score"]) for r in rows if r["score"] != ""]


# Output order comes from FIELDS, not from the dataclass, so the two only have to
# describe the same set of columns. Checked at import because a column added to one
# and not the other would otherwise surface as a KeyError halfway through a run.
assert {f.name for f in fields(Row)} == set(FIELDS), (
    "Row and FIELDS describe different columns: "
    f"{ {f.name for f in fields(Row)} ^ set(FIELDS) }"
)
