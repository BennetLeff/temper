# netclass_rules.py.j2 — Jinja2 template for Pydantic NetClassRules model

"""Generated NetClassRules Pydantic model.

DO NOT EDIT MANUALLY — edit the manifest at
packages/temper-placer/configs/netclass_rules_manifest.yaml and run:

    python3 scripts/gen_domain_models.py

Documentation fields (YAML-only, not stored in the model):
    because: Rationale for the chosen parameters (documentation only)
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict


class NetClassRules(BaseModel):
    """Routing rules for a net class.

    Defines the physical parameters for traces in a given net class,
    including width, clearance, and via specifications.
    """

    model_config = ConfigDict(frozen=True)

    # Net class name (e.g., 'Power', 'Signal', 'HighSpeed')
    name: str

    # Trace width in mm
    trace_width: float

    # Minimum clearance to other traces in mm
    clearance: float

    # Lower value emits earlier in DRU trace-width section
    dru_priority: int = 0

    # Via pad diameter in mm (for single vias)
    via_diameter: float = 0.6

    # Via drill diameter in mm (for single vias)
    via_drill: float = 0.3

    # Via array template name (e.g., 'Via2x2' for high-current)
    via_template: str | None = None

    # Creepage distance for high-voltage nets
    creepage_mm: float = 0.0

    # Voltage rating for safety distance calculation
    voltage_v: float = 0.0

    # Target impedance in ohms (for controlled impedance)
    target_impedance: float | None = None

    # Maximum current rating in amperes for thermal/trace-width calculations
    max_current_rating: float | None = None

    # KiCad layer name constraint or None for no constraint
    required_layer: str | None = None

    # KiCad layer name for this net class
    layer: str | None = None

    # Safety classification: HV, LV, AC, iso, or null
    safety_category: Literal["HV", "LV", "AC", "iso"] | None = None

    # Routing strategy: plane_required, plane_preferred, wide_trace, or standard
    routing_strategy: str | None = None

    # Multiplier for via cost (higher = fewer vias)
    via_cost_multiplier: float = 1.0

    # Layer-specific cost multipliers e.g. {'F.Cu': 10.0, 'In1.Cu': 0.1}
    layer_costs: dict[str, float] | None = None

    def __init__(self, name: str = "", **data: object) -> None:
        # Accept a positional name for ergonomics so callers can write
        # ``NetClassRules("HighVoltage", trace_width=0.5)`` instead of
        # ``NetClassRules(name="HighVoltage", trace_width=0.5)``.
        if name and "name" not in data:
            data["name"] = name
        super().__init__(**data)
