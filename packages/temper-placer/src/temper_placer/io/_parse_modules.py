"""Internal: footprint/module parsing, pad extraction, and bounds calculation.

Migrated to the Rust parse engine (``temper_design_bundle_python.parse_engine``,
Wave 4 Phase 3 candidate 3) — ``_extract_components_from_pcb``,
``_extract_pads_from_pcb`` and ``_calculate_footprint_bounds`` now run inside
``parse_kicad_pcb`` on the Rust side.

One function deliberately stays Python (R3-style boundary, argued in
VERIFICATION.md): ``_get_footprint_reference`` is a kiutils-free attribute
reader retained for the Phase-4 consumer ``validation/placement_roundtrip.py``,
which still re-parses written boards with kiutils (its own surface migrates in
Phase 4; the helper retires then).
"""

from __future__ import annotations

from typing import Any


# fp is a payload object from extract_footprint_info_py (Rust, dynamically
# shaped): duck-typed here, hence Any rather than object.
def _get_footprint_reference(fp: Any) -> str | None:
    """
    Extract reference designator from a footprint item.

    Reads attributes generically (no kiutils import), so it also works on the
    raw parsed board objects from ``parse_engine``. Retained in Python for
    ``validation/placement_roundtrip.py`` (Phase-4 surface, still kiutils-based);
    the migrated engine uses the identical Rust port internally.

    Args:
        fp: kiutils ``Footprint``-shaped item (duck-typed).

    Returns:
        Reference string (e.g., "U1") or None.
    """
    if hasattr(fp, "properties"):
        props = fp.properties
        if isinstance(props, dict):
            if "Reference" in props:
                return props["Reference"]
        elif isinstance(props, list):
            for p in props:
                if getattr(p, "name", "") == "Reference":
                    return getattr(p, "value", None)

    if fp.graphicItems:
        for item in fp.graphicItems:
            if hasattr(item, "text") and getattr(item, "layer", "") in [
                "F.SilkS",
                "B.SilkS",
                "F.Fab",
                "B.Fab",
            ]:
                ref_candidate = item.text.strip()
                if ref_candidate and not ref_candidate.startswith("REF**"):
                    return ref_candidate

    for item in fp.graphicItems:
        if hasattr(item, "text") and getattr(item, "layer", "") in [
            "F.SilkS",
            "B.SilkS",
            "F.Fab",
            "B.Fab",
        ]:
            ref_candidate = item.text.strip()
            if ref_candidate and not ref_candidate.startswith("REF**"):
                return ref_candidate

    ename = getattr(fp, "entryName", None)
    if ename and not ename.startswith("REF**") and ":" not in ename and len(ename) < 10:
        return ename

    return None
