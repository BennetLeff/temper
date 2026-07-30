"""Rotation-convention regression guard for the KiCad R(-theta) sign fix.

The bug this guards against
----------------------------
KiCad rotates a footprint's pad local offsets **clockwise**, ``R(-theta)``.
This repo used the standard-math CCW ``R(+theta)`` in 12 places (see
``docs/evidence/2026-07-29-rotation-convention-sign-fix-cpsat-rerun.md``),
including ``requirements/validators/_copper.py::_rotate`` -- the function
REQ-SAFE-01 (the mains-safety clearance/creepage check) uses to compute
copper positions. The wrong sign concealed real clearance hazards on 18
production components on a mains-connected board.

Ground truth, reproduced directly against ``pcbnew`` (KiCad's own placement
engine, not a reimplementation of its rotation formula) as part of building
this test:

    footprint at 37 deg, pad local offset (10, 4) mm
    pcbnew actual:   (10.393615, -2.823608)   <- R(-theta), correct
    R(+theta) CCW:   ( 5.579095,  9.212692)   <- what 12 sites used

Why the existing test suite missed this
-----------------------------------------
1. Round-trip tests (``parse(write(x)) == x``) pass under any *consistent
   but wrong* convention -- this repo's parser and writer shared the bug.
2. 90-degree multiples are degenerate: R(+theta) and R(-theta) agree
   exactly at 0/180 degrees, and at 90/270 they differ only in *which* of
   X/Y gets negated -- so a test whose geometry happens to be symmetric
   about the axis the sign flips (as ``pcb/temper.kicad_pcb``'s footprints
   all are, being placed only at 90-degree multiples) cannot discriminate
   the two conventions even when it looks like it is testing rotation.
   ``tests/requirements/safety/test_clearance_copper.py::TestRotation::
   test_rotated_footprint_moves_its_pads`` is exactly this case: B sits on
   the world X axis, so A's pad reflecting to y=+3 vs y=-3 produces an
   *identical* measured distance -- the test passes under both signs.
3. Self-consistency is not correctness: this repo's own convention agreed
   with itself and disagreed with KiCad.

What this file does about it (see the task brief this was built from,
also mirrored in ``docs/evidence/2026-07-29-cross-domain-creepage-
rotation-convention.md``):

(a) Cheap, dependency-free metamorphic/pin tests -- one assertion each,
    always run, catch a sign reversion instantly. Covers the safety path
    (``_copper.py::_rotate``) and every other *distinct* rotation
    implementation still alive on this branch that is unit-testable
    without a real board fixture: ``deterministic/stages/setup.py::
    DRCOracleSetupStage._rotate_point``, ``placer/cp_sat/
    isolation_barrier.py::_project_onto_barrier_axis``, ``core/
    courtyard.py::Courtyard.get_global_polygon``, and ``scripts/
    check_isolation_keepout.py::_rotate`` (the live gate enforcing
    8.0mm mains<->SELV creepage on this repo's actual board).

(b) A property-based differential test against ``pcbnew`` as oracle for
    the two sites that most directly gate mains safety today
    (``_copper.py::_rotate`` and ``check_isolation_keepout.py::_rotate``).
    Generates random ``(dx, dy, angle)``, asks KiCad's own placement
    engine where the pad really lands, and compares to ~1e-6mm.

    The filter excluding angles at/near multiples of 90 degrees is
    LOAD-BEARING (see point 2 above) -- do not remove it "to get more
    coverage". Without it, Hypothesis is statistically likely to hand
    back exactly the degenerate cases that let this bug hide for as long
    as it did, and the test would report green while checking nothing
    discriminating.

    Skips loudly (never silently -- the skip reason names exactly what
    was tried) when no interpreter with ``pcbnew`` bindings is available.
    In CI (``ghcr.io/bennetleff/temper-ci:latest``, built from
    ``.github/docker/ci.Dockerfile``), that interpreter is ``apt-get
    install kicad``'s system ``/usr/bin/python3``, so the oracle runs
    for real there, not just locally.
"""

from __future__ import annotations

import json
import math
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from temper_placer.core.courtyard import Courtyard
from temper_placer.deterministic.stages.setup import DRCOracleSetupStage
from temper_placer.placer.cp_sat.isolation_barrier import _project_onto_barrier_axis
from temper_placer.requirements.validators._copper import _rotate as copper_rotate

# `_resolve_pcbnew_python` already exists and is battle-tested (its own
# docstring records that a hardcoded `/usr/bin/python3` -- one that EXISTS
# but lacks pcbnew -- silently skipped this whole test family for a week on
# macOS dev machines). Reused, not re-implemented, per this task's brief.
from tests.placer.cp_sat.test_zone_pour_production_measurement import (
    _resolve_pcbnew_python,
)

