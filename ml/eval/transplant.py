"""Separation between two score sets, and what it means at small n.

Split out of the tool so it can be tested without a checkpoint, and because the
arithmetic is the part that is easy to get quietly wrong. Two means can both move a
long way while separation stays exactly zero, which is why the gate reads separation
and not means.
"""

from __future__ import annotations

from typing import TypedDict


class Separation(TypedDict):
    genuine_range: tuple[float, float]
    spoof_range: tuple[float, float]
    overlap: float


def separation(genuine: list[float], spoof: list[float]) -> Separation:
    """Ranges of both classes and how much they overlap.

    Exactly the function the H+4 brief specifies, kept literal so the gate is
    evaluated on the agreed arithmetic rather than on a local improvement.

    `overlap` is the width of the interval both ranges cover, floored at zero.
    """
    return {
        "genuine_range": (min(genuine), max(genuine)),
        "spoof_range": (min(spoof), max(spoof)),
        "overlap": max(
            0.0, min(max(genuine), max(spoof)) - max(min(genuine), min(spoof))
        ),
    }


def gap(genuine: list[float], spoof: list[float]) -> float:
    """Distance from the top of the genuine range to the bottom of the spoof range.

    Reported alongside `separation` because **`overlap` is degenerate at one clip
    per class**. With a single genuine score g and a single spoof score s, the
    overlap expression reduces to `min(g, s) - max(g, s)`, which is never positive,
    so it is floored to 0.0 whatever the two values are. Reading that as "the
    classes are still separated" would be reading a property of n=1, not a result.

    `gap` is negative when the classes are the wrong way round, which is the outcome
    that matters here and the one `overlap` cannot express at n=1.
    """
    return min(spoof) - max(genuine)


def overlap_is_meaningful(genuine: list[float], spoof: list[float]) -> bool:
    """Whether `overlap` carries information for these sample sizes."""
    return len(genuine) > 1 and len(spoof) > 1


def describe(genuine: list[float], spoof: list[float]) -> str:
    """One block of text stating separation, the gap, and what n supports."""
    values = separation(genuine, spoof)
    low_g, high_g = values["genuine_range"]
    low_s, high_s = values["spoof_range"]
    lines = [
        f"genuine  n={len(genuine)}  {low_g:.4f} to {high_g:.4f}",
        f"spoof    n={len(spoof)}  {low_s:.4f} to {high_s:.4f}",
        f"overlap  {values['overlap']:.4f}",
        f"gap      {gap(genuine, spoof):+.4f}  (spoof floor minus genuine ceiling)",
    ]
    if not overlap_is_meaningful(genuine, spoof):
        lines.append(
            "  overlap is 0.0 by construction at one clip per class and carries no "
            "information here. Read the gap."
        )
    return "\n".join(lines)
