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
- 2 originally miscounted here as "legitimately self-referential"
  (``discharge.k_dis1-no``, ``discharge.k_dis2-no``) on the false premise
  that identical ``(component_ref, pin_name)`` tuples imply the same
  physical pad. **Corrected 2026-08-13**: both nets have 2 genuinely
  distinct physical pads 7.5mm apart (K2/K3's manufacturer-duplicated
  relay contact pads) per ``pad_connectivity_audit`` ground truth -- a
  real, currently-unconnected 2-terminal net each, not a legitimate
  zero-copper case. See ``is_self_referential_net``'s docstring and
  ``test_duplicate_pin_tuple_net_with_no_copper_is_unexplained_not_legitimate``.
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
    # Corrected 2026-08-13: a net with 2+ pin instances is NOT trusted as
    # self-referential just because the (component_ref, pin_name) tuples
    # are identical -- K2/K3's manufacturer-duplicated relay contact pads
    # (this board's real discharge.k_dis1-no/discharge.k_dis2-no) prove
    # that tuple identity does not imply physical-pad identity. Only a
    # genuinely single-pin-instance net (nothing else it could resolve to)
    # is trusted.
    assert not is_self_referential_net([("K2", "3"), ("K2", "3")])
    assert is_self_referential_net([("K2", "3")])
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


def test_true_single_pin_net_with_no_copper_is_legitimate_gap():
    content = _board()  # no segment/via/zone blocks at all
    audit = audit_topology_vs_copper(
        ["self_ref_net"],
        content,
        net_pins={"self_ref_net": [("K2", "3")]},
        is_zone_pour_eligible=lambda _: False,
        is_excluded_from_astar=lambda _: False,
    )
    assert audit.unexplained_gap == []
    assert audit.legitimate_gap == ["self_ref_net"]
    outcome = audit.outcomes["self_ref_net"]
    assert outcome.legitimate_reason == "self_referential_pad"


