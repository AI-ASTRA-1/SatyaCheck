"""Read the diagnosis CSVs and print the H+4 gate result.

    .venv\\Scripts\\python.exe -m ml.tools.gate
    .venv\\Scripts\\python.exe -m ml.tools.gate --transplant data/results/transplant_iphone.csv

Reads `ood.csv` for `S_ood` and a transplant CSV for the deltas, applies the five
rules in order, and prints the block that goes in the group chat verbatim.

It also prints the saturation diagnostic, because the rules alone can be misread.
`delta_spoof` is bounded by how high the spoof scores already were, so a saturated
spoof class produces a small `delta_spoof` whatever the channel does. That reads as
Rule 3 when the truth may be Rule 4, and those lead to opposite decisions. Where the
diagnostic disagrees with the matched rule, this says so rather than letting the
rule stand on its own.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from ml.eval import runlog
from ml.eval.gate import (
    BRANCH_NO_RETRAIN,
    BRANCH_RETRAIN,
    Inputs,
    apply_rules,
    headroom_traversed,
    saturation,
)
from ml.eval.transplant import gap, separation

#: Channels a transplant row can carry, by the path they belong to.
PATH_A_CHANNEL = "broadcast"
PATH_B_CHANNELS = {"phone", "phone_exotel"}


def read_scores(path: Path) -> tuple[dict[str, float], dict[str, float]]:
    """Path A and path B scores from a transplant CSV, keyed by clip name."""
    before: dict[str, float] = {}
    after: dict[str, float] = {}
    for row in runlog.read(path):
        if row["score"] == "":
            continue
        score = float(row["score"])
        name = row["filename"]
        if row["channel"] == PATH_A_CHANNEL:
            before[name] = score
        elif row["channel"] == "phone" and name.endswith("_phone"):
            after[name.removesuffix("_phone")] = score
    return before, after


def s_ood_from(path: Path) -> float | None:
    """Mean over the gate-bypassed non-speech probes."""
    probes = [
        float(r["score"])
        for r in runlog.read(path)
        if r["run_id"] == "ood_novad"
        and r["label"] == "non_speech"
        and r["score"] != ""
    ]
    return sum(probes) / len(probes) if probes else None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--ood", type=Path, default=Path("data/results/ood.csv"))
    parser.add_argument(
        "--transplant", type=Path, default=Path("data/results/transplant.csv")
    )
    parser.add_argument(
        "--delta-dsp",
        type=float,
        default=None,
        help="from ML-2's dsp.csv. Absent, Rule 2 is skipped and the output says so",
    )
    args = parser.parse_args(argv)

    if not args.ood.exists():
        raise SystemExit(f"missing {args.ood}. Run ml.tools.ood first.")
    if not args.transplant.exists():
        raise SystemExit(f"missing {args.transplant}. Run ml.tools.transplant first.")

    s_ood = s_ood_from(args.ood)
    before, after = read_scores(args.transplant)
    paired = sorted(set(before) & set(after))

    genuine_pairs = [(before[n], after[n]) for n in paired if "bonafide" in n]
    spoof_pairs = [(before[n], after[n]) for n in paired if "deepfake" in n]

    def mean_delta(pairs: list[tuple[float, float]]) -> float | None:
        return sum(b - a for a, b in pairs) / len(pairs) if pairs else None

    inputs = Inputs(
        s_ood=s_ood,
        delta_genuine_phone=mean_delta(genuine_pairs),
        delta_spoof_phone=mean_delta(spoof_pairs),
        delta_dsp=args.delta_dsp,
    )
    verdict = apply_rules(inputs)

    observations = [
        (before[n], after[n], "spoof" if "deepfake" in n else "genuine")
        for n in paired
    ]
    signature = saturation(observations)

    print(f"source   {args.transplant.name}, {len(paired)} paired clips\n")
    print("per clip, path A to path B")
    header = f"{'clip':<20} {'class':<8} {'before':>7} {'after':>7} {'delta':>8} {'headroom':>9}"
    print(header)
    print("-" * len(header))
    for name in paired:
        fraction = headroom_traversed(before[name], after[name])
        shown = "  -" if fraction is None else f"{fraction:>8.2f}"
        print(
            f"{name:<20} {'spoof' if 'deepfake' in name else 'genuine':<8} "
            f"{before[name]:>7.4f} {after[name]:>7.4f} "
            f"{after[name] - before[name]:>+8.4f} {shown}"
        )

    print("\nGATE RESULT - H+4")
    print(f"S_ood                = {_show(inputs.s_ood)}")
    print(f"delta_genuine_phone  = {_show(inputs.delta_genuine_phone, sign=True)}")
    print(f"delta_spoof_phone    = {_show(inputs.delta_spoof_phone, sign=True)}")
    print(f"delta_dsp            = {_show(inputs.delta_dsp, sign=True)}   (from ML-2)")
    if genuine_pairs and spoof_pairs:
        first = separation([a for a, _ in genuine_pairs], [a for a, _ in spoof_pairs])
        second = separation([b for _, b in genuine_pairs], [b for _, b in spoof_pairs])
        print(f"overlap before       = {first['overlap']:.4f}")
        print(f"overlap after        = {second['overlap']:.4f}")
        print(
            f"gap before / after   = "
            f"{gap([a for a, _ in genuine_pairs], [a for a, _ in spoof_pairs]):+.4f} / "
            f"{gap([b for _, b in genuine_pairs], [b for _, b in spoof_pairs]):+.4f}"
        )
    print(f"RULE MATCHED         = {verdict.rule if verdict.rule else 'none'}")
    print(f"BRANCH               = {verdict.branch or 'undetermined'}")
    print(f"\n{verdict.reason}")
    for item in verdict.skipped:
        print(f"  rule {item} skipped, not measured")

    if signature is not None:
        print("\nsaturation diagnostic")
        print(
            f"  correlation of delta with the starting score: "
            f"r = {signature.correlation:+.3f}"
        )
        print(f"  genuine: {signature.genuine.describe()}")
        print(f"  spoof:   {signature.spoof.describe()}")
        if signature.both_classes_saturate and verdict.branch == BRANCH_RETRAIN:
            print(
                "\n  THE RULE AND THE DIAGNOSTIC DISAGREE.\n"
                "  Rule 3 matched because delta_spoof is small, but both classes "
                "travel most of\n  their headroom toward 1.0, which is the Rule 4 "
                "signature. delta_spoof is\n  bounded by how high the spoof scores "
                "already were and cannot express this.\n  Read the per-clip table "
                "above before accepting the branch."
            )
        elif signature.both_classes_saturate and verdict.branch == BRANCH_NO_RETRAIN:
            print("\n  The diagnostic agrees with the matched rule.")

    print(
        "\nEvidence, not a verdict. This is one checkpoint, one replay session and "
        "five subjects.\nThe branch is a team decision; this prints what the rules "
        "and the data say."
    )
    return 0


def _show(value: float | None, *, sign: bool = False) -> str:
    if value is None:
        return "not measured"
    return f"{value:+.4f}" if sign else f"{value:.4f}"


if __name__ == "__main__":
    sys.exit(main())
