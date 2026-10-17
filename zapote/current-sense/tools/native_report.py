"""Fail-closed validation for KiCad JSON reports used by current-sense tools."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

_SCHEMAS = {
    "erc": "https://schemas.kicad.org/erc.v1.json",
    "drc": "https://schemas.kicad.org/drc.v1.json",
}


def require_success(kind: str, returncode: int, stdout: str = "", stderr: str = "") -> None:
    """Reject a native command failure before its report can be consumed."""
    if returncode != 0:
        raise RuntimeError(
            f"KiCad {kind} command failed with returncode={returncode}; "
            f"stdout={stdout[-400:]!r} stderr={stderr[-400:]!r}"
        )


def load_kicad_report(path: Path, kind: str) -> dict[str, Any]:
    """Load and minimally validate a real KiCad ERC/DRC report envelope.

    KiCad can leave no report, or a caller can accidentally point at an
    arbitrary JSON file.  Both must fail before a zero-count result is used.
    The report's finding arrays are deliberately validated as lists while
    preserving all other KiCad fields unchanged for review.
    """
    if kind not in _SCHEMAS:
        raise ValueError(f"unsupported KiCad report kind: {kind!r}")
    if not path.is_file():
        raise RuntimeError(f"KiCad produced no {kind} report: {path}")
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"invalid KiCad {kind} report {path}: {exc}") from exc
    if not isinstance(raw, dict):
        raise ValueError(f"KiCad {kind} report must be a JSON object")
    if raw.get("$schema") != _SCHEMAS[kind]:
        raise ValueError(
            f"KiCad {kind} report has unexpected $schema: {raw.get('$schema')!r}"
        )

    if kind == "erc":
        sheets = raw.get("sheets")
        if not isinstance(sheets, list):
            raise ValueError("KiCad ERC report must contain a sheets list")
        for index, sheet in enumerate(sheets):
            if not isinstance(sheet, dict) or not isinstance(sheet.get("violations"), list):
                raise ValueError(
                    f"KiCad ERC report sheet {index} must contain a violations list"
                )
    else:
        for field in ("violations", "unconnected_items", "schematic_parity"):
            if not isinstance(raw.get(field), list):
                raise ValueError(f"KiCad DRC report must contain a {field} list")
    return raw
