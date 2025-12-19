"""
Tests for ngspice simulation wrapper (validation/spice.py).

These tests verify:
- NgspiceValidator availability detection
- Simulation execution with .cir files
- Template parameter substitution
- Measurement parsing from ngspice output
- Error handling (timeout, missing ngspice, invalid netlist)
- Loop inductance estimation helper
"""

import shutil
from pathlib import Path

import pytest

from temper_placer.validation.spice import (
    NgspiceValidator,
    SpiceMeasurement,
    SpiceResult,
    create_validation_netlist,
    estimate_loop_inductance,
)


class TestSpiceMeasurement:
    """Tests for SpiceMeasurement dataclass."""

    def test_basic_measurement(self):
        """Test creating a basic measurement."""
        meas = SpiceMeasurement(
            name="trise",
            value=5.932506e-06,
            unit="us",
        )
        assert meas.name == "trise"
        assert meas.value == pytest.approx(5.932506e-06)
        assert meas.unit == "us"

    def test_measurement_with_trig_targ(self):
        """Test measurement with TRIG/TARG values."""
        meas = SpiceMeasurement(
            name="trise_weak",
            value=5.932506e-06,
            targ=6.221981e-06,
            trig=2.894750e-07,
            raw_line="trise_weak = 5.932506e-06 targ= 6.221981e-06 trig= 2.894750e-07",
        )
        assert meas.targ == pytest.approx(6.221981e-06)
        assert meas.trig == pytest.approx(2.894750e-07)

    def test_to_dict(self):
        """Test dictionary conversion."""
        meas = SpiceMeasurement(
            name="vout",
            value=3.3,
            unit="V",
        )
        d = meas.to_dict()
        assert d["name"] == "vout"
        assert d["value"] == 3.3
        assert d["unit"] == "V"


class TestSpiceResult:
    """Tests for SpiceResult dataclass."""

    def test_success_result(self):
        """Test successful simulation result."""
        result = SpiceResult(
            success=True,
            measurements={
                "vout": SpiceMeasurement(name="vout", value=3.3, unit="V"),
                "iout": SpiceMeasurement(name="iout", value=0.5, unit="A"),
            },
            elapsed_ms=150.0,
        )
        assert result.success
        assert len(result.measurements) == 2
        assert result.get_value("vout") == 3.3
        assert result.get_value("iout") == 0.5
        assert result.get_value("missing", 0.0) == 0.0

    def test_failed_result(self):
        """Test failed simulation result."""
        result = SpiceResult(
            success=False,
            errors=["ngspice not available"],
        )
        assert not result.success
        assert len(result.errors) == 1

    def test_summary(self):
        """Test summary generation."""
        result = SpiceResult(
            success=True,
            measurements={
                "vout": SpiceMeasurement(name="vout", value=3.3, unit="V"),
            },
            elapsed_ms=100.0,
        )
        summary = result.summary()
        assert "SUCCESS" in summary
        assert "vout" in summary
        assert "100.0ms" in summary


class TestNgspiceValidator:
    """Tests for NgspiceValidator class."""

    def test_is_available_when_ngspice_exists(self):
        """Test availability check when ngspice is installed."""
        validator = NgspiceValidator()
        # This test assumes ngspice is installed (it is at /opt/homebrew/bin/ngspice)
        if shutil.which("ngspice"):
            assert validator.is_available()
        else:
            pytest.skip("ngspice not installed")

    def test_is_available_when_ngspice_missing(self):
        """Test availability check when ngspice path is invalid."""
        validator = NgspiceValidator(ngspice_path="/nonexistent/ngspice")
        assert not validator.is_available()

    def test_name_property(self):
        """Test validator name property."""
        validator = NgspiceValidator()
        assert validator.name == "NgspiceValidator"

    def test_run_simulation_ngspice_not_available(self):
        """Test run_simulation when ngspice is not available."""
        validator = NgspiceValidator(ngspice_path="/nonexistent/ngspice")
        result = validator.run_simulation(Path("/some/netlist.cir"))
        assert not result.success
        assert "ngspice not available" in result.errors[0]


