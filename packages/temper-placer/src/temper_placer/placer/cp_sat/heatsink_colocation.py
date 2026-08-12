"""Shared-heatsink co-location: a HARD placement constraint for the two
TO-247 IGBTs (``U5``/``U6``) that both bolt to the single BOM-costed
heatsink ``HS1``.

Why this module exists
----------------------
``HS1`` (Wakefield-Vette ``392-120AB``) is one physical extrusion shared by
four power devices -- ``docs/hardware/BOM.md:542``:

    HS1 | Shared Heatsink (2xTO-247 + 2xTO-220) | 392-120AB | Wakefield-Vette
       | 1 | Extruded, 120x125x135.8mm, 0.5C/W natural / 0.2C/W forced

backed by two individually die-cut TO-247 TIM pads (``BOM.md:545``,
Bergquist ``SP400-0.009-00-58``, one per IGBT, both pressing on the *same*
heatsink body) and four mounting sets (``BOM.md:546``). This is a real,
currently-sourced, costed mechanical assembly, not a template artifact.

The committed board cannot be assembled with it. Measured directly from
``pcb/temper.kicad_pcb`` (read-only; this module does not modify the
board):

===== ================================ =================== ==============
Ref   ``(at x y rot)``                  rotation index      board line
===== ================================ =================== ==============
U5    ``(at 23.72 233.25 270.0)``       3                   ``:7969``
U6    ``(at 100.07 159.33 180.0)``      2                   ``:8008``
===== ================================ =================== ==============

Both carry the identical footprint
``Package_TO_SOT_THT:TO-247-3_Vertical``, so the 90-degree difference is a
real difference in which direction each device's mounting tab faces, not a
package-variant artifact. **An extruded heatsink presents one flat
mounting profile; it cannot simultaneously contact two tabs whose planes
are perpendicular** -- at any separation, so this is not fixable by moving
the parts closer. Derived independently in
``docs/evidence/2026-08-12-thermal-constraint-derivation.md`` (constraint 1
"REAL, VIOLATED").

``thermal_management.yaml``'s constraint 1 declares the requirement
(``on_side`` + ``aligned``, ``[Q1, Q2]``) but (a) names ``Q1``/``Q2``,
which are live designators for *different* parts on this board and are
explicitly refused an alias in
``packages/temper-placer/configs/temper_constraints.references.yaml``
(``unresolved_components``), and (b) constrains only centre coordinates --
it is satisfiable with the rotations still 90 degrees apart, i.e. it
cannot even express the part of the requirement the board actually
violates. This module is where the enforcement lives instead.

What is encoded, and what could not be derived
----------------------------------------------
1. **Identical rotation -- derivable, non-negotiable, and the part that
   makes the current placement unbuildable.** Both tab planes must face
   the same direction. Lead-forming (the plan's own mounting note,
   ``docs/plans/2026-07-16-001-feat-active-bus-discharge-and-thermal-bom-plan.md:118``:
   "mount to chassis, not PCB; devices lead-formed or on a daughter edge")
   can absorb millimetres of positional error, but it cannot rotate a
   device's body 90 degrees relative to its own lead row -- the leads
   leave the package in a fixed line. So rotation equality survives every
   mechanical degree of freedom this design has.

2. **Bounded separation along the mounting axis --
   ``MAX_COLOCATED_GAP_MM`` = 87.2mm**, derived below from HS1's own
   published length and the committed TO-247 footprint. Conservative in
   both inputs.

3. **Near-zero offset perpendicular to that axis -- NOT independently
   derivable.** See ``ALIGNMENT_TOLERANCE_MM``.

4. **Board-edge proximity -- deliberately NOT encoded.** The mechanical
   documentation says the opposite of "the heatsink mounts at a board
   edge": ``2026-07-16-001...:118`` records HS1 as a ~1kg chassis part,
   *not* PCB-mounted, reached by lead-forming. No in-repo document names
   which board edge the devices should sit at (no chassis/enclosure
   drawing exists -- the same gap
   ``2026-08-12-thermal-constraint-derivation.md`` flags for the NTC lead
   budget). ``thermal_management.yaml``'s ``side: top, edge: flush`` is a
   declaration, not a derivation, so it is not encoded here.

Why no new constraint type
--------------------------
Every constraint this module emits is an **existing** wire type, encoded
in *both* backends already:

- ``fixed_rotation`` -- Pumpkin ``docs/evidence/2026-08-07-pumpkin-engine/src/main.rs:558``;
  OR-Tools ``CpSatModel.add_fixed_rotation`` (``model.py:344``).
- ``aligned`` -- Pumpkin ``main.rs:399``; OR-Tools ``handlers/aligned.py:22``.
- ``adjacent`` -- Pumpkin ``main.rs:358``; OR-Tools ``handlers/adjacent.py:22``.

That matters concretely, not just as tidiness: Pumpkin ``exit(2)``s on an
unregistered type (``main.rs:621-627``) while OR-Tools warns and silently
continues (``_encoder_core.py:327-334``), so a new type encoded in only
one backend under-constrains the other in silence. It also means the
pinned engine binary (``scripts/verify_pumpkin_engine.py``,
``engine_pin.json``) does **not** have to be rebuilt and re-pinned -- a
rebuild would land in the shared ``CARGO_TARGET_DIR`` and break the
identity gate for every other worktree on this machine.

Rotation equality vs. rotation pinning -- the one real gap
----------------------------------------------------------
The physical requirement is ``rot[U5] == rot[U6]``: four equally valid
assignments (0/0, 1/1, 2/2, 3/3). No wire type expresses variable-to-
variable rotation equality; ``fixed_rotation`` pins to a literal. This
module therefore follows the pattern ``isolation_barrier.py`` already
established for exactly this situation (``_best_rotation_for_barrier``,
line 389, then ``Add(cvars.rot_ref == rot_value)``, line 631): *choose* a
common rotation, then pin both devices to it, and let the caller
enumerate the alternatives when one choice is infeasible
(``COMMON_ROTATIONS``).

Pinning is stronger than physics requires, but not arbitrary in effect:
HS1's mounting pattern is drilled by us, not by the vendor ("drill/tap M3
pattern for 2x TO-247 + 2x TO-220",
``2026-07-16-001...:109``), and no chassis drawing exists that would
privilege one orientation, so all four common rotations describe equally
buildable assemblies. The requirement that has physical content is that
the two agree.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from temper_placer.placer.cp_sat.model import CpSatModel

__all__ = [
    "ALIGNMENT_TOLERANCE_MM",
    "COMMON_ROTATIONS",
    "ColocationViolation",
    "HEATSINK_GROUPS",
    "HS1_MOUNTING_FACE_LENGTH_MM",
    "HeatsinkGroup",
    "MAX_COLOCATED_GAP_MM",
    "TO247_FOOTPRINT_WIDTH_MM",
    "add_heatsink_colocation_to_model",
    "check_heatsink_colocation",
    "heatsink_colocation_wire_constraints",
]


# ---------------------------------------------------------------------------
# Derived figures. Every one of these carries its source; where a figure is
# NOT derivable that is stated here rather than papered over with a number.
# ---------------------------------------------------------------------------

#: Length of HS1's flat device-mounting face, mm.
#:
#: ``docs/hardware/BOM.md:542`` and
#: ``docs/plans/2026-07-16-001-feat-active-bus-discharge-and-thermal-bom-plan.md:109``
#: both give HS1's envelope as "120 x 125 x 135.8mm" and nothing else.
#: **Which of the three is the mounting-face extent is not established by
#: any in-repo document** -- there is no Wakefield-Vette datasheet under
#: ``datasheets/`` (independently noted as a gap at
#: ``docs/hardware/PART_STRESS_AUDIT.md:338``). 120mm is taken because it
#: is the *smallest* of the three, which makes every bound derived from it
#: the tightest the available data supports; if the real face is 125mm or
#: 135.8mm this constraint is conservative, never permissive.
HS1_MOUNTING_FACE_LENGTH_MM: float = 120.0

#: Width of the committed TO-247 footprint along its lead row, mm.
#:
#: Measured from the board itself, not a datasheet: the F.CrtYd rect of
#: ``Package_TO_SOT_THT:TO-247-3_Vertical`` is ``(-2.75, -2.58) ->
#: (13.65, 2.95)`` (``pcb/temper.kicad_pcb:7982``), i.e. 16.40 x 5.53mm,
#: and ``parse_kicad_pcb`` reports ``bounds = (16.4, 5.9)`` for both U5 and
#: U6. The TO-247 *body* is narrower than its courtyard (15.875mm nominal),
#: so using the courtyard width overstates how much of the heatsink face
#: each device consumes -- again the conservative direction, since it
#: shrinks the permitted gap below.
TO247_FOOTPRINT_WIDTH_MM: float = 16.4

#: Maximum permitted edge-to-edge gap between two co-located TO-247s, mm.
#:
#: Both packages must land on one face of length
#: ``HS1_MOUNTING_FACE_LENGTH_MM``; at the extreme they sit at opposite
#: ends of it, so the gap between their near edges is the face length less
#: both package widths. 120.0 - 2 x 16.4 = 87.2mm.
#:
#: This is a bound on *co-location*, not the tight thermal/electrical
#: spacing a commutation loop would want -- the two TO-220 rectifiers share
#: the same face and have to fit somewhere in that gap. It is genuinely
#: derived from the part, and it is genuinely loose; it is stated as such
#: rather than tightened by invention.
MAX_COLOCATED_GAP_MM: float = HS1_MOUNTING_FACE_LENGTH_MM - 2.0 * TO247_FOOTPRINT_WIDTH_MM

#: Permitted centre offset perpendicular to the heatsink's mounting axis, mm.
#:
#: **NOT independently derived. This is the figure
#: ``thermal_management.yaml:30`` already declared, carried across
#: unchanged -- neither tightened nor loosened.**
#:
#: What bounds it in principle: a coplanarity error between two tabs
#: pressed on one flat face is taken up by the TIM. Sil-Pad 400 0.009"
#: (``BOM.md:545``) is 0.2286mm thick in total, so 0.2286mm is the offset
#: at which a rigidly-mounted pair would consume the entire pad -- an
#: absolute floor for any "tabs still touching" argument.
#:
#: What makes that floor inapplicable as a *placement* tolerance: the
#: devices are lead-formed to a chassis-mounted sink
#: (``2026-07-16-001...:118``), which decouples the tab plane from the PCB
#: pad plane by however much the lead form allows. No lead-form drawing
#: exists in this repo, so the mapping from "millimetres of PCB centre
#: offset" to "millimetres of tab coplanarity error" is unknown, and any
#: number picked here -- including 1.0 -- is a declaration.
#:
#: What *is* known: the current board misses this by 70.90mm of centre
#: offset perpendicular to U5's own mounting axis (box centres U5
#: (23.72, 238.70), U6 (94.62, 159.33) in raw board coordinates; 106.4mm
#: apart), which no plausible lead form absorbs. The qualitative violation
#: does not depend on the exact figure.
ALIGNMENT_TOLERANCE_MM: float = 1.0

#: The four rotation indices at which two devices agree. The model's
#: rotation variable is an integer 0..3 and index x 90 = degrees
#: (``model.py:202-206``, ``cli/__init__.py:788``); index 0 and 2 leave the
#: lead row along X (package spans 16.4mm in X), 1 and 3 along Y.
COMMON_ROTATIONS: tuple[int, ...] = (0, 1, 2, 3)


@dataclass(frozen=True)
class HeatsinkGroup:
    """A set of components that bolt to one physical heatsink.

    ``refs`` are real board designators, deliberately not the
    ``thermal_management.yaml`` spellings: ``Q1``/``Q2`` are live
    designators for ``power_in.q_relay_drv`` / ``discharge.q_dis_drv`` on
    this board and are refused an alias on purpose
    (``temper_constraints.references.yaml``, ``unresolved_components``).
    The IGBTs are ``U5`` (``hb.power_loop.q_high``) and ``U6``
    (``hb.power_loop.q_low``), matched by KiCad Sheetpath.
    """

    heatsink_ref: str
    refs: tuple[str, ...]
    part_number: str
    max_gap_mm: float = MAX_COLOCATED_GAP_MM
    alignment_tolerance_mm: float = ALIGNMENT_TOLERANCE_MM


#: The heatsink groups this board actually has.
#:
#: Only the two TO-247 IGBTs are listed. HS1 also carries two TO-220
#: rectifiers (``BOM.md:542``, ``:546``'s 4 mounting sets), but this repo's
#: reference manifest does not resolve them to board designators -- ``D1``
#: and ``D2`` are refused aliases for the same reason ``Q1``/``Q2`` are
#: (``temper_constraints.references.yaml``, ``unresolved_components``:
#: "legacy config means power_in.d1 (board ref U1)"), and no in-repo source
#: establishes which two board refs are the TO-220s on HS1. Adding them
#: without that evidence would be inventing group membership, so the group
#: is stated as partial rather than guessed at.
HEATSINK_GROUPS: tuple[HeatsinkGroup, ...] = (
    HeatsinkGroup(
        heatsink_ref="HS1",
        refs=("U5", "U6"),
        part_number="392-120AB",
    ),
)


@dataclass(frozen=True)
class ColocationViolation:
    """One way a placement fails a :class:`HeatsinkGroup`'s requirement."""

    heatsink_ref: str
    kind: str  # "rotation" | "alignment" | "separation"
    refs: tuple[str, ...]
    measured: float
    limit: float
    detail: str


