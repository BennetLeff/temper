"""Dead-letter quarantine for pipeline failures with structured taxonomy.

Every board error (parse, stage, invariant) is routed to a quarantine
directory with structured metadata.  Failures are auto-clustered by
similarity (exception class + stack hash + board fingerprint) so
untested edge cases are surfaced systematically rather than buried in
CI logs.

Taxonomy classes (TAXONOMY):
    - PARSE_KICAD_VERSION_MISMATCH
    - PARSE_UNSUPPORTED_SYNTAX
    - PARSE_MISSING_FOOTPRINT_LIB
    - PARSE_DECODE_ERROR
    - PARSE_EMPTY_BOARD
    - PARSE_UNKNOWN
    - STAGE_PREFLIGHT_FAILED
    - STAGE_GEOMETRIC_DIVERGED
    - STAGE_ROUTING_FAILED
    - STAGE_OUTPUT_FAILED
    - INVARIANT_BROKEN
    - UNKNOWN
"""

from __future__ import annotations

import hashlib
import json
import traceback
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


TAXONOMY_CLASSES: dict[str, str] = {
    "PARSE_KICAD_VERSION_MISMATCH": "KiCad version not supported by parser",
    "PARSE_UNSUPPORTED_SYNTAX": "S-expression construct not handled",
    "PARSE_MISSING_FOOTPRINT_LIB": "Footprint library not found",
    "PARSE_DECODE_ERROR": "UTF-8 or binary decode failure",
    "PARSE_EMPTY_BOARD": "Board has zero components or zero nets",
    "PARSE_UNKNOWN": "Parser failed with unrecognized error pattern",
    "STAGE_PREFLIGHT_FAILED": "Preflight checks rejected the board",
    "STAGE_GEOMETRIC_DIVERGED": "JAX optimizer failed to converge",
    "STAGE_ROUTING_FAILED": "Router could not complete routing",
    "STAGE_OUTPUT_FAILED": "Output serialization failed",
    "INVARIANT_BROKEN": "Cross-stage or per-stage invariant violated",
    "UNKNOWN": "Unclassified failure",
}


@dataclass
class QuarantineEntry:
    board_id: str
    board_path: str
    stage: str
    error_class: str
    error_message: str
    stack_hash: str
    fingerprint: dict[str, Any] = field(default_factory=dict)
    taxonomy: str = "UNKNOWN"
    taxonomy_label: str = ""
    timestamp: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    git_commit: str = ""

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["taxonomy_label"] = TAXONOMY_CLASSES.get(self.taxonomy, "")
        return d

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2)


def classify_error(
    stage: str,
    error: Exception,
) -> str:
    msg = str(error)
    cls_name = type(error).__name__

    if stage == "parse":
        if "version" in msg.lower() or "format_version" in msg.lower():
            return "PARSE_KICAD_VERSION_MISMATCH"
        if "footprint" in msg.lower() or "lib" in msg.lower():
            return "PARSE_MISSING_FOOTPRINT_LIB"
        if "decode" in msg.lower() or "utf" in msg.lower() or "encoding" in msg.lower():
            return "PARSE_DECODE_ERROR"
        if "zero" in msg.lower() and ("component" in msg.lower() or "net" in msg.lower()):
            return "PARSE_EMPTY_BOARD"
        if cls_name in ("SyntaxError", "ValueError", "KeyError"):
            return "PARSE_UNSUPPORTED_SYNTAX"
        return "PARSE_UNKNOWN"

    if stage == "preflight":
        return "STAGE_PREFLIGHT_FAILED"
    if stage == "geometric":
        return "STAGE_GEOMETRIC_DIVERGED"
    if stage == "routing":
        return "STAGE_ROUTING_FAILED"
    if stage == "output":
        return "STAGE_OUTPUT_FAILED"

    return "UNKNOWN"


def compute_stack_hash(exc: Exception) -> str:
    tb = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
    return hashlib.sha256(tb.encode()).hexdigest()[:12]


def compute_fingerprint(board_path: Path) -> dict[str, Any]:
    fp: dict[str, Any] = {"path": str(board_path), "exists": board_path.exists()}
    if board_path.exists():
        fp["size_bytes"] = board_path.stat().st_size
        try:
            content = board_path.read_text(encoding="utf-8", errors="replace")
            fp["lines"] = content.count("\n") + 1
            fp["has_kicad_header"] = "(kicad_pcb" in content.lower()[:200]
        except Exception:
            fp["readable"] = False
    return fp


def quarantine_error(
    quarantine_dir: Path,
    board_id: str,
    board_path: Path,
    stage: str,
    error: Exception,
    *,
    git_commit: str = "",
) -> QuarantineEntry:
    taxonomy = classify_error(stage, error)
    entry = QuarantineEntry(
        board_id=board_id,
        board_path=str(board_path),
        stage=stage,
        error_class=type(error).__name__,
        error_message=str(error),
        stack_hash=compute_stack_hash(error),
        fingerprint=compute_fingerprint(board_path),
        taxonomy=taxonomy,
        git_commit=git_commit,
    )

    date_dir = quarantine_dir / datetime.now(UTC).strftime("%Y-%m-%d")
    date_dir.mkdir(parents=True, exist_ok=True)

    safe_name = board_id.replace("/", "_").replace(" ", "_")
    entry_path = date_dir / f"{safe_name}_{stage}_{entry.stack_hash}.json"
    entry_path.write_text(entry.to_json())

    _update_manifest(quarantine_dir, entry)

    return entry


def _update_manifest(quarantine_dir: Path, entry: QuarantineEntry) -> None:
    manifest_path = quarantine_dir / "manifest.json"
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text())
    else:
        manifest = {"entries": [], "taxonomy_counts": {}}

    manifest["entries"].append(entry.to_dict())
    manifest["taxonomy_counts"][entry.taxonomy] = (
        manifest["taxonomy_counts"].get(entry.taxonomy, 0) + 1
    )
    manifest["last_updated"] = datetime.now(UTC).isoformat()

    manifest_path.write_text(json.dumps(manifest, indent=2))


def load_manifest(quarantine_dir: Path) -> dict[str, Any]:
    manifest_path = quarantine_dir / "manifest.json"
    if manifest_path.exists():
        return json.loads(manifest_path.read_text())
    return {"entries": [], "taxonomy_counts": {}}


def quarantine_summary(quarantine_dir: Path) -> str:
    manifest = load_manifest(quarantine_dir)
    total = len(manifest.get("entries", []))
    counts = manifest.get("taxonomy_counts", {})
    lines = [f"Quarantine: {total} total entries"]
    for tax, count in sorted(counts.items(), key=lambda x: -x[1]):
        label = TAXONOMY_CLASSES.get(tax, tax)
        lines.append(f"  {tax}: {count} ({label})")
    return "\n".join(lines)