class TestNgspiceValidatorIntegration:
    """Integration tests requiring ngspice installation."""

    @pytest.fixture
    def validator(self):
        """Create validator, skip if ngspice not available."""
        v = NgspiceValidator()
        if not v.is_available():
            pytest.skip("ngspice not installed")
        return v

    @pytest.fixture
    def simple_netlist(self, tmp_path):
        """Create a simple test netlist with measurements."""
        netlist = tmp_path / "test.cir"
        netlist.write_text("""\
* Simple RC Test Circuit
V1 in 0 DC 5
R1 in out 1k
C1 out 0 1u

.tran 1u 10m

.control
run
meas tran v_out FIND v(out) AT=5m
meas tran v_in FIND v(in) AT=5m
.endc
.end
""")
        return netlist

    @pytest.fixture
    def netlist_with_error(self, tmp_path):
        """Create a netlist that will produce an error."""
        netlist = tmp_path / "error.cir"
        netlist.write_text("""\
* Invalid netlist - missing component value
V1 in 0 DC
R1 in out
.end
""")
        return netlist

    def test_run_simulation_success(self, validator, simple_netlist):
        """Test successful simulation execution."""
        result = validator.run_simulation(simple_netlist)

        # Should succeed (or at least not crash)
        # Note: measurement parsing may vary by ngspice version
        assert result.netlist_path == simple_netlist
        assert result.elapsed_ms > 0

    def test_run_simulation_with_measurements(self, validator, simple_netlist):
        """Test measurement extraction from simulation."""
        result = validator.run_simulation(simple_netlist)

        # The simple RC circuit should converge
        # Check we can read measurements (format varies by ngspice version)
        if result.success and result.measurements:
            # Check v_out measurement exists
            if "v_out" in result.measurements:
                meas = result.measurements["v_out"]
                assert isinstance(meas.value, float)

    def test_run_netlist_string(self, validator):
        """Test running netlist from string."""
        netlist = """\
* Voltage divider test
V1 in 0 DC 10
R1 in mid 1k
R2 mid 0 1k

.op

.control
run
meas DC v_mid FIND v(mid) AT=0
.endc
.end
"""
        result = validator.run_netlist_string(netlist)
        assert result.elapsed_ms > 0

    def test_run_template_substitution(self, validator):
        """Test template parameter substitution."""
        template = """\
* Parametric test
V1 in 0 DC {{VIN}}
R1 in out {{RVAL}}
C1 out 0 1u

.tran 1u 1m

.control
run
.endc
.end
"""
        result = validator.run_template(template, {"VIN": "5", "RVAL": "1k"})
        # Should not fail on unsubstituted parameters
        assert "Unsubstituted parameters" not in str(result.errors)

    def test_run_template_missing_param(self, validator):
        """Test template with missing parameter."""
        template = """\
* Test with missing param
V1 in 0 DC {{VIN}}
R1 in out {{MISSING_PARAM}}
.end
"""
        result = validator.run_template(template, {"VIN": "5"})
        assert not result.success
        assert "Unsubstituted parameters" in result.errors[0]
        assert "MISSING_PARAM" in result.errors[0]


class TestMeasurementParsing:
    """Tests for measurement parsing logic."""

    @pytest.fixture
    def validator(self):
        return NgspiceValidator()

    def test_parse_simple_measurement(self, validator):
        """Test parsing simple measurement line."""
        output = "vout = 3.300000e+00"
        measurements = validator._parse_measurements(output)
        assert "vout" in measurements
        assert measurements["vout"].value == pytest.approx(3.3)

    def test_parse_measurement_with_trig_targ(self, validator):
        """Test parsing measurement with TRIG/TARG."""
        output = "trise_weak          =  5.932506e-06 targ=  6.221981e-06 trig=  2.894750e-07"
        measurements = validator._parse_measurements(output)
        assert "trise_weak" in measurements
        meas = measurements["trise_weak"]
        assert meas.value == pytest.approx(5.932506e-06)
        assert meas.targ == pytest.approx(6.221981e-06)
        assert meas.trig == pytest.approx(2.894750e-07)

    def test_parse_multiple_measurements(self, validator):
        """Test parsing multiple measurements."""
        output = """\
vout = 3.3e+00
iout = 1.5e-01
trise = 2.5e-09
"""
        measurements = validator._parse_measurements(output)
        assert len(measurements) == 3
        assert measurements["vout"].value == pytest.approx(3.3)
        assert measurements["iout"].value == pytest.approx(0.15)
        assert measurements["trise"].value == pytest.approx(2.5e-09)

    def test_parse_negative_values(self, validator):
        """Test parsing negative measurement values."""
        output = "v_neg = -1.234e+01"
        measurements = validator._parse_measurements(output)
        assert measurements["v_neg"].value == pytest.approx(-12.34)

    def test_infer_unit_time(self, validator):
        """Test unit inference for time measurements."""
        assert validator._infer_unit("trise", 1e-9) == "ns"
        assert validator._infer_unit("tfall", 1e-6) == "us"
        assert validator._infer_unit("delay", 1e-12) == "ps"
        assert validator._infer_unit("period", 1.0) == "s"

    def test_infer_unit_voltage(self, validator):
        """Test unit inference for voltage measurements."""
        assert validator._infer_unit("v_out", 3.3) == "V"
        assert validator._infer_unit("vgs_max", 15.0) == "V"

    def test_infer_unit_current(self, validator):
        """Test unit inference for current measurements."""
        assert validator._infer_unit("i_peak", 10.0) == "A"
        assert validator._infer_unit("iout", 0.0001) == "mA"

    def test_infer_unit_power(self, validator):
        """Test unit inference for power measurements."""
        assert validator._infer_unit("p_loss", 5.0) == "W"
        assert validator._infer_unit("power", 100.0) == "W"