# ---------------------------------------------------------------------------
# Geometry helpers
# ---------------------------------------------------------------------------


def _row_axis(rot_index: int) -> str:
    """Board axis along which devices sharing one flat face must sit.

    At rotation index 0 the footprint's lead row runs along board X (pads
    at local x = 0, 5.45, 10.9 -- ``pcb/temper.kicad_pcb:7989-7993``) and
    the package's wide flat faces -- one of which is the metal tab -- are
    normal to board Y. Two devices bolted to one such face are therefore
    offset along **X** and share a **Y** coordinate. Index 2 is the same
    axis (tab pointing the other way); indices 1 and 3 swap the roles.
    """
    return "x" if rot_index % 2 == 0 else "y"


def _alignment_axis(rot_index: int) -> str:
    """The ``aligned`` constraint's ``axis`` value for *rot_index*.

    ``aligned`` names the axis whose *centres must match*, i.e. the axis
    perpendicular to the row. The Pumpkin encoder treats ``"x"``/``"major"``
    as "constrain cx" and everything else as "constrain cy"
    (``main.rs:402``); ``handlers/aligned.py:46-49`` uses the identical
    rule. ``"horizontal"`` therefore means "share a Y coordinate" in both,
    which is what a row running along X requires.
    """
    return "horizontal" if _row_axis(rot_index) == "x" else "x"


