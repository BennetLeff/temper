"""Differential test: placement round-trip oracle compute in Rust
(temper_design_bundle_python.validation) vs the pinned Python oracle
(Wave 4, Phase 4 — validation remainder slice).

``temper_placer/validation/placement_roundtrip.py`` moves its decision
compute — ``canonical_angle`` (mod-360), ``_angle_diff`` (shortest
signed-magnitude angle difference), ``_pad_key`` (stable per-footprint pad
key), and ``_check_footprint``'s comparison logic (anchor / footprint-angle
/ pad-presence / pad-position / pad-angle checks and mismatch-record
construction) — to the ``validation`` submodule of
``temper_design_bundle_python``. The Python module keeps the file I/O
(KTD4: ``parse_kicad_pcb_v6`` + ``KiBoard.from_file`` re-parse), the
kiutils-tree extraction (written anchors/angles/pad local offsets), the
template ``Component`` attribute reads, the kicad_transform primitives
(``place_local_to_world`` / ``rotate_local_to_world`` stay single-source in
``geometry/kicad_transform.py`` — both arms call the same Python, so the
shared geometry is identical by construction), and the
``_get_footprint_reference`` consumer relationship (the #723 note's
kiutils-free attribute reader stays imported verbatim from
``io/_parse_modules``).

Comparison convention: mismatch records are compared with the concrete
type carried on every leaf and floats via ``float.hex()`` (expected/actual
positions are tuples of floats; scalar angles are floats; the string
leaves carry ``str`` tags).

Sections:
- Differential bit-exactness (pure kernels + full round-trips through both
  the writer and hand-built falsifier boards).
- PBT (hypothesis): five non-vacuous properties.
- Metamorphic relations: three, honestly bounded.
"""

from __future__ import annotations

from pathlib import Path

import temper_design_bundle_python as _tdb
from hypothesis import given, settings
from hypothesis import strategies as st

import tests.validation._placement_roundtrip_py_oracle as _oracle
from temper_placer.io.kicad_parser import parse_kicad_pcb
from temper_placer.io.kicad_writer import PlacementUpdate, write_placements_to_pcb
from temper_placer.validation.placement_roundtrip import (
    RoundTripResult,
)
from temper_placer.validation.placement_roundtrip import (
    canonical_angle as shim_canonical_angle,  # noqa: E402
)
from temper_placer.validation.placement_roundtrip import (
    check_placement_roundtrip as shim_check_placement_roundtrip,  # noqa: E402
)

# Rust symbols under test — must exist or this file fails to collect (RED).
CANONICAL_ANGLE = _tdb.validation.canonical_angle
ANGLE_DIFF = _tdb.validation.angle_diff
PAD_KEY = _tdb.validation.pad_key
CHECK_FOOTPRINT_GEOMETRY = _tdb.validation.check_footprint_geometry

# ---------------------------------------------------------------------------
# Canonicalization
# ---------------------------------------------------------------------------


def _canon_value(v):
    if isinstance(v, float):
        return ("float", v.hex())
    if isinstance(v, int) and not isinstance(v, bool):
        return ("int", v)
    if isinstance(v, bool):
        return ("bool", v)
    if isinstance(v, str):
        return ("str", v)
    if isinstance(v, tuple):
        return ("tuple", tuple(_canon_value(x) for x in v))
    if isinstance(v, list):
        return ("list", [_canon_value(x) for x in v])
    return ("obj", type(v).__name__, repr(v))


def _canon_mismatch(m) -> tuple:
    return (
        m.ref,
        m.kind,
        m.pad,
        _canon_value(m.expected),
        _canon_value(m.actual),
        m.detail,
    )


def _canon_result(r: RoundTripResult) -> tuple:
    return (
        tuple(_canon_mismatch(m) for m in r.mismatches),
        r.checked_components,
        r.checked_pads,
        tuple(r.skipped_refs),
    )


# ---------------------------------------------------------------------------
# Board builders (kiutils-parseable, same shape as test_placement_roundtrip)
# ---------------------------------------------------------------------------


def _board_content(fp_blocks: str) -> str:
    return (
        "(kicad_pcb (version 20240108) (generator pcbnew)\n"
        "  (general (thickness 1.6))\n"
        '  (paper "A4")\n'
        "  (layers\n"
        '    (0 "F.Cu" signal)\n'
        '    (31 "B.Cu" signal)\n'
        '    (44 "Edge.Cuts" user)\n'
        "  )\n"
        "  (setup (pad_to_mask_clearance 0))\n"
        f"{fp_blocks}\n"
        ")\n"
    )


