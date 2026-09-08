"""One call that hands the runner a configured check.

    from ml.checks.machine_fingerprint import build_default_check

    check = build_default_check()   # raises on a CPU-only box, deliberately
    # already warmed: the first real window does not pay seconds of loading

Everything device-, checkpoint- and torch-shaped stays behind this function, so
`ml/runner/` never imports a scorer, a path or a device string. `docs/interfaces.md`
already allows `ml/runner/` to import `ml/checks/*`, so no contract moves.

**It refuses to build the flagship model on a CPU, and that is the point.** Measured
on this machine, `data/results/latency.csv`:

    cuda  xlsr-aasist  score_and_embed    31.5 ms   inside the 180 ms deadline
    cpu   xlsr-aasist  score_and_embed   522.9 ms   2.9x over

A check that misses the deadline on every window does not degrade, it backs the call
buffer up. Failing at startup with the numbers attached is better than discovering it
per-window in production. `allow_cpu_fallback=True` gets AASIST-L at 159.8 ms, which
fits, with the caveat in its own section below.
"""

from __future__ import annotations

from .check import MachineFingerprintCheck

#: Median milliseconds per window, measured. Quoted in the error so whoever hits it
#: does not have to go and find the CSV.
MEASURED_MS = {
    ("xlsr-aasist", "cuda"): 31.5,
    ("xlsr-aasist", "cpu"): 522.9,
    ("AASIST-L", "cpu"): 159.8,
}

#: The runner's per-check deadline, from AGENTS.md stage 04.
DEADLINE_MS = 180.0


def cuda_available() -> bool:
    try:
        import torch
    except ImportError:  # pragma: no cover - torch is a hard dependency of the check
        return False
    return bool(torch.cuda.is_available())


def build_default_check(
    *,
    device: str | None = None,
    allow_cpu_fallback: bool = False,
    with_confidence: bool = True,
    warmup: bool = True,
) -> MachineFingerprintCheck:
    """The check the runner should use, configured for this machine.

    `device` defaults to cuda when one is present. `with_confidence` adds the domain
    distance estimate, which costs nothing extra: it comes out of the same forward
    pass as the score.

    The returned check is **already warmed**, so the runner never has to know a
    scorer exists. Loading is lazy and costs seconds; a cold first window would blow
    the deadline on its own. Pass `warmup=False` only when constructing a check you
    do not intend to run, such as in a test.

    Raises `RuntimeError` on a CPU-only machine unless `allow_cpu_fallback` is set,
    rather than returning a check that cannot meet the deadline.
    """
    resolved = device or ("cuda" if cuda_available() else "cpu")

    if resolved == "cpu" and not allow_cpu_fallback:
        raise RuntimeError(
            f"xlsr-aasist needs {MEASURED_MS[('xlsr-aasist', 'cpu')]:.0f} ms per "
            f"window on a CPU against a {DEADLINE_MS:.0f} ms deadline, so every "
            "window would miss it and the call buffer would back up.\n"
            "  With a GPU:      nothing to do, this builds automatically.\n"
            "  Without one:     build_default_check(allow_cpu_fallback=True) gives "
            f"AASIST-L at {MEASURED_MS[('AASIST-L', 'cpu')]:.0f} ms, which fits and "
            "is INVERTED on the IFD samples; read ml/README.md first.\n"
            "  To override:     build_default_check(device='cpu', "
            "allow_cpu_fallback=True)."
        )

    scorer = _build_scorer(resolved, with_confidence=with_confidence)
    if warmup:
        scorer.warmup()
    return MachineFingerprintCheck(scorer)


def _build_scorer(device: str, *, with_confidence: bool) -> object:
    if device == "cpu":
        # AASIST-L is the only model measured inside the deadline without a GPU. It
        # scores bonafide above deepfake on the IFD samples, so it is a latency
        # fallback and not an accuracy one. No confidence estimate exists for it:
        # the reference is fitted in XLS-R embedding space.
        from .aasist_scorer import AasistScorer

        return AasistScorer("AASIST-L", device=device)

    if with_confidence:
        from .domain import DomainAwareScorer

        return DomainAwareScorer()

    from .ssl_aasist import SslAasistScorer

    return SslAasistScorer(device=device)