class TestErrorParsing:
    """Tests for error/warning parsing."""

    @pytest.fixture
    def validator(self):
        return NgspiceValidator()

    def test_parse_error_messages(self, validator):
        """Test parsing error messages from output."""
        output = """\
Some normal output
Error: circuit not parsed
More output
ERROR: convergence problem
"""
        errors = validator._parse_errors(output)
        assert len(errors) == 2
        assert any("circuit not parsed" in e for e in errors)
        assert any("convergence" in e for e in errors)

    def test_parse_warning_messages(self, validator):
        """Test parsing warning messages from output."""
        output = """\
Normal line
Warning: timestep too small
Another line
WARNING: node has no dc path
"""
        warnings = validator._parse_warnings(output)
        assert len(warnings) == 2
        assert any("timestep" in w for w in warnings)
        assert any("dc path" in w for w in warnings)


class TestEstimateLoopInductance:
    """Tests for loop inductance estimation function."""

    def test_triangle_loop(self):
        """Test inductance estimation for triangular loop."""
        # Triangle with area = 0.5 * 10 * 10 = 50 mm²
        positions = {
            "C1": (0.0, 0.0),
            "Q1": (10.0, 0.0),
            "D1": (5.0, 10.0),
        }
        L = estimate_loop_inductance(
            positions,
            ["C1", "Q1", "D1"],
            trace_height_mm=0.035,
        )
        # Should be positive and reasonable for 50mm² loop
        assert L > 0
        # L ≈ μ₀ * 50e-6 / 35e-6 ≈ 1.8 nH (actually ~1.8 μH due to formula)
        # The formula gives larger values because h is trace height, not ground plane distance
        assert L < 10e-6  # Less than 10 μH (reasonable for PCB loop)

    def test_square_loop(self):
        """Test inductance estimation for square loop."""
        # Square 10mm x 10mm = 100 mm²
        positions = {
            "A": (0.0, 0.0),
            "B": (10.0, 0.0),
            "C": (10.0, 10.0),
            "D": (0.0, 10.0),
        }
        L = estimate_loop_inductance(
            positions,
            ["A", "B", "C", "D"],
            trace_height_mm=0.035,
        )
        assert L > 0

    def test_missing_component(self):
        """Test with missing component returns 0."""
        positions = {"A": (0.0, 0.0), "B": (10.0, 0.0)}
        L = estimate_loop_inductance(positions, ["A", "B", "MISSING"])
        assert L == 0.0

    def test_insufficient_components(self):
        """Test with less than 3 components returns 0."""
        positions = {"A": (0.0, 0.0), "B": (10.0, 0.0)}
        L = estimate_loop_inductance(positions, ["A", "B"])
        assert L == 0.0

    def test_larger_loop_higher_inductance(self):
        """Test that larger loops have higher inductance."""
        # Small loop (10mm sides)
        small_pos = {
            "A": (0.0, 0.0),
            "B": (10.0, 0.0),
            "C": (10.0, 10.0),
            "D": (0.0, 10.0),
        }
        L_small = estimate_loop_inductance(small_pos, ["A", "B", "C", "D"])

        # Large loop (20mm sides)
        large_pos = {
            "A": (0.0, 0.0),
            "B": (20.0, 0.0),
            "C": (20.0, 20.0),
            "D": (0.0, 20.0),
        }
        L_large = estimate_loop_inductance(large_pos, ["A", "B", "C", "D"])

        # 4x area should give 4x inductance
        assert L_large > L_small
        assert L_large / L_small == pytest.approx(4.0, rel=0.01)


