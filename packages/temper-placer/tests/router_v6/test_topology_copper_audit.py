"""Tests for ``topology_copper_audit.py``.

This is the anti-vacuity fix for the gap found in this investigation:
``net_batching.py``'s trace reports "N/110 nets fell back" purely at the
topology level (did Stage 3's SAT solve produce a channel-graph assignment
for a net?), which can read as full success while a material fraction of
those "solved" nets emit no copper at all once Stage 4 (clearance-aware A*,
fails closed) and zone regeneration (``_should_route`` /
``_zone_layers_for_net``) actually run.

MEASURED on a real net-batched production run (`pcb/temper.kicad_pcb`,
``--net-batching --batch-size 10``): 36 of 110 topology-solved nets emitted
no explicit copper. Breakdown, all MEASURED (see the accompanying
investigation report, not re-derived here):

- 9 legitimately zone-pour-covered (``+15V_LS``, ``+170V_BUS``,
  ``DC_BUS_RTN``, ``SW_NODE``, ``ac_l``, ``ac_n``, ``tank-out``,
  ``tank.c_tank1-p2``, ``w1_1``) -- HighVoltage/ACMains netclass,
  ``routing_strategy == "plane_required"``.
- 2 legitimately self-referential (``discharge.k_dis1-no``,
  ``discharge.k_dis2-no`` -- both "pins" are the literal same physical pad).
- 19 genuinely attempted by Stage 4's A* and failed closed (forced segment
  disallowed) -- a real, expected outcome the topology-level trace can't see.
- 6 orphaned by a policy mismatch between two independently-evolving
  classifiers: ``_should_route`` excludes ``+15V``/``+3V3``/``PWR_RTN``/
  ``V_BUS_SENSE``/``gnd``/``vcc`` from A* on the stated assumption "zone
  pours will handle them", but their netclasses (``Power``/``GND``) do not
  declare ``routing_strategy == "plane_required"`` (only
  ``ACMains``/``HighVoltage`` do, since `d4047607`) -- so neither mechanism
  ever produces copper for them. This is a real, pre-existing pipeline gap,
  independent of net-batching, that this test suite pins as a real
  (currently-failing-if-fixed-incorrectly) regression check using the
  actual production predicates -- not a mock.

The first group of tests below exercises the audit's classification logic
in isolation (synthetic content, injected predicates) -- these are what
the task means by "a test that fails if a net reports solved but emits no
copper without a recorded legitimate reason." The last test
(``test_real_policy_predicates_flag_the_measured_power_ground_orphans``)
runs the *real* ``_should_route``/``_zone_layers_for_net`` production
predicates against the real net names discovered orphaned in the
investigation, without needing a full ~13-minute production route.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from temper_placer.router_v6.topology_copper_audit import (
    audit_topology_vs_copper,
    is_self_referential_net,
    net_number_to_name_map,
    nets_carrying_copper,
    nets_with_copper,
)

REPO_ROOT = Path(__file__).resolve().parents[4]
FIXTURE_33 = REPO_ROOT / "pcb" / "benchmarks" / "temper_fixture_33.kicad_pcb"

# --- minimal synthetic .kicad_pcb fragments -------------------------------

_NET_DECLS = """
  (net 0 "")
  (net 1 "signal_a")
  (net 2 "signal_b")
  (net 3 "plane_net")
  (net 4 "self_ref_net")
  (net 5 "orphan_net")
