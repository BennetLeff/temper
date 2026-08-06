"""Differential tests: ``placer/template.py`` compute vs the pinned oracle.

Wave 4 Phase 4: the geometry compute of ``ComponentTemplate.apply`` and
``ParametricTemplate.apply`` (anchor-offset scaling, KiCad R(-theta)
rotation around the anchor, absolute placement, modulo-360 composite
rotation) moved to ``temper-io-types/placer_core/placer_compute.rs``,
exposed as ``temper_io_types.placer_apply_component_template`` /
``placer_apply_parametric_template``. The dataclasses, the ``create_*``
data constructors and ``load_template_from_yaml`` (a ``yaml.safe_load``
library seam) stay Python in the delegation shim; the two ``apply``
methods delegate.

The oracle is the verbatim pre-migration module in
``tests/placer/_placer_py_oracle/template.py``.

Bit-exactness notes (see the module docstring of the oracle):
- The rotation transcendental (``math.cos``/``math.sin``) is a Python seam:
  the shim passes a ``(cos, sin)`` callable into the Rust kernel, so the
  oracle's libm bits are preserved by construction. Rust's ``f64::sin`` is
  NOT bit-identical to CPython's ``math.sin`` on this platform (measured
  461/200k 1-ULP mismatches 2026-08-05), which is why the seam exists.
- ``math.radians`` is CPython's ``x * (pi/180)`` (precomputed ratio), NOT
  ``(x*pi)/180``; the kernel transcribes the ratio form.
- ``% 360`` uses Python's floored-modulo semantics (the kernel applies it
  via ``py_mod``), so negative rotations are covered, not assumed away.
- The R(-theta) rotation formula is transcribed from
  ``kicad_transform.rotate_local_to_world``: ``(x*c + y*s, -x*s + y*c)``
  with ``c, s`` from the seam.

RED state: this file fails to collect with ``AttributeError: module
'temper_io_types' has no attribute 'placer_apply_component_template'``
until the Rust kernels land (the TDD-RED evidence).
"""

from __future__ import annotations

import math
import tempfile
from pathlib import Path

import pytest
import yaml

import temper_io_types as _t

from temper_placer.placer.template import (
    ComponentPosition,
    ComponentTemplate,
    HalfBridgeTemplate,
    ParametricComponentPosition,
    ParametricTemplate,
    load_template_from_yaml,
)
from tests.placer._placer_diff import assert_placement_equal
from tests.placer._placer_py_oracle import template as oracle

# The Rust surface this differential pins. Imported at module level so the
# RED state is a collection failure (AttributeError) before the kernels
# land, per the TDD convention.
placer_apply_component_template = _t.placer_apply_component_template
placer_apply_parametric_template = _t.placer_apply_parametric_template


def _cos_sin(theta):
    return (math.cos(theta), math.sin(theta))

_ROTATIONS = [0, 90, 180, 270, -90, 45, 137, 359, 360, 720, -45, -270]


def _prod_template(components, anchor_point=None, name="t"):
    return ComponentTemplate(
        name=name,
        components=components,
        anchor_point=anchor_point,
    )


def _oracle_template(components, anchor_point=None, name="t"):
    return oracle.ComponentTemplate(
        name=name,
        components=components,
        anchor_point=anchor_point,
    )


@pytest.mark.parametrize("rotation", _ROTATIONS)
def test_component_template_apply_matches(rotation):
    comps = [
        ComponentPosition("Q1", 0.0, 0.0, 0),
        ComponentPosition("Q2", 0.0, -20.0, 0),
        ComponentPosition("D1", 10.0, 0.0, 90),
        ComponentPosition("D2", 10.0, -20.0, 270),
        ComponentPosition("C1", 28.0, -5.0, 180),
    ]
    anchor = comps[0].ref
    for anchor_x, anchor_y in [(25.0, 25.0), (0.0, 0.0), (-12.5, 7.25)]:
        prod = _prod_template(comps, anchor).apply(anchor_x, anchor_y, rotation=rotation)
        ref = _oracle_template(comps, anchor).apply(anchor_x, anchor_y, rotation=rotation)
        assert_placement_equal(prod, ref)