# `tests/requirements/safety/test_X.py` -> repo root is 5 levels up
# (safety -> requirements -> tests -> temper-placer -> packages -> root).
_REPO_ROOT = Path(__file__).resolve().parents[5]
_SCRIPTS_DIR = _REPO_ROOT / "scripts"
_ORACLE_SCRIPT = _SCRIPTS_DIR / "kicad_pad_rotation_oracle.py"
assert _SCRIPTS_DIR.is_dir(), f"expected scripts/ at {_SCRIPTS_DIR}"

if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

import check_isolation_keepout as _check_isolation_keepout  # noqa: E402


# =============================================================================
# (a) Cheap, dependency-free metamorphic pin tests
# =============================================================================
#
# Same derivation for all of them: R(-theta): (x, y) -> (x*cos(t) + y*sin(t),
# -x*sin(t) + y*cos(t)). At t=90deg this simplifies to (x, y) -> (y, -x); at
# t=270deg to (x, y) -> (-y, x). CCW/R(+theta) would give (x,y) -> (-y, x) at
# 90deg instead -- the OPPOSITE of the correct answer -- which is exactly
# what makes this such a cheap, high-signal check: one sign flip anywhere in
# the formula and these invert.


class TestCopperRotateDirectionPin:
    """`requirements/validators/_copper.py::_rotate` -- the function
    REQ-SAFE-01 uses to place copper for clearance/creepage measurement.
    This is the safety path; if only one test in this file survives a
    future refactor, it must be this one.
    """

    def test_ninety_degrees_maps_x_axis_to_negative_y(self):
        """R(-theta): (1,0) at 90 deg -> (0,-1). CCW would give (0,+1)."""
        x, y = copper_rotate(1.0, 0.0, math.radians(90.0))
        assert x == pytest.approx(0.0, abs=1e-9)
        assert y == pytest.approx(-1.0, abs=1e-9)

    def test_two_seventy_degrees_maps_x_axis_to_positive_y(self):
        """R(-theta): (1,0) at 270 deg -> (0,+1). CCW would give (0,-1)."""
        x, y = copper_rotate(1.0, 0.0, math.radians(270.0))
        assert x == pytest.approx(0.0, abs=1e-9)
        assert y == pytest.approx(1.0, abs=1e-9)

    def test_matches_reproduced_pcbnew_ground_truth_at_37_degrees(self):
        """Hardcoded from a real ``pcbnew`` run (not this test's own
        arithmetic) reproduced while building this test:

            footprint at 37 deg, pad local offset (10, 4) mm
            pcbnew actual: (10.393615, -2.823608)

        Needs no pcbnew at test time (the number is already captured), so
        this always runs -- unlike the Hypothesis oracle test below, which
        skips when pcbnew is unavailable. The R(+theta) answer for the same
        input is (5.579095, 9.212692); if this ever starts asserting
        something close to that instead, the sign flipped back.
        """
        x, y = copper_rotate(10.0, 4.0, math.radians(37.0))
        assert x == pytest.approx(10.393615, abs=1e-5)
        assert y == pytest.approx(-2.823608, abs=1e-5)


