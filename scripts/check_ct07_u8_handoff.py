#!/usr/bin/env python3
"""Sealed CT07 U8 replay and sensing-producer handoff gate.

The runner reads candidate evidence and the ISO U8 contract, computes their
byte identities, and delegates all producer validation to Rust.  It never
computes a joint total and never writes a favorable handoff for a stopped or
rejected domain.
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


REPO_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_ROOT = Path("power_pcb_dataset/qualification/ct07_t2")
DEFAULT_INPUT = REPO_ROOT / OUTPUT_ROOT / "u8_input.json"
DEFAULT_OUTPUT = REPO_ROOT / OUTPUT_ROOT / "authority/preliminary_decision.json"
CONTRACT = Path("power_pcb_dataset/qualification/isolation_joint/contract.json")


class Ct07U8ReplayError(qualification_replay.ReplayError):
    """A fail-closed CT07 U8 replay error."""


def _read_json(path: Path, *, root: Path) -> tuple[dict[str, Any], bytes]:
    try:
        read = qualification_replay.read_once(path, root=root)
        value = json.loads(read.data.decode("utf-8"))
    except (qualification_replay.ReplayError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise Ct07U8ReplayError(f"invalid CT07 U8 JSON {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise Ct07U8ReplayError(f"CT07 U8 JSON must be an object: {path}")
    return value, read.data


def _digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def compose_input(*, root: Path = REPO_ROOT) -> dict[str, Any]:
    """Compose the U8 input from canonical CT07 and ISO-owned bytes."""
    construction, construction_bytes = _read_json(root / OUTPUT_ROOT / "construction_manifest.json", root=root)
    projection, _ = _read_json(root / OUTPUT_ROOT / "construction_projection.json", root=root)
    # Keep this read even though U8 no longer copies source metadata into its
    # Rust payload: evidence-file presence and JSON validity remain a gate.
    _read_json(root / OUTPUT_ROOT / "evidence_index.json", root=root)
    ruling, ruling_bytes = _read_json(root / OUTPUT_ROOT / "authority/preliminary_ruling.json", root=root)
    contract_read = qualification_replay.read_once(root / CONTRACT, root=root)

    # The projection and transform policy digests are the reusable identities,
    # not labels copied into a receipt.  Recompute both from their canonical
    # Rust-compatible JSON payloads before handing anything to the evaluator.
    projection_payload = projection.get("payload")
    policy_payload = projection.get("allowed_transform_policy")
    if not isinstance(projection_payload, dict) or not isinstance(policy_payload, dict):
        raise Ct07U8ReplayError("construction projection is missing its payload or transform policy")
    if _digest(json.dumps(projection_payload, separators=(",", ":"), ensure_ascii=False).encode()) != projection.get("construction_projection_digest"):
        raise Ct07U8ReplayError("construction projection digest does not match its payload")
    if _digest(json.dumps(policy_payload, separators=(",", ":"), ensure_ascii=False).encode()) != projection.get("allowed_transform_policy_digest"):
        raise Ct07U8ReplayError("allowed transform policy digest does not match its payload")

    internal_path = root / OUTPUT_ROOT / "internal_decision.json"
    if internal_path.exists():
        internal, internal_bytes = _read_json(internal_path, root=root)
    else:
        internal = {
            "schema_version": 1,
            "construction_id": construction["construction_identity"]["construction_id"],
            "construction_digest": construction["construction_identity"]["construction_digest"],
            "internal_stage": "stopped-indeterminate",
            "stage": "stopped-indeterminate",
            "reasons": ["u7-a.pending", "u5.evidence", "u6.construction", "u9.environment"],
        }
        internal_bytes = json.dumps(internal, sort_keys=True, separators=(",", ":")).encode()

    identity = construction.get("construction_identity", {})
    construction_id = identity.get("construction_id", construction.get("candidate_id"))
    construction_digest = identity.get("construction_digest", construction.get("construction_digest"))
    if not isinstance(construction_id, str) or not isinstance(construction_digest, str):
        raise Ct07U8ReplayError("construction identity is missing")
    return {
        "schema_version": 1,
        "construction_id": construction_id,
        "construction_digest": construction_digest,
        "internal_decision_digest": _digest(internal_bytes),
        "internal_stage": internal.get("internal_stage", internal.get("stage", "stopped-indeterminate")),
        "internal_reasons": internal.get("reasons", ["internal.evidence-pending"]),
        "construction_projection_digest": projection.get("construction_projection_digest"),
        "allowed_transform_policy_digest": projection.get("allowed_transform_policy_digest"),
        "joint_contract_digest": _digest(contract_read.data),
        "ocp02_status": "DNF",
        "preliminary_decision_digest": _digest(ruling_bytes),
        "preliminary": ruling,
        "sensor_threshold_to_system_latch_assertion_max_ns": None,
        "threshold_crossing_policy": None,
        "normative_threshold_crossing_policy_digest": None,
        "timing_basis": None,
        "uncertainty_components": [],
        "signers": [],
        "construction_bytes": list(construction_bytes),
        "internal_decision_bytes": list(internal_bytes),
        "preliminary_decision_bytes": list(ruling_bytes),
        "joint_contract_bytes": list(contract_read.data),
    }


def _evaluate(package: dict[str, Any]) -> dict[str, Any]:
    try:
        import temper_quality_oracle
    except ImportError as exc:  # pragma: no cover
        raise Ct07U8ReplayError("temper_quality_oracle is unavailable; rebuild extensions") from exc
    evaluator = getattr(temper_quality_oracle, "evaluate_ct07_u8_handoff_json", None)
    if not callable(evaluator):
        raise Ct07U8ReplayError("CT07 U8 Rust evaluator registration is unavailable")
    try:
        result = json.loads(evaluator(json.dumps(package, sort_keys=True, separators=(",", ":"))))
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        raise Ct07U8ReplayError(f"CT07 U8 evaluator rejected package: {exc}") from exc
    if not isinstance(result, dict):
        raise Ct07U8ReplayError("CT07 U8 evaluator returned a non-object")
    return result


def _validate_output(result: dict[str, Any]) -> None:
    stage = result.get("stage")
    handoff = result.get("handoff")
    if stage == "construction-envelope-approved":
        if not isinstance(handoff, dict):
            raise Ct07U8ReplayError("favorable CT07 U8 result must include a handoff")
        if any(key in handoff for key in ("joint_total_ns", "aggregate_ns", "timing_pass", "verdict")):
            raise Ct07U8ReplayError("CT07 U8 handoff must not contain a joint aggregate")
        timing = handoff.get("sensor_threshold_to_system_latch_assertion_max_ns")
        if not isinstance(timing, str) or not timing.isascii() or not timing.isdecimal():
            raise Ct07U8ReplayError("CT07 U8 timing bound must be a canonical decimal string")
        if "sensor_threshold_to_system_latch_assertion_max_us" in handoff:
            raise Ct07U8ReplayError("CT07 U8 handoff must not contain a microsecond timing alias")
    elif handoff is not None:
        raise Ct07U8ReplayError("stopped/rejected CT07 U8 result must not publish a handoff")


def replay(
    input_path: Path | None = None,
    output_path: Path | None = None,
    *,
    repo_root: Path = REPO_ROOT,
    fixture_mode: bool | None = None,
) -> dict[str, Any]:
    """Replay U8 and optionally write the preliminary decision."""
    input_path = input_path or DEFAULT_INPUT
    if fixture_mode is None:
        # The Python API is retained for focused unit fixtures; the CLI below
        # requires an explicit --fixture so production invocation cannot be
        # redirected accidentally.
        fixture_mode = input_path.resolve() != DEFAULT_INPUT.resolve()
    if fixture_mode:
        if output_path is not None:
            raise Ct07U8ReplayError("fixture mode cannot publish a decision or handoff")
        if not input_path.exists():
            raise Ct07U8ReplayError(f"CT07 U8 fixture input does not exist: {input_path}")
        package, _ = _read_json(input_path, root=repo_root)
    else:
        # The production runner always rebuilds the package from its canonical
        # read-once sources.  Even the repository's default input file is a
        # fixture and must not become an alternate publication path.
        package = compose_input(root=repo_root)
    result = _evaluate(package)
    _validate_output(result)
    if output_path is not None:
        output = output_path if output_path.is_absolute() else repo_root / output_path
        output_root = (repo_root / OUTPUT_ROOT).resolve()
        try:
            output.resolve().relative_to(output_root)
        except ValueError as exc:
            raise Ct07U8ReplayError("CT07 U8 output must remain under qualification root") from exc
        output.parent.mkdir(parents=True, exist_ok=True)
        rendered = json.dumps(result, indent=2, sort_keys=True) + "\n"
        try:
            qualification_replay.publish_atomic(output, rendered, root=repo_root)
        except qualification_replay.ReplayError as exc:
            raise Ct07U8ReplayError(f"cannot publish CT07 U8 decision: {exc}") from exc
        if result.get("stage") == "construction-envelope-approved":
            handoff = output_root / "joint_handoff.json"
            try:
                qualification_replay.publish_atomic(
                    handoff,
                    json.dumps(result["handoff"], indent=2, sort_keys=True) + "\n",
                    root=repo_root,
                )
            except qualification_replay.ReplayError as exc:
                raise Ct07U8ReplayError(f"cannot publish CT07 U8 handoff: {exc}") from exc
        else:
            # A stopped/rejected replay must invalidate any favorable handoff
            # left by an earlier run.  Publication is atomic and carries the
            # current preliminary-decision identity for every consumer.
            handoff = output_root / "joint_handoff.json"
            invalidated = {
                "status": "invalidated",
                "preliminary_decision_digest": package.get("preliminary_decision_digest"),
                "reason": result.get("stage"),
            }
            try:
                qualification_replay.publish_atomic(
                    handoff,
                    json.dumps(invalidated, indent=2, sort_keys=True) + "\n",
                    root=repo_root,
                )
            except qualification_replay.ReplayError as exc:
                raise Ct07U8ReplayError(f"cannot invalidate CT07 U8 handoff: {exc}") from exc
    elif not fixture_mode and result.get("stage") != "construction-envelope-approved":
        # Canonical replay is also a state transition when the caller accepts
        # the default decision path. Never leave an older favorable handoff
        # live after current evidence stops or rejects qualification.
        handoff = (repo_root / OUTPUT_ROOT).resolve() / "joint_handoff.json"
        invalidated = {
            "status": "invalidated",
            "preliminary_decision_digest": package.get("preliminary_decision_digest"),
            "reason": result.get("stage"),
        }
        try:
            qualification_replay.publish_atomic(
                handoff,
                json.dumps(invalidated, indent=2, sort_keys=True) + "\n",
                root=repo_root,
            )
        except qualification_replay.ReplayError as exc:
            raise Ct07U8ReplayError(f"cannot invalidate CT07 U8 handoff: {exc}") from exc
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument(
        "--fixture",
        action="store_true",
        help="evaluate --input as an unpublishable test fixture",
    )
    args = parser.parse_args(argv)
    try:
        if args.input is not None and not args.fixture:
            raise Ct07U8ReplayError(
                "--input is fixture-only; pass --fixture and omit --output, or use canonical composition"
            )
        if args.fixture and args.output is not None:
            raise Ct07U8ReplayError("fixture mode cannot publish a decision or handoff")
        result = replay(args.input, args.output, fixture_mode=args.fixture)
    except Ct07U8ReplayError as exc:
        print(f"CT07 U8 replay stopped: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