def test_component_template_anchor_is_not_first():
    comps = [
        ComponentPosition("Q1", 0.0, 0.0, 0),
        ComponentPosition("Q2", 0.0, -20.0, 90),
    ]
    prod = _prod_template(comps, anchor_point="Q2").apply(30.0, 40.0, rotation=90)
    ref = _oracle_template(comps, anchor_point="Q2").apply(30.0, 40.0, rotation=90)
    assert_placement_equal(prod, ref)


def test_component_template_anchor_not_found_raises():
    comps = [ComponentPosition("Q1", 0.0, 0.0, 0)]
    with pytest.raises(ValueError, match="not found in template"):
        _prod_template(comps, anchor_point="MISSING").apply(1.0, 2.0)
    with pytest.raises(ValueError, match="not found in template"):
        _oracle_template(comps, anchor_point="MISSING").apply(1.0, 2.0)


@pytest.mark.parametrize("rotation", [0, 90, 180, 270, -90, 45])
def test_parametric_template_apply_matches(rotation):
    comps = [
        ParametricComponentPosition("Q1", 0.2, 0.8),
        ParametricComponentPosition("Q2", 0.2, 0.2),
        ParametricComponentPosition("D1", 0.5, 0.8, 90),
        ParametricComponentPosition("C1", 0.8, 0.5, 180),
    ]
    for anchor_x, anchor_y in [(50.0, 50.0), (0.0, 0.0)]:
        for tw, th in [(100.0, 100.0), (40.0, 30.0), (17.5, 9.25)]:
            prod = ParametricTemplate("p", comps, "Q1").apply(
                anchor_x, anchor_y, tw, th, rotation=rotation
            )
            ref = oracle.ParametricTemplate("p", comps, "Q1").apply(
                anchor_x, anchor_y, tw, th, rotation=rotation
            )
            assert_placement_equal(prod, ref)


def test_parametric_template_default_anchor_center():
    # anchor_ref not among components -> oracle falls back to the template
    # center (0.5 * target dims).
    comps = [ParametricComponentPosition("Q1", 0.2, 0.8)]
    prod = ParametricTemplate("p", comps, "NOPE").apply(10.0, 20.0, 100.0, 50.0, rotation=90)
    ref = oracle.ParametricTemplate("p", comps, "NOPE").apply(10.0, 20.0, 100.0, 50.0, rotation=90)
    assert_placement_equal(prod, ref)


def test_create_half_bridge_parametric_data_matches():
    prod = ParametricTemplate.create_half_bridge()
    ref = oracle.ParametricTemplate.create_half_bridge()
    assert prod.name == ref.name == "half_bridge_parametric"
    assert prod.anchor_ref == ref.anchor_ref == "Q1"
    assert len(prod.components) == len(ref.components) == 6
    for pc, rc in zip(prod.components, ref.components):
        assert pc.ref == rc.ref
        assert pc.x_ratio == rc.x_ratio
        assert pc.y_ratio == rc.y_ratio
        assert pc.rotation == rc.rotation


def test_half_bridge_vertical_matches():
    prod = HalfBridgeTemplate.create_vertical()
    ref = oracle.HalfBridgeTemplate.create_vertical()
    assert prod.name == ref.name == "half_bridge_vertical"
    assert prod.anchor_point == ref.anchor_point == "Q1"
    for rotation in [0, 180]:
        for ax, ay in [(30.0, 30.0), (0.0, 0.0)]:
            assert_placement_equal(
                prod.apply(ax, ay, rotation=rotation), ref.apply(ax, ay, rotation=rotation)
            )


def test_component_template_get_anchor_position_matches():
    comps = [ComponentPosition("Q1", 0.0, 0.0, 0), ComponentPosition("Q2", 5.0, 5.0, 0)]
    prod = _prod_template(comps, anchor_point="Q2")
    ref = _oracle_template(comps, anchor_point="Q2")
    assert prod.get_anchor_position().ref == ref.get_anchor_position().ref
    assert _prod_template(comps).get_anchor_position().ref == comps[0].ref
    assert _oracle_template(comps).get_anchor_position().ref == comps[0].ref