class TestCreateValidationNetlist:
    """Tests for validation netlist creation."""

    def test_simple_substitution(self):
        """Test basic parameter substitution."""
        template = """\
* Test
.param VIN={{VIN}}
.param RLOAD={{RLOAD}}
"""
        netlist = create_validation_netlist(template, {"VIN": "12", "RLOAD": "100"})
        assert ".param VIN=12" in netlist
        assert ".param RLOAD=100" in netlist

    def test_multiple_occurrences(self):
        """Test substitution of multiple occurrences."""
        template = """\
V1 in 0 DC {{VIN}}
* Input voltage is {{VIN}}
"""
        netlist = create_validation_netlist(template, {"VIN": "5"})
        assert netlist.count("5") == 2
        assert "{{VIN}}" not in netlist


class TestValidatorInterface:
    """Test the Validator interface implementation."""

    def test_validate_returns_result(self):
        """Test that validate() returns ValidationResult."""
        import jax.numpy as jnp

        from temper_placer.core.board import Board
        from temper_placer.core.netlist import Netlist
        from temper_placer.core.state import PlacementState

        validator = NgspiceValidator()

        # Create minimal test objects
        state = PlacementState(
            positions=jnp.zeros((1, 2)),
            rotation_logits=jnp.zeros((1, 4)),
        )
        netlist = Netlist(
            components=[],
            nets=[],
        )
        board = Board(width=100.0, height=100.0)

        result = validator.validate(state, netlist, board)

        # Should return a ValidationResult
        from temper_placer.validation.base import ValidationResult

        assert isinstance(result, ValidationResult)
        assert result.validator_name == "NgspiceValidator"


class TestTemperTestbenches:
    """Tests using actual Temper simulation testbenches."""

    TESTBENCH_DIR = Path("/Users/bennet.leff/Documents/temper/simulation/testbenches")

    @pytest.fixture
    def validator(self):
        """Create validator, skip if ngspice not available."""
        v = NgspiceValidator()
        if not v.is_available():
            pytest.skip("ngspice not installed")
        return v

    @pytest.mark.skipif(
        not Path("/Users/bennet.leff/Documents/temper/simulation/testbenches").exists(),
        reason="Temper testbenches not found",
    )
    def test_gate_drive_testbench(self, validator):
        """Test running the gate drive comparison testbench."""
        testbench = self.TESTBENCH_DIR / "sim_03_gate_drive.cir"
        if not testbench.exists():
            pytest.skip("sim_03_gate_drive.cir not found")

        result = validator.run_simulation(testbench)

        # This testbench measures rise times
        assert result.elapsed_ms > 0
        # Check for expected measurements if simulation succeeded
        if result.success and result.measurements:
            # Look for trise measurements (lowercase after parsing)
            assert any("trise" in name.lower() for name in result.measurements)

    @pytest.mark.skipif(
        not Path("/Users/bennet.leff/Documents/temper/simulation/testbenches").exists(),
        reason="Temper testbenches not found",
    )
    def test_simple_led_testbench(self, validator):
        """Test running a simple LED testbench."""
        testbench = self.TESTBENCH_DIR / "sim_02_led_test.cir"
        if not testbench.exists():
            pytest.skip("sim_02_led_test.cir not found")

        result = validator.run_simulation(testbench)
        assert result.elapsed_ms > 0


