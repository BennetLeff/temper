"""U1: zone emission primitive — tests."""

from __future__ import annotations

from temper_placer.router_v6.zone_emission import (
    ZoneDefinition,
    compute_zone_for_net,
    emit_zone_s_expr,
)


def test_compute_zone_for_two_pads():
    zd = compute_zone_for_net("GND", 1, [(0.0, 0.0), (10.0, 0.0)])
    assert zd.net_name == "GND"
    assert zd.net_number == 1
    assert zd.layer == "F.Cu"
    assert len(zd.points) == 4  # bounding box corners


def test_compute_zone_for_empty_pads_raises():
    import pytest
    with pytest.raises(ValueError):
        compute_zone_for_net("EMPTY", 1, [])


def test_emit_zone_s_expr_contains_zone_keyword():
    zd = compute_zone_for_net("+3V3", 5, [(0.0, 0.0), (5.0, 0.0), (0.0, 5.0)])
    expr = emit_zone_s_expr(zd)
    assert "(zone " in expr
    assert '(net_name "+3V3")' in expr
    assert "(net 5)" in expr
    assert "(layer " in expr
    assert "(polygon " in expr


def test_pwr_rtn_gets_bcu_layer():
    zd = compute_zone_for_net("PWR_RTN", 1, [(0.0, 0.0), (10.0, 0.0)], layer="B.Cu")
    assert zd.layer == "B.Cu"


def test_emit_zone_s_expr_includes_fill_directive():
    """Regression: without (fill yes ...), a zone is only an outline
    polygon -- KiCad DRC's connectivity check sees it as no copper at
    all. CI's kicad-cli 8.0.9 doesn't support --refill-zones, so the
    fill directive must live in the emitted geometry itself, not a CLI
    flag, to work across KiCad versions."""
    zd = compute_zone_for_net("GND", 1, [(0.0, 0.0), (10.0, 0.0)])
    expr = emit_zone_s_expr(zd)
    assert "(fill yes" in expr