def test_load_template_from_yaml_matches(tmp_path: Path):
    data = {
        "name": "half_bridge_vertical",
        "anchor_point": "Q1",
        "description": "Vertical half-bridge layout",
        "width": 43.0,
        "height": 40.0,
        "components": [
            {"ref": "Q1", "x": 0.0, "y": 0.0, "rotation": 0},
            {"ref": "Q2", "x": 0.0, "y": -25.0, "rotation": 0},
            {"ref": "D1", "x": 18.0, "y": 0.0, "rotation": 90},
        ],
    }
    path = tmp_path / "tpl.yaml"
    path.write_text(yaml.safe_dump(data))
    prod = load_template_from_yaml(path)
    ref = oracle.load_template_from_yaml(path)
    assert prod.name == ref.name
    assert prod.anchor_point == ref.anchor_point
    assert prod.width == ref.width
    assert prod.height == ref.height
    assert prod.description == ref.description
    for pc, rc in zip(prod.components, ref.components):
        assert pc.ref == rc.ref and pc.x == rc.x and pc.y == rc.y and pc.rotation == rc.rotation
    assert_placement_equal(prod.apply(10.0, 10.0, rotation=90), ref.apply(10.0, 10.0, rotation=90))


def test_component_template_kernel_matches_oracle():
    # Direct kernel-vs-oracle pin (bypassing the shim): the kernel's raw
    # placement sequence must equal the oracle's dict, given the same flat
    # template data and anchor inputs the shim marshals.
    comps = [
        ComponentPosition("Q1", 0.0, 0.0, 0),
        ComponentPosition("Q2", 0.0, -20.0, 90),
        ComponentPosition("D1", 10.0, 0.0, 270),
    ]
    for rotation in [0, 90, 180, -90, 45]:
        for ax, ay in [(25.0, 25.0), (-1.5, 7.25)]:
            ref = _oracle_template(comps, comps[0].ref).apply(ax, ay, rotation=rotation)
            out = placer_apply_component_template(
                [c.ref for c in comps],
                [c.x for c in comps],
                [c.y for c in comps],
                [c.rotation for c in comps],
                0,
                ax,
                ay,
                rotation,
                _cos_sin,
            )
            assert_placement_equal(dict(out), ref)


def test_parametric_template_kernel_matches_oracle():
    comps = [
        ParametricComponentPosition("Q1", 0.2, 0.8),
        ParametricComponentPosition("Q2", 0.2, 0.2, 90),
    ]
    for rotation in [0, 90, -90, 270, 45]:
        for ax, ay, tw, th in [(50.0, 50.0, 100.0, 100.0), (0.0, 0.0, 40.0, 30.0)]:
            ref = oracle.ParametricTemplate("p", comps, "Q1").apply(
                ax, ay, tw, th, rotation=rotation
            )
            out = placer_apply_parametric_template(
                [c.ref for c in comps],
                [c.x_ratio for c in comps],
                [c.y_ratio for c in comps],
                [c.rotation for c in comps],
                (comps[0].x_ratio, comps[0].y_ratio),
                ax,
                ay,
                tw,
                th,
                rotation,
                _cos_sin,
            )
            assert_placement_equal(dict(out), ref)


def test_parametric_template_kernel_default_anchor_matches_oracle():
    comps = [ParametricComponentPosition("Q1", 0.2, 0.8)]
    ref = oracle.ParametricTemplate("p", comps, "NOPE").apply(10.0, 20.0, 100.0, 50.0, rotation=90)
    out = placer_apply_parametric_template(
        [c.ref for c in comps],
        [c.x_ratio for c in comps],
        [c.y_ratio for c in comps],
        [c.rotation for c in comps],
        None,
        10.0,
        20.0,
        100.0,
        50.0,
        90,
        _cos_sin,
    )
    assert_placement_equal(dict(out), ref)