def _fp(
    ref: str,
    at: tuple[float, float, float | None],
    pads: list[tuple[str, float, float, float | None]],
    lib: str = "Test:PART",
) -> str:
    at_x, at_y, at_ang = at
    at_suffix = "" if at_ang is None else f" {at_ang}"
    pad_blocks = []
    for num, px, py, p_ang in pads:
        p_suffix = "" if p_ang is None else f" {p_ang}"
        pad_blocks.append(
            f'    (pad "{num}" smd rect (at {px} {py}{p_suffix}) (size 0.6 1.2)'
            f' (layers "F.Cu" "F.Paste" "F.Mask") (net 1 "n1"))'
        )
    pads_str = "\n".join(pad_blocks)
    return (
        f'  (footprint "{lib}" (layer "F.Cu")\n'
        f"    (tstamp 00000000-0000-0000-0000-000000000001)\n"
        f"    (at {at_x} {at_y}{at_suffix})\n"
        f'    (property "Reference" "{ref}" (at 0 0 0) (layer "F.SilkS"))\n'
        f"{pads_str}\n"
        "  )"
    )


def _template_components(path: Path):
    return parse_kicad_pcb(path, normalize=False).netlist.components


def _placements_dict(items):
    return {
        ref: PlacementUpdate(ref=ref, x=v[0], y=v[1], rotation=v[2])
        for ref, v in items.items()
    }


def _run_roundtrip_both(written_path, positions, rotations, components, epsilon=1e-3):
    oracle = _oracle.check_placement_roundtrip(
        written_path, positions, rotations, components, epsilon=epsilon
    )
    shim = shim_check_placement_roundtrip(
        written_path, positions, rotations, components, epsilon=epsilon
    )
    return _canon_result(oracle), _canon_result(shim)


# ---------------------------------------------------------------------------
# Pure-kernel differentials
# ---------------------------------------------------------------------------


@settings(max_examples=60, deadline=None)
@given(st.floats(min_value=-720.0, max_value=720.0, allow_nan=False, allow_infinity=False))
def test_canonical_angle_differential_random(angle):
    oracle = _oracle.canonical_angle(angle)
    shim = shim_canonical_angle(angle)
    assert shim.hex() == oracle.hex()


def test_canonical_angle_differential_hand_built():
    for angle in [360.0, 0.0, 270.0, -90.0, 720.0, -360.0, 90.5, -0.5, 359.999, 1e-12]:
        assert shim_canonical_angle(angle).hex() == _oracle.canonical_angle(angle).hex(), angle


@settings(max_examples=60, deadline=None)
@given(
    st.floats(min_value=-720.0, max_value=720.0, allow_nan=False, allow_infinity=False),
    st.floats(min_value=-720.0, max_value=720.0, allow_nan=False, allow_infinity=False),
)
def test_angle_diff_differential_random(a, b):
    oracle = _oracle._angle_diff(a, b)
    shim = ANGLE_DIFF(a, b)
    assert shim.hex() == oracle.hex()


@settings(max_examples=40, deadline=None)
@given(st.one_of(st.none(), st.text(min_size=0, max_size=8)), st.integers(min_value=0, max_value=100))
def test_pad_key_differential_random(number, index):
    oracle = _oracle._pad_key(_FakePad(number), index)
    shim = PAD_KEY(number, index)
    assert shim == oracle


class _FakePad:
    def __init__(self, number):
        self.number = number


