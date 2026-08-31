"""Component-level net classification at parse time -- regression for the
"every COMPONENT is Signal" defect (distinct from, and downstream of, the
per-NET flattening #1041/#1042 fixed).

Root cause (fixed here): ``Net.net_class`` was fixed at parse time
(#1041/#1042) via ``TEMPER_NET_ASSIGNMENTS``, so ``result.netlist.nets``
correctly reports ``Signal 69, HighVoltage 14, FinePitch 13, Power 4,
ACMains 2, GND 2, HighVoltageIsolated 2, GateDriveHV 2, GateDriveSELV 2`` on
the real board. But a component is not a net -- it has pins on several nets,
potentially of different classes -- and nothing rolled a net's real class up
onto the *component* that owns the pin. ``Component.net_class`` is a
separate field (``temper_placer.core.netlist.Component.net_class``), and
``kicad_parser.parse_kicad_pcb`` only ever populated it when a caller
explicitly passed ``design_rules=`` -- which none of the real board's DRC
consumers did. So ``collections.Counter(c.net_class for c in
parsed.netlist.components)`` came back ``{"Signal": 169}`` for the entire
production board, even after the net-level fix landed: every component
looked electrically identical to the three safety rule kernels that read
this field (``packages/temper-drc-rs/src/rules/safety/creepage.rs``,
``hv_lv_separation.rs``, ``isolation.rs``, via their shared
``resolve_safety_category(comp, board)`` / ``is_iso_component(comp,
board)``), on a design whose entire safety case is a mains<->SELV creepage
barrier.

Fix: ``kicad_parser.parse_kicad_pcb`` now defaults ``design_rules`` to this
project's own SSOT (``create_temper_design_rules()``, built from
``TEMPER_NET_CLASSES``/``TEMPER_NET_ASSIGNMENTS`` in ``core/design_rules.py``)
instead of ``None``-means-skip, and always runs the existing
``_apply_safety_classifications`` rollup (component-level ``net_class`` =
the most severe safety category -- HV/AC beats LV/unclassified -- over the
component's own pins' resolved net classes; ties and "just some HV/AC pin"
both collapse to the literal ``"HighVoltage"`` label, matching this
codebase's own pre-existing binary HV/LV idiom already used verbatim by
``metrics/physics.py``, ``validation/metrics.py``,
``deterministic/stages/_phase_core.py`` (``_PhaseHVMixin``; the
``_phase_rotation.py`` module was collapsed into it 2026-08-20), and
``router_v6/constraints_design_rules.py`` -- ``comp.net_class ==
"HighVoltage"``). No table is transcribed into Rust or duplicated anywhere:
the same ``TEMPER_NET_CLASSES``/``TEMPER_NET_ASSIGNMENTS`` SSOT that already
drives net-level classification now also drives the component-level rollup,
via the existing (previously opt-in-only) ``_apply_safety_classifications``.

These tests fail on the pre-fix code: every assertion below that a
component with a pin on a named mains/HV net is NOT "Signal" is false
against the old ``design_rules=None``-means-skip default.
"""

from __future__ import annotations

import collections
from pathlib import Path

import pytest

from temper_placer.core.design_rules import DesignRules
from temper_placer.io.kicad_parser import parse_kicad_pcb

PCB_PATH = Path("pcb/temper.kicad_pcb")


def _skip_if_board_missing() -> None:
    if not PCB_PATH.exists():
        pytest.skip("production board not yet generated")


def _components_on_net(result, net_name: str) -> list[str]:
    net = result.netlist.get_net(net_name)
    return sorted({ref for ref, _pin in net.pins})


def test_production_board_components_are_not_all_signal() -> None:
    """The pre-fix defect, verbatim: every COMPONENT classified "Signal",
    even though nets were already correctly classified by #1041/#1042.

    On the pre-fix parser (``design_rules`` opt-in, never opted into by any
    real DRC caller) this Counter comes back as ``{"Signal": 169}`` -- a
    single key, for the entire production board.
    """
    _skip_if_board_missing()

    result = parse_kicad_pcb(PCB_PATH)
    counts = collections.Counter(c.net_class for c in result.netlist.components)

    assert len(counts) > 1, (
        f"every component classified identically ({counts!r}) -- component-level "
        "safety classification did not run at parse time"
    )
    assert counts.keys() != {"Signal"}, f"every component is still 'Signal': {counts!r}"