# ---------------------------------------------------------------------------
# Pumpkin wire-format emission
# ---------------------------------------------------------------------------


def heatsink_colocation_wire_constraints(
    group: HeatsinkGroup,
    rot_index: int,
    *,
    present_refs: frozenset[str] | None = None,
) -> list[dict]:
    """Pumpkin ``ModelSpec.constraints`` entries enforcing *group*.

    Emits only wire types ``docs/evidence/2026-08-07-pumpkin-engine/src/main.rs``
    already registers, so the pinned engine binary is used unmodified.

    *present_refs*, when given, filters to refs the payload actually
    declares -- a constraint naming an absent component is silently
    dropped by ``aligned``/``adjacent`` but ``fixed_rotation`` would also
    no-op, so filtering here keeps the emitted set honest about what is
    actually being enforced.
    """
    if rot_index not in COMMON_ROTATIONS:
        raise ValueError(f"rot_index must be one of {COMMON_ROTATIONS}, got {rot_index!r}")

    refs = [r for r in group.refs if present_refs is None or r in present_refs]
    if len(refs) < 2:
        return []

    out: list[dict] = []

    # (1) Identical rotation. The requirement is equality; the wire format
    #     can only pin, so both are pinned to the same literal and the
    #     caller sweeps COMMON_ROTATIONS. See module docstring.
    for ref in refs:
        out.append({"type": "fixed_rotation", "component": ref, "rot": rot_index})

    # (2) Near-zero offset perpendicular to the heatsink's mounting axis.
    out.append(
        {
            "type": "aligned",
            "components": refs,
            "axis": _alignment_axis(rot_index),
            "tolerance_mm": group.alignment_tolerance_mm,
            "tier": 1,
            "because": (
                f"{group.heatsink_ref} ({group.part_number}) is one flat extruded face; "
                f"co-located devices sit in a line along board "
                f"{_row_axis(rot_index).upper()}."
            ),
        }
    )

    # (3) Both packages inside the heatsink's usable face length.
    #     ``adjacent`` bounds the edge-to-edge gap on BOTH axes
    #     (main.rs:358-397 posts four one-sided bounds, an AND not an OR),
    #     which is what "both on one face" needs.
    for i in range(len(refs)):
        for j in range(i + 1, len(refs)):
            out.append(
                {
                    "type": "adjacent",
                    "a": refs[i],
                    "b": refs[j],
                    "max_distance_mm": group.max_gap_mm,
                    "metric": "edge_to_edge",
                    "tier": 1,
                    "because": (
                        f"Both packages must land on {group.heatsink_ref}'s "
                        f"{HS1_MOUNTING_FACE_LENGTH_MM}mm mounting face "
                        f"(face length less two {TO247_FOOTPRINT_WIDTH_MM}mm packages)."
                    ),
                }
            )
    return out


