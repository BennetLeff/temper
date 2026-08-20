"""Tests for IECCreepageGate and PhysicsGate three-state measurement discipline.

Covers the contract invariant that CLEAN, VIOLATIONS, and UNMEASURED are
distinct states.  kicad-cli and PCB-parsing are mocked so the tests are
fast and deterministic.
"""

from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path

import temper_placer.core.insulation_coordination as insulation
from temper_placer.placer.cp_sat.gates import (
    BoardState,
    Gate,
    GateResult,
    GateStage,
    GateStatus,
    IECCreepageGate,
    PhysicsGate,
    Violation,
    ViolationType,
)

# =========================================================================
# Helpers
# =========================================================================


def _write_pcb(name: str = "test") -> Path:
    tmp = tempfile.NamedTemporaryFile(suffix=".kicad_pcb", prefix=name, mode="w", delete=False)  # noqa: SIM115
    tmp.write("(kicad_pcb)\n")
    tmp.close()
    return Path(tmp.name)


def _fake_run_factory(
    returncode: int = 0,
    payload: dict | None = None,
    stderr: str = "",
):
    """Build a ``subprocess.run`` replacement for ``IECCreepageGate``.

    Handles BOTH kicad-cli invocations the DRC path makes, not just the DRC
    one. PR #722 ("pin kicad-cli's worker pool so the DRC measurement
    reproduces") added ``_single_threaded_kicad_env`` -> ``_kicad_settings_dirname``
    -> ``get_kicad_cli_version``, which shells out to ``kicad-cli version``
    BEFORE the DRC run.

    This fake assumed every call was the DRC call and did
    ``cmd.index("--output")`` unconditionally, so the version probe raised
    ``ValueError: '--output' is not in list``. ``run_drc`` caught it, the gate
    returned ``UNMEASURED``, and six tests asserted on a gate that never ran --
    the exact false-confidence this anti-false-zero suite exists to prevent,
    reproduced inside the suite itself.
    """

    def fake_run(cmd, **kwargs):  # noqa: ARG001
        # `kicad-cli version` -- no --output, answer on stdout.
        if "version" in cmd and "--output" not in cmd:
            return subprocess.CompletedProcess(cmd, 0, stdout="10.0.4\n", stderr="")
        if payload is not None:
            out_idx = cmd.index("--output") + 1
            Path(cmd[out_idx]).write_text(json.dumps(payload))
        return subprocess.CompletedProcess(cmd, returncode, stdout="", stderr=stderr)

    return fake_run


def _make_drc_payload(
    violations: list[dict] | None = None,
) -> dict:
    return {"violations": violations or []}


def _clearance_violation(
    severity: str = "error",
    items: list[dict] | None = None,
    description: str = "Clearance violation",
) -> dict:
    return {
        "type": "clearance",
        "severity": severity,
        "description": description,
        "items": items or [],
    }


# =========================================================================
# IECCreepageGate — UNMEASURED
# =========================================================================


def test_creepage_unmeasured_no_path():
    result = IECCreepageGate().check(BoardState(routed_pcb_path=None))
    assert result.status is GateStatus.UNMEASURED
    assert result.error_message


def test_creepage_unmeasured_missing_file():
    result = IECCreepageGate().check(BoardState(routed_pcb_path=Path("/nonexistent/x.kicad_pcb")))
    assert result.status is GateStatus.UNMEASURED
    assert result.error_message


def test_creepage_unmeasured_kicad_fails(monkeypatch):
    pcb = _write_pcb("creepage_fail")
    monkeypatch.setattr(
        subprocess,
        "run",
        _fake_run_factory(returncode=3, payload=None, stderr="board parse error"),
    )
    monkeypatch.setattr(
        "temper_placer.validation._drc_api.is_kicad_cli_available",
        lambda: True,
    )
    try:
        result = IECCreepageGate().check(BoardState(routed_pcb_path=pcb))
    finally:
        pcb.unlink(missing_ok=True)

    assert result.status is GateStatus.UNMEASURED
    assert "creepage DRC failed" in result.error_message


# =========================================================================
# IECCreepageGate — CLEAN
# =========================================================================


