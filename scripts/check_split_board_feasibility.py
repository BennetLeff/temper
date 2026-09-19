#!/usr/bin/env python3
"""Replay the split-board feasibility admission and U7 terminal gates.

This command is a sealed boundary.  It reads the upstream U9 package and its
decision exactly once, snapshots all consumed qualification bytes before and
after evaluation, and delegates schema, identity, precedence, and verdict
policy to ``temper_quality_oracle``.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any

try:
    from scripts._lib import qualification_replay
except ImportError:  # pragma: no cover
    from _lib import qualification_replay

REPO_ROOT = Path(__file__).resolve().parent.parent
QUALIFICATION_ROOT = Path("power_pcb_dataset/qualification/split_board_feasibility")
U9_ROOT = Path("power_pcb_dataset/qualification/isolation_joint")
U9_MANIFEST = U9_ROOT / "manifest.json"
U9_DECISION = U9_ROOT / "decision.json"
U9_CONTRACT = U9_ROOT / "contract.json"
DEFAULT_OUTPUT = REPO_ROOT / QUALIFICATION_ROOT / "admission_decision.json"
TERMINAL_OUTPUT = REPO_ROOT / QUALIFICATION_ROOT / "decision.json"
PROTECTED_DESCRIPTOR_REQUIRED_PATHS = (
    Path("pcb/temper.kicad_pcb"),
    Path("pcb/temper.kicad_pro"),
    Path("pcb/fp-lib-table"),
    Path("power_pcb_dataset/drc_ceiling.json"),
    Path("elec/domain_manifest.yaml"),
    Path("elec/ato.yaml"),
    Path("docs/ENVIRONMENTAL_SPEC.md"),
    Path("docs/hardware/BOM.md"),
    Path("packages/temper-placer/src/temper_placer/core/isolation_constants.py"),
    Path("packages/temper-design-bundle/src/safety_value.rs"),
    Path("packages/temper-design-bundle/src/safety_value_authority.rs"),
    Path("packages/temper-thermal/src/safety.rs"),
)
PROTECTED_DESCRIPTOR_RECURSIVE_PATHS = (
    Path("pcb/libs"),
    Path("elec/src"),
    Path("elec/exports"),
    Path("elec/build"),
    Path("firmware"),
    Path("packages/temper-drc-rs/src/rules/safety"),
    U9_ROOT,
)
U9_EXTERNAL_PROTECTED_PATHS = (
    Path("elec/qualification/isolation_joint/interface_contract.json"),
    Path("elec/qualification/isolation_joint/validation/fixture_contract.json"),
)
# The production protected set is the same authority as the descriptor roots.
# Keep one source of truth so a newly protected campaign input cannot silently
# evade the before/after mutation check.
PRODUCTION_PROTECTED_PATHS = (
    PROTECTED_DESCRIPTOR_REQUIRED_PATHS + PROTECTED_DESCRIPTOR_RECURSIVE_PATHS
)


class SplitBoardReplayError(qualification_replay.ReplayError):
    """A fail-closed split-board admission replay error."""


def _read_once(path: Path, *, root: Path) -> qualification_replay.ReadOnce:
    try:
        return qualification_replay.read_once(path, root=root)
    except qualification_replay.ReplayError as exc:
        raise SplitBoardReplayError(f"invalid split-board input {path}: {exc}") from exc


def _snapshot_paths(
    root: Path, paths: list[Path]
) -> dict[str, qualification_replay.SnapshotEntry]:
    try:
        return qualification_replay.snapshot_paths(root, paths)
    except qualification_replay.ReplayError as exc:
        raise SplitBoardReplayError(
            f"cannot snapshot split-board protected inputs: {exc}"
        ) from exc


def _read_json(path: Path, *, root: Path) -> tuple[dict[str, Any], bytes]:
    try:
        read = _read_once(path, root=root)
        value = json.loads(read.data.decode("utf-8"))
    except (qualification_replay.ReplayError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SplitBoardReplayError(f"invalid split-board JSON {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise SplitBoardReplayError(f"split-board JSON must be an object: {path}")
    return value, read.data


def _path_from_manifest(value: Any) -> list[Path]:
    paths: list[Path] = []
    if not isinstance(value, dict):
        return paths
    inputs = value.get("inputs", {})
    if not isinstance(inputs, Mapping):
        raise SplitBoardReplayError("split-board manifest inputs must be a mapping")
    for record in inputs.values():
        if not isinstance(record, dict):
            continue
        for key in ("internal_decision_path", "preliminary_decision_path", "handoff_path"):
            item = record.get(key)
            if isinstance(item, str) and item:
                paths.append(Path(item))
    # The U9 root snapshot already covers its candidate, signoffs, contract,
    # and decision paths (some are intentionally relative to that root).
    # Only source decisions outside that root need separate entries here.
    return paths


def _verify_manifest_protected_pins(manifest: dict[str, Any], *, root: Path) -> None:
    """Fail if a manifest pin does not match the current protected bytes."""

    entries = manifest.get("protected_inputs")
    if not isinstance(entries, list) or not entries:
        raise SplitBoardReplayError("split-board manifest protected_inputs must be non-empty")
    seen: set[str] = set()
    for entry in entries:
        if not isinstance(entry, dict):
            raise SplitBoardReplayError("split-board protected input entry must be an object")
        path_text = entry.get("path")
        expected = entry.get("sha256")
        if not isinstance(path_text, str) or not path_text:
            raise SplitBoardReplayError("split-board protected input path must be non-empty")
        if path_text in seen:
            raise SplitBoardReplayError(f"duplicate split-board protected input {path_text}")
        seen.add(path_text)
        if (
            not isinstance(expected, str)
            or len(expected) != 64
            or any(character not in "0123456789abcdefABCDEF" for character in expected)
        ):
            raise SplitBoardReplayError(
                f"split-board protected input {path_text} has an invalid SHA-256"
            )
        current = _read_once(root / path_text, root=root)
        actual = current.sha256
        if actual != expected.lower():
            raise SplitBoardReplayError(
                f"split-board protected input digest mismatch for {path_text}: "
                f"expected {expected.lower()}, got {actual}"
            )


def _descriptor_paths() -> tuple[Path, ...]:
    return PROTECTED_DESCRIPTOR_REQUIRED_PATHS + PROTECTED_DESCRIPTOR_RECURSIVE_PATHS


def _snapshot_digest(snapshot: dict[str, qualification_replay.SnapshotEntry]) -> str:
    """Hash a stable path/kind/content view of a protected subtree."""

    rows = [
        (path, entry.kind, entry.sha256)
        for path, entry in sorted(snapshot.items())
    ]
    encoded = json.dumps(rows, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _descriptor_snapshot(
    path: Path,
    *,
    root: Path,
    snapshot: dict[str, qualification_replay.SnapshotEntry] | None = None,
) -> dict[str, Any]:
    if snapshot is None:
        snapshot = _snapshot_paths(root, [path])
    key = path.as_posix()
    entry = snapshot[key]
    result: dict[str, Any] = {"path": path.as_posix(), "kind": entry.kind}
    if entry.kind == "file":
        result["content_sha256"] = entry.sha256
    elif entry.kind == "directory":
        subtree = {
            child_path: child_entry
            for child_path, child_entry in snapshot.items()
            if child_path == key or child_path.startswith(f"{key}/")
        }
        result["tree_sha256"] = _snapshot_digest(subtree)
    return result


def _verify_protected_descriptor(
    manifest: dict[str, Any],
    *,
    root: Path,
    snapshot: dict[str, qualification_replay.SnapshotEntry] | None = None,
) -> None:
    """Verify the manifest's clean campaign-base identity before evaluation."""

    descriptor = manifest.get("protected_descriptor")
    if not isinstance(descriptor, dict):
        raise SplitBoardReplayError("split-board protected_descriptor is required")
    required = descriptor.get("required_paths")
    recursive = descriptor.get("recursive_paths")
    expected_required = [path.as_posix() for path in PROTECTED_DESCRIPTOR_REQUIRED_PATHS]
    expected_recursive = [path.as_posix() for path in PROTECTED_DESCRIPTOR_RECURSIVE_PATHS]
    if required != expected_required or recursive != expected_recursive:
        raise SplitBoardReplayError(
            "split-board protected_descriptor path set does not match runner constants"
        )
    pins = descriptor.get("campaign_base")
    if not isinstance(pins, list):
        raise SplitBoardReplayError("split-board protected_descriptor campaign_base is required")
    expected_paths = set(expected_required + expected_recursive)
    if {pin.get("path") for pin in pins if isinstance(pin, dict)} != expected_paths:
        raise SplitBoardReplayError("split-board protected_descriptor pins do not cover declared roots")
    if len(pins) != len(expected_paths) or any(not isinstance(pin, dict) for pin in pins):
        raise SplitBoardReplayError("split-board protected_descriptor pins must be unique objects")
    for pin in pins:
        path_text = pin.get("path")
        if not isinstance(path_text, str):
            raise SplitBoardReplayError("split-board protected_descriptor pin path is invalid")
        actual = _descriptor_snapshot(Path(path_text), root=root, snapshot=snapshot)
        if actual != pin:
            raise SplitBoardReplayError(
                f"split-board campaign-base protected descriptor mismatch for {path_text}"
            )


