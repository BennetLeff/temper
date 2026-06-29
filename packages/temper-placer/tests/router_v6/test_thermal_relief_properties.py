"""Domain-correctness property tests for Router V6 Stage 5.4: Add Thermal Relief.

Verifies two module-specific invariants beyond the six generic DFM
container invariants exercised by ``test_dfm_hypothesis_fuzzing.py``:

* **R14 — Power-net scoping** (TS1): thermal relief spokes are only
  inserted for nets matching ``_POWER_NET_PATTERN``; signal nets get none.
* **R15 — Spoke count consistency** (TS2, TS3): every ``ThermalRelief``
  has ``spoke_count ≤ configured_spoke_count``, and
  ``report.total_spokes == sum(tr.spoke_count for tr in report.thermal_reliefs)``.

Each property runs 200 iterations with a 2000 ms deadline.
"""

from __future__ import annotations

from hypothesis import HealthCheck, given, settings

from temper_placer.router_v6.routing_results import RoutingResults
from temper_placer.router_v6.thermal_relief import (
    ThermalReliefReport,
    _is_power_net,
    add_thermal_relief,
)
from tests.router_v6.dfm_property_strategies import (
    mixed_net_routing_results,
    realistic_routing_results,
)

# ---------------------------------------------------------------------------
# Shared Hypothesis settings
# ---------------------------------------------------------------------------

_SETTINGS = settings(
    max_examples=200,
    deadline=2000,
    suppress_health_check=[HealthCheck.too_slow],
)

# ---------------------------------------------------------------------------
# R14 — Power-net scoping
# ---------------------------------------------------------------------------


@given(results=mixed_net_routing_results(
    power_nets=("GND", "VCC"),
    signal_nets=("SIG1", "SIG2", "DATA0", "CLK", "RST", "ENABLE", "TX+", "RX-"),
    min_routes=2,
    max_routes=10,
))
@_SETTINGS
def test_thermal_relief_power_net_scoping(results: RoutingResults) -> None:
    """TS1: Power nets may receive thermal reliefs; signal nets must get none.

    Uses ``mixed_net_routing_results`` to guarantee at least one power net
    (GND, VCC) and at least one signal net (SIG1, SIG2, DATA0).
    """
    report: ThermalReliefReport = add_thermal_relief(results)

    # Partition the input nets by power-net classification.
    power_nets: set[str] = set()
    signal_nets: set[str] = set()
    for net_name in results.compiled_routes:
        if _is_power_net(net_name):
            power_nets.add(net_name)
        else:
            signal_nets.add(net_name)

    # Build a set of net names that actually received reliefs.
    relief_nets: set[str] = {tr.net_name for tr in report.thermal_reliefs}

    # Every net that received a relief must be a power net.
    assert relief_nets.issubset(power_nets), (
        f"Non-power nets received thermal reliefs: "
        f"{relief_nets - power_nets}"
    )

    # Signal nets must get exactly zero reliefs.
    signal_relief_count = sum(
        1 for tr in report.thermal_reliefs if tr.net_name in signal_nets
    )
    assert signal_relief_count == 0, (
        f"Signal nets received {signal_relief_count} thermal relief(s)"
    )

    # Power nets may get zero or more reliefs (zero if no via touches a
    # plane layer in this random draw), but every relief must come from a
    # power net — already verified above.
    assert report.relief_count >= 0


# ---------------------------------------------------------------------------
# R15 — Spoke count consistency
# ---------------------------------------------------------------------------


@given(results=realistic_routing_results())
@_SETTINGS
def test_thermal_relief_spoke_count_upper_bound(results: RoutingResults) -> None:
    """TS2: Every ThermalRelief has spoke_count ≤ the configured spoke_count=4."""
    configured_spoke_count = 4
    report: ThermalReliefReport = add_thermal_relief(
        results, spoke_count=configured_spoke_count
    )

    for tr in report.thermal_reliefs:
        assert tr.spoke_count <= configured_spoke_count, (
            f"ThermalRelief for {tr.net_name!r} has spoke_count={tr.spoke_count}, "
            f"but configured spoke_count={configured_spoke_count}"
        )


@given(results=realistic_routing_results())
@_SETTINGS
def test_thermal_relief_total_spokes_consistency(results: RoutingResults) -> None:
    """TS3: report.total_spokes must equal the sum of individual spoke counts."""
    report: ThermalReliefReport = add_thermal_relief(results, spoke_count=4)

    computed_total = sum(tr.spoke_count for tr in report.thermal_reliefs)
    assert report.total_spokes == computed_total, (
        f"total_spokes={report.total_spokes} but sum of individual "
        f"spoke_counts={computed_total}"
    )