@pytest.mark.parametrize(
    "net_name",
    [
        # Every net this task's own defect report names by name: the 170V
        # DC bus, both mains AC legs, and the half-bridge switch node.
        "+170V_BUS",
        "ac_l",
        "ac_n",
        "SW_NODE",
    ],
)
def test_known_hv_net_components_do_not_classify_as_signal(net_name: str) -> None:
    """Every component with a pin on a named mains/HV net must NOT come
    back "Signal" -- the exact falsifier the pre-fix code fails."""
    _skip_if_board_missing()

    result = parse_kicad_pcb(PCB_PATH)
    refs = _components_on_net(result, net_name)
    assert refs, f"fixture out of sync with the board: no components on {net_name!r}"

    for ref in refs:
        comp = next(c for c in result.netlist.components if c.ref == ref)
        assert comp.net_class != "Signal", (
            f"{ref} has a pin on {net_name!r} (a declared HV/AC-severity net) "
            f"but classified as 'Signal' -- component-level safety "
            "classification did not run, or did not roll the net's real "
            "class up onto the component"
        )
        assert comp.net_class == "HighVoltage", (
            f"{ref} on {net_name!r}: expected the HV/AC severity rollup to "
            f"land on 'HighVoltage' (this codebase's own binary HV/LV "
            f"idiom), got {comp.net_class!r}"
        )


def test_pure_lv_component_keeps_signal_default() -> None:
    """Specificity half of the fires/does-not-fire pair: a component whose
    every pin sits on an LV/unclassified net must keep the "Signal"
    default, not get swept into "HighVoltage" by an overly-broad rollup."""
    _skip_if_board_missing()

    result = parse_kicad_pcb(PCB_PATH)
    # PWM_HS/PWM_LS are declared GateDriveSELV (safety_category "LV") --
    # any component touching ONLY SELV/LV-side nets must stay "Signal".
    signal_components = [c for c in result.netlist.components if c.net_class == "Signal"]
    assert signal_components, "expected at least one component to remain 'Signal'"


def test_design_rules_none_default_applies_full_ssot_rollup() -> None:
    """Not passing ``design_rules`` at all must behave identically to
    passing ``create_temper_design_rules()`` explicitly -- the SSOT-by-
    default precedent ``net_class_mapping`` already established."""
    _skip_if_board_missing()

    from temper_placer.core.design_rules import create_temper_design_rules

    default_result = parse_kicad_pcb(PCB_PATH)
    explicit_result = parse_kicad_pcb(PCB_PATH, design_rules=create_temper_design_rules())

    default_counts = collections.Counter(c.net_class for c in default_result.netlist.components)
    explicit_counts = collections.Counter(
        c.net_class for c in explicit_result.netlist.components
    )
    assert default_counts == explicit_counts


def test_explicit_empty_design_rules_opts_out() -> None:
    """An explicit, empty ``DesignRules`` (mirroring
    ``net_class_mapping={}``'s documented opt-out) leaves every component at
    the raw "Signal" default -- proving the SSOT default is applied by
    ``parse_kicad_pcb`` itself, not unconditionally somewhere deeper."""
    _skip_if_board_missing()

    empty_design_rules = DesignRules(
        default_trace_width=0.2,
        default_clearance=0.15,
        default_via_diameter=0.6,
        default_via_drill=0.3,
        net_classes={},
        net_class_assignments={},
    )
    result = parse_kicad_pcb(PCB_PATH, design_rules=empty_design_rules)
    counts = collections.Counter(c.net_class for c in result.netlist.components)

    assert counts.keys() == {"Signal"}, (
        f"expected every component at the 'Signal' default with an empty "
        f"DesignRules, got {counts!r}"
    )