def _protected_paths(manifest: dict[str, Any], *, include_u7: bool = False) -> list[Path]:
    """Return a complete, de-duplicated U9 consumed-byte protected set."""

    # The root snapshot recursively covers every receipt, evidence record,
    # decision byte, and capture under the U9 package.
    paths = list(PRODUCTION_PROTECTED_PATHS) + list(U9_EXTERNAL_PROTECTED_PATHS) + [U9_ROOT]
    u7_names = ["manifest.json", "admission_decision.json"]
    if include_u7:
        u7_names.extend(("evidence_index.json", "owner_signoffs.json"))
    paths.extend(QUALIFICATION_ROOT / name for name in u7_names)
    paths.extend(_path_from_manifest(manifest))
    unique: list[Path] = []
    seen: set[str] = set()
    for path in paths:
        key = path.as_posix()
        try:
            if path != U9_ROOT and path.is_relative_to(U9_ROOT):
                continue
        except AttributeError:  # pragma: no cover - Python 3.8 compatibility
            if path != U9_ROOT and U9_ROOT in path.parents:
                continue
        if key not in seen:
            seen.add(key)
            unique.append(path)
    return unique


def _evaluate(package: dict[str, Any]) -> dict[str, Any]:
    try:
        import temper_quality_oracle
    except ImportError as exc:  # pragma: no cover
        raise SplitBoardReplayError("temper_quality_oracle is unavailable; rebuild extensions") from exc
    evaluator = getattr(temper_quality_oracle, "evaluate_split_board_feasibility_json", None)
    if not callable(evaluator):
        raise SplitBoardReplayError("split-board Rust evaluator registration is unavailable")
    try:
        result = json.loads(evaluator(json.dumps(package, sort_keys=True, separators=(",", ":"))))
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        raise SplitBoardReplayError(f"split-board evaluator rejected package: {exc}") from exc
    if not isinstance(result, dict):
        raise SplitBoardReplayError("split-board evaluator returned a non-object")
    return result


