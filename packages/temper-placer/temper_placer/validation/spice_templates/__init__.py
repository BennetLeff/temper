"""SPICE templates for placement-dependent electrical validation.

This module provides parameterized SPICE netlists that can be run with
placement-derived parameters (e.g., loop inductance from component positions).

Templates use {{PARAM}} syntax for parameter substitution.

Example usage:
    from temper_placer.validation.spice_templates import load_template, TEMPLATE_THRESHOLDS
    from temper_placer.validation.spice import NgspiceValidator

    template = load_template("gate_drive")
    validator = NgspiceValidator()
    result = validator.run_template(template, {
        "GATE_LOOP_INDUCTANCE": "50n",
        "GATE_RESISTANCE": "4.7",
    })

    # Check against thresholds
    thresholds = TEMPLATE_THRESHOLDS["gate_drive"]
    for meas_name, limits in thresholds.items():
        value = result.measurements.get(meas_name)
        if value and "max" in limits and value.value > limits["max"]:
            print(f"{meas_name} exceeds limit: {value.value} > {limits['max']}")
"""

from pathlib import Path
from typing import Any, Dict, List, Optional

TEMPLATE_DIR = Path(__file__).parent


def load_template(name: str) -> str:
    """Load a SPICE template by name.

    Args:
        name: Template name without .cir extension (e.g., "gate_drive")

    Returns:
        Template content as string with {{PARAM}} placeholders

    Raises:
        FileNotFoundError: If template doesn't exist
    """
    path = TEMPLATE_DIR / f"{name}.cir"
    if not path.exists():
        available = get_available_templates()
        raise FileNotFoundError(f"Template '{name}' not found. Available templates: {available}")
    return path.read_text()


def get_available_templates() -> list[str]:
    """List available template names.

    Returns:
        List of template names (without .cir extension)
    """
    return sorted(p.stem for p in TEMPLATE_DIR.glob("*.cir"))


def get_template_parameters(name: str) -> list[str]:
    """Extract parameter names from a template.

    Args:
        name: Template name

    Returns:
        List of parameter names (e.g., ["GATE_LOOP_INDUCTANCE", "GATE_RESISTANCE"])
    """
    import re

    template = load_template(name)
    # Find all {{PARAM}} patterns
    matches = re.findall(r"\{\{(\w+)\}\}", template)
    return sorted(set(matches))


# Template metadata: parameters and their descriptions
TEMPLATE_PARAMETERS: dict[str, dict[str, str]] = {
    "gate_drive": {
        "GATE_LOOP_INDUCTANCE": "Gate drive loop inductance in Henries (e.g., '50n' for 50nH)",
        "GATE_RESISTANCE": "External gate resistance in Ohms (e.g., '4.7')",
    },
    "bootstrap_charging": {
        "BOOTSTRAP_LOOP_INDUCTANCE": "Bootstrap charging loop inductance in Henries",
        "BOOTSTRAP_CAPACITANCE": "Bootstrap capacitor value in Farads (e.g., '1u')",
        "BOOTSTRAP_RESISTANCE": "Total bootstrap loop ESR in Ohms",
    },
    "power_integrity": {
        "DC_BUS_INDUCTANCE": "DC bus loop inductance in Henries",
        "DECAP_ESR": "Decoupling capacitor ESR in Ohms",
        "DECAP_VALUE": "Decoupling capacitor value in Farads (e.g., '100u')",
    },
}


# Validation thresholds for pass/fail determination
# Each measurement has optional min/max limits and unit for display
TEMPLATE_THRESHOLDS: dict[str, dict[str, dict[str, Any]]] = {
    "gate_drive": {
        # Overshoot should be <20% to avoid gate oxide stress
        "v_overshoot_pct": {"max": 20.0, "unit": "%", "description": "Gate voltage overshoot"},
        # Undershoot (negative) should be minimal
        "v_undershoot_pct": {"max": 5.0, "unit": "%", "description": "Gate voltage undershoot"},
        # Rise time affects EMI and switching losses
        "t_rise": {"max": 100e-9, "unit": "s", "description": "Gate voltage rise time"},
        # Fall time affects turn-off switching losses
        "t_fall": {"max": 100e-9, "unit": "s", "description": "Gate voltage fall time"},
        # Ringing should settle quickly
        "v_ring_pp": {
            "max": 3.0,
            "unit": "V",
            "description": "Post-switching ringing peak-to-peak",
        },
    },
    "bootstrap_charging": {
        # Bootstrap voltage must exceed UCC21550 UVLO with margin
        "v_margin": {"min": 1.0, "unit": "V", "description": "Margin above UVLO threshold"},
        # Should charge quickly during low-side ON time
        "t_charge_12v": {"max": 500e-6, "unit": "s", "description": "Time to reach 12V"},
        # Final voltage should be near supply - diode drop
        "v_boot_final": {"min": 13.0, "unit": "V", "description": "Final bootstrap voltage"},
        # Minimum voltage during operation
        "v_boot_min": {"min": 12.0, "unit": "V", "description": "Minimum bootstrap voltage"},
    },
    "power_integrity": {
        # DC bus ripple affects output quality
        "v_ripple": {"max": 20.0, "unit": "V", "description": "DC bus voltage ripple"},
        # Average voltage drop from nominal
        "v_drop": {"max": 30.0, "unit": "V", "description": "Average voltage drop from 400V"},
        # Minimum bus voltage (affects IGBT VCE margin)
        "v_dc_min": {"min": 350.0, "unit": "V", "description": "Minimum DC bus voltage"},
    },
}


