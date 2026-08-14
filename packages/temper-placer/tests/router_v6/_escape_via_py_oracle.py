"""Pinned Python oracle for ``router_v6/escape_via_generator.py`` (Wave-4 cluster G).

DO NOT EDIT -- THESE ARE THE REFERENCE.
=======================================
Every executable statement below is a **verbatim** ``git show`` extraction
from commit ``143752893c177dc976da614566c64e4e53e4951f`` (``origin/main``,
2026-08-05) of ``temper_placer/router_v6/escape_via_generator.py``:
``EscapeVia``, ``generate_escape_vias``, ``_is_position_valid`` --
i.e. the whole module except its import block.

Nothing has been cleaned up, refactored, or fixed *by this file*.
``test_escape_via_rust_differential.py::test_oracle_is_verbatim_copy``
re-extracts each definition from the pinned commit and compares the source
text character for character.

**Re-pinned 2026-08-05.**  The original pin was
``15110feccc6ec9389f0777d3cff1ce9f81b11068`` (2026-08-04), which predated
#760 (``aebaecd99``).  That PR repaired defect D4 below, so the old pin
recorded behaviour the product no longer has -- 1 of the 41 ``PACKAGES``
cases (``side_1_back``) diverged, the pin saying ``F.Cu`` where main says
``B.Cu``.  The re-capture is a fresh ``git show`` of the same three
definitions at the new commit, not a hand-edit; only
``generate_escape_vias`` moved (6 lines: the ``getattr`` and its comment).
``EscapeVia`` and ``_is_position_valid`` are byte-identical across the two
commits, so every measurement in the "which operator" and "NaN behaviour"
sections below still holds unchanged -- D4 touched neither the geometry nor
the clearance predicate, only the layer *label*.

Why this is its own oracle module, separate from ``net_ordering``
------------------------------------------------------------------
See the "Why this is its OWN oracle module" section of
``_net_ordering_py_oracle.py``.  Short version: the survey's cluster G is two
modules that share no type, no fixture, no corpus and no divergence class,
and the survey itself said "do not force it".  This one is a **clearance
predicate over pad geometry**; the other is a **total-order comparator over
nets**.  Split, with a separate corpus and a separate differential each.

Where this kernel actually belongs (a recommendation, not an edit)
--------------------------------------------------------------------
``_is_position_valid`` is
``sqrt((x - px)**2 + (y - py)**2) < radius + pin_radius + clearance - 0.001``
evaluated against every pad of one component.  That is the same shape as
cluster **A**'s DRC distance predicates (``constraints_geometry``, in flight
as PR #732) and the same shape as the already-delegating
``clearance_check``/``creepage_check`` in ``temper-drc-rs``.  If this module
is ported, its kernel should extend one of those crates rather than found a
"cluster G" crate of its own -- there is no third thing here.

Which language's operator each call site uses (catalog §2)
-----------------------------------------------------------
This module imports **no numpy**: **B12 does not apply**.  It contains no
``max``/``min`` of any kind, so **B5 does not apply either** -- recorded
explicitly so a reviewer does not grep for a py_max that should not exist.

**B1 -- host-runtime libm via ``dlsym``.  This is the live trap here.**
``rotate_local_to_world(dx, dy, angle)``
(``temper_placer.geometry.kicad_transform``) is
``c, s = math.cos(theta), math.sin(theta)`` then
``(x*c + y*s, -x*s + y*c)``.  Those are CPython's ``math.cos``/``math.sin``,
which come from the *host Python runtime's* libm; a statically bound
``f64::cos``/``f64::sin`` measured 1 ulp apart on the uv standalone build.
The Rust mirror must resolve them with ``dlsym`` (``pad_geometry.rs``'s
``dlsym_math`` is the in-repo helper) and must preserve the
``x*c + y*s`` / ``-x*s + y*c`` op order and grouping (B7).

**And a quadrant rotation is NOT an exact transform.**  Every caller here
passes a quadrant angle (``initial_rotation_quadrant`` is a 0-3 index), which invites
the "optimization" of replacing the trig with an exact axis swap.  Do not:
``math.cos(pi/2)`` is ``6.123233995736766e-17``, not ``0.0``, so the
reference leaves a residue proportional to the *other* coordinate.  Measured:
``rotate(0.9375, 0.0, pi/2)`` -> ``(5.740531871003219e-17, -0.9375)`` where an
axis swap gives ``(0.0, -0.9375)``; ``rotate(1e6, 1.0, pi/2)`` ->
``1.0000000000612324``, 6.1e-7 mm from the swap's ``1.0``.  A Rust mirror
that swaps axes is *more* correct and *fails the differential*.  Pinned by
``test_escape_via_pbt.py::test_quadrant_rotations_are_not_exact``.

**B7 -- ``**`` is libm ``pow``, and the spelling matters.**
``_is_position_valid`` computes
``math.sqrt((x - p_pos[0]) ** 2 + (y - p_pos[1]) ** 2)``.  Measured over
20 000 random pairs: this form disagrees with ``math.hypot`` on **17.39%**
of them, and with ``math.sqrt(dx*dx + dy*dy)`` on **0.06%**.  Copy the
``pow``-then-``sqrt`` form; neither ``hypot`` nor ``dx*dx`` is a legal
substitute (this is B6's point restated for a non-GEOS oracle).

**B2 -- measured NOT to apply, and that is worth recording.**
``angle = float(component.initial_rotation_quadrant) * math.pi / 2.0`` looks like the
``PI / 2.0``-vs-``FRAC_PI_2`` trap.  It is not: the expression is
``(v * PI) / 2.0``, and division by ``2.0`` is exact in binary floating
point, so it agrees with ``v * (PI / 2.0)`` and with ``v * FRAC_PI_2`` on
**0 of 20 000** random ``v``.  Any of the three spellings is bit-exact here.
Recorded as a measured non-divergence rather than left for a future reader to
re-derive.

**Denormals (B8).** The ``- 0.001`` in ``dist < required_dist - 0.001`` is a
subtraction of a non-representable decimal from a distance; the corpus
carries a case that lands the comparison inside the denormal band so a
fast-math/FTZ build is caught.

Known defects -- D4 REPAIRED, re-pinned
----------------------------------------
**D4 -- every escape via was placed on ``F.Cu``, whatever side the component
was on.  REPAIRED by #760 (``aebaecd99``, issue #752 defect 3).**

As originally pinned: ``generate_escape_vias`` resolved the layer with
``side = getattr(component, "side", 0) or 0`` and then
``layer = side_to_layer_name(side)``.  ``Component`` has **no ``side``
attribute** -- the field is called ``initial_side`` (and
``pin_world_position`` reads *that* one when it mirrors the pad).  So the
``getattr`` default fired unconditionally, ``side`` was always ``0``, and
``layer`` was always ``"F.Cu"``.  Measured on the old pin: a component with
``initial_side=1`` (back side) still produced ``layer='F.Cu'`` on every
generated via, while its pad coordinates *were* mirrored -- the vias were
geometrically on the back and labelled front.

The shipped line is now ``side = component.initial_side or 0``, and this
oracle carries that.  Measured on the re-pinned oracle: ``side_1_back``
yields ``{'B.Cu'}``; ``side_0`` and ``side_none`` still yield ``{'F.Cu'}``
(``initial_side=None`` short-circuits to ``0`` through the ``or``, which is
the pre-existing default and did not change).  Geometry is untouched --
``side_0`` and ``side_1_back`` still differ in pad coordinates, exactly as
before, so the *label* now agrees with the *geometry* instead of
contradicting it.

The pin for it was **inverted, not deleted**:
``test_d4_layer_is_always_f_cu_regardless_of_side`` became
``test_repaired_d4_layer_follows_the_component_side``, which fails if the
``getattr`` form or any other side-blind resolution comes back.

Two further behaviours that look like defects and are **not**, so nobody
"fixes" them into a differential failure:

* ``_ignore_net`` is prefixed with an underscore and never read, so the
  source pin's own pad *is* checked for clearance.  The module's inline
  comment argues for exactly that ("If it overlaps source pin, it's
  effectively Via-in-Pad, not Dog-Bone").  The consequence is measurable and
  is pinned: with the corpus's default rules, dog-bone placement fails for
  every pin at pitches 0.4/0.5/0.65/0.8 mm and succeeds at 1.0/1.27 mm.
* ``_comp_pos`` and ``_comp_angle`` are likewise underscore-prefixed and
  unused; the collision test is done entirely in world coordinates.

NaN behaviour is a contract, not an accident
----------------------------------------------
``dist < required_dist - 0.001`` is **False** when ``dist`` is NaN, so
``_is_position_valid`` returns ``True`` and the NaN candidate is *accepted*.
Measured: a ``DensePackage`` with ``pitch_mm = NaN`` yields 9 dog-bone vias
at ``(nan, nan)``.  A Rust mirror that flips the comparison to
``!(dist >= required)`` or that early-returns on NaN produces a different
count, so this is pinned by ``test_nan_pitch_emits_nan_positioned_vias``.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from temper_placer.core.netlist import Component
from temper_placer.core.pin_geometry import pin_world_position, pin_world_radius
from temper_placer.geometry.kicad_transform import rotate_local_to_world
from temper_placer.router_v6.dense_package_detection import DensePackage
from temper_placer.router_v6.stage0_data import DesignRules

__all__ = ["EscapeVia", "generate_escape_vias"]


# --- escape_via_generator.py -------------------------------------------


@dataclass
class EscapeVia:
    """
    Computed escape via definition.

    Attributes:
        position: (x, y) absolute coordinates in mm.
        net_name: Name of the net.
        pin_number: Pin number being escaped.
        diameter: Via diameter in mm.
        drill: Via drill diameter in mm.
        via_type: "dog-bone" or "via-in-pad".
        layer: KiCad layer name resolved from the component's side
            (e.g. "F.Cu" or "B.Cu").
    """

    position: tuple[float, float]
    net_name: str
    pin_number: str
    diameter: float
    drill: float
    via_type: str
    layer: str = "F.Cu"


def generate_escape_vias(
    dense_pkg: DensePackage,
    design_rules: DesignRules,
    strategy: str = "dog-bone",
) -> list[EscapeVia]:
    """
    Generate escape vias for a dense package.

    Args:
        dense_pkg: The DensePackage to process.
        design_rules: Board design rules (clearance, via sizes).
        strategy: "dog-bone" (default) or "via-in-pad".

    Returns:
        List of EscapeVia objects.
    """
    escape_vias = []
    component = dense_pkg.component

    # Resolve layer from component side
    from temper_placer.core.board import side_to_layer_name

    # The contract field is `initial_side` (core/netlist.py), not `side`.
    # Reading a `side` attribute Component does not have made the getattr
    # default fire unconditionally, labelling every escape via "F.Cu" -- while
    # pin_world_position DID mirror the pad coordinates for bottom-side parts,
    # so the two halves of the same via disagreed. See issue #752 defect 3.
    side = component.initial_side or 0
    layer = side_to_layer_name(side)

    # Get component absolute position
    comp_x, comp_y = 0.0, 0.0
    if component.initial_position:
        comp_x, comp_y = component.initial_position

    # Get component rotation in radians
    # Component.initial_rotation_quadrant is index 0-3 (0=0, 1=90, 2=180, 3=270)
    angle = 0.0
    if component.initial_rotation_quadrant is not None:
        angle = float(component.initial_rotation_quadrant) * math.pi / 2.0

    for pin in component.pins:
        if not pin.net:
            continue

        rules = design_rules.get_rules_for_net(pin.net)
        via_diameter = rules.via_diameter_mm
        via_drill = rules.via_drill_mm
        clearance = rules.clearance_mm

        # Determine via position
        if strategy == "via-in-pad":
            # Via in center of pad
            abs_pos = pin_world_position(pin, component)

            escape_vias.append(
                EscapeVia(
                    position=abs_pos,
                    net_name=pin.net,
                    pin_number=pin.number,
                    diameter=via_diameter,
                    drill=via_drill,
                    via_type="via-in-pad",
                    layer=layer,
                )
            )

        elif strategy == "dog-bone":
            pin_abs_pos = pin_world_position(pin, component)

            # Valid candidates for BGA/Grid dogbone (relative to pin in component space)
            # We try 4 diagonals: (+half_pitch, +half_pitch), etc.
            half_pitch = dense_pkg.pitch_mm / 2.0

            # Note: For non-square grids or non-BGA, this pitch-based heuristic
            # might need refinement, but it's a good robust start for "dense" packages.
            candidates = [
                (half_pitch, half_pitch),
                (half_pitch, -half_pitch),
                (-half_pitch, half_pitch),
                (-half_pitch, -half_pitch),
            ]

            chosen_pos = None

            for dx, dy in candidates:
                # Rotate the offset to match component rotation. `angle`
                # is the component's real board rotation (radians) and
                # `pin_abs_pos` below is KiCad-derived (core.pin_geometry),
                # so this must use KiCad's footprint-child rotation
                # convention, R(-theta) -- see
                # temper_placer.geometry.kicad_transform's module
                # docstring. Masked today because `angle` is always an
                # exact quadrant value (Component.initial_rotation_quadrant is a
                # 0-3 index), at which this symmetric 4-way candidate set
                # is set-invariant to R(+theta) vs R(-theta); fixed anyway
                # so a non-quadrant future caller does not inherit a
                # mirrored escape direction.
                rot_dx, rot_dy = rotate_local_to_world(dx, dy, angle)

                # Candidate absolute position
                cand_x = pin_abs_pos[0] + rot_dx
                cand_y = pin_abs_pos[1] + rot_dy

                # Check collision with other pins
                if _is_position_valid(
                    cand_x,
                    cand_y,
                    via_diameter / 2.0,
                    component,
                    (comp_x, comp_y),
                    angle,
                    clearance,
                    _ignore_net=pin.net,  # Ignore clearance to same net
                ):
                    chosen_pos = (cand_x, cand_y)
                    break

            if chosen_pos:
                escape_vias.append(
                    EscapeVia(
                        position=chosen_pos,
                        net_name=pin.net,
                        pin_number=pin.number,
                        diameter=via_diameter,
                        drill=via_drill,
                        via_type="dog-bone",
                        layer=layer,
                    )
                )
            else:
                # Could not find valid dog-bone position.
                # This happens if pitch is too tight for the via size.
                pass

    return escape_vias


def _is_position_valid(
    x: float,
    y: float,
    radius: float,
    component: Component,
    _comp_pos: tuple[float, float],
    _comp_angle: float,
    clearance: float,
    _ignore_net: str | None = None,
) -> bool:
    """
    Check if via at (x,y) with radius collides with any component pin.

    Args:
        x, y: Via center coordinates.
        radius: Via radius.
        component: Component to check against.
        comp_pos: Component absolute position.
        comp_angle: Component rotation angle.
        clearance: Required clearance.
        ignore_net: Net name to ignore (e.g. source pin's net).
    """

    for pin in component.pins:
        # If pin is on the same net, physical overlap is allowed/expected for connection.
        # However, for dog-bone, we ideally want separation.
        # But strictly speaking, DRC allows overlap on same net.
        # Let's enforce separation even for same net to ensure "dog-bone" shape,
        # but maybe with reduced requirement?
        # Actually, for dog-bone, the via IS separated.
        # If we return False here, we say "invalid position".
        # If it overlaps source pin, it's effectively Via-in-Pad, not Dog-Bone.
        # So we SHOULD check collision even for same net to force separation.
        # BUT, standard BGA pitch might barely fit.
        # Let's check pure geometric overlap.

        p_pos = pin_world_position(pin, component)

        # Shared, shape-correct conservative radius (core.pin_geometry's
        # single implementation -- see its docstring for the exact
        # circle/oval/rect/roundrect closed form and never-under-reports
        # proof). This used to be max(width, height) / 2.0 duplicated here,
        # which under-reports a square/near-square rect pad's true corner
        # extent.
        pin_radius = pin_world_radius(pin)

        dist = math.sqrt((x - p_pos[0]) ** 2 + (y - p_pos[1]) ** 2)

        required_dist = radius + pin_radius + clearance

        # If on same net, we don't need electrical clearance, but we might want mechanical separation.
        # If ignore_net matches, we can relax the check?
        # Let's maintain strict check for now to ensure quality fanout.

        if dist < required_dist - 0.001:  # epsilon tolerance
            return False

    return True