def _canonical_bytes(result: dict[str, Any]) -> bytes:
    # Rust's serde_json pretty serializer preserves its deterministic map
    # order.  Preserve that order here so the comparison is genuinely byte
    # exact rather than a semantic JSON comparison.
    return (json.dumps(result, indent=2) + "\n").encode("utf-8")


def _require_byte_match(
    result: dict[str, Any], expected_path: Path, *, root: Path, label: str
) -> bytes:
    expected = _read_once(expected_path, root=root).data
    actual = _canonical_bytes(result)
    if actual != expected:
        raise SplitBoardReplayError(f"Rust {label} decision does not byte-match {expected_path}")
    return expected


def compose_input(*, root: Path = REPO_ROOT) -> tuple[dict[str, Any], list[Path]]:
    """Compose the live admission input from the exact U9 replay boundary."""

    split_manifest, _ = _read_json(root / QUALIFICATION_ROOT / "manifest.json", root=root)
    _verify_manifest_protected_pins(split_manifest, root=root)
    manifest, manifest_bytes = _read_json(root / U9_MANIFEST, root=root)
    published, published_bytes = _read_json(root / U9_DECISION, root=root)
    _contract, contract_bytes = _read_json(root / U9_CONTRACT, root=root)
    combined, combined_bytes = _read_json(root / (U9_ROOT / "combined_candidate.json"), root=root)
    try:
        # This is the canonical U9 replay, not a copied status field.  It
        # performs its own receipt/decision identity checks before returning.
        from scripts import check_isolation_joint_qualification as joint
    except ImportError:  # pragma: no cover
        import check_isolation_joint_qualification as joint
    try:
        replayed = joint.replay_u9(root=root)
    except Exception as exc:  # normalize both sealed replay and extension errors
        raise SplitBoardReplayError(f"upstream U9 replay failed: {exc}") from exc
    if json.dumps(replayed, sort_keys=True, indent=2) + "\n" != published_bytes.decode("utf-8"):
        raise SplitBoardReplayError("published U9 decision does not byte-match its fresh replay")
    package = {
        "schema_version": 1,
        "candidate_id": "split-board-feasibility-u1-admission",
        "evaluator_identity": "split-board-feasibility-admission-v1",
        "joint_contract_digest": hashlib.sha256(contract_bytes).hexdigest(),
        "upstream_decision": replayed,
        "replayed_decision": replayed,
        "published_decision": published,
        "published_decision_bytes": list(published_bytes),
        "published_decision_digest": hashlib.sha256(published_bytes).hexdigest(),
        "upstream_manifest_digest": hashlib.sha256(manifest_bytes).hexdigest(),
        "upstream_manifest_bytes": list(manifest_bytes),
        "joint_contract_bytes": list(contract_bytes),
        "combined_candidate": combined,
        "combined_candidate_bytes": list(combined_bytes),
        "local_evidence": [],
        "candidate_family": {"members": [], "closed": True, "exhausted": False},
    }
    return package, _protected_paths(manifest)


