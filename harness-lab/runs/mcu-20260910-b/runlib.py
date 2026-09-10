"""P1 U4 shared helpers: run identity, memory freeze/delivery, briefs.

Run-local apparatus (not a harness capability). Owns the exact identities the
selection is frozen against and the P2 delivery chain
(:func:`memory.deliver_selection`). Both the live transport driver and the
scripted fallback import this so the selection, store, and delivery proof are
identical regardless of which attempt path executes.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

RUN = Path(__file__).resolve().parent
REPO = RUN.parents[2]
HARNESS = REPO / "harness-lab"

import sys  # noqa: E402

sys.path.insert(0, str(HARNESS))

import memory  # noqa: E402
import run_block  # noqa: E402
from artifacts import Store  # noqa: E402

MODEL = "muse-spark-1.3-contributor-free"
FULL_MODEL = "opencode/" + MODEL
CANDIDATE = RUN / "candidate"
TARGET_CONTEXT = REPO / "pcb" / "blocks" / "control-assembly" / "target-context.json"
BASE_SKILLS = HARNESS / "skills" / "base" / "skills.py"

# The five curated buck lessons this selection is required to carry (P2 U1).
REQUIRED_MEMORY_IDS = [
    "buck-mem-001",
    "buck-mem-002",
    "buck-mem-003",
    "buck-mem-004",
    "buck-mem-005",
]

SOURCE_IDENTITY_FILES = {
    "p3.target-context.json": TARGET_CONTEXT,
    "harness-lab.blocks.mcu.identity-inventory.json": HARNESS
    / "blocks"
    / "mcu"
    / "identity-inventory.json",
    "harness-lab.blocks.mcu.mcu.ato": HARNESS / "blocks" / "mcu" / "mcu.ato",
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def source_identities(candidate: Path | None = None) -> dict[str, str]:
    """Current compiled-artifact / context hashes the freeze is bound to."""
    candidate = Path(candidate or CANDIDATE)
    manifest = candidate / "source-manifest.json"
    identities = {
        "mcu.source-manifest.json": sha256(manifest),
        "mcu.default.net": sha256(candidate / "build-evidence" / "default.net"),
        "mcu.candidate.kicad_pcb": sha256(next(candidate.glob("*.kicad_pcb"))),
    }
    for key, path in SOURCE_IDENTITY_FILES.items():
        if path.is_file():
            identities[key] = sha256(path)
    return identities


def freeze_selection(store_root: Path, candidate: Path | None = None) -> dict:
    """Load the catalog, validate every entry, and ask Rust for the selection.

    No delivery yet; this is the content-bound selection receipt source.
    """
    candidate = Path(candidate or CANDIDATE)
    loaded = memory.load_catalog()
    verdicts = memory.validate_loaded(loaded)
    identities = source_identities(candidate)
    selection = memory.request_selection(
        loaded,
        task_capabilities=run_block.MCU_CAPABILITIES,
        source_identities=identities,
        required_ids=REQUIRED_MEMORY_IDS,
    )
    return {
        "loaded": loaded,
        "verdicts": verdicts,
        "selection": selection,
        "source_identities": identities,
    }


def deliver(
    frozen: dict,
    worker: object,
    *,
    attempt_id: str,
    attempt_dir: Path,
    store_root: Path,
) -> dict:
    """Materialize through Store and deliver into the live worker; prove it.

    Returns the full chain plus the delivery-proof verdict. Raises if the
    selected IDs are not exactly the required applicable set or if
    ``model_delivery_proven`` is false.
    """
    selected = list(frozen["selection"]["selected_ids"])
    rejected = [
        verdict
        for verdict in frozen["verdicts"]
        if verdict.get("status") not in ("pass", "valid")
    ]
    if rejected:
        raise RuntimeError(f"memory entries failed validation: {rejected}")
    missing = [i for i in REQUIRED_MEMORY_IDS if i not in selected]
    if missing:
        raise RuntimeError(f"selection omitted required memory: {missing}")
    store = Store(Path(store_root))
    record, receipt, capture, paths = memory.deliver_selection(
        store,
        worker,
        frozen["loaded"],
        frozen["selection"],
        base_skills_source=BASE_SKILLS.read_text(encoding="utf-8"),
        attempt_id=attempt_id,
        attempt_dir=Path(attempt_dir),
    )
    proven = memory.model_delivery_proven(capture, record)
    if not proven:
        raise RuntimeError("model_delivery_proven is false")
    return {
        "selection": frozen["selection"],
        "source_identities": frozen["source_identities"],
        "verdicts": frozen["verdicts"],
        "record": record,
        "receipt": receipt,
        "capture": capture,
        "paths": {name: str(path) for name, path in paths.items()},
        "model_delivery_proven": proven,
    }


def compact_delivery_report(delivery: dict) -> dict:
    """Small, committable summary of the freeze/delivery (full JSON stays on disk)."""
    selection = delivery["selection"]
    record = delivery["record"]
    return {
        "schema": "temper.mcu-memory-delivery.v1",
        "attempt_id": delivery["capture"]["attempt_id"],
        "selection_sha256": selection["selection_sha256"],
        "selected_ids": list(selection["selected_ids"]),
        "exclusions": selection.get("exclusions", []),
        "source_identities": delivery["source_identities"],
        "entry_content": delivery["capture"]["entry_content"],
        "materialized": {
            "revision_sha256": record["revision_sha256"],
            "notes_sha256": record["receipt"]["notes_sha256"],
            "skills_sha256": record["receipt"]["skills_sha256"],
        },
        "delivery": delivery["receipt"]["delivery"],
        "model_delivery_proven": delivery["model_delivery_proven"],
        "receipt_path": delivery["paths"]["receipt"],
        "model_input_path": delivery["paths"]["model_input"],
    }


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