"""


def _board(*extra_blocks: str) -> str:
    return _NET_DECLS + "\n" + "\n".join(extra_blocks)


def test_explicit_segment_counts_as_copper():
    content = _board(
        '  (segment (start 0 0) (end 1 1) (width 0.25) (layer "F.Cu") (net 1) (tstamp "x"))'
    )
    explicit, zoned = nets_with_copper(content)
    assert explicit == {"signal_a"}
    assert zoned == set()


def test_via_counts_as_copper():
    content = _board(
        '  (via (at 1 1) (size 0.8) (drill 0.4) (layers "F.Cu" "B.Cu") (net 1) (tstamp "x"))'
    )
    explicit, _ = nets_with_copper(content)
    assert explicit == {"signal_a"}


def test_zone_counts_as_zone_copper_not_explicit():
    content = _board(
        '  (zone (net 3) (net_name "plane_net") (layer "F.Cu")\n'
        "    (polygon (pts (xy 0 0) (xy 1 0) (xy 1 1))))"
    )
    explicit, zoned = nets_with_copper(content)
    assert explicit == set()
    assert zoned == {"plane_net"}


def test_multiline_zone_block_fully_consumed_not_misparsed():
    """A zone spans many lines (priority/connect_pads/fill/polygon each on
    their own line, per pcb/temper.kicad_pcb) -- the paren-depth extraction
    must consume the whole block, not just its opening line."""
    content = _board(
        '  (zone (net 3) (net_name "plane_net") (layer "F.Cu")\n'
        "    (priority 1)\n"
        "    (connect_pads (clearance 0.3))\n"
        "    (min_thickness 0.2)\n"
        "    (fill yes)\n"
        "    (polygon\n"
        "      (pts\n"
        "        (xy 0 0)\n"
        "        (xy 1 0)\n"
        "        (xy 1 1)\n"
        "      )\n"
        "    )\n"
        "  )"
    )
    explicit, zoned = nets_with_copper(content)
    assert zoned == {"plane_net"}
    assert explicit == set()


def test_nets_carrying_copper_is_the_union_not_explicit_only():
    """The accessor this task exists to make unambiguous: a net covered
    only by a zone pour (no explicit trace/via) still carries copper, and
    must count in the single-number "nets carrying copper" total -- this
    is exactly the convention split that produced two different baseline
    counts (52 explicit-only vs. 64 union) for the identical routed board
    in the investigation this function's docstring cites."""
    content = _board(
        '  (segment (start 0 0) (end 1 1) (width 0.25) (layer "F.Cu") (net 1) (tstamp "x"))',
        '  (zone (net 3) (net_name "plane_net") (layer "F.Cu")\n'
        "    (polygon (pts (xy 0 0) (xy 1 0) (xy 1 1))))",
    )
    assert nets_carrying_copper(content) == {"signal_a", "plane_net"}


def test_is_self_referential_net():
    assert is_self_referential_net([("K2", "3"), ("K2", "3")])
    assert not is_self_referential_net([("K2", "3"), ("K3", "1")])
    assert not is_self_referential_net([])


def test_net_number_to_name_map():
    mapping = net_number_to_name_map(_board())
    assert mapping[1] == "signal_a"
    assert mapping[3] == "plane_net"


# --- audit classification (the anti-vacuity gate) -------------------------


def test_solved_net_with_explicit_copper_is_not_a_gap():
    content = _board(
        '  (segment (start 0 0) (end 1 1) (width 0.25) (layer "F.Cu") (net 1) (tstamp "x"))'
    )
    audit = audit_topology_vs_copper(
        ["signal_a"],
        content,
        net_pins={"signal_a": [("U1", "1"), ("U2", "1")]},
        is_zone_pour_eligible=lambda _: False,
        is_excluded_from_astar=lambda _: False,
    )
    assert audit.with_copper == ["signal_a"]
    assert audit.unexplained_gap == []
    assert audit.legitimate_gap == []


def test_solved_net_with_zone_copper_is_legitimate_not_a_gap():
    content = _board(
        '  (zone (net 3) (net_name "plane_net") (layer "F.Cu")\n'
        "    (polygon (pts (xy 0 0) (xy 1 0) (xy 1 1))))"
    )
    audit = audit_topology_vs_copper(
        ["plane_net"],
        content,
        net_pins={"plane_net": [("U1", "1"), ("U2", "1"), ("U3", "1")]},
        is_zone_pour_eligible=lambda _: True,
        is_excluded_from_astar=lambda _: True,
    )
    assert audit.with_copper == ["plane_net"]
    assert audit.unexplained_gap == []


def test_self_referential_net_with_no_copper_is_legitimate_gap():
    content = _board()  # no segment/via/zone blocks at all
    audit = audit_topology_vs_copper(
        ["self_ref_net"],
        content,
        net_pins={"self_ref_net": [("K2", "3"), ("K2", "3")]},
        is_zone_pour_eligible=lambda _: False,
        is_excluded_from_astar=lambda _: False,
    )
    assert audit.unexplained_gap == []
    assert audit.legitimate_gap == ["self_ref_net"]
    outcome = audit.outcomes["self_ref_net"]
    assert outcome.legitimate_reason == "self_referential_pad"


def test_solved_net_with_no_copper_and_no_reason_is_unexplained():
    """The core anti-vacuity assertion: a net Stage 3 calls 'solved' that
    emits literally no copper, and isn't self-referential, isn't
    zone-pour-eligible, and isn't excluded from A* by policy, MUST be
    flagged -- this is exactly the "can't-fail metric" the investigation
    found (a net_batching batch reporting solved=True with 0 crashed/failed
    for a net that ends up with zero segments/vias/zones in the output)."""
    content = _board()  # zero copper of any kind for orphan_net
    audit = audit_topology_vs_copper(
        ["orphan_net"],
        content,
        net_pins={"orphan_net": [("U1", "1"), ("U2", "1")]},
        is_zone_pour_eligible=lambda _: False,
        is_excluded_from_astar=lambda _: False,
    )
    assert audit.unexplained_gap == ["orphan_net"]
    assert audit.legitimate_gap == []
    outcome = audit.outcomes["orphan_net"]
    assert outcome.is_unexplained
    assert "A*" in outcome.note


