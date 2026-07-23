from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class NoiseIsolationRule(BaseModel):
    """Rule for physical isolation between sensitive components and noise sources."""

    model_config = ConfigDict(frozen=True)

    name: str = Field(description="Unique name for the isolation rule")
    sensitive_components: list[str] = Field(description="List of sensitive component references")
    noise_sources: list[str] = Field(description="List of noise source component references")
    min_distance_mm: float = Field(
        default=10.0, ge=0, description="Minimum required separation in mm"
    )
    weight: float = Field(default=1.0, ge=0, description="Importance weight")


class NoiseDomain(BaseModel):
    """Noise coupling domain: emitters and victims that must not run parallel."""

    model_config = ConfigDict(frozen=True)

    emitters: list[str] = Field(description="List of emitter net names")
    victims: list[str] = Field(description="List of victim net names")
    max_parallel_run_mm: float = Field(
        default=5.0, ge=0, description="Maximum allowed parallel run length in mm"
    )
