"""End-to-end regression test for the Temper induction cooker constraint pipeline.

Loads temper_induction_cooker.yaml, runs full pipeline:
1. Parse the PCL constraint file
2. Auto-enrich (decoupling detection + keepout emission)
3. Verify keepout constraints emitted for ISOLATION_BARRIER
4. Verify decoupling detection finds caps near IGBTs
5. Lint passes (no errors)
6. DRC compilation produces assertions for keepout constraints
"""

from __future__ import annotations

from pathlib import Path

import pytest

import yaml

from temper_placer.core.board import Board, Zone
from temper_placer.pcl.constraints import (
    CompilationContext,
    CompilationTarget,
    ConstraintType,
    KeepoutConstraint,
)
from temper_placer.pcl.parser import ConstraintCollection, parse_constraint_dict


CONFIG_PATH = Path(__file__).parent.parent.parent / "configs" / "constraints" / "temper_induction_cooker.yaml"


@pytest.fixture
def constraint_collection():
    """Load the Temper induction cooker PCL file.

    Pre-processes YAML to strip the 'zones' key which is not part of the
    PCL schema but used for board-level zone definitions.
    """
    assert CONFIG_PATH.exists(), f"Config not found: {CONFIG_PATH}"
    with open(CONFIG_PATH) as f:
        data = yaml.safe_load(f)
    constraints_data = data.get("constraints", [])
    parsed = [parse_constraint_dict(c) for c in constraints_data]
    return ConstraintCollection(constraints=parsed, version=data.get("version", "1.0"))


@pytest.fixture
def temper_board():
    """Build a minimal board matching the Temper cooker board."""
    return Board(
        width=120.0,
        height=80.0,
        zones=[
            Zone("HV_ZONE", (0, 0, 60, 80), zone_type="hv"),
            Zone("MCU_ZONE", (70, 0, 50, 80), zone_type="lv"),
            Zone("ISOLATION_BARRIER", (60, 0, 10, 80), zone_type="keepout"),
        ],
    )


class TestParseAndValidate:
    """Parse the YAML file and validate basic structure."""

    def test_parse_produces_constraints(self, constraint_collection):
        """Parsing the YAML file yields constraints."""
        assert len(constraint_collection) > 0, "Expected at least 1 constraint"

    def test_constraint_types_present(self, constraint_collection):
        """Key constraint types are present."""
        types_found = {c.constraint_type for c in constraint_collection.constraints}
        expected_types = {ConstraintType.ADJACENT, ConstraintType.SEPARATED, ConstraintType.ENCLOSING}
        for ct in expected_types:
            assert ct in types_found, f"Expected constraint type {ct.value}"

    def test_tiers_are_valid(self, constraint_collection):
        """All constraints have valid tiers."""
        for c in constraint_collection.constraints:
            assert c.tier is not None
            assert c.tier.value in (1, 2, 3)


class TestAutoEnrichKeepout:
    """Verify keepout constraints are auto-generated.

    Note: The YAML file defines ISOLATION_BARRIER as a zone with type=keepout.
    When auto_enrich runs with a board that has this zone, a KeepoutConstraint
    should be emitted.
    """

    def test_keepout_emitted_for_isolation_barrier(self, constraint_collection, temper_board):
        """auto_enrich emits KeepoutConstraint for ISOLATION_BARRIER zone."""
        from temper_placer.core.netlist import Netlist

        netlist = Netlist(components=[], nets=[])
        collection = constraint_collection.copy()
        collection.auto_enrich(netlist, temper_board)

        keepouts = [c for c in collection.constraints if isinstance(c, KeepoutConstraint)]
        assert len(keepouts) >= 1, f"Expected KeepoutConstraint, got {len(keepouts)}"
        iso_keepouts = [k for k in keepouts if k.zone_name == "ISOLATION_BARRIER"]
        assert len(iso_keepouts) >= 1, (
            f"Expected KeepoutConstraint for ISOLATION_BARRIER, "
            f"found zones: {[k.zone_name for k in keepouts]}"
        )

    def test_keepout_is_hard(self, constraint_collection, temper_board):
        """Keepout constraints from keepout zones are HARD tier."""
        from temper_placer.core.netlist import Netlist

        netlist = Netlist(components=[], nets=[])
        collection = constraint_collection.copy()
        collection.auto_enrich(netlist, temper_board)

        keepouts = [c for c in collection.constraints if isinstance(c, KeepoutConstraint)]
        for k in keepouts:
            if k.zone_name == "ISOLATION_BARRIER":
                from temper_placer.pcl.constraints import ConstraintTier
                assert k.tier == ConstraintTier.HARD, (
                    f"ISOLATION_BARRIER keepout should be HARD, got {k.tier}"
                )


