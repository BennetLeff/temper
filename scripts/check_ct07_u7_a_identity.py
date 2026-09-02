#!/usr/bin/env python3
"""Replay the CT07 U7-A identity/source eligibility checkpoint.

The Rust quality oracle owns the policy and verdict.  This adapter performs
only bounded repository I/O: it reads the identity package and the selected
U4-B generated manifest, checks their byte identities, and formats the Rust
decision.  It intentionally cannot publish a U6 construction release.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

try:
    from scripts._lib import qualification_replay
except ImportError:  # pragma: no cover
    from _lib import qualification_replay

try:
    import temper_quality_oracle
except ImportError:  # pragma: no cover - exercised in environments without the extension
    temper_quality_oracle = None  # type: ignore[assignment]


REPO_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_ROOT = REPO_ROOT / "power_pcb_dataset/qualification/ct07_t2"
DEFAULT_PACKAGE = OUTPUT_ROOT / "identity_eligibility.json"
SOURCE_PATH = Path("power_pcb_dataset/qualification/ct07_t2/generated/manifest.json")


class U7AIdentityGateError(RuntimeError):
    """The checkpoint cannot be replayed from the supplied identities."""


def _read_json(path: Path, *, root: Path) -> tuple[dict[str, Any], bytes]:
    try:
        read = qualification_replay.read_once(path, root=root)
    except qualification_replay.ReplayError as exc:
        raise U7AIdentityGateError(f"cannot securely read identity input {path}: {exc}") from exc
    raw = read.data
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise U7AIdentityGateError(f"invalid identity JSON {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise U7AIdentityGateError(f"identity JSON root must be an object: {path}")
    return value, raw


def _validate_candidate_source(package: dict[str, Any], source: dict[str, Any], raw: bytes) -> None:
    binding = package.get("candidate_source")
    if not isinstance(binding, dict):
        raise U7AIdentityGateError("candidate_source binding is required")
    if binding.get("source_path") != SOURCE_PATH.as_posix():
        raise U7AIdentityGateError("candidate_source must bind the canonical U4-B generated manifest")
    expected = binding.get("source_sha256")
    actual = hashlib.sha256(raw).hexdigest()
    if expected != actual:
        raise U7AIdentityGateError("U4-B candidate source digest does not match its bytes")
    for field in ("candidate_id", "status"):
        if source.get(field) != binding.get(field):
            raise U7AIdentityGateError(f"U4-B candidate source {field} does not match identity package")
    if source.get("candidate_id") != package.get("candidate_id"):
        raise U7AIdentityGateError("U4-B candidate ID does not match identity package")


def _evaluate(package: dict[str, Any], source: dict[str, Any], raw: bytes) -> str:
    _validate_candidate_source(package, source, raw)
    if temper_quality_oracle is None:
        raise U7AIdentityGateError(
            "temper_quality_oracle is unavailable; rebuild the pyo3 extension before U7-A replay"
        )
    evaluator = getattr(temper_quality_oracle, "evaluate_ct07_u7_a_identity_json", None)
    if not callable(evaluator):
        raise U7AIdentityGateError("CT07 U7-A Rust evaluator registration is unavailable")
    try:
        return evaluator(json.dumps(package, separators=(",", ":"), ensure_ascii=False))
    except (TypeError, ValueError) as exc:
        raise U7AIdentityGateError(f"CT07 U7-A Rust evaluator rejected package: {exc}") from exc


def replay(package_path: Path = DEFAULT_PACKAGE, output_path: Path | None = None, *, repo_root: Path = REPO_ROOT) -> str:
    package_path = Path(package_path)
    package, _ = _read_json(package_path, root=repo_root)
    source, source_raw = _read_json(repo_root / SOURCE_PATH, root=repo_root)
    result = _evaluate(package, source, source_raw)
    try:
        decision = json.loads(result)
    except json.JSONDecodeError as exc:
        raise U7AIdentityGateError(f"Rust U7-A decision is not JSON: {exc}") from exc
    if not isinstance(decision, dict):
        raise U7AIdentityGateError("Rust U7-A decision must be an object")
    if decision.get("candidate_id") != package.get("candidate_id"):
        raise U7AIdentityGateError("U7-A decision candidate ID does not match package")
    if decision.get("construction_release_eligible") is True and decision.get("status") != "eligible":
        raise U7AIdentityGateError("U7-A decision has an inconsistent release flag")
    rendered = json.dumps(decision, indent=2, sort_keys=True) + "\n"
    if output_path is not None:
        output = Path(output_path)
        output_root = repo_root / "power_pcb_dataset/qualification/ct07_t2"
        try:
            output.resolve().relative_to(output_root.resolve())
        except ValueError as exc:
            raise U7AIdentityGateError("U7-A output must remain under the CT07 qualification root") from exc
        output.parent.mkdir(parents=True, exist_ok=True)
        try:
            qualification_replay.publish_atomic(output, rendered, root=repo_root)
        except qualification_replay.ReplayError as exc:
            raise U7AIdentityGateError(f"cannot publish U7-A decision: {exc}") from exc
    return rendered


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("--package", type=Path, default=DEFAULT_PACKAGE)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    try:
        rendered = replay(args.package, args.output)
    except U7AIdentityGateError as exc:
        print(f"CT07 U7-A IDENTITY GATE ERROR: {exc}", file=sys.stderr)
        return 2
    if args.output is None:
        sys.stdout.write(rendered)
    else:
        print(f"wrote {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