# ---------------------------------------------------------------------------
# OR-Tools CpSatModel emission
# ---------------------------------------------------------------------------


def add_heatsink_colocation_to_model(
    model: CpSatModel,
    group: HeatsinkGroup,
    rot_index: int,
) -> list[str]:
    """Post *group*'s constraints onto an OR-Tools :class:`CpSatModel`.

    Mirrors :func:`heatsink_colocation_wire_constraints` exactly, using the
    model's own primitives rather than the PCL handler path (the same
    approach ``isolation_barrier.add_isolation_barrier_to_model`` takes,
    and for the same reason: ``fixed_rotation`` has no PCL constraint type,
    only a model API, ``model.py:344``).

    Returns the assumption labels created, so an UNSAT core can name this
    constraint rather than reporting an anonymous conflict.
    """
    if rot_index not in COMMON_ROTATIONS:
        raise ValueError(f"rot_index must be one of {COMMON_ROTATIONS}, got {rot_index!r}")

    refs: list[str] = []
    for ref in group.refs:
        try:
            model.get_component(ref)
        except KeyError:
            continue
        refs.append(ref)
    if len(refs) < 2:
        return []

    labels: list[str] = []
    tol_u = model.mm_to_units(group.alignment_tolerance_mm)
    gap_u = model.mm_to_units(group.max_gap_mm)
    align_on_cy = _alignment_axis(rot_index) != "x"

    # (1) Identical rotation -- a hard pin, deliberately NOT enforced by an
    #     assumption literal: it is the one part of this constraint that is
    #     not negotiable, and an assumption is exactly a thing a relaxation
    #     search is allowed to drop.
    for ref in refs:
        model.add_fixed_rotation(ref, rot_index)

    for i in range(len(refs)):
        for j in range(i + 1, len(refs)):
            va = model.get_component(refs[i])
            vb = model.get_component(refs[j])

            label = f"heatsink_align_{group.heatsink_ref}_{refs[i]}_{refs[j]}"
            assumption = model.new_assumption(label)
            ca, cb = (va.y_center, vb.y_center) if align_on_cy else (va.x_center, vb.x_center)
            model.add_constraint_enforced(ca - cb <= tol_u, assumption)
            model.add_constraint_enforced(cb - ca <= tol_u, assumption)
            labels.append(label)

            label = f"heatsink_gap_{group.heatsink_ref}_{refs[i]}_{refs[j]}"
            assumption = model.new_assumption(label)
            # Edge-to-edge on both axes, matching main.rs:375-396 and
            # handlers/adjacent.py:62-65.
            model.add_constraint_enforced(va.x_start - vb.x_start - vb.x_size <= gap_u, assumption)
            model.add_constraint_enforced(vb.x_start - va.x_start - va.x_size <= gap_u, assumption)
            model.add_constraint_enforced(va.y_start - vb.y_start - vb.y_size <= gap_u, assumption)
            model.add_constraint_enforced(vb.y_start - va.y_start - va.y_size <= gap_u, assumption)
            labels.append(label)

    return labels


