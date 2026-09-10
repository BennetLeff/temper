"""Cross-unit engineering-memory host plumbing (P2).

The Rust policy in `src/memory.rs` (reached here through the standalone
`src/bin/memory_judge.rs` bridge until P1 registers it in the main
dispatcher) owns every decision: entry validation, deterministic selection,
and promotion review. This module owns only process and filesystem work:
reading the `harness-lab/memory/` catalog, verifying bytes, materializing a
selection through the existing :class:`artifacts.Store`, and publishing
content-bound receipts. It contains no selection/validation policy of its
own; any disagreement between this host and the Rust judge is resolved in
favor of Rust.

Ownership: P2 owns this adapter and its tests. P1 exclusively owns
`workspace.py`, `workspace_worker.py`, `test_workspace.py`, shared
observation/receipt wiring, and calls from `run_block.py`; P2 supplies the
interface (:func:`p1_interface`, :func:`deliver_selection`) without editing
those files.

U3 delivery (KTD6) reuses the existing runtime path only: the selected
revision is materialized through :class:`artifacts.Store` and loaded with
``Workspace.apply_revision``; notes travel in the revision and in the
retained model-input capture; helpers execute only inside the sandbox via
``Workspace.execute`` with every nested ``pcb.call`` attributed to the
executing revision. No change to the shared runtime files was needed: the
existing ``apply_revision`` acknowledgement, ``revision_events`` log, and
``current_revision`` already express everything KTD6 requires. The only new
plumbing is receipt-side (helper-call provenance entries and the
model-input capture), which the shared observation channel cannot express.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
from pathlib import Path
from typing import Any

import artifacts

ROOT = Path(__file__).resolve().parent
MEMORY_DIR = ROOT / "memory"
CATALOG = MEMORY_DIR / "catalog.json"
ENTRIES_DIR = MEMORY_DIR / "entries"
SCHEMA = "memory/v1"


def default_judge() -> Path:
    """Locate the standalone memory judge next to the main harness judge."""
    override = os.environ.get("TEMPER_MEMORY_JUDGE")
    if override:
        return Path(override)
    main = (
        Path(os.environ["TEMPER_E00_JUDGE"])
        if "TEMPER_E00_JUDGE" in os.environ
        else None
    )
    if main is not None:
        return main.parent / "memory_judge"
    import harness

    return harness.default_judge().parent / "memory_judge"


def judge(command: str, value: dict, *, timeout: float = 5) -> dict:
    """Call the Rust memory policy; raise unless it passes."""
    binary = default_judge()
    try:
        result = subprocess.run(
            [str(binary)],
            input=json.dumps(
                {"schema": SCHEMA, "command": command, "input": value},
                ensure_ascii=False,
                allow_nan=False,
                separators=(",", ":"),
            ),
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as error:
        raise RuntimeError(f"memory Rust judge unavailable: {error}") from error
    try:
        answer = json.loads(result.stdout)
    except ValueError as error:
        raise RuntimeError("memory Rust judge returned invalid JSON") from error
    if answer.get("status") == "invalid":
        raise ValueError(answer.get("error", "Rust policy rejected input"))
    if result.returncode != 0 or answer.get("schema") != SCHEMA:
        raise RuntimeError("memory Rust judge unavailable")
    return answer


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON field")
        result[key] = value
    return result


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def load_catalog(memory_dir: Path = MEMORY_DIR) -> dict:
    """Read the catalog and every referenced entry file with byte hashes.

    Returns ``{"catalog": ..., "entries": [{"descriptor": ..., "text": ...,
    "content_sha256": ...}]}``. Priority is catalog order (index); the Rust
    judge owns ordering. No policy lives here: this only binds bytes.
    """
    catalog_path = memory_dir / "catalog.json"
    catalog = json.loads(
        catalog_path.read_text(encoding="utf-8"),
        object_pairs_hook=_unique_object,
    )
    if catalog.get("version") != 1 or not isinstance(catalog.get("entries"), list):
        raise ValueError("unsupported memory catalog version")
    loaded: list[dict] = []
    for descriptor in catalog["entries"]:
        entry_id = descriptor.get("id")
        if not isinstance(entry_id, str) or not entry_id:
            raise ValueError("catalog entry without an id")
        matches = sorted((memory_dir / "entries").glob(f"{entry_id}*.md"))
        if len(matches) != 1:
            raise ValueError(f"entry {entry_id} does not resolve to exactly one file")
        text = matches[0].read_text(encoding="utf-8")
        loaded.append(
            {
                "descriptor": descriptor,
                "path": matches[0].name,
                "text": text,
                "content_sha256": _sha256_bytes(text.encode("utf-8")),
            }
        )
    return {"catalog": catalog, "entries": loaded}


def _evidence_hashes() -> dict[str, str]:
    """Authoritative evidence hashes, read live from the working tree."""
    roots = [ROOT.parent, ROOT]
    hashes: dict[str, str] = {}
    catalog = json.loads((MEMORY_DIR / "catalog.json").read_text(encoding="utf-8"))
    for descriptor in catalog["entries"]:
        for item in descriptor.get("evidence", []):
            rel = item["path"]
            if rel in hashes:
                continue
            for root in roots:
                candidate = root / rel
                if candidate.is_file():
                    hashes[rel] = _sha256_bytes(candidate.read_bytes())
                    break
    return hashes


def validate_loaded(
    loaded: dict, *, evidence_hashes: dict[str, str] | None = None
) -> list[dict]:
    """Ask Rust to validate every loaded entry (R1-R4)."""
    authoritative = (
        evidence_hashes if evidence_hashes is not None else _evidence_hashes()
    )
    verdicts = []
    for index, item in enumerate(loaded["entries"]):
        descriptor = item["descriptor"]
        applicability = descriptor.get("applicability", {})
        verdicts.append(
            judge(
                "entry.validate",
                {
                    "id": descriptor["id"],
                    "title": descriptor.get("title", ""),
                    "applicability": {
                        "board_specific": bool(
                            applicability.get("board_specific", False)
                        ),
                        "exact_fact_transfer": applicability.get(
                            "exact_fact_transfer", False
                        ),
                        "required_capabilities": applicability.get(
                            "required_capabilities", []
                        ),
                        **(
                            {
                                "source_dependencies": applicability[
                                    "source_dependencies"
                                ]
                            }
                            if "source_dependencies" in applicability
                            else {}
                        ),
                    },
                    "evidence": descriptor.get("evidence", []),
                    "evidence_hashes": authoritative,
                    "provenance_class": descriptor.get(
                        "provenance_class",
                        descriptor.get("provenance_class_default", ""),
                    )
                    or loaded["catalog"].get("provenance_class_default", ""),
                    "validation_state": descriptor.get("validation_state", ""),
                    "priority": index,
                    "content_sha256": item["content_sha256"],
                },
            )
        )
    return verdicts


def request_selection(
    loaded: dict,
    *,
    task_capabilities: list[str],
    source_identities: dict[str, str] | None = None,
    required_ids: list[str] | None = None,
    allow_empty_baseline: bool = False,
    base_notes_bytes: int = 0,
    base_skills_bytes: int = 0,
) -> dict:
    """Ask Rust for the deterministic selection (R5, KTD7).

    Priority is catalog order. The receipt binds selected IDs to
    byte-verified content hashes; the host never reorders or trims.
    """
    entries = []
    entry_bytes: dict[str, int] = {}
    entry_hashes: dict[str, str] = {}
    for index, item in enumerate(loaded["entries"]):
        descriptor = item["descriptor"]
        applicability = descriptor.get("applicability", {})
        entries.append(
            {
                "id": descriptor["id"],
                "priority": index,
                "state": descriptor.get("validation_state", ""),
                "capabilities": applicability.get("required_capabilities", []),
                "content_hash": item["content_sha256"],
            }
        )
        entry_bytes[descriptor["id"]] = len(item["text"].encode("utf-8"))
        entry_hashes[descriptor["id"]] = item["content_sha256"]
    return judge(
        "selection.select",
        {
            "entries": entries,
            "task_capabilities": task_capabilities,
            "source_identities": source_identities or {},
            "required_ids": required_ids or [],
            "allow_empty_baseline": allow_empty_baseline,
            "entry_bytes": entry_bytes,
            "entry_hashes": entry_hashes,
            "base_notes_bytes": base_notes_bytes,
            "base_skills_bytes": base_skills_bytes,
        },
    )


def review_proposal(
    *,
    proposal_id: str,
    claim_kind: str,
    basis: str,
    evidence_independent: bool,
    helper_test: str,
    source_artifact_match: bool,
) -> dict:
    """Ask Rust for the promotion outcome (KTD4)."""
    return judge(
        "promotion.review",
        {
            "proposal_id": proposal_id,
            "claim_kind": claim_kind,
            "basis": basis,
            "evidence_independent": evidence_independent,
            "helper_test": helper_test,
            "source_artifact_match": source_artifact_match,
        },
    )


def materialize_selection(
    store: artifacts.Store,
    loaded: dict,
    selection: dict,
    *,
    base_skills_source: str,
) -> dict:
    """Materialize a selection as a new Store revision (KTD2/KTD6).

    Notes carry a selection-receipt header plus the selected entry texts;
    skills extend the current base helpers (the U1 seed ships no executable
    helpers, so this is notes-only delivery, recorded as delivered rather
    than executed). The 64-KiB pair cap was already enforced by Rust at
    selection time from these same bytes; exceeding it here is a hard
    failure, never a silent truncation.
    """
    by_id = {item["descriptor"]["id"]: item for item in loaded["entries"]}
    selected_ids: list[str] = selection["selected_ids"]
    header_lines = [
        "# Cross-unit memory selection",
        "",
        f"selection_sha256: {selection['selection_sha256']}",
        f"selected_ids: {', '.join(selected_ids)}",
        "delivery: notes-only (no executable helpers in this seed package)",
        "",
    ]
    notes = "\n".join(header_lines) + "".join(
        f"\n--- {entry_id} ({by_id[entry_id]['path']}, "
        f"sha256:{by_id[entry_id]['content_sha256']}) ---\n"
        f"{by_id[entry_id]['text']}\n"
        for entry_id in selected_ids
    )
    skills = base_skills_source
    pair_bytes = len(notes.encode("utf-8")) + len(skills.encode("utf-8"))
    if pair_bytes > 64 * 1024:
        raise ValueError("materialized notes/skills pair exceeds 64 KiB")
    record = store.base(notes, skills)
    if record["notes_utf8"] != notes or record["skills_utf8"] != skills:
        raise ValueError("materialized revision differs from selected content")
    return record


def publish_receipt(directory: Path, receipt: dict) -> Path:
    """Atomically publish a content-bound selection/delivery receipt (R5)."""
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "memory-selection.json"
    artifacts.write_once(path, receipt)
    path.chmod(0o444)
    return path


def build_receipt(
    *,
    selection: dict,
    loaded: dict,
    revision_sha256: str,
    notes_sha256: str,
    skills_sha256: str,
    attempt_id: str | None = None,
) -> dict:
    """Assemble the delivery receipt (KTD6).

    Records selected IDs, materialized content hashes, the active revision,
    and helper-call provenance (empty here: notes-only applicability is
    reported as delivered, not executed). Never infers that reading notes
    caused a decision.
    """
    by_id = {item["descriptor"]["id"]: item for item in loaded["entries"]}
    return {
        "schema": SCHEMA,
        "selection_sha256": selection["selection_sha256"],
        "selected_ids": selection["selected_ids"],
        "exclusions": selection.get("exclusions", []),
        "entry_content": {
            entry_id: {
                "path": f"harness-lab/memory/entries/{by_id[entry_id]['path']}",
                "content_sha256": by_id[entry_id]["content_sha256"],
            }
            for entry_id in selection["selected_ids"]
        },
        "materialized": {
            "revision_sha256": revision_sha256,
            "notes_sha256": notes_sha256,
            "skills_sha256": skills_sha256,
        },
        "delivery": {
            "attempt_id": attempt_id,
            "acknowledged": False,
            "helper_calls": [],
            "notes": "selected notes delivered to model-visible context; "
            "no helper executed (seed package is notes-only)",
        },
    }


def apply_to_workspace(workspace_obj: Any, record: dict) -> bool:
    """Load a materialized memory revision into a live worker (KTD6).

    Thin adapter over the P1-owned ``Workspace.apply_revision``: the notes
    are supplied initially (and P1 re-supplies them whenever the active
    revision changes); helpers load only inside the existing sandbox. The
    worker compiles the skills source itself, so ``False`` means the helper
    initialization failed and the previous active revision is retained --
    the caller records the rejection and keeps the old revision, never a
    half-loaded one.
    """
    return bool(
        workspace_obj.apply_revision(
            record["revision_sha256"],
            record["skills_utf8"],
            record["notes_utf8"],
        )
    )


def capture_model_input(
    *,
    attempt_id: str,
    selection: dict,
    loaded: dict,
    record: dict,
) -> dict:
    """Assemble the retained model-visible payload (KTD6, scenario 2).

    This is the delivery evidence P1 persists per attempt: the exact notes
    bytes the model sees, bound to the attempt, the selection, and the
    active revision. A worker load acknowledgement alone cannot prove model
    delivery; only this retained capture (checked by
    :func:`model_delivery_proven`) can.
    """
    by_id = {item["descriptor"]["id"]: item for item in loaded["entries"]}
    return {
        "schema": SCHEMA,
        "attempt_id": attempt_id,
        "selection_sha256": selection["selection_sha256"],
        "selected_ids": list(selection["selected_ids"]),
        "revision_sha256": record["revision_sha256"],
        "notes_sha256": record["receipt"]["notes_sha256"],
        "skills_sha256": record["receipt"]["skills_sha256"],
        "model_notes": record["notes_utf8"],
        "entry_content": {
            entry_id: by_id[entry_id]["content_sha256"]
            for entry_id in selection["selected_ids"]
        },
    }


def publish_model_input(directory: Path, capture: dict) -> Path:
    """Atomically publish the retained model-input capture next to the receipt."""
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "model-input.json"
    artifacts.write_once(path, capture)
    path.chmod(0o444)
    return path


def model_delivery_proven(capture: dict, record: dict) -> bool:
    """Check that a retained capture proves delivery of the active revision.

    Requires the capture to carry the record's exact notes bytes and all
    three content bindings. A receipt whose only evidence is
    ``delivery.acknowledged`` (worker load ack) fails this check by
    construction: it carries no model-visible bytes.
    """
    try:
        return (
            capture["revision_sha256"] == record["revision_sha256"]
            and capture["notes_sha256"] == record["receipt"]["notes_sha256"]
            and capture["skills_sha256"] == record["receipt"]["skills_sha256"]
            and capture["model_notes"] == record["notes_utf8"]
            and bool(capture["attempt_id"])
            and bool(capture["selection_sha256"])
        )
    except KeyError:
        return False


def acknowledge_delivery(receipt: dict) -> dict:
    """Record the worker load acknowledgement on a receipt (KTD6).

    Explicitly not model-delivery proof: it records that the sandboxed
    worker accepted the revision, nothing about what the model saw. P1
    calls this from the ``revision_applied`` path; the capture from
    :func:`capture_model_input` remains the delivery evidence.
    """
    receipt["delivery"]["acknowledged"] = True
    return receipt


def record_helper_call(
    receipt: dict,
    *,
    revision_sha256: str,
    helper: str,
    operations: list[str],
    result_ref: str,
) -> dict:
    """Append helper-execution provenance to a receipt (KTD6).

    Loading a helper is not executing it: each invocation records the
    executing revision, the helper name, the admitted operations it nested,
    and a reference to the result. Notes-only applicability keeps an empty
    list, reported as delivered rather than executed.
    """
    if not re.fullmatch("[0-9a-f]{64}", revision_sha256):
        raise ValueError("invalid executing revision identity")
    if not helper or not operations or not result_ref:
        raise ValueError("helper provenance requires a name, operations, and result ref")
    receipt["delivery"]["helper_calls"].append(
        {
            "revision_sha256": revision_sha256,
            "helper": helper,
            "operations": list(operations),
            "result_ref": result_ref,
        }
    )
    return receipt


def inspect_evidence(mounted_root: Path, relpath: str, *, max_bytes: int = 65536) -> bytes:
    """Agent-facing read gate: allowed evidence within the mounted task package.

    Resolves ``relpath`` strictly inside ``mounted_root`` and returns its
    bytes. Absolute paths, parent escapes, backslashes, hidden
    cross-attempt artifacts (``attempt-``/``check-``/``state-`` siblings are
    addressed only through the mounted root, never by absolute tmp path),
    symlinks, and over-limit reads are rejected. This never grants
    repository-wide filesystem access.
    """
    if not isinstance(relpath, str) or not relpath:
        raise ValueError("evidence path is required")
    if relpath.startswith(("/", "\\")) or "\\" in relpath:
        raise ValueError(f"evidence path must be task-relative: {relpath!r}")
    root = mounted_root.resolve()
    # Symlink check on the unresolved join: resolve() follows links, so a
    # resolved path can never report one.
    probe = root
    for part in Path(relpath).parts:
        probe = probe / part
        if probe.is_symlink():
            raise ValueError(f"evidence path must not traverse a symlink: {relpath!r}")
    target = (root / relpath).resolve()
    try:
        target.relative_to(root)
    except ValueError as error:
        raise ValueError(f"evidence path escapes the task package: {relpath!r}") from error
    if not target.is_file():
        raise ValueError(f"evidence is not a readable file: {relpath!r}")
    data = target.read_bytes()
    if len(data) > max_bytes:
        raise ValueError("evidence exceeds the read limit")
    return data


def deliver_selection(
    store: artifacts.Store,
    workspace_obj: Any,
    loaded: dict,
    selection: dict,
    *,
    base_skills_source: str,
    attempt_id: str,
    attempt_dir: Path,
) -> tuple[dict, dict, dict, dict[str, Path]]:
    """P1 entry point: selection -> Store revision -> worker -> retained evidence.

    Materializes the selection through the existing Store, loads it into
    the live worker via :func:`apply_to_workspace` (``False`` raises: the
    previous revision stays active and the rejection is reported, never
    silently kept), then publishes the content-bound receipt and the
    model-input capture. Returns ``(record, receipt, capture, paths)``.
    """
    record = materialize_selection(
        store, loaded, selection, base_skills_source=base_skills_source
    )
    if not apply_to_workspace(workspace_obj, record):
        raise ValueError(
            "worker rejected the memory revision; previous revision retained"
        )
    receipt = build_receipt(
        selection=selection,
        loaded=loaded,
        revision_sha256=record["revision_sha256"],
        notes_sha256=record["receipt"]["notes_sha256"],
        skills_sha256=record["receipt"]["skills_sha256"],
        attempt_id=attempt_id,
    )
    acknowledge_delivery(receipt)
    capture = capture_model_input(
        attempt_id=attempt_id, selection=selection, loaded=loaded, record=record
    )
    paths = {
        "receipt": publish_receipt(attempt_dir, receipt),
        "model_input": publish_model_input(attempt_dir, capture),
    }
    return record, receipt, capture, paths


def p1_interface() -> dict:
    """Interface contract for P1's runner/dispatcher integration (U3).

    P2 supplies this; P1 exclusively owns the shared runtime files. The
    dispatcher commands below are served today by the standalone
    ``memory_judge`` bridge and move into the main judge when P1 registers
    ``mod memory`` with schema ``memory/v1``.

    Runtime entry point for P1: :func:`deliver_selection` chains
    materialize -> apply -> receipt -> model-input capture. The worker
    acknowledgement (:func:`acknowledge_delivery`) alone never proves model
    delivery; only a retained capture passing :func:`model_delivery_proven`
    does.
    """
    return {
        "schema": SCHEMA,
        "dispatcher_commands": [
            "memory.entry.validate",
            "memory.selection.select",
            "memory.promotion.review",
        ],
        "task_context": {
            "task_capabilities": "list[str]: capabilities the construction task offers; "
            "selection matches required capabilities exactly (no semantic search)",
            "source_identities": "dict[str, sha256]: current compiled-artifact hashes; "
            "exact-fact transfer requires a match (R3)",
            "required_ids": "list[str]: entries the milestone requires; "
            "a required entry that is excluded fails the selection",
            "allow_empty_baseline": "bool: only an explicitly requested baseline may select nothing",
        },
        "hooks": {
            "before_construction": "load_catalog -> validate_loaded -> request_selection -> "
            "materialize_selection -> publish_receipt, before the first construction call",
            "on_revision_change": "supply current notes initially and whenever the active "
            "revision changes; helpers load only inside the existing sandbox",
            "helper_provenance": "record every helper call (revision, operation, result ref) "
            "separately from merely loading it; never infer causation from delivery",
        },
        "entry_point": "deliver_selection(store, workspace_obj, loaded, "
        "selection, base_skills_source=..., attempt_id=..., attempt_dir=...): "
        "P1 calls this before the first construction call and whenever the "
        "active revision changes; it returns (record, receipt, capture, paths)",
        "model_input_artifact": "model-input.json, retained next to "
        "memory-selection.json and bound to attempt_id + selection_sha256 + "
        "revision_sha256; live MCU attempts must retain the actual payload, "
        "a control may retain this exact shape (P1 U4 owns live evidence)",
        "agent_inspection": "inspect_evidence(mounted_root, relpath): read-only, "
        "resolves inside the mounted task package only; absolute paths, "
        "parent escapes, symlinks, and cross-attempt hidden artifacts are "
        "rejected (no repository-wide filesystem access)",
        "forbidden": [
            "editing workspace.py, workspace_worker.py, test_workspace.py, run_block.py, "
            "src/main.rs, or shared observation/receipt wiring from P2",
            "granting the agent repository-wide filesystem access: agent-facing inspection "
            "returns allowed evidence within the mounted task package only",
            "changing the active skills revision in the middle of a native operation",
            "manufacturing a historical continual-learning receipt from a cross-unit selection",
        ],
    }


__all__ = [
    "SCHEMA",
    "MEMORY_DIR",
    "default_judge",
    "judge",
    "load_catalog",
    "validate_loaded",
    "request_selection",
    "review_proposal",
    "materialize_selection",
    "publish_receipt",
    "build_receipt",
    "apply_to_workspace",
    "capture_model_input",
    "publish_model_input",
    "model_delivery_proven",
    "acknowledge_delivery",
    "record_helper_call",
    "inspect_evidence",
    "deliver_selection",
    "p1_interface",
]