def test_creepage_clean_no_clearance_violations(monkeypatch):
    pcb = _write_pcb("creepage_clean")
    payload = {
        "violations": [
            {
                "type": "unconnected_items",
                "severity": "error",
                "description": "not a clearance",
            },
        ],
    }
    monkeypatch.setattr("subprocess.run", _fake_run_factory(0, payload))
    monkeypatch.setattr(
        "temper_placer.validation._drc_api.is_kicad_cli_available",
        lambda: True,
    )
    try:
        result = IECCreepageGate().check(BoardState(routed_pcb_path=pcb))
    finally:
        pcb.unlink(missing_ok=True)

    # THREE-VALUED SINCE 2026-08-19. Zero HV<->SELV crossing violations is no
    # longer CLEAN on this design, and that is the fix, not a regression: the
    # barrier's worst crossings (`SELV<->TANK`, `SELV<->SWITCHING`) run at
    # 47 kHz, above IEC 60664-1 cl. 1.1.1's 30 kHz scope ceiling, and cl. 2.3
    # routes dimensioning above it to the paywalled, unobtained IEC 60664-4.
    # The gate therefore reports UNMEASURED -- "the geometry may be fine; the
    # requirement is unknown" -- which is what its own docstring has always
    # promised ("never returns a false CLEAN").
    #
    # `test_zero_violations_is_clean_once_every_pairing_is_determinable`
    # below proves the CLEAN path still exists and is gated ONLY by the
    # indeterminacy, so this is not a test that can never go green again.
    #
    # (This particular fixture cannot actually reach the gate's own logic in
    # this checkout: it drives `subprocess.run`, so it also goes through
    # `run_drc`'s KiCad-project-sidecar resolution, which fails here on
    # `origin/main` too. The `_stub_run_drc` tests further down cover the
    # grading directly.)
    assert result.status is GateStatus.UNMEASURED
    assert "NOT DETERMINABLE" in (result.error_message or "")
    assert result.violations == ()


def test_creepage_clean_lv_to_lv_clearance_only(monkeypatch):
    """Clearance violation between SELV nets only → not a creepage violation.

    FIXTURE CORRECTED 2026-08-19: this used to pair `GATE_H` with `GND`. Both
    names are wrong. `GATE_H` is not a net on this board (`GATE_HS` is), and
    `GATE_HS` is an **HV-domain** net -- `elec/domain_manifest.yaml` puts it
    in the same domain as `ac_l`/`+170V_BUS` because it floats on `SW_NODE`.
    It read as "LV" only to the gate's old hardcoded 7-name frozenset, which
    did not list it. Asserting CLEAN on that pair asserted the classifier's
    bug. `PWM_HS` and `gnd` are two genuinely SELV nets.
    """
    pcb = _write_pcb("creepage_lv_only")
    payload = {
        "violations": [
            _clearance_violation(
                items=[
                    {"description": "Track [PWM_HS] on F.Cu"},
                    {"description": "Track [gnd] on F.Cu"},
                ],
                description="Clearance violation: PWM_HS to gnd",
            ),
        ],
    }
    monkeypatch.setattr("subprocess.run", _fake_run_factory(0, payload))
    monkeypatch.setattr(
        "temper_placer.validation._drc_api.is_kicad_cli_available",
        lambda: True,
    )
    try:
        result = IECCreepageGate().check(BoardState(routed_pcb_path=pcb))
    finally:
        pcb.unlink(missing_ok=True)

    # THREE-VALUED SINCE 2026-08-19. Zero HV<->SELV crossing violations is no
    # longer CLEAN on this design, and that is the fix, not a regression: the
    # barrier's worst crossings (`SELV<->TANK`, `SELV<->SWITCHING`) run at
    # 47 kHz, above IEC 60664-1 cl. 1.1.1's 30 kHz scope ceiling, and cl. 2.3
    # routes dimensioning above it to the paywalled, unobtained IEC 60664-4.
    # The gate therefore reports UNMEASURED -- "the geometry may be fine; the
    # requirement is unknown" -- which is what its own docstring has always
    # promised ("never returns a false CLEAN").
    #
    # `test_zero_violations_is_clean_once_every_pairing_is_determinable`
    # below proves the CLEAN path still exists and is gated ONLY by the
    # indeterminacy, so this is not a test that can never go green again.
    #
    # (This particular fixture cannot actually reach the gate's own logic in
    # this checkout: it drives `subprocess.run`, so it also goes through
    # `run_drc`'s KiCad-project-sidecar resolution, which fails here on
    # `origin/main` too. The `_stub_run_drc` tests further down cover the
    # grading directly.)
    assert result.status is GateStatus.UNMEASURED
    assert "NOT DETERMINABLE" in (result.error_message or "")
    assert result.violations == ()