class TestOtherRotationImplementationsDirectionPin:
    """Every other *distinct* rotation implementation on this branch that
    is unit-testable without a full board fixture (see the module
    docstring for the full inventory and why the write/parse/export sites
    aren't covered here). Each of these was independently wrong and
    independently fixed -- see ``docs/evidence/2026-07-29-rotation-
    convention-sign-fix-cpsat-rerun.md``'s inventory table -- so each gets
    its own direct pin instead of relying on `_copper.py` staying right.
    """

    def test_setup_stage_rotate_point(self):
        """`deterministic/stages/setup.py::DRCOracleSetupStage._rotate_point`.
        Confirmed unused by any caller today (see its own docstring) --
        pinned anyway so a future caller inherits the fix, not the bug.
        """
        stage = DRCOracleSetupStage()
        x, y = stage._rotate_point((1.0, 0.0), 90.0)
        assert x == pytest.approx(0.0, abs=1e-9)
        assert y == pytest.approx(-1.0, abs=1e-9)

    def test_isolation_barrier_project_onto_axis(self):
        """`placer/cp_sat/isolation_barrier.py::_project_onto_barrier_axis`
        -- its own docstring already documents the 4-way rotation table
        this pins the rot=1 row of. Feeds the mains<->SELV isolation-
        barrier placement logic in CP-SAT.
        """
        # rot_value=1 (90deg): local (1,0) -> global (0,-1) per the
        # convention table in the function's own docstring.
        assert _project_onto_barrier_axis(1.0, 0.0, 1, barrier_axis=0) == pytest.approx(
            0.0, abs=1e-9
        )
        assert _project_onto_barrier_axis(1.0, 0.0, 1, barrier_axis=1) == pytest.approx(
            -1.0, abs=1e-9
        )

    def test_courtyard_get_global_polygon(self):
        """`core/courtyard.py::Courtyard.get_global_polygon`. Uses
        ``shapely.affinity.rotate`` rather than raw cos/sin, and was
        missed by the original grep-based sweep for exactly that reason
        (see the evidence doc's method-limitation note) -- caught only
        because fixing the grep-found bugs moved this class's own
        downstream tests. The polygon here is deliberately asymmetric
        about the local origin: a symmetric one (e.g. an axis-aligned box
        centered on the footprint origin) cannot discriminate the sign at
        all, per the docstring on `get_global_polygon` itself.
        """
        courtyard = Courtyard("U1", [(1.0, 0.0), (3.0, 0.0), (3.0, 2.0)])
        polygon = courtyard.get_global_polygon(0.0, 0.0, rotation_idx=1)
        coords = list(polygon.exterior.coords)
        # (1,0) -> (0,-1) under R(-theta) at 90deg. Under the CCW bug this
        # repo used to have, it would land at (0, +1) instead.
        assert any(
            math.isclose(cx, 0.0, abs_tol=1e-9) and math.isclose(cy, -1.0, abs_tol=1e-9)
            for cx, cy in coords
        ), coords

    def test_check_isolation_keepout_rotate(self):
        """`scripts/check_isolation_keepout.py::_rotate` -- the live gate
        enforcing 8.0mm mains<->SELV creepage on ``origin/main`` today
        (per ``docs/evidence/2026-07-29-cross-domain-creepage-rotation-
        convention.md``'s headline finding). Imported the same way
        ``tests/regression/test_metrics_trend.py`` imports
        ``scripts/pipeline_metrics.py`` -- a CLI script, not a package.
        """
        x, y = _check_isolation_keepout._rotate(1.0, 0.0, 90.0)
        assert x == pytest.approx(0.0, abs=1e-9)
        assert y == pytest.approx(-1.0, abs=1e-9)


# =============================================================================
# (b) Property-based differential test against pcbnew as oracle
# =============================================================================


def _pcbnew_oracle_batch(
    interpreter: Path, triples: list[tuple[float, float, float]]
) -> list[tuple[float, float]] | None:
    """Ask real ``pcbnew`` where each (dx, dy, angle_deg) pad offset lands.

    Returns ``None`` (never raises) on any failure, so the caller can skip
    loudly with a specific reason instead of the test erroring opaquely.
    """
    with tempfile.TemporaryDirectory() as tmp:
        in_path = Path(tmp) / "in.json"
        out_path = Path(tmp) / "out.json"
        in_path.write_text(json.dumps(triples))
        try:
            proc = subprocess.run(
                [str(interpreter), str(_ORACLE_SCRIPT), str(in_path), str(out_path)],
                capture_output=True,
                text=True,
                timeout=60,
            )
        except (OSError, subprocess.TimeoutExpired):
            return None
        if proc.returncode != 0 or not out_path.exists():
            return None
        try:
            rows = json.loads(out_path.read_text())
        except (OSError, json.JSONDecodeError):
            return None
        return [(row[0], row[1]) for row in rows]


def _pcbnew_python_or_skip() -> Path:
    interpreter = _resolve_pcbnew_python()
    if interpreter is None:
        pytest.skip(
            "No interpreter with pcbnew bindings found (tried "
            "$TEMPER_PCBNEW_PYTHON, /usr/bin/python3, KiCad.app's bundled "
            "Python) -- the pcbnew-oracle differential test cannot run. "
            "This is an environment gap, not a code defect; see "
            "_resolve_pcbnew_python's docstring. The cheap dependency-free "
            "pin tests above still ran and still guard the sign."
        )
    return interpreter


# LOAD-BEARING FILTER -- see module docstring point 2. At angles within
# ~1 degree of a multiple of 90, R(+theta) and R(-theta) differ by a
# vanishingly small amount (they coincide exactly AT the multiple), so a
# generated example near one is statistically indistinguishable from the
# degenerate case that let this bug hide in the first place. Do not narrow
# or remove this filter to "get more examples through" -- that is exactly
# the failure mode this test exists to prevent.
def _far_from_ninety_multiples(angle_deg: float) -> bool:
    remainder = angle_deg % 90.0
    return 1.0 < remainder < 89.0