def test_check_footprint_geometry_kernel_direct():
    """Direct kernel pin: a clean footprint (no mismatches, 2 pads checked)
    and a dropped-rotation footprint (footprint_angle + pad_angle)."""
    # Clean: theta == written angle, anchors agree, pads match.
    mismatches, checked = CHECK_FOOTPRINT_GEOMETRY(
        "U1",
        (10.0, 20.0),          # pos
        (0.0, 0.0),            # rot_center (center offset (0,0) at any angle)
        (10.0, 20.0),          # written anchor == pos
        0.0,                   # theta
        0.0,                   # written angle
        1e-3,                  # epsilon
        [("1", 9.225, 20.0, 0.0), ("2", 10.775, 20.0, 0.0)],  # template pads (world)
        [("1", 9.225, 20.0, 0.0), ("2", 10.775, 20.0, 0.0)],  # written pads (world)
    )
    assert checked == 2
    assert mismatches == []

    # Dropped rotation: written angle 0 vs theta 180 -> footprint_angle and
    # every pad_angle mismatch (intrinsic 0 + delta 180).
    mismatches, checked = CHECK_FOOTPRINT_GEOMETRY(
        "U1",
        (50.0, 60.0),
        (0.0, 0.0),
        (50.0, 60.0),
        180.0,
        0.0,
        1e-3,
        [("1", 49.225, 60.0, 0.0), ("2", 50.775, 60.0, 0.0)],
        [("1", 49.225, 60.0, 0.0), ("2", 50.775, 60.0, 0.0)],
    )
    assert checked == 2
    kinds = [m["kind"] for m in mismatches]
    assert "footprint_angle" in kinds
    assert kinds.count("pad_angle") == 2

    # Missing template pad.
    mismatches, checked = CHECK_FOOTPRINT_GEOMETRY(
        "U1",
        (10.0, 20.0),
        (0.0, 0.0),
        (10.0, 20.0),
        0.0,
        0.0,
        1e-3,
        [("1", 9.225, 20.0, 0.0), ("2", 10.775, 20.0, 0.0)],
        [("1", 9.225, 20.0, 0.0)],
    )
    assert [m["kind"] for m in mismatches] == ["pad_missing"]
    assert checked == 1


# ---------------------------------------------------------------------------
# Full round-trip differentials (through the written FILE — KTD4)
# ---------------------------------------------------------------------------