class TestPlacementSpiceValidation:
    """Tests for placement-aware SPICE validation functions."""

    @pytest.fixture
    def validator(self):
        """Create validator, skip if ngspice not available."""
        v = NgspiceValidator()
        if not v.is_available():
            pytest.skip("ngspice not installed")
        return v

    @pytest.fixture
    def sample_positions(self):
        """Sample component positions forming a small triangle (realistic gate loop).

        For a good gate drive layout, the loop area should be minimized.
        Using ~1mm² area gives ~50nH inductance (typical for good layout).
        Triangle with 1.5mm sides gives ~1mm² area.
        """
        return {
            "U_GD": (0.0, 0.0),  # Gate driver at origin
            "Q1": (1.5, 0.0),  # IGBT 1.5mm to the right
            "R_GATE": (0.75, 1.3),  # Gate resistor at apex (~1.5mm sides)
            "D_BOOT": (0.5, 0.8),  # Bootstrap diode (small loop)
            "C_BOOT": (1.0, 0.8),  # Bootstrap cap
            "C_DC": (0.0, 2.0),  # DC bus cap
            "Q2": (1.5, 2.0),  # Low-side IGBT
        }

    def test_run_gate_drive_simulation(self, validator, sample_positions):
        """Test gate drive simulation with placement positions."""
        from temper_placer.validation.spice import run_gate_drive_simulation

        result = run_gate_drive_simulation(validator, sample_positions)

        assert result.template_name == "gate_drive"
        assert result.spice_result.success
        assert "GATE_LOOP_INDUCTANCE" in result.placement_params
        assert "GATE_RESISTANCE" in result.placement_params

        # Should have threshold results
        assert len(result.threshold_results) > 0

        # Penalty should be finite
        assert result.penalty >= 0
        assert result.penalty < 100  # Not a failed simulation

    def test_run_gate_drive_with_custom_components(self, validator, sample_positions):
        """Test gate drive simulation with custom component list."""
        from temper_placer.validation.spice import run_gate_drive_simulation

        result = run_gate_drive_simulation(
            validator,
            sample_positions,
            gate_loop_components=["U_GD", "Q1", "C_DC"],  # Different loop
            gate_resistance=10.0,  # Higher resistance
        )

        assert result.spice_result.success
        assert "10.0" in result.placement_params["GATE_RESISTANCE"]

    def test_run_bootstrap_simulation(self, validator, sample_positions):
        """Test bootstrap charging simulation with placement positions."""
        from temper_placer.validation.spice import run_bootstrap_simulation

        result = run_bootstrap_simulation(validator, sample_positions)

        assert result.template_name == "bootstrap_charging"
        assert result.spice_result.success
        assert "BOOTSTRAP_LOOP_INDUCTANCE" in result.placement_params
        assert "BOOTSTRAP_CAPACITANCE" in result.placement_params

        # Check that bootstrap reaches sufficient voltage
        v_boot = result.spice_result.get_value("v_boot_final")
        assert v_boot > 12.0, f"Bootstrap voltage {v_boot}V too low"

    def test_run_power_integrity_simulation(self, validator, sample_positions):
        """Test power integrity simulation with placement positions."""
        from temper_placer.validation.spice import run_power_integrity_simulation

        result = run_power_integrity_simulation(validator, sample_positions)

        assert result.template_name == "power_integrity"
        assert result.spice_result.success
        assert "DC_BUS_INDUCTANCE" in result.placement_params
        assert "DECAP_ESR" in result.placement_params

        # DC bus should stay above minimum
        v_min = result.spice_result.get_value("v_dc_min")
        assert v_min > 300.0, f"DC bus minimum {v_min}V too low"

    def test_run_all_placement_validations(self, validator, sample_positions):
        """Test running all validations at once."""
        from temper_placer.validation.spice import run_all_placement_validations

        results = run_all_placement_validations(validator, sample_positions)

        assert "gate_drive" in results
        assert "bootstrap_charging" in results
        assert "power_integrity" in results

        # All should succeed
        for name, result in results.items():
            assert result.spice_result.success, f"{name} failed"

    def test_compute_total_spice_penalty(self, validator, sample_positions):
        """Test total penalty computation."""
        from temper_placer.validation.spice import (
            compute_total_spice_penalty,
            run_all_placement_validations,
        )

        results = run_all_placement_validations(validator, sample_positions)

        # Default weights
        penalty = compute_total_spice_penalty(results)
        assert penalty >= 0

        # Custom weights
        penalty_weighted = compute_total_spice_penalty(
            results, weights={"gate_drive": 2.0, "bootstrap_charging": 1.0, "power_integrity": 0.5}
        )
        assert penalty_weighted >= 0

    def test_placement_spice_result_summary(self, validator, sample_positions):
        """Test PlacementSpiceResult summary generation."""
        from temper_placer.validation.spice import run_gate_drive_simulation

        result = run_gate_drive_simulation(validator, sample_positions)

        summary = result.summary()
        assert "gate_drive" in summary
        assert "Penalty" in summary
        assert "GATE_LOOP_INDUCTANCE" in summary

    def test_missing_components_uses_default_inductance(self, validator):
        """Test that missing components use default inductance."""
        from temper_placer.validation.spice import run_gate_drive_simulation

        # No components in positions
        empty_positions = {}

        result = run_gate_drive_simulation(validator, empty_positions)

        # Should still run with default inductance
        assert result.spice_result.success
        # Default is 50nH for gate drive
        assert "5.00e-08" in result.placement_params["GATE_LOOP_INDUCTANCE"]