def test_policy_orphan_excluded_from_astar_and_not_zone_eligible_is_unexplained():
    """Reproduces the exact shape of the 6-net production gap
    (+15V/+3V3/PWR_RTN/V_BUS_SENSE/gnd/vcc): excluded from A* by
    `_should_route` AND not zone-pour-eligible per the netclass SSOT.
    Deliberately NOT classified as legitimate -- being excluded from A* is
    only legitimate if a zone actually covers the net, which this predicate
    combination says it does not."""
    content = _board()
    audit = audit_topology_vs_copper(
        ["orphan_net"],
        content,
        net_pins={"orphan_net": [("U1", "1"), ("U2", "1")]},
        is_zone_pour_eligible=lambda _: False,
        is_excluded_from_astar=lambda _: True,
    )
    outcome = audit.outcomes["orphan_net"]
    assert outcome.is_unexplained
    assert "policy mismatch" in outcome.note


def test_zone_eligible_but_zone_missing_from_output_is_unexplained_not_legitimate():
    """A net that SHOULD have gotten a zone (per the SSOT) but the output
    board has no zone block for it is a zone-generation bug, not a
    legitimate no-copper case -- the audit must not paper over that by
    trusting eligibility instead of the actual output."""
    content = _board()  # no zone block emitted despite eligibility
    audit = audit_topology_vs_copper(
        ["orphan_net"],
        content,
        net_pins={"orphan_net": [("U1", "1"), ("U2", "1")]},
        is_zone_pour_eligible=lambda _: True,
        is_excluded_from_astar=lambda _: True,
    )
    outcome = audit.outcomes["orphan_net"]
    assert outcome.is_unexplained
    assert "zone-generation gap" in outcome.note


def test_format_report_lists_unexplained_net_names():
    content = _board()
    audit = audit_topology_vs_copper(
        ["orphan_net"],
        content,
        net_pins={"orphan_net": [("U1", "1"), ("U2", "1")]},
        is_zone_pour_eligible=lambda _: False,
        is_excluded_from_astar=lambda _: False,
    )
    report = audit.format_report()
    assert "1 UNEXPLAINED" in report
    assert "orphan_net" in report


def test_real_policy_predicates_no_longer_orphan_the_measured_power_ground_nets():
    """Runs the REAL production predicates (`_should_route`,
    `_zone_layers_for_net` -- not mocks) against the exact net names this
    investigation measured as orphaned on `pcb/temper.kicad_pcb`
    (net-batched production run, 2026-08-08). No full route needed: this
    only needs the classification logic, which is a pure function of net
    name plus the netclass SSOT already loaded by these modules.

    UPDATED 2026-08-08 as the reconciliation this test's own previous
    docstring anticipated: `_should_route` no longer excludes a
    Power/GND-classified net from A* unless `_zone_layers_for_net` actually
    grants it zone eligibility (see `_net_policy.py`'s `_should_route`
    docstring for the per-net evidence -- `docs/evidence/
    2026-07-28-pour-strategy-audit.md` Task 1/Task 3 -- for why A*-routing,
    not zone eligibility, is the correct fix for all six of these nets).
    So these six nets are no longer excluded from A* (`_should_route` now
    returns ``True``), while remaining correctly zone-ineligible per the
    netclass SSOT (`_zone_layers_for_net` still returns ``[]`` -- that half
    of the classifier was already correct and is untouched by this fix).
    This is the real regression pin now: if either predicate regresses back
    toward re-excluding these nets from A* without restoring zone
    eligibility, this test must fail.
    """
    from temper_placer.router_v6._net_policy import _should_route
    from temper_placer.router_v6._zone_pour_stitch import _zone_layers_for_net

    orphaned_by_policy = ["+15V", "+3V3", "PWR_RTN", "V_BUS_SENSE", "gnd", "vcc"]
    for name in orphaned_by_policy:
        assert _should_route(name), (
            f"{name!r} must be routed by A* now that it is not zone-eligible "
            "-- excluding it here without zone coverage would re-orphan it "
            "from both copper-producing mechanisms"
        )
        assert _zone_layers_for_net(name) == [], (
            f"{name!r} unexpectedly gained zone eligibility; if that's "
            "intentional this test (and _should_route's docstring) should "
            "be updated to match, not just this assertion"
        )

    # And the audit agrees: with real copper present for these nets (as the
    # production run now provides -- see
    # test_full_pipeline_run_surfaces_the_same_unexplained_gap below), they
    # are no longer unexplained gaps.
    content = "\n".join(
        f'  (net {i} "{name}")\n'
        f'  (segment (start 0 0) (end 1 1) (width 0.25) (layer "F.Cu") '
        f"(net {i}) (tstamp \"t{i}\"))"
        for i, name in enumerate(orphaned_by_policy, start=1)
    )
    net_pins = {name: [("U1", "1"), ("U2", "1")] for name in orphaned_by_policy}
    audit = audit_topology_vs_copper(orphaned_by_policy, content, net_pins)
    assert audit.with_copper == sorted(orphaned_by_policy)
    assert audit.unexplained_gap == []