class TestDecouplingDetection:
    """Verify decoupling detection in the pipeline context."""

    def test_decoupling_detection_finds_bulk_caps(self):
        """Detect C_BUS1/C_BUS2 as bulk caps near gate driver IC U_GATE."""
        from temper_placer.core.netlist import Component, Net, Netlist, Pin
        from temper_placer.losses.decoupling import auto_detect_decoupling

        u_gate_pins = [
            Pin("VCC1", "1", (0.0, 0.0), net="VCC1"),
            Pin("VCC2", "2", (0.0, 0.0), net="HV_DC"),
            Pin("GND", "3", (0.0, 0.0), net="GND_PWR"),
            Pin("HO", "4", (0.0, 0.0), net="GATE_H"),
            Pin("LO", "5", (0.0, 0.0), net="GATE_L"),
        ]
        cbus1_pins = [
            Pin("1", "1", (0.0, 0.0), net="HV_DC"),
            Pin("2", "2", (0.0, 0.0), net="GND_PWR"),
        ]
        cbus2_pins = [
            Pin("1", "1", (0.0, 0.0), net="HV_DC"),
            Pin("2", "2", (0.0, 0.0), net="GND_PWR"),
        ]

        nl = Netlist(
            components=[
                Component(ref="U_GATE", footprint="SOIC-16", bounds=(10.0, 6.0), pins=u_gate_pins),
                Component(ref="C_BUS1", footprint="ELEC_D12_5", bounds=(12.5, 20.0), pins=cbus1_pins),
                Component(ref="C_BUS2", footprint="ELEC_D12_5", bounds=(12.5, 20.0), pins=cbus2_pins),
            ],
            nets=[
                Net("HV_DC", [("U_GATE", "VCC2"), ("C_BUS1", "1"), ("C_BUS2", "1")], net_class="Power"),
                Net("GND_PWR", [("U_GATE", "GND"), ("C_BUS1", "2"), ("C_BUS2", "2")], net_class="Power"),
                Net("VCC1", [("U_GATE", "VCC1")], net_class="Power"),
                Net("GATE_H", [("U_GATE", "HO")], net_class="Signal"),
                Net("GATE_L", [("U_GATE", "LO")], net_class="Signal"),
            ],
        )

        rules = auto_detect_decoupling(nl)

        # C_BUS1 and C_BUS2 should be detected as decoupling
        detected_caps = {r.cap_ref for r in rules}
        assert "C_BUS1" in detected_caps, f"Expected C_BUS1 in detections, got {detected_caps}"
        assert "C_BUS2" in detected_caps, f"Expected C_BUS2 in detections, got {detected_caps}"

        # They should be classified as BULK due to ELEC_D12_5 footprint
        from temper_placer.losses.decoupling import auto_detect_decoupling_set
        dset = auto_detect_decoupling_set(nl)
        for d in dset:
            if d.cap_ref in ("C_BUS1", "C_BUS2"):
                assert d.classification.name == "BULK", (
                    f"Expected BULK for {d.cap_ref}, got {d.classification.name}"
                )