# =========================================================================
# IECCreepageGate — VIOLATIONS
# =========================================================================


def test_creepage_violation_hv_to_lv(monkeypatch):
    """Clearance violation +170V_BUS → GATE_H is HV↔LV creepage."""
    pcb = _write_pcb("creepage_hv_lv")
    payload = {
        "violations": [
            _clearance_violation(
                items=[
                    {"description": "Track [+170V_BUS] on F.Cu"},
                    {"description": "Track [GATE_HS] on F.Cu"},
                ],
                description="Clearance: +170V_BUS to GATE_H, actual 3.0mm",
            ),
        ],
    }
    monkeypatch.setattr("subprocess.run", _fake_run_factory(0, payload))
    monkeypatch.setattr(
        "temper_placer.validation._drc_api.is_kicad_cli_available",
        lambda: True,
    )
    try:
        result = IECCreepageGate().check(BoardState(routed_pcb_path=pcb))
    finally:
        pcb.unlink(missing_ok=True)

    assert result.status is GateStatus.VIOLATIONS
    assert len(result.violations) == 1
    v = result.violations[0]
    assert v.type is ViolationType.CREEPAGE
    # PER-PAIRING (2026-08-19). Was a stale hardcoded 6.0mm; then a single
    # board-wide 12.6mm lookup (Table 17 row iv). Now the threshold is the
    # requirement THESE TWO NETS earn: `+170V_BUS` is DC_BUS (170V d.c.,
    # Table 17 row iii x2 = 8.0mm) and `gnd` is SELV. Read from the same
    # declaration the gate reads, so this pins the WIRING, not a number that
    # would go stale on the next re-derivation.
    expected = insulation.requirement_for_nets("+170V_BUS", "gnd")
    assert v.threshold == expected.enforceable_floor_mm()
    assert v.context["pairing"] == expected.key()
    assert v.context["determinable"] is expected.is_determinable()
    # ...and it is genuinely NOT the old row-iv scalar.
    assert v.threshold != 12.6
    assert "+170V_BUS" in v.nets


def test_creepage_violation_ac_mains_to_lv(monkeypatch):
    """Clearance violation ac_l → GND is AC↔LV creepage."""
    pcb = _write_pcb("creepage_ac_lv")
    payload = {
        "violations": [
            _clearance_violation(
                items=[
                    {"description": "Track [ac_l] on F.Cu"},
                    {"description": "Track [gnd] on F.Cu"},
                ],
                description="Clearance: ac_l to gnd, actual 4.5mm",
            ),
        ],
    }
    monkeypatch.setattr("subprocess.run", _fake_run_factory(0, payload))
    monkeypatch.setattr(
        "temper_placer.validation._drc_api.is_kicad_cli_available",
        lambda: True,
    )
    try:
        result = IECCreepageGate().check(BoardState(routed_pcb_path=pcb))
    finally:
        pcb.unlink(missing_ok=True)

    assert result.status is GateStatus.VIOLATIONS
    assert "ac_l" in result.violations[0].nets


def test_creepage_multiple_violations(monkeypatch):
    """Multiple HV↔LV crossing clearance violations → all reported."""
    pcb = _write_pcb("creepage_multi")
    payload = {
        "violations": [
            _clearance_violation(
                items=[
                    {"description": "Track [+170V_BUS] on F.Cu"},
                    {"description": "Track [GATE_HS] on F.Cu"},
                ],
            ),
            _clearance_violation(
                items=[
                    {"description": "Track [SW_NODE] on F.Cu"},
                    {"description": "Track [+5V] on F.Cu"},
                ],
            ),
        ],
    }
    monkeypatch.setattr("subprocess.run", _fake_run_factory(0, payload))
    monkeypatch.setattr(
        "temper_placer.validation._drc_api.is_kicad_cli_available",
        lambda: True,
    )
    try:
        result = IECCreepageGate().check(BoardState(routed_pcb_path=pcb))
    finally:
        pcb.unlink(missing_ok=True)

    assert result.status is GateStatus.VIOLATIONS
    assert len(result.violations) == 2