class TestRoundTripDifferential:
    def test_identity_write(self, tmp_path):
        content = _board_content(
            _fp("U1", (10.0, 20.0, None), [("1", -0.775, 0.0, None), ("2", 0.775, 0.0, None)])
        )
        template = tmp_path / "template.kicad_pcb"
        template.write_text(content, encoding="utf-8")
        components = _template_components(template)
        out = tmp_path / "out.kicad_pcb"
        write_placements_to_pcb(
            template, out, _placements_dict({"U1": (10.0, 20.0, 0.0)}), components=components
        )
        oracle, shim = _run_roundtrip_both(out, {"U1": (10.0, 20.0)}, {}, components)
        assert shim == oracle
        assert shim[0] == ()  # pass

    def test_rotated_with_intrinsic_pad_angle(self, tmp_path):
        content = _board_content(
            _fp("U1", (10.0, 20.0, None), [("1", -0.775, 0.0, 90.0), ("2", 0.775, 0.0, 90.0)])
        )
        template = tmp_path / "template.kicad_pcb"
        template.write_text(content, encoding="utf-8")
        components = _template_components(template)
        out = tmp_path / "out.kicad_pcb"
        write_placements_to_pcb(
            template, out, _placements_dict({"U1": (50.0, 60.0, 180.0)}), components=components
        )
        oracle, shim = _run_roundtrip_both(out, {"U1": (50.0, 60.0)}, {"U1": 180.0}, components)
        assert shim == oracle
        assert shim[0] == ()

    def test_center_offset_component(self, tmp_path):
        content = _board_content(
            _fp(
                "Q1",
                (10.0, 20.0, None),
                [("1", 0.0, 0.0, None), ("2", 10.0, 0.0, None), ("3", 20.0, 0.0, None)],
                lib="Test:TO247",
            )
        )
        template = tmp_path / "template.kicad_pcb"
        template.write_text(content, encoding="utf-8")
        components = _template_components(template)
        out = tmp_path / "out.kicad_pcb"
        write_placements_to_pcb(
            template, out, _placements_dict({"Q1": (100.0, 100.0, 90.0)}), components=components
        )
        oracle, shim = _run_roundtrip_both(out, {"Q1": (100.0, 100.0)}, {"Q1": 90.0}, components)
        assert shim == oracle
        assert shim[0] == ()

    def test_dropped_rotation_fails_both(self, tmp_path):
        content = _board_content(
            _fp("U1", (10.0, 20.0, None), [("1", -0.775, 0.0, None), ("2", 0.775, 0.0, None)])
        )
        template = tmp_path / "template.kicad_pcb"
        template.write_text(content, encoding="utf-8")
        components = _template_components(template)
        out = tmp_path / "out.kicad_pcb"
        write_placements_to_pcb(
            template, out, _placements_dict({"U1": (50.0, 60.0, 0.0)}), components=components
        )
        oracle, shim = _run_roundtrip_both(out, {"U1": (50.0, 60.0)}, {"U1": 180.0}, components)
        assert shim == oracle
        assert shim[0]  # both fail

    def test_sign_flip_fails_both(self, tmp_path):
        content = _board_content(
            _fp(
                "Q1",
                (10.0, 20.0, None),
                [("1", 0.0, 0.0, None), ("2", 20.0, 8.0, None)],
                lib="Test:TO247",
            )
        )
        template = tmp_path / "template.kicad_pcb"
        template.write_text(content, encoding="utf-8")
        components = _template_components(template)
        pos = (100.0, 100.0)
        theta = 37.0
        wrong_anchor = (94.4209, 90.7873)
        mutant = tmp_path / "mutant.kicad_pcb"
        mutant.write_text(
            _board_content(
                _fp(
                    "Q1",
                    (wrong_anchor[0], wrong_anchor[1], theta),
                    [("1", 0.0, 0.0, theta), ("2", 20.0, 8.0, theta)],
                    lib="Test:TO247",
                )
            ),
            encoding="utf-8",
        )
        oracle, shim = _run_roundtrip_both(mutant, {"Q1": pos}, {"Q1": theta}, components)
        assert shim == oracle
        assert any(m[1] == "footprint_anchor" for m in shim[0])

    def test_missing_template_pad_reported_both(self, tmp_path):
        """A template pad absent from the written footprint -> pad_missing."""
        content = _board_content(
            _fp("U1", (10.0, 20.0, None), [("1", -0.775, 0.0, None), ("2", 0.775, 0.0, None)])
        )
        template = tmp_path / "template.kicad_pcb"
        template.write_text(content, encoding="utf-8")
        components = _template_components(template)
        # Written board with only pad "1".
        mutant = tmp_path / "mutant.kicad_pcb"
        mutant.write_text(
            _board_content(
                _fp("U1", (10.0, 20.0, None), [("1", -0.775, 0.0, None)])
            ),
            encoding="utf-8",
        )
        oracle, shim = _run_roundtrip_both(mutant, {"U1": (10.0, 20.0)}, {}, components)
        assert shim == oracle
        assert any(m[1] == "pad_missing" for m in shim[0])

    def test_missing_ref_and_skipped_ref(self, tmp_path):
        """A model ref absent from the board -> footprint_missing; a ref with
        no template component -> skipped."""
        content = _board_content(
            _fp("U1", (10.0, 20.0, None), [("1", -0.775, 0.0, None), ("2", 0.775, 0.0, None)])
            + "\n"
            + _fp("U2", (10.0, 40.0, None), [("1", -0.775, 0.0, None), ("2", 0.775, 0.0, None)])
        )
        template = tmp_path / "template.kicad_pcb"
        template.write_text(content, encoding="utf-8")
        components = _template_components(template)
        dropped = tmp_path / "dropped.kicad_pcb"
        dropped.write_text(
            _board_content(
                _fp("U1", (10.0, 20.0, None), [("1", -0.775, 0.0, None), ("2", 0.775, 0.0, None)])
            ),
            encoding="utf-8",
        )
        oracle, shim = _run_roundtrip_both(
            dropped, {"U1": (10.0, 20.0), "U2": (10.0, 40.0), "U3": (1.0, 1.0)}, {}, components
        )
        assert shim == oracle
        assert any(m[1] == "footprint_missing" for m in shim[0])
        assert any("no template component" in s for s in shim[3])

    def test_refstar_footprints_skipped_both(self, tmp_path):
        """REF** placeholder footprints are excluded from the written map."""
        content = _board_content(
            _fp("U1", (10.0, 20.0, None), [("1", -0.775, 0.0, None), ("2", 0.775, 0.0, None)])
            + '\n  (footprint "Test:REF" (layer "F.Cu")\n'
            '    (tstamp 00000000-0000-0000-0000-000000000099)\n'
            '    (at 0 0)\n'
            '    (property "Reference" "REF**" (at 0 0 0) (layer "F.SilkS"))\n  )'
        )
        template = tmp_path / "template.kicad_pcb"
        template.write_text(content, encoding="utf-8")
        components = _template_components(template)
        out = tmp_path / "out.kicad_pcb"
        write_placements_to_pcb(
            template, out, _placements_dict({"U1": (10.0, 20.0, 0.0)}), components=components
        )
        oracle, shim = _run_roundtrip_both(out, {"U1": (10.0, 20.0)}, {}, components)
        assert shim == oracle
        assert shim[0] == ()

    def test_unparseable_board_is_parse_error_both(self, tmp_path):
        bad = tmp_path / "bad.kicad_pcb"
        bad.write_text("not a kicad pcb at all ((((", encoding="utf-8")
        oracle, shim = _run_roundtrip_both(bad, {"U1": (0.0, 0.0)}, {}, [])
        assert shim == oracle
        assert any(m[1] == "parse_error" for m in shim[0])