_non_degenerate_angles = st.floats(
    min_value=0.0, max_value=360.0, allow_nan=False, allow_infinity=False
).filter(_far_from_ninety_multiples)
_offsets = st.floats(min_value=-50.0, max_value=50.0, allow_nan=False, allow_infinity=False)

# pcbnew stores coordinates as integer nanometers internally (VECTOR2I), so
# feeding it an arbitrary-precision mm float quantizes it to the nearest nm
# before any rotation happens -- confirmed empirically: without this slack,
# Hypothesis reliably finds examples differing from our unquantized Python
# float math by ~1-2e-6mm, purely from that input rounding, not from the
# rotation formula. 5e-6mm (5nm) absorbs that noise with wide margin while
# staying about 5 orders of magnitude tighter than the ~mm-scale error a
# sign flip in the rotation formula actually produces -- so this cannot
# mask the bug, only the oracle's own unit quantization.
_ORACLE_TOLERANCE_MM = 5e-6


class TestCopperRotateAgainstPcbnewOracle:
    @settings(
        max_examples=20,
        deadline=None,
        suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture],
    )
    @given(dx=_offsets, dy=_offsets, angle_deg=_non_degenerate_angles)
    def test_matches_pcbnew_for_non_degenerate_angles(self, dx, dy, angle_deg):
        interpreter = _pcbnew_python_or_skip()
        oracle = _pcbnew_oracle_batch(interpreter, [(dx, dy, angle_deg)])
        if oracle is None:
            pytest.skip(f"pcbnew oracle call failed for interpreter {interpreter}")
        (ox, oy) = oracle[0]
        x, y = copper_rotate(dx, dy, math.radians(angle_deg))
        assert x == pytest.approx(ox, abs=_ORACLE_TOLERANCE_MM), (dx, dy, angle_deg)
        assert y == pytest.approx(oy, abs=_ORACLE_TOLERANCE_MM), (dx, dy, angle_deg)

    def test_exact_ninety_degrees_pinned_not_relied_on_as_discriminator(self):
        """90/270 are pinned too (per this task's brief), but NOT as the
        discriminating case -- see the module docstring for why a
        90-multiple cannot tell R(+theta) from R(-theta) reliably in a
        fixture-shaped test; here it works only because the expected value
        is asserted exactly, not inferred from symmetry.
        """
        interpreter = _pcbnew_python_or_skip()
        oracle = _pcbnew_oracle_batch(interpreter, [(3.0, 7.0, 90.0), (3.0, 7.0, 270.0)])
        if oracle is None:
            pytest.skip(f"pcbnew oracle call failed for interpreter {interpreter}")
        for (dx, dy, angle_deg), (ox, oy) in zip([(3.0, 7.0, 90.0), (3.0, 7.0, 270.0)], oracle):
            x, y = copper_rotate(dx, dy, math.radians(angle_deg))
            assert x == pytest.approx(ox, abs=_ORACLE_TOLERANCE_MM), (dx, dy, angle_deg)
            assert y == pytest.approx(oy, abs=_ORACLE_TOLERANCE_MM), (dx, dy, angle_deg)


class TestCheckIsolationKeepoutRotateAgainstPcbnewOracle:
    """Same oracle, targeting the live mains<->SELV creepage gate
    (`scripts/check_isolation_keepout.py::_rotate`) directly -- it is a
    distinct implementation from `_copper.py::_rotate`, not a shared call,
    and was independently wrong/independently fixed (evidence doc,
    "Known-wrong site #1").
    """

    @settings(
        max_examples=15,
        deadline=None,
        suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture],
    )
    @given(dx=_offsets, dy=_offsets, angle_deg=_non_degenerate_angles)
    def test_matches_pcbnew_for_non_degenerate_angles(self, dx, dy, angle_deg):
        interpreter = _pcbnew_python_or_skip()
        oracle = _pcbnew_oracle_batch(interpreter, [(dx, dy, angle_deg)])
        if oracle is None:
            pytest.skip(f"pcbnew oracle call failed for interpreter {interpreter}")
        (ox, oy) = oracle[0]
        x, y = _check_isolation_keepout._rotate(dx, dy, angle_deg)
        assert x == pytest.approx(ox, abs=_ORACLE_TOLERANCE_MM), (dx, dy, angle_deg)
        assert y == pytest.approx(oy, abs=_ORACLE_TOLERANCE_MM), (dx, dy, angle_deg)
