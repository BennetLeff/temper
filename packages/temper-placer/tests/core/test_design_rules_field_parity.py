"""Field-parity pin for the DesignRules / NetClassRules ``_mm`` read surface.

Wave 4, Phase 2 moved the ``DesignRules`` data model to a pyo3 pyclass
(``temper_design_bundle_python``) while ``NetClassRules`` stayed a Pydantic
model generated from ``configs/netclass_rules_manifest.yaml``. The canonical
field names are the non-``_mm`` manifest names (``trace_width``,
``clearance``, ``via_diameter``, ``via_drill``; the Rust ``DesignRules``
pyclass constructor accepts exactly those kwargs, matching
``create_temper_design_rules()`` and the pre-migration oracle
``tests/core/_design_rules_py_oracle.py``).

A large swath of pre-migration router_v6 call sites
(``_astar_search.py``, ``escape_via_generator.py``, ``bundle_analyzer.py``,
``constraint_model.py``, ``capacity_check.py``, ``deterministic/stages/setup.py``,
``regression/drc_ratchet.py``, ``validation/drc_oracle.py``) read the
``_mm``-suffixed spellings off whatever object
``DesignRules.get_rules_for_net()`` / ``net_classes`` holds. Two fixes closed
the asymmetry on the read side without renaming those call sites:

- ``28dc960de`` added ``_mm`` getter/setter aliases to the Rust ``DesignRules``
  pyclass (``packages/temper-design-bundle/src/design_rules.rs``).
- ``592cf4b29`` added ``_mm`` read-only property aliases to the generated
  Pydantic ``NetClassRules`` model (``scripts/templates/netclass_rules.py.j2``).

This file pins the resulting contract so a future drift (either spelling
disappearing from either type) fails loudly: every net-class object the
parser/loader can produce must answer both spellings identically. The
regression that motivated it: every golden/production board write-reparse
round trip failed with
``DesignRules.__new__() got an unexpected keyword argument
'default_clearance_mm'`` (parser passing ``_mm`` constructor kwargs), and
after that was fixed, ``route_pcb`` crashed with
``AttributeError: 'NetClassRules' object has no attribute 'via_diameter_mm'``
on YAML-loaded net classes.
"""

from __future__ import annotations

from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[4]
_RULES_PATH = (
    _REPO_ROOT / "packages" / "temper-placer" / "configs" / "netclass_rules.yaml"
)

# (alias, canonical) pairs the drift broke.
_MM_PAIRS = (
    ("trace_width_mm", "trace_width"),
    ("clearance_mm", "clearance"),
    ("via_diameter_mm", "via_diameter"),
    ("via_drill_mm", "via_drill"),
)


def test_pydantic_netclass_rules_answers_mm_and_canonical_reads() -> None:
    """The generated Pydantic model answers both spellings identically."""
    from temper_placer.core.netclass_rules_gen import NetClassRules

    nc = NetClassRules(
        name="Signal",
        trace_width=0.2,
        clearance=0.15,
        via_diameter=0.6,
        via_drill=0.3,
    )
    for alias, canonical in _MM_PAIRS:
        assert getattr(nc, alias) == getattr(nc, canonical), (
            f"{alias} must delegate to {canonical} on the Pydantic model"
        )
    # The canonical field names remain the authoritative constructor surface.
    assert nc.trace_width == 0.2
    assert nc.clearance == 0.15


def test_temper_net_classes_answer_mm_reads() -> None:
    """TEMPER_NET_CLASSES (Pydantic objects) answer the router_v6 reads."""
    from temper_placer.core.design_rules import TEMPER_NET_CLASSES

    assert len(TEMPER_NET_CLASSES) >= 10
    for nc in TEMPER_NET_CLASSES.values():
        for alias, _canonical in _MM_PAIRS:
            assert hasattr(nc, alias), f"{nc.name} missing {alias}"


def test_rust_design_rules_pyclass_answers_mm_and_canonical_reads() -> None:
    """The Rust pyclass answers both spellings for the four scalars (#666)."""
    import temper_design_bundle_python as _tdb

    pytest.importorskip("temper_design_bundle_python")
    dr = _tdb.DesignRules(
        default_trace_width=0.2,
        default_clearance=0.15,
        default_via_diameter=0.6,
        default_via_drill=0.3,
    )
    # The constructor is the canonical non-_mm surface (#666 fixed the parser
    # that was passing _mm kwargs here).
    assert dr.default_trace_width == 0.2
    assert dr.default_clearance == 0.15
    assert dr.default_via_diameter == 0.6
    assert dr.default_via_drill == 0.3
    # The _mm read aliases added by #666 (validated/written in production by
    # stage0_data.py::ParsedPCB.validate_placement and the router_v6 reads).
    assert dr.default_trace_width_mm == 0.2
    assert dr.default_clearance_mm == 0.15
    assert dr.default_via_diameter_mm == 0.6
    assert dr.default_via_drill_mm == 0.3


def test_yaml_loaded_design_rules_net_classes_answer_mm_reads() -> None:
    """Production load path: YAML-loaded net classes answer router_v6 reads.

    This is the exact regression surface: ``load_netclass_rules()`` populates
    the Rust pyclass ``net_classes`` dict with Pydantic ``NetClassRules``
    objects, and ``route_pcb()`` / ``_apply_placements_to_pcb()`` read
    ``_mm`` spellings off ``get_rules_for_net()`` results. Before 592cf4b29
    every such read raised ``AttributeError``.
    """
    from temper_placer.io.netclass_loader import load_netclass_rules

    assert _RULES_PATH.exists(), f"Rules not found: {_RULES_PATH}"
    rules = load_netclass_rules(_RULES_PATH)
    dr = rules.design_rules

    assert dr.net_classes, "YAML loaded no net classes"
    for name, nc in dr.net_classes.items():
        for alias, _canonical in _MM_PAIRS:
            assert hasattr(nc, alias), f"net class {name} missing {alias}"

    # get_rules_for_net returns objects answering both spellings (the
    # router_v6 read path), including the Default fallback for unknown nets.
    for net_name in ("+170V_BUS", "AC_L", "definitely-not-a-net"):
        rc = dr.get_rules_for_net(net_name)
        for alias, _canonical in _MM_PAIRS:
            assert hasattr(rc, alias), f"{net_name} -> {rc.name} missing {alias}"
        # Values agree across spellings.
        for alias, canonical in _MM_PAIRS:
            assert getattr(rc, alias) == getattr(rc, canonical), (
                f"{net_name} -> {rc.name}: {alias} != {canonical}"
            )