# ---------------------------------------------------------------------------
# PBT — five non-vacuous properties (R1c)
# ---------------------------------------------------------------------------


@settings(max_examples=40, deadline=None)
@given(st.floats(min_value=-720.0, max_value=720.0, allow_nan=False, allow_infinity=False))
def test_prop1_canonical_angle_in_unit_interval(angle):
    """canonical_angle maps every input into [0, 360]. The upper bound is
    INCLUSIVE: CPython's float_rem (transcribed by the kernel) yields
    exactly 360.0 for a tiny negative input whose |value| is below
    ulp(360) -- fmod gives the negative remainder and the sign-correction
    ``mod += b`` rounds it to 360.0. That IS the oracle's value (the
    differential pins it bit-for-bit); the invariant is
    ``0 <= out <= 360`` with 360.0 meaning 0 (mod 360)."""
    out = shim_canonical_angle(angle)
    assert 0.0 <= out <= 360.0


@settings(max_examples=40, deadline=None)
@given(
    st.floats(min_value=-720.0, max_value=720.0, allow_nan=False, allow_infinity=False),
    st.floats(min_value=-720.0, max_value=720.0, allow_nan=False, allow_infinity=False),
)
def test_prop2_angle_diff_is_symmetric_bounded(a, b):
    """angle_diff is symmetric, non-negative, and <= 180 (the shortest
    signed-magnitude difference)."""
    d = ANGLE_DIFF(a, b)
    assert 0.0 <= d <= 180.0
    assert d == ANGLE_DIFF(b, a)


def test_prop3_angle_diff_of_equal_angles_is_zero():
    for a in [0.0, 90.0, 180.0, 270.0, 360.0, -90.0, 37.5, 359.999]:
        assert ANGLE_DIFF(a, a) == 0.0
        assert ANGLE_DIFF(a, a + 360.0) == 0.0
        assert ANGLE_DIFF(a, a - 360.0) == 0.0


@settings(max_examples=40, deadline=None)
@given(
    st.one_of(st.none(), st.text(min_size=0, max_size=8)),
    st.integers(min_value=0, max_value=100),
)
def test_prop4_pad_key_is_unique_and_stable(number, index):
    """A pad with a number keys by its number; a numbered pad and an
    unnumbered pad at the same index never collide."""
    key = PAD_KEY(number, index)
    assert key == (number or f"__pad_{index}")
    # The positional fallback embeds the index, so two unnumbered pads at
    # different indices never collide.
    if number is None:
        assert PAD_KEY(None, index) != PAD_KEY(None, index + 1)


def test_prop5_roundtrip_pass_implies_every_checked_pad_matched():
    """A PASS result with checked pads implies each template pad had a
    written counterpart (no silent pad drop is consistent with a pass)."""
    content = _board_content(
        _fp("U1", (10.0, 20.0, None), [("1", -0.775, 0.0, None), ("2", 0.775, 0.0, None)])
    )
    import tempfile

    with tempfile.TemporaryDirectory() as td:
        template = Path(td) / "template.kicad_pcb"
        template.write_text(content, encoding="utf-8")
        components = _template_components(template)
        out = Path(td) / "out.kicad_pcb"
        write_placements_to_pcb(
            template, out, _placements_dict({"U1": (10.0, 20.0, 0.0)}), components=components
        )
        result = shim_check_placement_roundtrip(out, {"U1": (10.0, 20.0)}, {}, components)
        assert result.passed
        assert result.checked_pads == 2
        assert result.checked_components == 1


