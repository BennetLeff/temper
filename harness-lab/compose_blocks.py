"""P3 U2 preparation: source-derived block composition host (pre-MCU).

Thin native composition data-plane for the buck/MCU control assembly.
Composes the functional buck nine (U3/L2/C9-C13/R16/R17) from
source-derived geometry and stages the MCU side behind an explicit input
contract (``pcb/blocks/control-assembly/mcu-input-contract.json``) until
P1 U4 delivers the accepted package. No geometry is drawn here; this
module maps identities, layers, vias, ledger removals, and owned-region
membership, and scaffolds the assembly/overlay cross-view comparison.

Discipline (plan KTD4/KTD7):
- Source-path keyed mapping: canonical identity is the Atopile instance
  path (``buck.*`` / ``mcu.*`` from the P1 combined wrapper), never the
  refdes. Refdes and numeric net-code changes preserve connections.
- No independent rotation or net policy: transforms delegate to the
  native Rust kernel (``temper_geometry``); pin/net admission reuses the
  ``temper-design-bundle`` Rust gates. This module contains no trig.
- Prototype-only objects (J1/J2/TPs/Hs and their stubs) are excluded by
  the combined source inventory, never silently imported.
- Unsupported layers are rejected, never dropped. Through vias span the
  target outer copper exactly. Changes outside the owned envelopes fail
  before publication.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

LAB = Path(__file__).resolve().parent
REPO = LAB.parent

# Functional buck nine: source-derived, prototype fixtures excluded.
# (Mirrors build_buck.FUNCTIONAL_REFS; imported lazily to avoid a hard
# dependency at module import time.)
BUCK_FUNCTIONAL_REFS = (
    "U3",
    "L2",
    "C9",
    "C10",
    "C11",
    "C12",
    "C13",
    "R16",
    "R17",
)

# Prototype-only refs: fixture terminals, test pads, mounting holes.
# Never become product components (target-context reconciled
# contradiction #3). J3 is a harness-fixture terminal, not a prototype
# board object; it is likewise never imported into the product assembly.
PROTOTYPE_ONLY_REFS = frozenset(
    {"J1", "J2", "J3", "TP1", "TP2", "TP3", "TP4", "H1", "H2", "H3", "H4"}
)

# Functional MCU ten per harness-lab/blocks/mcu/identity-inventory.json.
MCU_FUNCTIONAL_REFS = (
    "U1",
    "C1",
    "C2",
    "C3",
    "R1",
    "R2",
    "R3",
    "R4",
    "SW1",
    "SW2",
)

# Source-path prefixes from the P1 combined wrapper
# (harness-lab/blocks/control-assembly/control-assembly.ato):
# ``buck = new BuckConverter3V3`` and ``mcu = new MCU``.
BUCK_PATH_PREFIX = "buck."
MCU_PATH_PREFIX = "mcu."

# Canonical functional identity is the combined-wrapper instance path. The
# combined assembly renumbers refdes (prototype U3/C9 -> combined U1/C1, MCU
# U1/C1 -> combined U2/C6), so the functional census must be checked by path,
# not by the prototype refdes (KTD4, plan U2 scenario 2).
BUCK_FUNCTIONAL_PATHS = (
    "buck.buck",
    "buck.l_out",
    "buck.c_in",
    "buck.c_boot",
    "buck.c_out1",
    "buck.c_out2",
    "buck.c_out_hf",
    "buck.r_fb_top",
    "buck.r_fb_bot",
)
MCU_FUNCTIONAL_PATHS = (
    "mcu.mcu",
    "mcu.c_vcc1",
    "mcu.c_vcc2",
    "mcu.c_en",
    "mcu.r_en",
    "mcu.r_boot",
    "mcu.r_sda_pullup",
    "mcu.r_scl_pullup",
    "mcu.btn_reset",
    "mcu.btn_boot",
)

# Target outer copper: the six-layer P3 stackup's outer pair. Prototype
# F.Cu/B.Cu maps onto these; inner layers are never a silent target.
TARGET_OUTER_PAIR = ("F.Cu", "B.Cu")
VIA_SPAN = "F.Cu-B.Cu"
VIA_DIAMETER_MM = 0.8
VIA_DRILL_MM = 0.4


class CompositionError(Exception):
    """A composition admission failure naming the responsible input."""


def _design_bundle():
    import temper_design_bundle_python as bundle

    return bundle


def _geometry():
    import temper_geometry as geometry

    return geometry


# ---------------------------------------------------------------------------
# Transforms: native Rust kernel only. No local trig, ever.
# ---------------------------------------------------------------------------


def rotate_local_to_world(dx_mm: float, dy_mm: float, angle_rad: float) -> tuple:
    """KiCad R(-theta) child rotation via the native Rust kernel."""
    geometry = _geometry()
    x, y = geometry.kicad_rotate_local_to_world_py(dx_mm, dy_mm, angle_rad)
    return (float(x), float(y))


def place_local_to_world(
    dx_mm: float,
    dy_mm: float,
    origin_x_mm: float,
    origin_y_mm: float,
    angle_rad: float,
) -> tuple:
    """Rotate-then-translate placement via the native Rust kernel."""
    geometry = _geometry()
    x, y = geometry.kicad_place_local_to_world_py(
        dx_mm, dy_mm, origin_x_mm, origin_y_mm, angle_rad
    )
    return (float(x), float(y))


# ---------------------------------------------------------------------------
# Layer mapping: prototype outer copper -> target outer copper.
# ---------------------------------------------------------------------------


def map_proto_layer(proto_layer: str, physical_copper_order: list) -> str:
    """Map a prototype copper layer onto the target stackup.

    Only the prototype outer pair (F.Cu/B.Cu) is mappable, onto the
    target outer pair of the same name. Anything else (inner layers,
    unknown names) raises instead of being dropped.
    """
    if proto_layer not in TARGET_OUTER_PAIR:
        raise CompositionError(
            f"unsupported prototype layer {proto_layer!r}: only {list(TARGET_OUTER_PAIR)} "
            f"map onto the target; rejected, not dropped"
        )
    if proto_layer not in physical_copper_order:
        raise CompositionError(
            f"target stackup has no {proto_layer!r}: order={physical_copper_order}"
        )
    return proto_layer


def recreate_through_via(position_mm: list, diameter_mm: float, drill_mm: float) -> dict:
    """Recreate one prototype via with the explicit target span contract."""
    if not math.isclose(diameter_mm, VIA_DIAMETER_MM) or not math.isclose(
        drill_mm, VIA_DRILL_MM
    ):
        raise CompositionError(
            f"via dims {diameter_mm}/{drill_mm}mm diverge from the admitted "
            f"{VIA_DIAMETER_MM}/{VIA_DRILL_MM}mm; review required, not silent adoption"
        )
    return {
        "position_mm": [float(position_mm[0]), float(position_mm[1])],
        "span": VIA_SPAN,
        "diameter_mm": VIA_DIAMETER_MM,
        "drill_mm": VIA_DRILL_MM,
    }


# ---------------------------------------------------------------------------
# Source-path keyed component mapping.
# ---------------------------------------------------------------------------


def _check_prototype_exclusion(reference: str) -> None:
    if reference in PROTOTYPE_ONLY_REFS:
        raise CompositionError(
            f"prototype-only {reference} must not become a product component "
            f"(excluded by the combined source inventory)"
        )


def build_source_map(
    bridge_components: list,
    expected_buck_refs: tuple = BUCK_FUNCTIONAL_REFS,
    expected_mcu_refs: tuple = MCU_FUNCTIONAL_REFS,
    require_mcu: bool = False,
    expected_buck_paths: tuple | None = None,
    expected_mcu_paths: tuple | None = None,
) -> dict:
    """Key bridge components by canonical instance path.

    ``bridge_components`` are P1 combined-wrapper entries
    (reference/instance_path/footprint). Returns instance_path ->
    {reference, footprint, block}. Fails closed on prototype-only refs,
    duplicate instance paths, missing functional instances, or a wrong
    block prefix. Refdes renumbering is preserved: the key is the
    instance path, never the refdes.

    ``require_mcu=False`` is the pre-U4 staging mode: the buck nine must
    be complete while the MCU side may be absent. Post-U4 composition
    passes ``require_mcu=True``.

    When ``expected_buck_paths`` / ``expected_mcu_paths`` are given the
    functional census is checked by canonical source path instead of refdes,
    which is required for the combined assembly where both blocks are
    renumbered together (U2 scenario 2).
    """
    mapping: dict = {}
    for comp in bridge_components:
        ref = comp["reference"]
        path = comp["instance_path"]
        _check_prototype_exclusion(ref)
        if path in mapping:
            raise CompositionError(f"duplicate instance path {path!r}")
        if path.startswith(BUCK_PATH_PREFIX):
            block = "buck"
        elif path.startswith(MCU_PATH_PREFIX):
            block = "mcu"
        else:
            raise CompositionError(
                f"component {ref} instance path {path!r} is in neither "
                f"block namespace ({BUCK_PATH_PREFIX!r}, {MCU_PATH_PREFIX!r})"
            )
        mapping[path] = {
            "reference": ref,
            "footprint": comp["footprint"],
            "block": block,
        }

    by_block: dict = {"buck": {}, "mcu": {}}
    for path, entry in mapping.items():
        by_block[entry["block"]][entry["reference"]] = path

    if expected_buck_paths is not None:
        missing_buck_paths = [p for p in expected_buck_paths if p not in mapping]
        if missing_buck_paths:
            raise CompositionError(
                f"functional buck source paths missing from the combined map: "
                f"{missing_buck_paths}"
            )
        extra_buck_paths = [
            p
            for p, entry in mapping.items()
            if entry["block"] == "buck" and p not in expected_buck_paths
        ]
        if extra_buck_paths:
            raise CompositionError(
                f"unexpected buck source paths beyond the functional nine: "
                f"{extra_buck_paths}"
            )
    else:
        missing_buck = [r for r in expected_buck_refs if r not in by_block["buck"]]
        if missing_buck:
            raise CompositionError(
                f"functional buck instances missing from the source map: {missing_buck}"
            )
        extra_buck = [r for r in by_block["buck"] if r not in expected_buck_refs]
        if extra_buck:
            raise CompositionError(
                f"unexpected buck instances beyond the functional nine: {extra_buck}"
            )

    mcu_refs = by_block["mcu"]
    if require_mcu or mcu_refs:
        if expected_mcu_paths is not None:
            missing_mcu_paths = [p for p in expected_mcu_paths if p not in mapping]
            if missing_mcu_paths:
                raise CompositionError(
                    f"functional MCU source paths missing from the combined map: "
                    f"{missing_mcu_paths}"
                )
            extra_mcu_paths = [
                p
                for p, entry in mapping.items()
                if entry["block"] == "mcu" and p not in expected_mcu_paths
            ]
            if extra_mcu_paths:
                raise CompositionError(
                    f"unexpected MCU source paths beyond the functional ten: "
                    f"{extra_mcu_paths}"
                )
        else:
            missing_mcu = [r for r in expected_mcu_refs if r not in mcu_refs]
            if missing_mcu:
                raise CompositionError(
                    f"functional MCU instances missing from the source map: {missing_mcu}"
                )
            extra_mcu = [r for r in mcu_refs if r not in expected_mcu_refs]
            if extra_mcu:
                raise CompositionError(
                    f"unexpected MCU instances beyond the functional ten: {extra_mcu}"
                )
    return mapping


def validate_pin_map_native(
    entries: list, pads_by_ref: dict, pins_by_ref: dict, unconnected: list
) -> None:
    """Admit an exact pin==pad map through the Rust identity gate.

    Wraps ``temper-design-bundle``'s ``candidate_validate_pin_map``:
    duplicates, missing maps, positional fallbacks, and split pads fail
    in Rust, not in a local reimplementation.
    """
    bundle = _design_bundle()
    bundle.candidate_validate_pin_map(
        json.dumps(entries, sort_keys=True),
        json.dumps(pads_by_ref, sort_keys=True),
        json.dumps(pins_by_ref, sort_keys=True),
        json.dumps(unconnected, sort_keys=True),
    )


def validate_net_admission(nets: list, board_nets: list) -> None:
    """Admit the net list through the Rust gate (empty nets rejected)."""
    bundle = _design_bundle()
    bundle.validation.candidate_check_net_admission(
        json.dumps(nets, sort_keys=True),
        json.dumps(board_nets, sort_keys=True),
    )


# ---------------------------------------------------------------------------
# Prototype-only exclusion + orphan stub stripping.
# ---------------------------------------------------------------------------


def partition_prototype_objects(references: list) -> tuple:
    """Split refs into (functional, prototype_only). Prototype set is exact."""
    functional = [r for r in references if r not in PROTOTYPE_ONLY_REFS]
    excluded = [r for r in references if r in PROTOTYPE_ONLY_REFS]
    return (functional, excluded)


def strip_orphan_stubs(tracks: list, excluded_refs: set, pad_owner: dict) -> tuple:
    """Remove copper serving excluded objects; report orphans left behind.

    ``tracks`` are {uuid, pads touched, ...}; ``pad_owner`` maps pad
    "REF.num" -> owning ref. Returns (kept, removed). Any track that
    touches BOTH an excluded and a functional pad is not a silent strip:
    it raises as a shared-copper review item.
    """
    kept: list = []
    removed: list = []
    for track in tracks:
        owners = {pad_owner.get(pad) for pad in track.get("pads", [])}
        owners.discard(None)
        if not owners:
            raise CompositionError(
                f"track {track.get('uuid')} touches no owned pad: orphan stub, rejected"
            )
        if owners <= excluded_refs:
            removed.append(track)
        elif owners & excluded_refs:
            raise CompositionError(
                f"track {track.get('uuid')} joins excluded {sorted(owners & excluded_refs)} "
                f"to functional {sorted(owners - excluded_refs)}: shared copper needs review"
            )
        else:
            kept.append(track)
    return (kept, removed)


# ---------------------------------------------------------------------------
# U1 replacement ledger application.
# ---------------------------------------------------------------------------


def apply_replacement_ledger(baseline_identities: dict, ledger_remove: list) -> list:
    """Verify-then-remove: every ledger entry must exist in the baseline.

    ``baseline_identities`` maps ref -> identity dict (tstamp, ...).
    Returns removal records retaining before/after identities
    (after = None: object deleted, replacement geometry arrives via the
    source map). Unknown refs, duplicate ledger entries, and duplicate
    functional instances fail.
    """
    seen: set = set()
    records: list = []
    for entry in ledger_remove:
        ref = entry["ref"]
        if ref in seen:
            raise CompositionError(f"duplicate ledger removal for {ref!r}")
        seen.add(ref)
        before = baseline_identities.get(ref)
        if before is None:
            raise CompositionError(
                f"ledger removes {ref!r} which does not exist in the baseline"
            )
        records.append(
            {
                "ref": ref,
                "before": dict(before),
                "after": None,
                "reason": entry.get("reason", ""),
            }
        )
    return records


def check_owned_region(
    x_mm: float, y_mm: float, owned_envelopes: list, ref: str = ""
) -> dict:
    """Guard: a coordinate must lie inside one owned envelope."""
    for envelope in owned_envelopes:
        if envelope["x1"] <= x_mm <= envelope["x2"] and envelope["y1"] <= y_mm <= envelope["y2"]:
            return envelope
    raise CompositionError(
        f"point ({x_mm}, {y_mm}) for {ref!r} lies outside every owned envelope: "
        f"unexpected change outside the owned region fails before publication"
    )


# ---------------------------------------------------------------------------
# Cross-view comparison scaffolding (assembly vs scratch overlay).
# ---------------------------------------------------------------------------

COMPARE_CATEGORIES = ("pads", "tracks", "vias", "zones", "endpoints")


def canonicalize_extract(extract: dict) -> dict:
    """Reduce a view extract to canonical comparable form.

    Expects {pads: {pad_key: {net, x_mm, y_mm}}, tracks/vias/zones:
    [{uuid, ...}], endpoints: {name: {...}}}. Sorted keys, rounded
    coordinates (1nm grid), net-identity preserving.
    """
    canonical: dict = {"pads": {}, "tracks": [], "vias": [], "zones": [], "endpoints": {}}
    for key in sorted(extract.get("pads", {})):
        pad = extract["pads"][key]
        canonical["pads"][key] = {
            "net": pad["net"],
            "x_mm": round(float(pad["x_mm"]), 6),
            "y_mm": round(float(pad["y_mm"]), 6),
        }
    for kind in ("tracks", "vias", "zones"):
        canonical[kind] = sorted(
            json.dumps(item, sort_keys=True) for item in extract.get(kind, [])
        )
    for key in sorted(extract.get("endpoints", {})):
        canonical["endpoints"][key] = json.loads(
            json.dumps(extract["endpoints"][key], sort_keys=True)
        )
    return canonical


def compare_views(assembly: dict, overlay: dict) -> list:
    """Diff canonical extracts; return mismatches (empty == agreement).

    Each mismatch is {category, key, assembly, overlay}. A pad, track,
    via, filled zone, or endpoint present or differing in only one view
    fails the comparison. Intentionally context-dependent zone fills are
    NOT silently excused here: they must be listed as mismatches and
    dispositioned with connectivity evidence in U3.
    """
    left = canonicalize_extract(assembly)
    right = canonicalize_extract(overlay)
    mismatches: list = []
    for key in sorted(set(left["pads"]) | set(right["pads"])):
        if left["pads"].get(key) != right["pads"].get(key):
            mismatches.append(
                {
                    "category": "pads",
                    "key": key,
                    "assembly": left["pads"].get(key),
                    "overlay": right["pads"].get(key),
                }
            )
    for kind in ("tracks", "vias", "zones"):
        only_left = sorted(set(left[kind]) - set(right[kind]))
        only_right = sorted(set(right[kind]) - set(left[kind]))
        for item in only_left:
            mismatches.append(
                {"category": kind, "key": item[:80], "assembly": item, "overlay": None}
            )
        for item in only_right:
            mismatches.append(
                {"category": kind, "key": item[:80], "assembly": None, "overlay": item}
            )
    for key in sorted(set(left["endpoints"]) | set(right["endpoints"])):
        if left["endpoints"].get(key) != right["endpoints"].get(key):
            mismatches.append(
                {
                    "category": "endpoints",
                    "key": key,
                    "assembly": left["endpoints"].get(key),
                    "overlay": right["endpoints"].get(key),
                }
            )
    return mismatches


# ---------------------------------------------------------------------------
# Buck staging readiness (pre-U4): functional geometry requirements.
# ---------------------------------------------------------------------------


def buck_staging_readiness(target_context_path: Path | None = None) -> dict:
    """Stage the buck functional geometry requirements for composition.

    Returns the nine functional refs, their source-path namespace, the
    prototype exclusion set, the target outer-copper contract, and the
    via contract, resolved against the P3 target context. No MCU
    geometry is staged here: the MCU side is owned by P1 U4 (see the
    input contract).
    """
    context_path = Path(target_context_path) if target_context_path else (
        REPO / "pcb" / "blocks" / "control-assembly" / "target-context.json"
    )
    context = json.loads(context_path.read_text(encoding="utf-8"))
    copper_order = context["target"]["physical_copper_order"]
    for layer in TARGET_OUTER_PAIR:
        if layer not in copper_order:
            raise CompositionError(
                f"target context lacks outer layer {layer!r}: order={copper_order}"
            )
    return {
        "functional_refs": list(BUCK_FUNCTIONAL_REFS),
        "source_namespace": BUCK_PATH_PREFIX,
        "prototype_excluded": sorted(PROTOTYPE_ONLY_REFS),
        "target_outer_copper": list(TARGET_OUTER_PAIR),
        "physical_copper_order": list(copper_order),
        "via": {
            "span": VIA_SPAN,
            "diameter_mm": VIA_DIAMETER_MM,
            "drill_mm": VIA_DRILL_MM,
        },
        "buck_region_mm": dict(context["reserved_regions_mm"]["buck_block"]),
        "mcu_pending": "P1 U4 accepted pcb/blocks/mcu/ package",
    }
