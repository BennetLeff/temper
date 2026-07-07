"""Load netclass_rules.yaml into a DesignRules instance."""

from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path
import logging
import yaml

from temper_placer.core.design_rules import DesignRules, NetClassRules, TEMPER_NET_ASSIGNMENTS
from temper_placer.core.net_classification import classify_net_type

logger = logging.getLogger(__name__)

# Map classify_net_type() return values to DesignRules net class names
_NET_TYPE_TO_CLASS = {
    "ground": "GND",
    "power": "Power",
    "hv": "HighVoltage",
    "signal": "Signal",
}

@dataclass
class NetClassRulesDict:
    """Convenience wrapper returned by load_netclass_rules()."""
    design_rules: DesignRules
    class_pairs: dict[tuple[str, str], dict] = field(default_factory=dict)  # (A,B) sorted -> {clearance, because}


def load_netclass_rules(path: Path) -> NetClassRulesDict:
    """Load netclass_rules.yaml and populate a DesignRules instance.
    
    Returns NetClassRulesDict with:
    - design_rules: DesignRules with net_classes populated from YAML classes
    - class_pairs: dict of (class_a, class_b) sorted -> {clearance, because}
    """
    with open(path) as f:
        data = yaml.safe_load(f)
    
    dr = DesignRules()
    dr.default_clearance = data["default_clearance_mm"]
    
    # Populate net_classes
    for class_name, class_data in data.get("classes", {}).items():
        # Map YAML field names to NetClassRules constructor args
        nc = NetClassRules(
            name=class_name,
            trace_width=class_data.get("trace_width", dr.default_trace_width),
            clearance=class_data.get("clearance", dr.default_clearance),
            via_diameter=class_data.get("via_diameter", dr.default_via_diameter),
            via_drill=class_data.get("via_drill", dr.default_via_drill),
            creepage_mm=class_data.get("creepage_mm", 0.0),
            voltage_v=class_data.get("voltage_v", 0.0),
            safety_category=class_data.get("safety_category"),
            dru_priority=class_data.get("dru_priority", 0),
            required_layer=class_data.get("required_layer"),
        )
        dr.net_classes[class_name] = nc
    
    # Populate net_class_assignments from TEMPER_NET_ASSIGNMENTS
    dr.net_class_assignments.update(TEMPER_NET_ASSIGNMENTS)
    
    # Parse class_pairs
    class_pairs: dict[tuple[str, str], dict] = {}
    for pair_key, pair_data in data.get("class_pairs", {}).items():
        parts = pair_key.split("-")
        if len(parts) != 2:
            logger.warning("Invalid class_pairs key '%s' — skipping", pair_key)
            continue
        a, b = parts[0], parts[1]
        key = tuple(sorted([a, b]))
        class_pairs[key] = {
            "clearance": pair_data.get("clearance", 0.0),
            "because": pair_data.get("because"),
        }
    dr.class_pairs = class_pairs
    
    return NetClassRulesDict(design_rules=dr, class_pairs=class_pairs)