# Default parameter values for testing (typical Temper design values)
DEFAULT_PARAMETERS: dict[str, dict[str, str]] = {
    "gate_drive": {
        "GATE_LOOP_INDUCTANCE": "50n",  # 50nH typical for good layout
        "GATE_RESISTANCE": "4.7",  # 4.7 ohm external gate resistor
    },
    "bootstrap_charging": {
        "BOOTSTRAP_LOOP_INDUCTANCE": "100n",  # 100nH typical
        "BOOTSTRAP_CAPACITANCE": "1u",  # 1µF bootstrap cap
        "BOOTSTRAP_RESISTANCE": "0.5",  # 0.5 ohm total ESR
    },
    "power_integrity": {
        "DC_BUS_INDUCTANCE": "200n",  # 200nH typical for bus bar
        "DECAP_ESR": "0.05",  # 50mΩ film cap ESR
        "DECAP_VALUE": "100u",  # 100µF decoupling
    },
}


def check_thresholds(
    template_name: str,
    measurements: dict[str, float],
) -> dict[str, dict[str, Any]]:
    """Check measurements against template thresholds.

    Args:
        template_name: Name of the template
        measurements: Dict of measurement name -> value

    Returns:
        Dict of measurement name -> {
            "value": measured value,
            "passed": bool,
            "limit": limit value that was violated (if any),
            "limit_type": "min" or "max",
            "description": human-readable description
        }
    """
    thresholds = TEMPLATE_THRESHOLDS.get(template_name, {})
    results = {}

    for meas_name, limits in thresholds.items():
        # Normalize measurement name (ngspice uses lowercase)
        meas_key = meas_name.lower()
        value = measurements.get(meas_key)

        if value is None:
            results[meas_name] = {
                "value": None,
                "passed": False,
                "error": "Measurement not found",
                "description": limits.get("description", ""),
            }
            continue

        passed = True
        violated_limit = None
        limit_type = None

        if "max" in limits and value > limits["max"]:
            passed = False
            violated_limit = limits["max"]
            limit_type = "max"
        elif "min" in limits and value < limits["min"]:
            passed = False
            violated_limit = limits["min"]
            limit_type = "min"

        results[meas_name] = {
            "value": value,
            "passed": passed,
            "unit": limits.get("unit", ""),
            "description": limits.get("description", ""),
        }

        if not passed:
            results[meas_name]["limit"] = violated_limit
            results[meas_name]["limit_type"] = limit_type

    return results


def compute_spice_penalty(
    results: dict[str, dict[str, float]],
    weights: dict[str, float] | None = None,
) -> float:
    """Compute aggregate penalty from SPICE simulation results.

    This function converts threshold violations into a scalar penalty
    suitable for use in the placement optimizer's loss function.

    Args:
        results: Dict of template_name -> {measurement_name: value}
        weights: Optional dict of template_name -> weight (default 1.0)

    Returns:
        Scalar penalty value (0 = all pass, >0 = violations)
    """
    if weights is None:
        weights = {}

    total_penalty = 0.0

    for template_name, measurements in results.items():
        thresholds = TEMPLATE_THRESHOLDS.get(template_name, {})
        weight = weights.get(template_name, 1.0)

        for meas_name, limits in thresholds.items():
            meas_key = meas_name.lower()
            value = measurements.get(meas_key)

            if value is None:
                # Missing measurement is a soft penalty
                total_penalty += 0.1 * weight
                continue

            # Calculate normalized violation
            if "max" in limits and value > limits["max"]:
                # Violation proportional to how much over the limit
                violation = (value - limits["max"]) / abs(limits["max"])
                total_penalty += violation * weight

            if "min" in limits and value < limits["min"]:
                # Violation proportional to how much under the limit
                violation = (limits["min"] - value) / abs(limits["min"])
                total_penalty += violation * weight

    return total_penalty


__all__ = [
    "load_template",
    "get_available_templates",
    "get_template_parameters",
    "TEMPLATE_PARAMETERS",
    "TEMPLATE_THRESHOLDS",
    "DEFAULT_PARAMETERS",
    "check_thresholds",
    "compute_spice_penalty",
]