def test_duplicate_pin_tuple_net_with_no_copper_is_unexplained_not_legitimate():
    """The regression this task fixes: a net whose pin list is 2+ IDENTICAL
    ``(component_ref, pin_name)`` tuples used to be classified as
    "legitimately self-referential, no copper needed" -- true only if tuple
    identity implies physical-pad identity, which is false on this board
    (K2/K3's manufacturer-duplicated relay contact pads: 2 genuinely
    distinct physical pads, 7.5mm apart, sharing one pad number). This
    exact shape -- ``discharge.k_dis1-no``'s real
    ``[('K2', '3'), ('K2', '3')]`` -- must now surface as unexplained
    (needs a real reason) instead of being falsely certified as legitimate,
    which is the accounting guard this task adds."""
    content = _board()  # zero copper of any kind
    audit = audit_topology_vs_copper(
        ["discharge.k_dis1-no"],
        content,
        net_pins={"discharge.k_dis1-no": [("K2", "3"), ("K2", "3")]},
        is_zone_pour_eligible=lambda _: False,
        is_excluded_from_astar=lambda _: False,
    )
    assert audit.legitimate_gap == []
    assert audit.unexplained_gap == ["discharge.k_dis1-no"]
    outcome = audit.outcomes["discharge.k_dis1-no"]
    assert outcome.legitimate_reason is None
    assert outcome.is_unexplained


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
    not zone eligibility, is the correct fix for these nets). Five of the
    six measured nets (`+15V`, `+3V3`, `V_BUS_SENSE`, `gnd`, `vcc`) are no
    longer excluded from A* (`_should_route` returns ``True``) while
    remaining correctly zone-ineligible per the netclass SSOT
    (`_zone_layers_for_net` returns ``[]``).

    `PWR_RTN` is the ONE exception the R4 pour-derivation fix (2026-08-07,
    `docs/plans/2026-07-29-001-fix-pour-derivation-rule-plan.md`) created
    on purpose: `GND` declares ``plane_preferred`` and `PWR_RTN` is its
    only member with committed zones on the board, so
    `_zone_layers_for_net("PWR_RTN")` is now
    ``["F.Cu", "In3.Cu", "In4.Cu", "B.Cu"]`` (widened 2026-08-13 alongside
    `ENGINE_SUPPORTED_SIGNAL_LAYERS_ORDERED`) and its A* exclusion is
    correct (the zone covers it). It is deliberately NOT in the
    A*-must-route list below.
    """
    from temper_placer.router_v6._net_policy import _should_route
    from temper_placer.router_v6._zone_pour_stitch import _zone_layers_for_net

    orphaned_by_policy = ["+15V", "+3V3", "V_BUS_SENSE", "gnd", "vcc"]
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

    # PWR_RTN: plane_preferred + committed board zones -> zone-covered, so
    # its A* exclusion is correct (the zone produces the copper).
    assert _zone_layers_for_net("PWR_RTN") == ["F.Cu", "In3.Cu", "In4.Cu", "B.Cu"], (
        "PWR_RTN's plane_preferred zone eligibility must persist (R4); "
        "regressing it back to [] would re-orphan it exactly as this test "
        "guards against"
    )
    assert not _should_route("PWR_RTN"), (
        "PWR_RTN is zone-covered (plane_preferred + committed zones), so "
        "its exclusion from A* is correct -- if it lost zone eligibility "
        "it must move back into the A*-routed list above"
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
    content. It is marked ``slow`` (~60-90s default phase + ~35-40s batched
    phase below: full skeleton/grid/A* pipeline, twice) rather than run on
    every commit, matching this repo's convention for tests that invoke the
    real router (see ``pytest.ini``/``pyproject.toml`` ``slow`` marker).

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

    EXTENDED 2026-08-19: the assertion below this docstring used to stop at
    ``result.topology_solved_nets == []`` and then check
    ``audit.unexplained_gap == []`` *over that same empty set* -- true by
    construction (``audit_topology_vs_copper`` iterates
    ``topology_solved_nets``; zero inputs makes zero outcomes), so the test
    passed without the audit's own per-net classification logic
    (has_explicit_copper / has_zone_copper / self-referential / policy-note)
    ever running on a real board (see
    docs/evidence/2026-08-18-no-rust-ledger-clearance-floor-and-topology-
    copper-audit.md Sec 2). The empty-set phase is kept below (it still
    pins a real, useful invariant: the default recipe's Stage 3 no-op), and
    a second phase is added with ``enable_net_batching=True``, which DOES
    make Stage 3 claim topology -- MEASURED: 25 topology-solved nets,
    reproduced identically across two independent runs (~36-38s wall each,
    this worktree, ``check_stale_extensions.py`` 10/10 fresh immediately
    before). Unsilencing the audit this way surfaces a REAL, currently-open
    finding rather than a clean pass: 8 of the 25 are unexplained
    (AC_L/AC_N/CGND/DC_BUS+/DC_BUS-/SW_NODE are zone-pour-eligible
    HV/ACMains nets whose zone-pour didn't cover them on this small
    fixture; SPI_CLK/SPI_MISO are genuine Stage 4 A* failures,
    "no_legal_path"). Per this task's own instruction not to suppress a
    real finding by weakening the check, this is pinned as the CURRENT
    measured state, not asserted as correct -- a change in this set is a
    real signal (fixed a gap, or introduced/renamed one) and should be
    investigated, not silently re-pinned.
    """
    if not FIXTURE_33.exists():
        pytest.skip(f"fixture board not found: {FIXTURE_33}")

    import tempfile

    from temper_placer.io.kicad_parser import parse_kicad_pcb
    from temper_placer.io.netclass_loader import load_netclass_rules
    from temper_io_types import strip_existing_copper
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

    # `route_pcb()` only reads `parsed_stub.source_path` off disk and never
    # writes back to it, so the same cleaned board is reused, unmodified,
    # for both phases below.
    parsed_stub = type(
        "ParsedStub", (), {"source_path": route_src, "nets": netlist.nets}
    )()

    result = route_pcb(parsed_stub, {}, design_rules=rules.design_rules)
    assert result.routed_pcb_content

    # Vacuity fix (docs/evidence/2026-08-16-sat-vacuity-noop-vs-direct-solver.md):
    # the default monolithic Stage 3 is now a structural no-op -- the SAT
    # model cannot force a `NetChannelVar` true, so it never decided
    # topology and the monolithic CNF (182-200 GB) could not even fit.
    # The default therefore claims NO topology; every net is routed by
    # Stage 4's occupancy-grid A* from raw pad positions. The audit's
    # anti-vacuity job (catch "claimed solved but no copper") is still
    # exercised by the synthetic tests above; over an empty claim set it
    # must find no gap, and the real signal here is that the route
    # completes with copper emitted.
    assert result.topology_solved_nets == [], (
        "vacuity fix: default (non-batched, non-bundling) Stage 3 must "
        "claim no topology (no-op path); got "
        f"{result.topology_solved_nets!r}"
    )

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

    # --- Phase 2: a REAL non-empty topology-solved population -----------
    # `enable_net_batching=True` is what makes Stage 3 claim topology at
    # all on this recipe (see the vacuity-fix comment above) -- this is
    # the literal "give it a non-empty claim set" the investigation asked
    # for, run against `audit_topology_vs_copper`'s real, unmocked
    # classification logic (not the synthetic-content tests above).
    result_batched = route_pcb(
        parsed_stub, {}, design_rules=rules.design_rules, enable_net_batching=True
    )
    assert result_batched.routed_pcb_content

    assert result_batched.topology_solved_nets, (
        "net-batching's Stage 3 driver is expected to claim topology for "
        "at least one net on this fixture -- an empty result here would "
        "make the population below vacuous again, the exact defect this "
        "phase exists to avoid"
    )

    audit_batched = audit_topology_vs_copper(
        result_batched.topology_solved_nets, result_batched.routed_pcb_content, net_pins
    )

    # MEASURED (this worktree, two independent runs, identical both times):
    # 25 topology-solved nets, 16 carrying copper, 1 legitimate no-copper
    # net, and these 8 UNEXPLAINED. This is NOT asserting the pipeline is
    # correct -- it is a real, open gap (see the docstring above) pinned so
    # a change in it is caught rather than silently re-measured away. If
    # you are here because this assertion failed: check whether the set
    # shrank (something got fixed -- update this list with a citation) or
    # changed shape (something regressed or moved -- do not just re-pin
    # without understanding which).
    assert audit_batched.unexplained_gap == [
        "AC_L",
        "AC_N",
        "CGND",
        "DC_BUS+",
        "DC_BUS-",
        "SPI_CLK",
        "SPI_MISO",
        "SW_NODE",
    ], (
        "topology-solved nets with no copper and no recorded legitimate "
        f"reason changed from the pinned measurement: {audit_batched.unexplained_gap} "
        "-- see this test's docstring (2026-08-19 EXTENDED) for what was "
        "measured and why it is pinned rather than asserted clean"
    )