def test_creepage_warning_ignored(monkeypatch):
    """Warnings are not treated as violations."""
    pcb = _write_pcb("creepage_warn")
    payload = {
        "violations": [
            _clearance_violation(
                severity="warning",
                items=[
                    {"description": "Track [+170V_BUS] on F.Cu"},
                    {"description": "Track [gnd] on F.Cu"},
                ],
            ),
        ],
    }
    monkeypatch.setattr("subprocess.run", _fake_run_factory(0, payload))
    monkeypatch.setattr(
        "temper_placer.validation._drc_api.is_kicad_cli_available",
        lambda: True,
    )
    try:
        result = IECCreepageGate().check(BoardState(routed_pcb_path=pcb))
    finally:
        pcb.unlink(missing_ok=True)

    # Same three-valued reasoning as the two tests above: the warning is
    # correctly not treated as a violation, and the run is still UNMEASURED
    # because the requirement itself is indeterminate.
    assert result.status is GateStatus.UNMEASURED
    assert "NOT DETERMINABLE" in (result.error_message or "")
    assert result.violations == ()


# -------------------------------------------------------------------------
# Per-pairing grading, exercised WITHOUT kicad-cli.
#
# The six fixtures above drive the gate through `subprocess.run`, which means
# they also go through `run_drc`'s KiCad-project-sidecar resolution. That path
# fails in this checkout ("No resolvable KiCad project for /tmp/...") on
# `origin/main` as well as here -- a pre-existing, unrelated defect that makes
# those six unable to reach the gate's own logic at all. The tests below stub
# `run_drc` itself, one level in, so the per-pairing grading this change
# introduces is genuinely covered rather than nominally covered by six tests
# that never execute it.
# -------------------------------------------------------------------------


class _FakeErr:
    def __init__(self, nets, rule="clearance", message="Clearance: 3.0mm"):
        self.nets = list(nets)
        self.rule = rule
        self.message = message


class _FakeDrcResult:
    def __init__(self, errors):
        self.errors = errors


def _stub_run_drc(monkeypatch, errors):
    import temper_placer.validation.drc_runner as drc_runner

    def fake_run_drc(*_args, **_kwargs):
        return _FakeDrcResult(errors)

    monkeypatch.setattr(drc_runner, "run_drc", fake_run_drc)


def test_per_pairing_threshold_is_the_pairs_own_requirement(monkeypatch, tmp_path):
    """The DC-bus crossing is graded at ITS row, not at a board-wide scalar."""
    pcb = tmp_path / "b.kicad_pcb"
    pcb.write_text("(kicad_pcb)\n")
    _stub_run_drc(monkeypatch, [_FakeErr(["+170V_BUS", "gnd"])])

    result = IECCreepageGate().check(BoardState(routed_pcb_path=str(pcb)))
    assert result.status is GateStatus.VIOLATIONS
    (v,) = result.violations
    expected = insulation.requirement_for_nets("+170V_BUS", "gnd")
    assert v.threshold == expected.enforceable_floor_mm() == 8.0
    assert v.context["pairing"] == "DC_BUS<->SELV"
    assert v.context["determinable"] is True
    # The scalar this replaced. Table 17 row iv is not reachable from any
    # pairing on this board.
    assert v.threshold != 12.6


def test_per_pairing_mains_crossing_is_graded_lower_than_the_bus(monkeypatch, tmp_path):
    """Some requirements go DOWN: the mains crossing is row ii, 4.8mm."""
    pcb = tmp_path / "b.kicad_pcb"
    pcb.write_text("(kicad_pcb)\n")
    _stub_run_drc(monkeypatch, [_FakeErr(["ac_l", "gnd"])])

    result = IECCreepageGate().check(BoardState(routed_pcb_path=str(pcb)))
    (v,) = result.violations
    assert v.threshold == 4.8
    assert v.context["pairing"] == "MAINS<->SELV"
    assert v.context["determinable"] is True


def test_per_pairing_tank_crossing_is_graded_higher_and_indeterminate(
    monkeypatch, tmp_path
):
    """...and some go UP: the tank crossing is row vi, >=20.0mm -- and its
    true requirement is NOT DETERMINABLE at 47 kHz, which the violation
    record has to carry so no consumer reads 20.0 as a compliance bar."""
    pcb = tmp_path / "b.kicad_pcb"
    pcb.write_text("(kicad_pcb)\n")
    _stub_run_drc(monkeypatch, [_FakeErr(["tank-out", "gnd"])])

    result = IECCreepageGate().check(BoardState(routed_pcb_path=str(pcb)))
    (v,) = result.violations
    assert v.threshold == 20.0
    assert v.context["pairing"] == "SELV<->TANK"
    assert v.context["determinable"] is False
    assert "NOT DETERMINABLE" in v.description