def replay(
    input_path: Path | None = None,
    output_path: Path | None = None,
    *,
    repo_root: Path = REPO_ROOT,
    fixture_mode: bool | None = None,
    mode: str = "both",
) -> dict[str, Any]:
    if fixture_mode is None:
        fixture_mode = input_path is not None
    if fixture_mode:
        if input_path is None:
            raise SplitBoardReplayError("fixture mode requires --input")
        package, _ = _read_json(input_path, root=repo_root)
        if output_path is not None:
            raise SplitBoardReplayError("fixture replay cannot publish an admission decision")
        return _evaluate(package)
    else:
        manifest, _ = _read_json(repo_root / U9_MANIFEST, root=repo_root)
        split_manifest, _ = _read_json(
            repo_root / QUALIFICATION_ROOT / "manifest.json", root=repo_root
        )
        if mode not in {"both", "admission", "terminal"}:
            raise SplitBoardReplayError(f"unknown replay mode {mode}")
        protected_paths = _protected_paths(manifest, include_u7=mode != "admission")
        protected_before = _snapshot_paths(repo_root, protected_paths)
        _verify_protected_descriptor(
            split_manifest, root=repo_root, snapshot=protected_before
        )
        package, _ = compose_input(root=repo_root)
        _, published_bytes = _read_json(repo_root / U9_DECISION, root=repo_root)
        _, contract_bytes = _read_json(repo_root / U9_CONTRACT, root=repo_root)
        _, manifest_bytes = _read_json(repo_root / U9_MANIFEST, root=repo_root)
        if mode != "admission":
            u7_sources = {}
            for name in ("manifest.json", "admission_decision.json", "evidence_index.json", "owner_signoffs.json"):
                u7_sources[name.removesuffix(".json")] = _read_once(
                    repo_root / QUALIFICATION_ROOT / name, root=repo_root
                ).data
            package["u7_source_bytes"] = {key: list(value) for key, value in u7_sources.items()}
    admission_result = _evaluate({**package, "evaluation_mode": "admission"})
    admission_path = repo_root / QUALIFICATION_ROOT / "admission_decision.json"
    admission_bytes = _require_byte_match(
        admission_result, admission_path, root=repo_root, label="admission"
    )
    if output_path is not None:
        raise SplitBoardReplayError("live feasibility replay is read-only; omit --output")
    if mode == "admission":
        protected_after = _snapshot_paths(repo_root, protected_paths)
        if protected_before != protected_after:
            raise SplitBoardReplayError("protected qualification inputs changed during replay")
        return admission_result

    combined = package["combined_candidate"]
    assert isinstance(combined, dict)
    terminal_bindings = {
        "admission_decision": {
            "path": (QUALIFICATION_ROOT / "admission_decision.json").as_posix(),
            "sha256": hashlib.sha256(admission_bytes).hexdigest(),
        },
        "manifest": {
            "path": (QUALIFICATION_ROOT / "manifest.json").as_posix(),
            "sha256": _read_once(
                repo_root / QUALIFICATION_ROOT / "manifest.json", root=repo_root
            ).sha256,
        },
        "upstream_joint_decision": {
            "path": U9_DECISION.as_posix(),
            "sha256": hashlib.sha256(published_bytes).hexdigest(),
        },
        "upstream_joint_contract": {
            "path": U9_CONTRACT.as_posix(),
            "sha256": hashlib.sha256(contract_bytes).hexdigest(),
        },
        "upstream_joint_manifest": {
            "path": U9_MANIFEST.as_posix(),
            "sha256": hashlib.sha256(manifest_bytes).hexdigest(),
        },
        "upstream_combined_candidate": {
            "path": (U9_ROOT / "combined_candidate.json").as_posix(),
            "sha256": hashlib.sha256(bytes(package["combined_candidate_bytes"])).hexdigest(),
        },
        "evidence_index": {
            "path": (QUALIFICATION_ROOT / "evidence_index.json").as_posix(),
            "sha256": hashlib.sha256(bytes(package["u7_source_bytes"]["evidence_index"])).hexdigest(),
        },
        "owner_signoffs": {
            "path": (QUALIFICATION_ROOT / "owner_signoffs.json").as_posix(),
            "sha256": hashlib.sha256(bytes(package["u7_source_bytes"]["owner_signoffs"])).hexdigest(),
        },
    }
    terminal_package = {
        **package,
        "evaluation_mode": "terminal",
        "terminal_context": {
            "combined_candidate": {
                "path": (U9_ROOT / "combined_candidate.json").as_posix(),
                "sha256": hashlib.sha256(bytes(package["combined_candidate_bytes"])).hexdigest(),
                "status": "absent",
                "source_status": combined.get("status", "not-materialized"),
            },
            "bindings": terminal_bindings,
            "source_bytes": package["u7_source_bytes"],
        },
    }
    terminal_result = _evaluate(terminal_package)
    _require_byte_match(
        terminal_result,
        repo_root / QUALIFICATION_ROOT / "decision.json",
        root=repo_root,
        label="U7 terminal",
    )
    protected_after = _snapshot_paths(repo_root, protected_paths)
    if protected_before != protected_after:
        raise SplitBoardReplayError("protected qualification inputs changed during replay")
    return terminal_result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, help="fixture input; requires --fixture")
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="deprecated publishing option; live replay is read-only",
    )
    parser.add_argument("--fixture", action="store_true", help="evaluate an unpublishable fixture")
    parser.add_argument(
        "--mode",
        choices=("both", "admission", "terminal"),
        default="both",
        help="replay admission only, U7 terminal only, or verify both (default)",
    )
    args = parser.parse_args(argv)
    try:
        if args.input is not None and not args.fixture:
            raise SplitBoardReplayError("--input is fixture-only; pass --fixture")
        if args.fixture and args.output is not None:
            raise SplitBoardReplayError("--output is incompatible with --fixture")
        if args.fixture and args.mode != "both":
            raise SplitBoardReplayError("--mode is incompatible with --fixture; set evaluation_mode in the fixture")
        result = replay(
            args.input,
            args.output if not args.fixture else None,
            fixture_mode=args.fixture,
            mode=args.mode,
        )
    except SplitBoardReplayError as exc:
        print(f"split-board admission replay stopped: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