# ---------------------------------------------------------------------------
# Metamorphic relations (R1d)
# ---------------------------------------------------------------------------


def test_mr1_adding_360_to_an_angle_is_identity_for_roundtrip():
    """Rotating by theta vs theta+360 produces identical round-trip results
    (mod-360 canonicalization makes them equivalent)."""
    content = _board_content(
        _fp("U1", (10.0, 20.0, 270.0), [("1", -0.775, 0.0, 270.0), ("2", 0.775, 0.0, 270.0)])
    )
    import tempfile

    with tempfile.TemporaryDirectory() as td:
        template = Path(td) / "template.kicad_pcb"
        template.write_text(content, encoding="utf-8")
        components = _template_components(template)
        out1 = Path(td) / "o1.kicad_pcb"
        out2 = Path(td) / "o2.kicad_pcb"
        write_placements_to_pcb(
            template, out1, _placements_dict({"U1": (50.0, 60.0, 45.0)}), components=components
        )
        write_placements_to_pcb(
            template, out2, _placements_dict({"U1": (50.0, 60.0, 405.0)}), components=components
        )
        r1 = _canon_result(shim_check_placement_roundtrip(out1, {"U1": (50.0, 60.0)}, {"U1": 45.0}, components))
        r2 = _canon_result(shim_check_placement_roundtrip(out2, {"U1": (50.0, 60.0)}, {"U1": 405.0}, components))
        assert r1 == r2


def test_mr2_epsilon_monotonicity_of_mismatch_count():
    """Raising epsilon can only shrink the mismatch set (comparisons are
    `abs(diff) > epsilon`)."""
    content = _board_content(
        _fp("U1", (10.0, 20.0, None), [("1", -0.775, 0.0, None), ("2", 0.775, 0.0, None)])
    )
    import tempfile

    with tempfile.TemporaryDirectory() as td:
        template = Path(td) / "template.kicad_pcb"
        template.write_text(content, encoding="utf-8")
        components = _template_components(template)
        out = Path(td) / "out.kicad_pcb"
        write_placements_to_pcb(
            template, out, _placements_dict({"U1": (50.0, 60.0, 0.0)}), components=components
        )
        tight = shim_check_placement_roundtrip(
            out, {"U1": (50.0, 60.0)}, {"U1": 180.0}, components, epsilon=1e-6
        )
        loose = shim_check_placement_roundtrip(
            out, {"U1": (50.0, 60.0)}, {"U1": 180.0}, components, epsilon=1e-1
        )
        assert len(loose.mismatches) <= len(tight.mismatches)


def test_mr3_translating_a_component_preserves_relative_findings():
    """Translating a component's written anchor and model position by the
    same delta preserves the mismatch KINDS (the comparisons are on
    differences, translation-invariant)."""
    content = _board_content(
        _fp("Q1", (10.0, 20.0, None), [("1", 0.0, 0.0, None), ("2", 20.0, 8.0, None)], lib="Test:TO247")
    )
    import tempfile

    with tempfile.TemporaryDirectory() as td:
        template = Path(td) / "template.kicad_pcb"
        template.write_text(content, encoding="utf-8")
        components = _template_components(template)
        pos = (100.0, 100.0)
        theta = 37.0
        wrong_anchor = (94.4209, 90.7873)

        def kinds_for(anchor, model_pos, shift):
            mutant = Path(td) / f"m{shift}.kicad_pcb"
            mutant.write_text(
                _board_content(
                    _fp(
                        "Q1",
                        (anchor[0] + shift[0], anchor[1] + shift[1], theta),
                        [("1", 0.0, 0.0, theta), ("2", 20.0, 8.0, theta)],
                        lib="Test:TO247",
                    )
                ),
                encoding="utf-8",
            )
            res = shim_check_placement_roundtrip(
                mutant,
                {"Q1": (model_pos[0] + shift[0], model_pos[1] + shift[1])},
                {"Q1": theta},
                components,
            )
            return {m.kind for m in res.mismatches}

        base = kinds_for(wrong_anchor, pos, (0.0, 0.0))
        shifted = kinds_for(wrong_anchor, pos, (25.0, -17.0))
        assert base == shifted
        assert "footprint_anchor" in base and "pad_position" in base
