"""
ngspice simulation wrapper for electrical validation.

This module provides:
- NgspiceValidator: Run SPICE simulations and extract measurements
- Template-based simulation with parameter substitution
- Measurement parsing from ngspice output
- Integration with validation framework

ngspice is invoked in batch mode (-b) for non-interactive execution.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from temper_placer.core.board import Board
from temper_placer.core.netlist import Netlist
from temper_placer.core.state import PlacementState
from temper_placer.validation.base import (
    ValidationIssue,
    ValidationResult,
    ValidationSeverity,
    Validator,
)


@dataclass
class SpiceMeasurement:
    """
    A measurement extracted from ngspice output.

    Attributes:
        name: Measurement name (from .meas statement).
        value: Measured value (numeric).
        unit: Optional unit (V, A, s, W, etc.).
        targ: Target value for TRIG/TARG measurements.
        trig: Trigger value for TRIG/TARG measurements.
        raw_line: Original output line from ngspice.
    """

    name: str
    value: float
    unit: str = ""
    targ: Optional[float] = None
    trig: Optional[float] = None
    raw_line: str = ""

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "name": self.name,
            "value": self.value,
            "unit": self.unit,
            "targ": self.targ,
            "trig": self.trig,
        }


@dataclass
class SpiceResult:
    """
    Result from running an ngspice simulation.

    Attributes:
        success: Whether simulation completed without errors.
        measurements: Dict of measurement name -> SpiceMeasurement.
        errors: List of error messages.
        warnings: List of warning messages.
        stdout: Full stdout from ngspice.
        stderr: Full stderr from ngspice.
        elapsed_ms: Time taken for simulation.
        netlist_path: Path to the netlist that was simulated.
    """

    success: bool
    measurements: Dict[str, SpiceMeasurement] = field(default_factory=dict)
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    stdout: str = ""
    stderr: str = ""
    elapsed_ms: float = 0.0
    netlist_path: Optional[Path] = None

    def get_value(self, name: str, default: float = 0.0) -> float:
        """Get a measurement value by name."""
        if name in self.measurements:
            return self.measurements[name].value
        return default

    def summary(self) -> str:
        """Get a human-readable summary."""
        status = "SUCCESS" if self.success else "FAILED"
        lines = [f"SPICE Simulation {status}"]

        if self.measurements:
            lines.append(f"Measurements ({len(self.measurements)}):")
            for name, meas in self.measurements.items():
                lines.append(f"  {name} = {meas.value:.6e}")

        if self.errors:
            lines.append(f"Errors ({len(self.errors)}):")
            for err in self.errors[:5]:
                lines.append(f"  {err}")

        lines.append(f"Elapsed: {self.elapsed_ms:.1f}ms")
        return "\n".join(lines)


class NgspiceValidator(Validator):
    """
    Validator that runs ngspice simulations for electrical validation.

    Can run arbitrary SPICE netlists or use templates with parameter
    substitution for validation-in-the-loop.

    Example usage:
        validator = NgspiceValidator()

        # Run a netlist file
        result = validator.run_simulation(Path("sim_01.cir"))
        print(result.measurements)

        # Run with parameter substitution
        template = '''
        .param LOOP_L={{LOOP_INDUCTANCE}}
        * rest of netlist
        '''
        result = validator.run_template(
            template,
            {"LOOP_INDUCTANCE": "50n"}
        )
    """

    def __init__(
        self,
        ngspice_path: Optional[str] = None,
        timeout_seconds: float = 60.0,
        working_dir: Optional[Path] = None,
    ):
        """
        Initialize ngspice validator.

        Args:
            ngspice_path: Path to ngspice binary. If None, uses 'ngspice' from PATH.
            timeout_seconds: Maximum time for simulation.
            working_dir: Working directory for simulation. If None, uses temp dir.
        """
        self.ngspice_path = ngspice_path or shutil.which("ngspice")
        self.timeout_seconds = timeout_seconds
        self.working_dir = working_dir

        # Measurement parsing patterns
        # Note: ngspice outputs "targ=  value" (with spaces after =)
        self._meas_pattern = re.compile(
            r"^(\w+)\s*=\s*([+-]?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)"
            r"(?:\s+targ=\s*([+-]?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?))?"
            r"(?:\s+trig=\s*([+-]?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?))?"
        )
        self._error_pattern = re.compile(r"Error[:\s]|ERROR[:\s]|fatal", re.IGNORECASE)
        self._warning_pattern = re.compile(r"Warning[:\s]|WARNING[:\s]", re.IGNORECASE)

    @property
    def name(self) -> str:
        return "NgspiceValidator"

    def is_available(self) -> bool:
        """Check if ngspice is available."""
        return self.ngspice_path is not None and Path(self.ngspice_path).exists()

    def validate(
        self,
        state: PlacementState,
        netlist: Netlist,
        board: Board,
    ) -> ValidationResult:
        """
        Run validation using SPICE simulation.

        This is the Validator interface method. For placement validation,
        you typically want to use run_simulation() or run_template() directly
        with placement-derived parameters.

        Args:
            state: Current placement state.
            netlist: Component netlist.
            board: Board definition.

        Returns:
            ValidationResult (always valid if ngspice is available,
            actual validation requires running specific simulations).
        """
        start_time = time.time()
        issues: List[ValidationIssue] = []
        metrics: Dict[str, float] = {}

        if not self.is_available():
            issues.append(
                ValidationIssue(
                    severity=ValidationSeverity.WARNING,
                    code="SPICE_NOT_AVAILABLE",
                    message="ngspice is not available - skipping SPICE validation",
                )
            )
            return ValidationResult(
                valid=True,  # Not invalid, just skipped
                issues=issues,
                metrics=metrics,
                elapsed_ms=(time.time() - start_time) * 1000,
                validator_name=self.name,
            )

        # Basic validation just confirms ngspice is available
        # Real validation happens via run_simulation() with specific netlists
        metrics["ngspice_available"] = 1.0

        return ValidationResult(
            valid=True,
            issues=issues,
            metrics=metrics,
            elapsed_ms=(time.time() - start_time) * 1000,
            validator_name=self.name,
        )

    def run_simulation(
        self,
        netlist_path: Path,
        include_paths: Optional[List[Path]] = None,
    ) -> SpiceResult:
        """
        Run an ngspice simulation on a netlist file.

        Args:
            netlist_path: Path to the SPICE netlist (.cir file).
            include_paths: Additional include paths for .include directives.

        Returns:
            SpiceResult with measurements and status.
        """
        if not self.is_available():
            return SpiceResult(
                success=False,
                errors=["ngspice not available"],
            )

        start_time = time.time()

        # Build command
        cmd = [self.ngspice_path, "-b", str(netlist_path)]

        # Set up environment with include paths
        env = os.environ.copy()
        if include_paths:
            env["SPICE_LIB_DIR"] = ":".join(str(p) for p in include_paths)

        # Determine working directory
        work_dir = self.working_dir or netlist_path.parent

        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=self.timeout_seconds,
                cwd=work_dir,
                env=env,
            )

            stdout = proc.stdout
            stderr = proc.stderr

            # Parse results
            measurements = self._parse_measurements(stdout)
            errors = self._parse_errors(stdout + stderr)
            warnings = self._parse_warnings(stdout + stderr)

            # Determine success
            success = proc.returncode == 0 and len(errors) == 0

            elapsed_ms = (time.time() - start_time) * 1000

            return SpiceResult(
                success=success,
                measurements=measurements,
                errors=errors,
                warnings=warnings,
                stdout=stdout,
                stderr=stderr,
                elapsed_ms=elapsed_ms,
                netlist_path=netlist_path,
            )

        except subprocess.TimeoutExpired:
            return SpiceResult(
                success=False,
                errors=[f"Simulation timed out after {self.timeout_seconds}s"],
                elapsed_ms=self.timeout_seconds * 1000,
                netlist_path=netlist_path,
            )
        except Exception as e:
            return SpiceResult(
                success=False,
                errors=[f"Simulation error: {str(e)}"],
                elapsed_ms=(time.time() - start_time) * 1000,
                netlist_path=netlist_path,
            )

    def run_template(
        self,
        template: str,
        parameters: Dict[str, str],
        include_paths: Optional[List[Path]] = None,
        cleanup: bool = True,
    ) -> SpiceResult:
        """
        Run simulation with parameter substitution.

        Parameters in the template are specified as {{PARAM_NAME}} and
        will be replaced with values from the parameters dict.

        Args:
            template: SPICE netlist template with {{PARAM}} placeholders.
            parameters: Dict of parameter name -> value (as strings).
            include_paths: Additional include paths.
            cleanup: Whether to delete temp files after simulation.

        Returns:
            SpiceResult with measurements and status.
        """
        # Substitute parameters
        netlist = template
        for name, value in parameters.items():
            placeholder = "{{" + name + "}}"
            netlist = netlist.replace(placeholder, str(value))

        # Check for unsubstituted placeholders
        remaining = re.findall(r"\{\{(\w+)\}\}", netlist)
        if remaining:
            return SpiceResult(
                success=False,
                errors=[f"Unsubstituted parameters: {remaining}"],
            )

        # Write to temp file and run
        temp_dir = tempfile.mkdtemp(prefix="ngspice_")
        temp_path = Path(temp_dir) / "simulation.cir"

        try:
            temp_path.write_text(netlist)
            result = self.run_simulation(temp_path, include_paths)
            return result
        finally:
            if cleanup:
                shutil.rmtree(temp_dir, ignore_errors=True)

    def run_netlist_string(
        self,
        netlist: str,
        include_paths: Optional[List[Path]] = None,
        cleanup: bool = True,
    ) -> SpiceResult:
        """
        Run simulation from a netlist string (no template substitution).

        Args:
            netlist: Complete SPICE netlist as string.
            include_paths: Additional include paths.
            cleanup: Whether to delete temp files after simulation.

        Returns:
            SpiceResult with measurements and status.
        """
        temp_dir = tempfile.mkdtemp(prefix="ngspice_")
        temp_path = Path(temp_dir) / "simulation.cir"

        try:
            temp_path.write_text(netlist)
            result = self.run_simulation(temp_path, include_paths)
            return result
        finally:
            if cleanup:
                shutil.rmtree(temp_dir, ignore_errors=True)

    def _parse_measurements(self, output: str) -> Dict[str, SpiceMeasurement]:
        """Parse .meas output from ngspice stdout."""
        measurements = {}

        for line in output.split("\n"):
            line = line.strip()
            if not line:
                continue

            # Try to match measurement line
            match = self._meas_pattern.match(line)
            if match:
                name = match.group(1).lower()
                value = float(match.group(2))
                targ = float(match.group(3)) if match.group(3) else None
                trig = float(match.group(4)) if match.group(4) else None

                # Infer unit from name
                unit = self._infer_unit(name, value)

                measurements[name] = SpiceMeasurement(
                    name=name,
                    value=value,
                    unit=unit,
                    targ=targ,
                    trig=trig,
                    raw_line=line,
                )

        return measurements

    def _parse_errors(self, output: str) -> List[str]:
        """Parse error messages from ngspice output."""
        errors = []
        for line in output.split("\n"):
            if self._error_pattern.search(line):
                errors.append(line.strip())
        return errors

    def _parse_warnings(self, output: str) -> List[str]:
        """Parse warning messages from ngspice output."""
        warnings = []
        for line in output.split("\n"):
            if self._warning_pattern.search(line) and not self._error_pattern.search(line):
                warnings.append(line.strip())
        return warnings

    def _infer_unit(self, name: str, value: float) -> str:
        """Infer unit from measurement name."""
        name_lower = name.lower()

        # Time measurements
        if any(x in name_lower for x in ["time", "trise", "tfall", "delay", "period"]):
            if abs(value) < 1e-9:
                return "ps"
            elif abs(value) < 1e-6:
                return "ns"
            elif abs(value) < 1e-3:
                return "us"
            else:
                return "s"

        # Voltage
        if any(x in name_lower for x in ["v_", "vce", "vgs", "vout", "vin", "voltage"]):
            return "V"

        # Current
        if any(x in name_lower for x in ["i_", "iout", "iin", "current"]):
            if abs(value) < 1e-3:
                return "mA"
            else:
                return "A"

        # Energy
        if any(x in name_lower for x in ["e_", "eoff", "eon", "energy"]):
            if abs(value) < 1e-6:
                return "uJ"
            elif abs(value) < 1e-3:
                return "mJ"
            else:
                return "J"

        # Power
        if any(x in name_lower for x in ["p_", "power", "pout", "pin"]):
            return "W"

        return ""


def estimate_loop_inductance(
    component_positions: Dict[str, Tuple[float, float]],
    loop_components: List[str],
    trace_height_mm: float = 0.035,  # 1oz copper
) -> float:
    """
    Estimate loop inductance from component positions.

    Uses simplified model: L ≈ μ₀ * Area / h
    where h is trace height (copper thickness).

    This is a rough estimate for validation purposes - actual
    inductance depends on trace geometry, ground plane distance, etc.

    Args:
        component_positions: Dict of component ref -> (x, y) position in mm.
        loop_components: List of component refs forming the loop, in order.
        trace_height_mm: Trace height (copper thickness) in mm.

    Returns:
        Estimated inductance in Henries.
    """
    if len(loop_components) < 3:
        return 0.0

    # Get positions for loop components
    positions = []
    for ref in loop_components:
        if ref in component_positions:
            positions.append(component_positions[ref])
        else:
            return 0.0  # Missing component

    # Calculate loop area using shoelace formula
    # Area = 0.5 * |sum(x_i * y_{i+1} - x_{i+1} * y_i)|
    n = len(positions)
    area = 0.0
    for i in range(n):
        x1, y1 = positions[i]
        x2, y2 = positions[(i + 1) % n]
        area += x1 * y2 - x2 * y1
    area = abs(area) / 2.0  # mm²

    # Convert to m²
    area_m2 = area * 1e-6

    # Inductance: L ≈ μ₀ * Area / h
    # μ₀ = 4π × 10⁻⁷ H/m
    mu_0 = 4 * 3.14159265359e-7
    h_m = trace_height_mm * 1e-3  # Convert to meters

    inductance_h = mu_0 * area_m2 / h_m

    return inductance_h


def create_validation_netlist(
    base_template: str,
    placement_params: Dict[str, str],
) -> str:
    """
    Create a validation netlist from template and placement parameters.

    Args:
        base_template: SPICE netlist template with {{PARAM}} placeholders.
        placement_params: Parameters derived from current placement.

    Returns:
        Complete netlist string ready for simulation.
    """
    netlist = base_template

    for name, value in placement_params.items():
        placeholder = "{{" + name + "}}"
        netlist = netlist.replace(placeholder, str(value))

    return netlist


@dataclass
class PlacementSpiceResult:
    """
    Result from placement-aware SPICE validation.

    Attributes:
        spice_result: Raw SpiceResult from ngspice.
        template_name: Name of the template used.
        threshold_results: Results from threshold checking.
        penalty: Computed penalty value for loss function.
        placement_params: Parameters derived from placement.
    """

    spice_result: SpiceResult
    template_name: str
    threshold_results: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    penalty: float = 0.0
    placement_params: Dict[str, str] = field(default_factory=dict)

    @property
    def passed(self) -> bool:
        """True if simulation succeeded and all thresholds pass."""
        if not self.spice_result.success:
            return False
        return all(r.get("passed", False) for r in self.threshold_results.values())

    def summary(self) -> str:
        """Get human-readable summary."""
        lines = [f"=== {self.template_name} Validation ==="]
        lines.append(f"Status: {'PASS' if self.passed else 'FAIL'}")
        lines.append(f"Penalty: {self.penalty:.4f}")

        if self.placement_params:
            lines.append("Placement parameters:")
            for name, value in self.placement_params.items():
                lines.append(f"  {name}: {value}")

        if self.threshold_results:
            lines.append("Threshold checks:")
            for name, result in self.threshold_results.items():
                status = "✓" if result.get("passed") else "✗"
                value = result.get("value")
                if value is not None:
                    lines.append(f"  {status} {name}: {value:.4e}")
                else:
                    lines.append(f"  {status} {name}: (missing)")

        return "\n".join(lines)


def run_gate_drive_simulation(
    validator: NgspiceValidator,
    component_positions: Dict[str, Tuple[float, float]],
    gate_loop_components: Optional[List[str]] = None,
    gate_resistance: float = 4.7,
    check_thresholds: bool = True,
) -> PlacementSpiceResult:
    """
    Run gate drive loop EMI validation simulation.

    This validates that gate drive switching is clean (low ringing/overshoot)
    based on the placement-derived loop inductance.

    Args:
        validator: NgspiceValidator instance.
        component_positions: Dict of component ref -> (x, y) position in mm.
        gate_loop_components: Components forming the gate loop, in order.
            Default: ["U_GD", "Q1", "R_GATE"] for typical half-bridge.
        gate_resistance: External gate resistance in ohms.
        check_thresholds: Whether to check against thresholds.

    Returns:
        PlacementSpiceResult with simulation results and threshold checks.
    """
    from temper_placer.validation.spice_templates import (
        load_template,
        check_thresholds as check_thresholds_fn,
        compute_spice_penalty,
    )

    if gate_loop_components is None:
        gate_loop_components = ["U_GD", "Q1", "R_GATE"]

    # Estimate loop inductance from placement
    loop_inductance = estimate_loop_inductance(
        component_positions,
        gate_loop_components,
    )

    # Use a reasonable minimum if positions don't give valid inductance
    if loop_inductance < 1e-12:
        loop_inductance = 50e-9  # 50nH default

    # Format parameters for template
    params = {
        "GATE_LOOP_INDUCTANCE": f"{loop_inductance:.2e}",
        "GATE_RESISTANCE": str(gate_resistance),
    }

    # Load and run template
    template = load_template("gate_drive")
    spice_result = validator.run_template(template, params)

    # Extract measurements and check thresholds
    threshold_results = {}
    penalty = 0.0

    if spice_result.success and check_thresholds:
        measurements = {name: meas.value for name, meas in spice_result.measurements.items()}
        threshold_results = check_thresholds_fn("gate_drive", measurements)
        penalty = compute_spice_penalty({"gate_drive": measurements})
    elif not spice_result.success:
        penalty = 50.0  # Heavy penalty for failed simulation

    return PlacementSpiceResult(
        spice_result=spice_result,
        template_name="gate_drive",
        threshold_results=threshold_results,
        penalty=penalty,
        placement_params=params,
    )


def run_bootstrap_simulation(
    validator: NgspiceValidator,
    component_positions: Dict[str, Tuple[float, float]],
    bootstrap_loop_components: Optional[List[str]] = None,
    bootstrap_capacitance: float = 1e-6,
    bootstrap_resistance: float = 0.5,
    check_thresholds: bool = True,
) -> PlacementSpiceResult:
    """
    Run bootstrap capacitor charging validation simulation.

    This verifies that the bootstrap capacitor charges to sufficient voltage
    (>12V for UCC21550) for high-side gate driver operation.

    Args:
        validator: NgspiceValidator instance.
        component_positions: Dict of component ref -> (x, y) position in mm.
        bootstrap_loop_components: Components forming the bootstrap loop, in order.
            Default: ["U_GD", "D_BOOT", "C_BOOT"] for typical bootstrap circuit.
        bootstrap_capacitance: Bootstrap capacitor value in Farads.
        bootstrap_resistance: Total loop ESR in ohms.
        check_thresholds: Whether to check against thresholds.

    Returns:
        PlacementSpiceResult with simulation results and threshold checks.
    """
    from temper_placer.validation.spice_templates import (
        load_template,
        check_thresholds as check_thresholds_fn,
        compute_spice_penalty,
    )

    if bootstrap_loop_components is None:
        bootstrap_loop_components = ["U_GD", "D_BOOT", "C_BOOT"]

    # Estimate loop inductance from placement
    loop_inductance = estimate_loop_inductance(
        component_positions,
        bootstrap_loop_components,
    )

    # Use a reasonable default if positions don't give valid inductance
    if loop_inductance < 1e-12:
        loop_inductance = 100e-9  # 100nH default

    # Format parameters for template
    params = {
        "BOOTSTRAP_LOOP_INDUCTANCE": f"{loop_inductance:.2e}",
        "BOOTSTRAP_CAPACITANCE": f"{bootstrap_capacitance:.2e}",
        "BOOTSTRAP_RESISTANCE": str(bootstrap_resistance),
    }

    # Load and run template
    template = load_template("bootstrap_charging")
    spice_result = validator.run_template(template, params)

    # Extract measurements and check thresholds
    threshold_results = {}
    penalty = 0.0

    if spice_result.success and check_thresholds:
        measurements = {name: meas.value for name, meas in spice_result.measurements.items()}
        threshold_results = check_thresholds_fn("bootstrap_charging", measurements)
        penalty = compute_spice_penalty({"bootstrap_charging": measurements})
    elif not spice_result.success:
        penalty = 50.0  # Heavy penalty for failed simulation

    return PlacementSpiceResult(
        spice_result=spice_result,
        template_name="bootstrap_charging",
        threshold_results=threshold_results,
        penalty=penalty,
        placement_params=params,
    )


def run_power_integrity_simulation(
    validator: NgspiceValidator,
    component_positions: Dict[str, Tuple[float, float]],
    dc_bus_components: Optional[List[str]] = None,
    decap_esr: float = 0.05,
    decap_value: float = 100e-6,
    check_thresholds: bool = True,
) -> PlacementSpiceResult:
    """
    Run DC bus power integrity validation simulation.

    This verifies that DC bus voltage remains stable (low ripple/droop)
    under switching load, based on placement-derived bus inductance.

    Args:
        validator: NgspiceValidator instance.
        component_positions: Dict of component ref -> (x, y) position in mm.
        dc_bus_components: Components forming the DC bus loop, in order.
            Default: ["C_DC", "Q1", "Q2"] for half-bridge.
        decap_esr: Decoupling capacitor ESR in ohms.
        decap_value: Decoupling capacitor value in Farads.
        check_thresholds: Whether to check against thresholds.

    Returns:
        PlacementSpiceResult with simulation results and threshold checks.
    """
    from temper_placer.validation.spice_templates import (
        load_template,
        check_thresholds as check_thresholds_fn,
        compute_spice_penalty,
    )

    if dc_bus_components is None:
        dc_bus_components = ["C_DC", "Q1", "Q2"]

    # Estimate loop inductance from placement
    loop_inductance = estimate_loop_inductance(
        component_positions,
        dc_bus_components,
    )

    # Use a reasonable default if positions don't give valid inductance
    if loop_inductance < 1e-12:
        loop_inductance = 200e-9  # 200nH default

    # Format parameters for template
    params = {
        "DC_BUS_INDUCTANCE": f"{loop_inductance:.2e}",
        "DECAP_ESR": str(decap_esr),
        "DECAP_VALUE": f"{decap_value:.2e}",
    }

    # Load and run template
    template = load_template("power_integrity")
    spice_result = validator.run_template(template, params)

    # Extract measurements and check thresholds
    threshold_results = {}
    penalty = 0.0

    if spice_result.success and check_thresholds:
        measurements = {name: meas.value for name, meas in spice_result.measurements.items()}
        threshold_results = check_thresholds_fn("power_integrity", measurements)
        penalty = compute_spice_penalty({"power_integrity": measurements})
    elif not spice_result.success:
        penalty = 50.0  # Heavy penalty for failed simulation

    return PlacementSpiceResult(
        spice_result=spice_result,
        template_name="power_integrity",
        threshold_results=threshold_results,
        penalty=penalty,
        placement_params=params,
    )


def run_all_placement_validations(
    validator: NgspiceValidator,
    component_positions: Dict[str, Tuple[float, float]],
    config: Optional[Dict[str, Any]] = None,
) -> Dict[str, PlacementSpiceResult]:
    """
    Run all placement-dependent SPICE validations.

    Args:
        validator: NgspiceValidator instance.
        component_positions: Dict of component ref -> (x, y) position in mm.
        config: Optional config dict with:
            - gate_loop_components: List of refs for gate loop
            - gate_resistance: External gate resistance (ohms)
            - bootstrap_loop_components: List of refs for bootstrap loop
            - bootstrap_capacitance: Bootstrap cap value (F)
            - bootstrap_resistance: Bootstrap loop ESR (ohms)
            - dc_bus_components: List of refs for DC bus loop
            - decap_esr: Decoupling cap ESR (ohms)
            - decap_value: Decoupling cap value (F)

    Returns:
        Dict of template_name -> PlacementSpiceResult.
    """
    if config is None:
        config = {}

    results = {}

    # Gate drive validation
    results["gate_drive"] = run_gate_drive_simulation(
        validator,
        component_positions,
        gate_loop_components=config.get("gate_loop_components"),
        gate_resistance=config.get("gate_resistance", 4.7),
    )

    # Bootstrap validation
    results["bootstrap_charging"] = run_bootstrap_simulation(
        validator,
        component_positions,
        bootstrap_loop_components=config.get("bootstrap_loop_components"),
        bootstrap_capacitance=config.get("bootstrap_capacitance", 1e-6),
        bootstrap_resistance=config.get("bootstrap_resistance", 0.5),
    )

    # Power integrity validation
    results["power_integrity"] = run_power_integrity_simulation(
        validator,
        component_positions,
        dc_bus_components=config.get("dc_bus_components"),
        decap_esr=config.get("decap_esr", 0.05),
        decap_value=config.get("decap_value", 100e-6),
    )

    return results


def compute_total_spice_penalty(
    results: Dict[str, PlacementSpiceResult],
    weights: Optional[Dict[str, float]] = None,
) -> float:
    """
    Compute total penalty from all SPICE validation results.

    Args:
        results: Dict of template_name -> PlacementSpiceResult.
        weights: Optional dict of template_name -> weight (default 1.0).

    Returns:
        Total weighted penalty suitable for loss function.
    """
    if weights is None:
        weights = {}

    total = 0.0
    for name, result in results.items():
        weight = weights.get(name, 1.0)
        total += result.penalty * weight

    return total
