"""An unresolvable net class must fail loudly, never silently thin --
EXCEPT for a caller that never wires up per-net classification at all.

``packages/temper-drc-rs/src/board_py_bridge.rs::build_board_state`` (the
K1-schema dict path ``temper_drc_rs.run_drc`` takes, exercised through the
same ``temper_drc_rs.run_drc``/``serialize_board_state`` entry points CI
uses) used to fall back to the THINNEST rule set on the board -- 0.2mm
trace width, 0.2mm clearance -- whenever a net's class could not be
resolved:

  - the net had no entry at all in ``net_classes`` (the dict-omission
    shape), or
  - the net's class had no matching entry in ``net_class_rules`` (the
    "resolved to a class nobody defined rules for" shape -- exactly what a
    stale/mistyped ``net_classes:`` config key produces; see
    ``scripts/check_netclass_map_board_correspondence.py``, which found 31
    such broken keys across 4 config files on this repo's mains board).

Silently applying 0.2mm clearance instead of, say, an 8.0mm reinforced
creepage requirement on a mains-voltage net is fail-OPEN: CI reports the
board clean on a clearance it never actually met. This closes that: both
shapes now raise instead of returning a degraded ``BoardState`` --
**provided the caller supplied ``net_classes``/``net_class_rules`` at
all**. A board whose ``net_classes``/``net_class_rules`` maps are BOTH
completely empty is a caller whose schema never carries per-net
classification in the first place -- concretely,
``temper_drc_rs.DrcBoardSnapshot.from_state`` (the CP-SAT/router
``Placement`` path) always builds an empty ``net_class_rules``, and its
real caller (``router_v6/_pipeline_verify.py::_parsed_pcb_to_drc_input``)
never populates ``Placement.net_classes`` even in production. Refusing to
run there unconditionally would make DRC entirely inoperable for that
whole pipeline rather than catch a real misconfiguration, so the legacy
"Unknown" class / thin default is preserved ONLY when the map is
completely empty -- never when it is populated but missing THIS ONE net,
which is the actual bug this file guards against.

The Rust-level unit tests (``board_py_bridge.rs::tests`` and
``drc_marshal.rs::tests``) cover the same shapes directly against
``BoardState``/``DrcBoardSnapshot``; this file proves the fix end-to-end
through the actual Python-facing entry points (``run_drc``,
``serialize_board_state``) CI and the placer/router call, so a fix that
works at the Rust unit level but is not actually wired into those
entry points would still be caught here.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

import temper_drc_rs as _tdrc


def _board_dict(
    *,
    wired: bool,
    net_classes: dict[str, str],
    net_class_rules: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    """A K1-schema board dict with two nets: "OTHER_NET" (always classed
    "Signal", with matching rules, when ``wired`` -- keeps
    ``net_classes``/``net_class_rules`` non-empty so the fixture matches the
    real "caller intended classification but has a gap for THIS net" shape)
    and "AC_L", whose classification the caller controls directly via
    ``net_classes``/``net_class_rules``.

    ``wired=False`` omits "OTHER_NET" entirely, leaving both maps exactly
    as passed in (typically both empty) -- the "this caller never carries
    per-net classification" shape.
    """
    nets = {"AC_L": []}
    if wired:
        nets["OTHER_NET"] = []
        net_classes = {**net_classes, "OTHER_NET": "Signal"}
        net_class_rules = {
            **net_class_rules,
            "Signal": {"trace_width_mm": 0.25, "clearance_mm": 0.2},
        }
    return {
        "board": {"width_mm": 100.0, "height_mm": 100.0, "margin_mm": 3.0},
        "components": [],
        "nets": nets,
        "net_classes": net_classes,
        "net_class_rules": net_class_rules,
    }


# A minimal constraints dict -- every field of the engine's ConstraintSet
# defaults, so `{}` is valid; run_drc's own K1-schema dict path is what's
# under test here, not constraint parsing.
_CONSTRAINTS: dict[str, Any] = {}


def test_net_missing_from_net_classes_is_hard_error_when_wired():
    """A net absent from a net_classes map that IS otherwise populated
    (another net is correctly classed) must raise, not silently default --
    the caller clearly intended per-net classification and has a gap."""
    board_dict = _board_dict(wired=True, net_classes={}, net_class_rules={})
    with pytest.raises(ValueError, match=r"AC_L.*net_classes"):
        _tdrc.run_drc(board_dict, _CONSTRAINTS)


def test_net_class_missing_from_net_class_rules_is_hard_error_when_wired():
    """A net that DID resolve to a class name, but that class has no
    matching ``net_class_rules`` entry in an otherwise-populated
    ``net_class_rules`` map, must also raise -- this is the shape a
    stale/mistyped ``net_classes:`` config key produces (the net resolves
    to *some* class string, just not one anyone defined rules for)."""
    board_dict = _board_dict(
        wired=True, net_classes={"AC_L": "ACMains"}, net_class_rules={}
    )
    with pytest.raises(ValueError, match=r"AC_L.*ACMains.*net_class_rules"):
        _tdrc.run_drc(board_dict, _CONSTRAINTS)


def test_serialize_board_state_also_hard_errors_when_wired():
    """``serialize_board_state`` shares ``build_board_state`` with
    ``run_drc`` -- confirm the fix is not path-specific."""
    board_dict = _board_dict(wired=True, net_classes={}, net_class_rules={})
    with pytest.raises(ValueError, match=r"AC_L.*net_classes"):
        _tdrc.serialize_board_state(board_dict)


def test_resolvable_net_class_is_unaffected():
    """Sanity/no-false-positive: a net whose class DOES resolve must keep
    working, with the REAL (non-thinned) rules actually applied -- not
    just "doesn't raise"."""
    board_dict = _board_dict(
        wired=True,
        net_classes={"AC_L": "ACMains"},
        net_class_rules={"ACMains": {"trace_width_mm": 1.5, "clearance_mm": 8.0}},
    )
    # Must not raise.
    _tdrc.run_drc(board_dict, _CONSTRAINTS)

    state = json.loads(_tdrc.serialize_board_state(board_dict))
    (net,) = [n for n in state["nets"] if n["name"] == "AC_L"]
    assert net["rules"]["clearance_mm"] == 8.0
    assert net["rules"]["trace_width_mm"] == 1.5


def test_completely_unwired_board_keeps_legacy_default_not_a_hard_error():
    """A board whose ``net_classes``/``net_class_rules`` maps are BOTH
    completely empty is a caller that never wires up per-net
    classification at all (e.g. the CP-SAT/router ``Placement`` path via
    ``DrcBoardSnapshot.from_state`` -- see this file's module docstring).
    Refusing to run there unconditionally would make DRC entirely
    inoperable for that pipeline, so it keeps the legacy "Unknown" class /
    thin default instead of raising."""
    board_dict = _board_dict(wired=False, net_classes={}, net_class_rules={})
    # Must not raise.
    _tdrc.run_drc(board_dict, _CONSTRAINTS)

    state = json.loads(_tdrc.serialize_board_state(board_dict))
    (net,) = [n for n in state["nets"] if n["name"] == "AC_L"]
    assert net["class"] == "Unknown"
    assert net["rules"]["trace_width_mm"] == 0.2
    assert net["rules"]["clearance_mm"] == 0.2


def test_regression_thin_default_no_longer_silently_applied_when_wired():
    """Regression proof: pre-fix, BOTH unresolved-class shapes below
    silently produced ``trace_width_mm=0.2, clearance_mm=0.2`` (the
    thinnest rule set on the board) instead of raising, regardless of
    whether the board's classification data was otherwise populated. Prove
    that shape is categorically gone whenever the caller wired up
    classification at all: every unresolved-class board dict below (each
    with a correctly-classed "OTHER_NET" alongside the broken "AC_L") now
    raises, so there is no successful ``BoardState`` left for a 0.2/0.2
    ``NetClassRules`` to hide inside.

    This test fails on the pre-fix code (both calls below returned a
    zero-violation board instead of raising) and passes post-fix.
    """
    for board_dict in [
        _board_dict(wired=True, net_classes={}, net_class_rules={}),
        _board_dict(
            wired=True, net_classes={"AC_L": "ACMains"}, net_class_rules={}
        ),
    ]:
        try:
            _tdrc.run_drc(board_dict, _CONSTRAINTS)
        except ValueError:
            continue  # correct: fails loudly instead of silently thinning.
        pytest.fail(
            "pre-fix regression: an unresolved net class silently ran DRC "
            "instead of raising -- the 0.2mm/0.2mm thin default is back "
            f"(board_dict={board_dict!r})"
        )
