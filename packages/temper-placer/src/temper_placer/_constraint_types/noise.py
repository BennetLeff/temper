from __future__ import annotations

from dataclasses import dataclass


@dataclass
class NoiseIsolationRule:
    """
    Rule for physical isolation between sensitive components and noise sources.

    Attributes:
        name: Unique name for the rule.
        sensitive_components: List of component refs (supports globs).
        noise_sources: List of component refs (supports globs).
        min_distance_mm: Minimum required separation.
        weight: Importance of this rule.
    """

    name: str
    sensitive_components: list[str]
    noise_sources: list[str]
    min_distance_mm: float = 10.0
    weight: float = 1.0


@dataclass
class NoiseDomain:
    """Noise coupling domain: emitters and victims that must not run parallel."""

    emitters: list[str]
    victims: list[str]
    max_parallel_run_mm: float = 5.0