class TestLintPasses:
    """Verify lint passes on the constraint set."""

    def test_lint_passes_with_minimal_netlist(self, constraint_collection, temper_board):
        """Lint should produce no errors with a minimal netlist and board."""
        from temper_placer.core.netlist import Component, Net, Netlist, Pin

        # Build a netlist with the components referenced in the YAML
        # (zone references are uppercase and won't be checked as components)
        comps = []
        for ref in ["Q1", "Q2", "U_GATE", "C_BUS1", "C_BUS2", "J_AC", "J_COIL",
                     "U_MCU", "J_DEBUG", "C_VCC1", "C_VCC2", "D_BOOT", "C_BOOT",
                     "C_TANK", "U_RTD", "J_FAN", "U_SPI_FLASH", "CT1", "R_BURDEN"]:
            comps.append(Component(
                ref=ref,
                footprint="0603",
                bounds=(5.0, 5.0),
                pins=[Pin("1", "1", (0.0, 0.0), net="NET1")],
            ))
        netlist = Netlist(components=comps, nets=[Net("NET1", [(r, "1") for r in ["Q1", "Q2"]])])

        result = constraint_collection.lint(netlist, temper_board)
        assert result.passed, (
            f"Lint should pass, got errors: {[e.message for e in result.errors]}"
        )


class TestDRCCompilation:
    """Verify DRC compilation produces assertions."""

    def test_drc_compilation_produces_keepout_assertions(self, temper_board):
        """DRC compilation for keepout constraints produces keepout-type assertions."""
        from temper_placer.core.netlist import Netlist
        from temper_placer.pcl.constraints import CompilationContext, ConstraintTier, KeepoutConstraint
        from temper_placer.pcl.parser import ConstraintCollection
        import temper_placer.pcl.drc_bridge  # noqa: F401  triggers backend registration

        netlist = Netlist(components=[], nets=[])
        kc = KeepoutConstraint(
            zone_name="ISOLATION_BARRIER",
            tier=ConstraintTier.HARD,
            because="Safety isolation for DRC test",
        )
        kc.targets = ["jax", "drc"]  # Ensure DRC target is included
        collection = ConstraintCollection(constraints=[kc])

        ctx = CompilationContext(netlist=netlist, board=temper_board)
        assertions = collection.compile(CompilationTarget.DRC, ctx)
        assert len(assertions) > 0, "DRC compilation should produce assertions"

        # Flatten list of lists
        flat = []
        for a in assertions:
            if isinstance(a, list):
                flat.extend(a)
            else:
                flat.append(a)
        keepout_assertions = [a for a in flat if hasattr(a, "check_type") and a.check_type == "keepout"]
        assert len(keepout_assertions) >= 1, (
            f"Expected keepout DRC assertions, got types: "
            f"{[getattr(a, 'check_type', type(a).__name__) for a in flat]}"
        )


class TestConstraintPipeline:
    """Full pipeline: parse -> enrich -> lint -> compile."""

    def test_full_pipeline_no_crash(self, constraint_collection, temper_board):
        """Full pipeline runs without exceptions."""
        from temper_placer.core.netlist import Component, Net, Netlist, Pin

        comps = []
        for ref in ["Q1", "Q2", "U_GATE", "C_BUS1", "C_BUS2", "J_AC", "J_COIL",
                     "U_MCU", "J_DEBUG", "C_VCC1", "C_VCC2", "D_BOOT", "C_BOOT",
                     "C_TANK", "U_RTD", "J_FAN", "U_SPI_FLASH", "CT1", "R_BURDEN"]:
            comps.append(Component(
                ref=ref,
                footprint="0603" if not ref.startswith("C_") else "ELEC_D12_5",
                bounds=(5.0, 5.0),
                pins=[Pin("1", "1", (0.0, 0.0), net="NET1")],
            ))
        netlist = Netlist(components=comps, nets=[Net("NET1", [("Q1", "1"), ("Q2", "1")])])

        collection = constraint_collection.copy()

        # Enrich
        collection.auto_enrich(netlist, temper_board)

        # Lint
        lint_result = collection.lint(netlist, temper_board)
        assert lint_result.passed, f"Lint failed: {lint_result.errors}"

        # JAX compile (default target for all constraints)
        ctx = CompilationContext(netlist=netlist, board=temper_board)
        jax_losses = collection.compile(CompilationTarget.JAX, ctx)
        assert jax_losses is not None
        assert len(jax_losses) > 0, "JAX compilation should produce loss functions"

        # DRC compile for constraints that have drc target
        import temper_placer.pcl.drc_bridge  # noqa: F401  triggers backend registration
        drc_assertions = collection.compile(CompilationTarget.DRC, ctx)
        assert drc_assertions is not None
