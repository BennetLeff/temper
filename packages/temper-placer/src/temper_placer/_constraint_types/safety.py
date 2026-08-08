from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class IsolationBarrier(BaseModel):
    """An isolation barrier across the board: a straight line (x_mm/y_span,
    the original representation) or a piecewise-linear polyline (points).

    Polyline support exists because a straight line cannot express every
    board's real barrier: the unmerged ``MAINS_SELV_ISOLATION_BARRIER``
    keepout on ``origin/safety/mains-selv-isolation-barrier`` (commit
    ``645154b7``) proved by exhaustive search that no single straight line
    separates this board's HV and SELV pads (the best candidate still
    misclassifies 28-32% of pads). ``points``, when it has >= 2 vertices,
    replaces the straight ``x_mm``/``y_span`` line with the polyline
    through those vertices, in order.

    Mirrors ``temper_drc_rs::constraints::IsolationBarrier`` in
    ``packages/temper-drc-rs/src/constraints.rs`` -- keep both in sync.
    """

    model_config = ConfigDict(frozen=True)

    name: str = Field(description="Barrier name")
    x_mm: float = Field(description="X-position of the straight-line barrier, in mm")
    y_span: tuple[float, float] = Field(
        description="(y_start, y_end) span of the straight-line barrier, in mm"
    )
    points: tuple[tuple[float, float], ...] = Field(
        default_factory=tuple,
        description=(
            "Optional polyline vertices (mm), >= 2 to take effect. When "
            "present, replaces the x_mm/y_span straight-line barrier with "
            "the exact piecewise-linear polyline through these vertices."
        ),
    )
    layers: str | list[str] = Field(default="all", description="Layer name(s) for the barrier")
    clearance_mm: float = Field(
        default=0.0,
        ge=0,
        description=(
            "Minimum required clearance (mm) from copper to the barrier "
            "geometry, beyond which no violation is raised. 0.0 (default) "
            "preserves pure crossing-only semantics. A real barrier should "
            "set this to the applicable IEC 60335-1 creepage figure (e.g. "
            "8.0mm REINFORCED)."
        ),
    )


class SnubberRequirement(BaseModel):
    """Snubber circuit requirement near an IGBT pair."""

    model_config = ConfigDict(frozen=True)

    igbt_pair: tuple[str, str] = Field(description="IGBT component reference pair")
    type: str = Field(default="RC", description="Snubber type: RC, RCD, etc.")
    across: str = Field(
        default="collector_emitter", description="Across which terminals: collector_emitter"
    )


class BleedResistor(BaseModel):
    """Bleed resistor specification for bus discharge."""

    model_config = ConfigDict(frozen=True)

    bus_voltage_v: float = Field(gt=0, description="Bus voltage in Volts")
    target_voltage_v: float = Field(ge=0, description="Target voltage after discharge in Volts")
    timeout_s: float = Field(default=5.0, gt=0, description="Discharge timeout in seconds")


class SkinEffectDerating(BaseModel):
    """Skin-effect derating for high-frequency traces."""

    model_config = ConfigDict(frozen=True)

    frequency_hz: float = Field(gt=0, description="Operating frequency in Hz")
    derating_factor: float = Field(default=3.0, gt=0, description="Derating factor multiplier")
