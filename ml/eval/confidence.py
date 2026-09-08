"""How far a window sits from the data this checkpoint was fine-tuned on.

The purpose is stated plainly because it is easy to overstate: when audio is unlike
anything the model was trained on, the system should report **low confidence**, not a
high score. `ml/README.md` records the model scoring genuine speakers 0.436 to 0.990
and a real clone at 0.938; a number that says "I cannot judge this" is worth more
than a confident wrong one.

**How well it works, measured, and it is not well.** On 96 clips with known labels
(48 held-out ASVspoof, 10 IFD, 6 internal, 20 replayed, 12 more), the distance below
predicts whether the model's answer is wrong with **AUC 0.822** and correlates with
the size of the error at **r = +0.518**. At a threshold that flags a tenth of the
clips the model gets right, it catches **44%** of the ones it gets wrong.

That is informative and it is not a detector. Two consequences, both binding:

  * `confidence` is a graded hint for the risk engine, never a gate. Nothing should
    suppress or raise a warning on it alone.
  * The three metrics that failed are recorded here so they are not tried again:
    per-dimension z-distance to the reference mean, PCA-Mahalanobis at 20
    components, and cosine distance to the mean. Cosine put 100% of out-of-domain
    clips inside the in-domain range, so it is worse than nothing. k-nearest
    neighbours was the only one of four with usable signal.

The reference set is fitted on ASVspoof eval clips only and lives outside the repo
beside the weights, because it is derived from a licensed corpus.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np

#: Neighbours averaged for the distance. Five is the usual choice and nothing here
#: was tuned on the evaluation clips, which would have been fitting to them.
DEFAULT_K = 5

#: Filename under the model root.
REFERENCE_FILE = "confidence_reference.npz"


@dataclass(frozen=True)
class Reference:
    """Embeddings of in-domain audio, and the distances they produce among themselves.

    `self_distances` is what turns a raw distance into a calibrated number: a window
    is scored by where it falls in the distribution of distances the reference set
    produces against itself, rather than against a threshold picked by hand.
    """

    embeddings: np.ndarray
    self_distances: np.ndarray
    k: int = DEFAULT_K

    @property
    def size(self) -> int:
        return int(self.embeddings.shape[0])

    def distance(self, embedding: np.ndarray) -> float:
        """Mean Euclidean distance to the `k` nearest reference embeddings."""
        gaps = np.linalg.norm(self.embeddings - embedding, axis=1)
        return float(np.sort(gaps)[: self.k].mean())

    def confidence(self, embedding: np.ndarray) -> float:
        """1.0 at the centre of the training distribution, falling to 0.0 outside.

        The value is one minus the fraction of reference clips whose own distance is
        below this one, so 0.5 means "as far out as the median reference clip". It is
        a position in a distribution, not a probability that the answer is right.
        """
        return distance_to_confidence(self.distance(embedding), self.self_distances)

    def save(self, path: Path) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        np.savez_compressed(
            path,
            embeddings=self.embeddings.astype(np.float32),
            self_distances=self.self_distances.astype(np.float32),
            k=np.array([self.k]),
        )
        return path

    @classmethod
    def load(cls, path: Path) -> Reference:
        with np.load(path) as data:
            return cls(
                embeddings=data["embeddings"],
                self_distances=data["self_distances"],
                k=int(data["k"][0]),
            )


def distance_to_confidence(distance: float, reference: np.ndarray) -> float:
    """Where `distance` falls in `reference`, inverted, clamped to [0, 1]."""
    if reference.size == 0:
        raise ValueError("an empty reference cannot calibrate anything")
    fraction = float((reference < distance).mean())
    return float(np.clip(1.0 - fraction, 0.0, 1.0))


def fit(embeddings: np.ndarray, k: int = DEFAULT_K) -> Reference:
    """Build a reference from in-domain embeddings.

    Each reference clip's own distance excludes itself, which would otherwise be zero
    and drag the whole calibration down.
    """
    if embeddings.ndim != 2:
        raise ValueError(f"expected a 2-D array of embeddings, got {embeddings.shape}")
    if embeddings.shape[0] <= k:
        raise ValueError(
            f"{embeddings.shape[0]} reference clips cannot support k={k} neighbours"
        )

    self_distances = []
    for index, row in enumerate(embeddings):
        gaps = np.linalg.norm(embeddings - row, axis=1)
        gaps[index] = np.inf  # a clip is not its own neighbour
        self_distances.append(np.sort(gaps)[:k].mean())

    return Reference(
        embeddings=embeddings.astype(np.float32),
        self_distances=np.asarray(self_distances, dtype=np.float32),
        k=k,
    )


def reference_path() -> Path:
    from ml.paths import model_root

    return model_root() / REFERENCE_FILE
