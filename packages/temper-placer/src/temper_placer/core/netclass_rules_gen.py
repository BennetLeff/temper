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

    # Via pad diameter in mm (for single vias). RAISED 0.6 -> 0.9 2026-08-16: 0.6/0.3 gave a 0.15mm annular ring, below the 0.254mm fab floor -- this is the loader fallback default for classes that omit via_diameter (docs/evidence/2026-08-16-hv-netclass-assignment-fix.md).
    via_diameter: float = 0.9

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

    # Legacy `_mm`-suffixed read aliases for the four scalar routing fields.
    # A large swath of pre-migration call sites (router_v6/_astar_search.py,
    # router_v6/escape_via_generator.py, router_v6/bundle_analyzer.py,
    # router_v6/constraint_model.py, router_v6/capacity_check.py,
    # deterministic/stages/setup.py, regression/drc_ratchet.py,
    # validation/drc_oracle.py) read `trace_width_mm` / `clearance_mm` /
    # `via_diameter_mm` / `via_drill_mm` off whatever object
    # ``DesignRules.get_rules_for_net()`` / ``net_classes`` holds. In
    # production that is this model; in router_v6 unit tests that construct
    # ``stage0_data.NetClassRules`` directly it is the legacy (already-`_mm`)
    # dataclass. The canonical field names are the non-`_mm` manifest names
    # (matching ``DesignRules`` pyclass constructor kwargs and
    # ``create_temper_design_rules()``); these aliases close the asymmetry on
    # the read side, mirroring the identical ``_mm`` getter aliases added to
    # the Rust ``DesignRules`` pyclass in
    # packages/temper-design-bundle/src/design_rules.rs (commit 28dc960de),
    # instead of renaming a dozen call sites (which would break the
    # stage0-constructed tests that pass the legacy dataclass into them).
    @property
    def trace_width_mm(self) -> float:
        return self.trace_width

    @property
    def clearance_mm(self) -> float:
        return self.clearance

    @property
    def via_diameter_mm(self) -> float:
        return self.via_diameter

    @property
    def via_drill_mm(self) -> float:
        return self.via_drill

    def __init__(self, name: str = "", **data: object) -> None:
        # Accept a positional name for ergonomics so callers can write
        # ``NetClassRules("HighVoltage", trace_width=0.5)`` instead of
        # ``NetClassRules(name="HighVoltage", trace_width=0.5)``.
        if name and "name" not in data:
            data["name"] = name
        super().__init__(**data)
