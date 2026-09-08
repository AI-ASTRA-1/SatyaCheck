"""Compare script-channel LLM back ends on the eval transcripts.

Developer tool, manual only. The `claude` and `chain` configs call the Anthropic
API and cost money; `qwen` and `rules` are local and free. Nothing is persisted.

    # local only, no API
    .venv\\Scripts\\python.exe -m ml.tools.compare_script_llms --configs rules,qwen

    # full comparison (needs ANTHROPIC_API_KEY in the environment)
    .venv\\Scripts\\python.exe -m ml.tools.compare_script_llms --configs rules,qwen,claude,chain

    # also score a file of real transcripts, one per line
    .venv\\Scripts\\python.exe -m ml.tools.compare_script_llms --configs claude,qwen --real-file calls.txt

Reports, per config: scam and ordinary `intent` ranges, their separation, how
often the LLM path actually produced the score (source == "llm"), and mean
latency per transcript.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

try:
    import truststore

    truststore.inject_into_ssl()  # this machine intercepts TLS; see ml/README.md
except Exception as _exc:  # noqa: BLE001 - not fatal for the local-only configs
    print(f"truststore not active: {_exc}", file=sys.stderr)

import json as _json

from ml.checks.stt_llm import (
    SYSTEM,
    AnthropicScriptLLM,
    GroqScriptLLM,
    QwenScriptLLM,
    analyze,
    schema_errors,
)
from ml.checks.stt_llm.eval_transcripts import NORMAL_TRANSCRIPTS, SCAM_TRANSCRIPTS


def _probe(llm: object | None) -> None:
    """Fail loudly if a config's primary model errors, instead of letting
    `analyze()` silently fall through to rules and reporting look-alike numbers."""
    primary = llm[0] if isinstance(llm, list) else llm
    if primary is None or not hasattr(primary, "complete"):
        return
    try:
        primary.complete(SYSTEM, "hello this is a short probe of the model")
    except Exception as exc:  # noqa: BLE001 - report and continue
        line = str(exc).splitlines()[0] if str(exc) else ""
        print(
            f"  !! {type(exc).__name__}: {line[:160]}\n"
            f"  !! this config's LLM is unavailable; its numbers below are the "
            f"fallback, not the model",
            file=sys.stderr,
        )


def _schema_scan(llm: object | None, transcripts: list[str]) -> None:
    """Call the primary model on each transcript and report how many raw
    responses conform to RESPONSE_SCHEMA (before any clamp/salvage)."""
    primary = llm[0] if isinstance(llm, list) else llm
    if primary is None or not hasattr(primary, "complete"):
        return
    conformant = 0
    seen: set[str] = set()
    for text in transcripts:
        try:
            raw = primary.complete(SYSTEM, text)
            data = _json.loads(raw)
        except Exception as exc:  # noqa: BLE001
            seen.add(f"{type(exc).__name__}: {str(exc).splitlines()[0][:80]}")
            continue
        errs = schema_errors(data)
        if errs:
            seen.update(errs[:2])
        else:
            conformant += 1
    print(f"  schema-conformant {conformant}/{len(transcripts)} raw responses")
    for msg in sorted(seen)[:6]:
        print(f"    - {msg}")


def _build(config: str, claude_model: str, groq_model: str) -> object | None:
    if config == "rules":
        return None
    if config == "qwen":
        return QwenScriptLLM()
    if config == "claude":
        return AnthropicScriptLLM(model=claude_model)
    if config == "groq":
        return GroqScriptLLM(model=groq_model)
    if config == "chain":
        return [AnthropicScriptLLM(model=claude_model), QwenScriptLLM()]
    if config == "groqchain":
        return [GroqScriptLLM(model=groq_model), QwenScriptLLM()]
    raise SystemExit(f"unknown config: {config}")


def _run(label: str, transcripts: list[str], llm: object | None) -> list[tuple[float, str, float]]:
    rows = []
    for text in transcripts:
        start = time.perf_counter()
        result = analyze(text, llm)
        rows.append(
            (result.intent, result.source, (time.perf_counter() - start) * 1000.0)
        )
    return rows


def _summary(name: str, scam: list, normal: list, extra: list) -> None:
    s_intent = [r[0] for r in scam]
    n_intent = [r[0] for r in normal]
    all_rows = scam + normal + extra
    llm_share = sum(1 for r in all_rows if r[1] == "llm") / len(all_rows)
    mean_ms = sum(r[2] for r in all_rows) / len(all_rows)
    print(f"\n=== {name} ===")
    print(
        f"  scam intent     {min(s_intent):.2f}-{max(s_intent):.2f}  "
        f"mean {sum(s_intent) / len(s_intent):.2f}"
    )
    print(
        f"  ordinary intent {min(n_intent):.2f}-{max(n_intent):.2f}  "
        f"mean {sum(n_intent) / len(n_intent):.2f}"
    )
    print(f"  separation      {min(s_intent) - max(n_intent):+.2f}")
    print(f"  llm-path share  {llm_share:.0%}")
    print(f"  mean latency    {mean_ms:.0f} ms/transcript")
    if extra:
        e_intent = sorted(r[0] for r in extra)
        print(f"  real transcripts intent {e_intent}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--configs",
        default="rules,qwen",
        help="comma list of rules,qwen,claude,groq,chain,groqchain (default: rules,qwen)",
    )
    parser.add_argument("--claude-model", default="claude-sonnet-5")
    parser.add_argument("--groq-model", default="openai/gpt-oss-120b")
    parser.add_argument(
        "--real-file",
        type=Path,
        default=None,
        help="file of real transcripts, one per line, scored alongside the eval set",
    )
    parser.add_argument(
        "--schema-check",
        action="store_true",
        help="also report RESPONSE_SCHEMA conformance of raw responses (doubles LLM calls)",
    )
    args = parser.parse_args(argv)

    real: list[str] = []
    if args.real_file is not None:
        real = [
            line.strip()
            for line in args.real_file.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]

    for config in [c.strip() for c in args.configs.split(",") if c.strip()]:
        llm = _build(config, args.claude_model, args.groq_model)
        _probe(llm)
        scam = _run("scam", list(SCAM_TRANSCRIPTS), llm)
        normal = _run("normal", list(NORMAL_TRANSCRIPTS), llm)
        extra = _run("real", real, llm) if real else []
        _summary(config, scam, normal, extra)
        if args.schema_check:
            _schema_scan(llm, [*SCAM_TRANSCRIPTS, *NORMAL_TRANSCRIPTS])

    print("\nEvidence, not a verdict. Nothing was persisted.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