# ---------------------------------------------------------------------------
# Pure checker -- the same predicate, evaluated against a concrete placement
# ---------------------------------------------------------------------------


def check_heatsink_colocation(
    positions: dict[str, tuple[float, float]],
    rotations: dict[str, int],
    sizes: dict[str, tuple[float, float]],
    group: HeatsinkGroup = HEATSINK_GROUPS[0],
) -> list[ColocationViolation]:
    """Evaluate *group*'s requirement against a concrete placement.

    *positions* are box centres in mm, *rotations* are model rotation
    indices (0..3), *sizes* are the components' unrotated ``(w0, h0)``.
    Refs absent from *positions* are skipped.

    This is the predicate the solver enforces, run in the other direction:
    it is what proves the committed board violates the constraint, and what
    proves a solved board satisfies it.
    """
    refs = [r for r in group.refs if r in positions and r in rotations and r in sizes]
    violations: list[ColocationViolation] = []
    if len(refs) < 2:
        return violations

    rots = {r: rotations[r] for r in refs}
    distinct = sorted(set(rots.values()))
    if len(distinct) > 1:
        violations.append(
            ColocationViolation(
                heatsink_ref=group.heatsink_ref,
                kind="rotation",
                refs=tuple(refs),
                measured=float(len(distinct)),
                limit=1.0,
                detail=(
                    "tab planes face different directions: "
                    + ", ".join(f"{r}={rots[r] * 90}deg" for r in refs)
                    + f" -- no single flat face of {group.heatsink_ref} can contact both"
                ),
            )
        )

    # Geometry is judged on the row axis implied by the placement's own
    # rotation. With mismatched rotations there is no single such axis, so
    # fall back to the first ref's -- the rotation violation above is the
    # governing finding in that case, and this keeps the alignment number
    # reported rather than suppressed.
    axis_is_x = _row_axis(rots[refs[0]]) == "x"

    def _wh(ref: str) -> tuple[float, float]:
        w0, h0 = sizes[ref]
        return (w0, h0) if rots[ref] % 2 == 0 else (h0, w0)

    for i in range(len(refs)):
        for j in range(i + 1, len(refs)):
            a, b = refs[i], refs[j]
            (ax, ay), (bx, by) = positions[a], positions[b]
            (aw, ah), (bw, bh) = _wh(a), _wh(b)

            offset = abs(ay - by) if axis_is_x else abs(ax - bx)
            if offset > group.alignment_tolerance_mm:
                violations.append(
                    ColocationViolation(
                        heatsink_ref=group.heatsink_ref,
                        kind="alignment",
                        refs=(a, b),
                        measured=offset,
                        limit=group.alignment_tolerance_mm,
                        detail=(
                            f"centre offset perpendicular to the "
                            f"{'X' if axis_is_x else 'Y'} mounting axis is {offset:.2f}mm"
                        ),
                    )
                )

            gap_x = max(ax - bx - (aw + bw) / 2.0, bx - ax - (aw + bw) / 2.0)
            gap_y = max(ay - by - (ah + bh) / 2.0, by - ay - (ah + bh) / 2.0)
            gap = max(gap_x, gap_y)
            if gap > group.max_gap_mm:
                violations.append(
                    ColocationViolation(
                        heatsink_ref=group.heatsink_ref,
                        kind="separation",
                        refs=(a, b),
                        measured=gap,
                        limit=group.max_gap_mm,
                        detail=(
                            f"edge-to-edge gap {gap:.2f}mm exceeds "
                            f"{group.heatsink_ref}'s usable face length"
                        ),
                    )
                )
    return violations