@pytest.mark.slow
def test_full_pipeline_run_surfaces_the_same_unexplained_gap():
    """End-to-end: actually run ``route_pcb()`` (no net-batching -- this
    confirms the gap is a general Stage3/Stage4 pipeline property, not a
    net-batching-specific artifact) on the small 33-net fixture board and
    audit its real output.

    This is the literal "test that fails if a net reports solved but emits
    no copper without a recorded legitimate reason" the investigation asked
    for, run against a real (if small) board rather than only synthetic
    content. It is marked ``slow`` (~60-90s: full skeleton/grid/A* pipeline)
    rather than run on every commit, matching this repo's convention for
    tests that invoke the real router (see ``pytest.ini``/``pyproject.toml``
    ``slow`` marker).

    FIXED 2026-08-08 (was ``xfail(strict=True)``, converted to a normal
    passing assertion now that the underlying gap is closed): this used to
    fail because the fixture's GND/+3V3/+5V/etc. power/ground nets hit the
    ``_should_route``-excludes-but-``_zone_layers_for_net``-doesn't-cover
    gap documented in this module's docstring, independent of net-batching.
    ``_should_route`` (``_net_policy.py``) now only excludes a
    Power/GND/HV-classified net from A* when ``_zone_layers_for_net`` says
    a zone pour will actually cover it -- see that function's docstring and
    ``docs/evidence/2026-07-28-pour-strategy-audit.md`` Task 1/Task 3 for
    the per-net evidence this fix was based on. Verified live on
    ``pcb/temper.kicad_pcb`` (``--net-batching --batch-size 10``): all six
    of the previously-orphaned nets (``+15V``, ``+3V3``, ``PWR_RTN``,
    ``V_BUS_SENSE``, ``gnd``, ``vcc``) now carry explicit copper.
    """
    if not FIXTURE_33.exists():
        pytest.skip(f"fixture board not found: {FIXTURE_33}")

    import tempfile

    from temper_placer.io.kicad_parser import parse_kicad_pcb
    from temper_placer.io.netclass_loader import load_netclass_rules
    from temper_placer.router_v6._strip_copper import strip_existing_copper
    from temper_placer.router_v6.adapter import route_pcb

    rules_path = REPO_ROOT / "packages" / "temper-placer" / "configs" / "netclass_rules.yaml"
    rules = load_netclass_rules(rules_path)
    netlist = parse_kicad_pcb(FIXTURE_33).netlist

    # Route from scratch, like scripts/route_board.py's route_once() default
    # (keep_existing_copper=False) -- routing on top of the fixture's own
    # already-committed copper/zones is a materially different, much more
    # expensive problem (existing pours can become routing obstacles) and is
    # not what this test means to measure.
    content = FIXTURE_33.read_text(encoding="utf-8")
    cleaned, _stripped_count = strip_existing_copper(content)
    with tempfile.NamedTemporaryFile(
        "w", suffix=".kicad_pcb", delete=False, encoding="utf-8"
    ) as tmp:
        tmp.write(cleaned)
        route_src = Path(tmp.name)

    parsed_stub = type(
        "ParsedStub", (), {"source_path": route_src, "nets": netlist.nets}
    )()

    result = route_pcb(parsed_stub, {}, design_rules=rules.design_rules)
    assert result.routed_pcb_content
    assert result.topology_solved_nets, "expected Stage 3 to solve at least one net's topology"

    net_pins = {n.name: list(n.pins) for n in netlist.nets}
    audit = audit_topology_vs_copper(
        result.topology_solved_nets, result.routed_pcb_content, net_pins
    )

    assert audit.unexplained_gap == [], (
        "topology-solved nets with no copper and no recorded legitimate "
        f"reason: {audit.unexplained_gap} -- see this module's docstring "
        "for the known power/ground _should_route/_zone_layers_for_net "
        "policy-mismatch root cause"
    )