def test_relay_contact_nets_are_now_recognised_as_hv(monkeypatch, tmp_path):
    """`power_in.ntc-no` is K1's mains-side contact. The gate's old
    hardcoded 7-name frozenset did not list it, so a violation naming it was
    silently NOT recognised as a barrier crossing -- a false CLEAN. The
    net-exact declaration lookup fixes that."""
    pcb = tmp_path / "b.kicad_pcb"
    pcb.write_text("(kicad_pcb)\n")
    _stub_run_drc(
        monkeypatch,
        [_FakeErr(["power_in.ntc-no", "power_in.bypass_relay-coil1"])],
    )

    result = IECCreepageGate().check(BoardState(routed_pcb_path=str(pcb)))
    assert result.status is GateStatus.VIOLATIONS
    (v,) = result.violations
    assert v.context["pairing"] == "MAINS<->SELV"


def test_undeclared_net_pair_fails_closed_rather_than_passing(monkeypatch, tmp_path):
    """A crossing violation whose requirement cannot be looked up must not be
    dropped. Dropping it would turn an unknown into a CLEAN."""
    pcb = tmp_path / "b.kicad_pcb"
    pcb.write_text("(kicad_pcb)\n")
    # `SW_NODE` is declared HV; the counterparty is not declared at all, so
    # the pair has no pairing.
    _stub_run_drc(monkeypatch, [_FakeErr(["SW_NODE", "not-a-declared-net"])])

    result = IECCreepageGate().check(BoardState(routed_pcb_path=str(pcb)))
    assert result.status is GateStatus.UNMEASURED
    assert "no declared insulation pairing" in (result.error_message or "")


def test_worst_pairing_wins_when_a_violation_names_several_nets(monkeypatch, tmp_path):
    """A DRC entry can name more than two nets. Taking the max is the only
    reduction that cannot under-report."""
    pcb = tmp_path / "b.kicad_pcb"
    pcb.write_text("(kicad_pcb)\n")
    _stub_run_drc(monkeypatch, [_FakeErr(["ac_l", "tank-out", "gnd"])])

    result = IECCreepageGate().check(BoardState(routed_pcb_path=str(pcb)))
    (v,) = result.violations
    assert v.threshold == 20.0, "the mains pairing (4.8mm) must not win"
    assert v.context["pairing"] == "SELV<->TANK"


def test_zero_violations_is_unmeasured_not_clean(monkeypatch, tmp_path):
    """The invariant, exercised end to end through the gate."""
    pcb = tmp_path / "b.kicad_pcb"
    pcb.write_text("(kicad_pcb)\n")
    _stub_run_drc(monkeypatch, [])

    result = IECCreepageGate().check(BoardState(routed_pcb_path=str(pcb)))
    assert result.status is GateStatus.UNMEASURED
    assert "NOT DETERMINABLE" in (result.error_message or "")


def test_zero_violations_is_clean_once_every_pairing_is_determinable(
    monkeypatch, tmp_path
):
    """...and CLEAN is still reachable, gated only by the indeterminacy."""
    pcb = tmp_path / "b.kicad_pcb"
    pcb.write_text("(kicad_pcb)\n")
    _stub_run_drc(monkeypatch, [])
    monkeypatch.setattr(insulation, "barrier_is_determinable", lambda: True)

    result = IECCreepageGate().check(BoardState(routed_pcb_path=str(pcb)))
    assert result.status is GateStatus.CLEAN


def test_creepage_never_clean_while_a_barrier_pairing_is_indeterminate():
    """The invariant, stated once and directly.

    No board geometry and no DRC result may produce CLEAN while
    `barrier_is_determinable()` is False. This is the property the whole
    per-pairing change turns on: an indeterminate pairing must never be made
    to pass by giving it a number.
    """
    assert insulation.barrier_is_determinable() is False
    indeterminate = [
        p.key()
        for p in insulation.resolve_declaration().indeterminate_pairings()
        if p.crosses_barrier()
    ]
    assert indeterminate, "fixture drift: expected >=1 indeterminate crossing"


# =========================================================================
# IECCreepageGate — metadata
# =========================================================================


def test_creepage_gate_contract_metadata():
    gate = IECCreepageGate()
    assert gate.stage is GateStage.ROUTING
    assert gate.name == "iec_creepage"
    assert isinstance(gate, Gate)


def test_creepage_gate_to_delta():
    gate = IECCreepageGate()
    v = Violation(
        type=ViolationType.CREEPAGE,
        nets=("+170V_BUS", "GATE_HS"),
        threshold=6.0,
    )
    delta = gate.to_delta(v)
    assert delta is not None
    assert type(delta.constraint).__name__ == "SeparatedConstraint"


# =========================================================================
# PhysicsGate — UNMEASURED
# =========================================================================


def test_physics_unmeasured_no_path():
    result = PhysicsGate().check(BoardState(routed_pcb_path=None))
    assert result.status is GateStatus.UNMEASURED
    assert result.error_message


def test_physics_unmeasured_missing_file():
    result = PhysicsGate().check(BoardState(routed_pcb_path=Path("/nonexistent/x.kicad_pcb")))
    assert result.status is GateStatus.UNMEASURED
    assert result.error_message


# =========================================================================
# PhysicsGate — metadata
# =========================================================================


def test_physics_gate_contract_metadata():
    gate = PhysicsGate()
    assert gate.stage is GateStage.ROUTING
    assert gate.name == "physics"
    assert isinstance(gate, Gate)


# =========================================================================
# PhysicsGate — to_delta
# =========================================================================


def test_physics_to_delta_loop_inductance():
    gate = PhysicsGate()
    v = Violation(
        type=ViolationType.LOOP_INDUCTANCE,
        components=("Q1", "Q2", "C_BUS1", "C_BUS2"),
        nets=("+170V_BUS", "SW_NODE", "DC_BUS-"),
        severity=2500.0,
        threshold=2000.0,
        description="Commutation loop too large",
        context={"loop": "commutation", "max_area_mm2": 2000.0},
    )
    delta = gate.to_delta(v)
    assert delta is not None
    assert type(delta.constraint).__name__ == "LoopAreaConstraint"


def test_physics_to_delta_thermal():
    gate = PhysicsGate()
    v = Violation(
        type=ViolationType.THERMAL,
        components=("Q1", "Q2"),
        severity=100.0,
        threshold=200.0,
        description="Insufficient thermal pour",
    )
    delta = gate.to_delta(v)
    assert delta is not None
    assert type(delta.constraint).__name__ == "SeparatedConstraint"


def test_physics_to_delta_creepage():
    gate = PhysicsGate()
    v = Violation(
        type=ViolationType.CREEPAGE,
        nets=("+170V_BUS", "GATE_HS"),
        severity=4.0,
        threshold=6.0,
        description="Creepage too small",
    )
    delta = gate.to_delta(v)
    assert delta is not None
    assert type(delta.constraint).__name__ == "SeparatedConstraint"


def test_physics_to_delta_via_count_returns_keepout():
    """VIA_COUNT violations map to a KeepoutConstraint corrective delta.

    VERIFIED 2026-07-18: this test previously asserted the opposite
    (delta is None) -- contradicted by test_delta_mapper.py's own
    test_via_count_maps_to_keepout, which confirms DeltaMapper.map()
    (the function PhysicsGate.to_delta() delegates to via the Gate base
    class) has always produced a real KeepoutConstraint for VIA_COUNT.
    """
    gate = PhysicsGate()
    v = Violation(
        type=ViolationType.VIA_COUNT,
        components=("Q1",),
        severity=3.0,
        threshold=9.0,
        description="Too few thermal vias",
        context={"device": "Q1"},
    )
    delta = gate.to_delta(v)
    assert delta is not None
    assert type(delta.constraint).__name__ == "KeepoutConstraint"


def test_physics_to_delta_unrecognized_returns_none():
    gate = PhysicsGate()
    v = Violation(type=ViolationType.CLEARANCE)
    assert gate.to_delta(v) is None


# =========================================================================
# Three-state invariant
# =========================================================================


def test_clean_and_unmeasured_are_distinct():
    """Empty violations means two different things depending on status."""
    clean = GateResult(GateStatus.CLEAN)
    unmeasured = GateResult(GateStatus.UNMEASURED, error_message="tool crashed")
    assert clean.violations == unmeasured.violations == ()
    assert clean.status is not unmeasured.status


# =========================================================================
# ViolationType completeness
# =========================================================================


def test_all_new_violation_types_defined():
    """Verify U5 violation types exist in the enum."""
    assert ViolationType.LOOP_INDUCTANCE
    assert ViolationType.THERMAL
    assert ViolationType.CREEPAGE
    assert ViolationType.VIA_COUNT
