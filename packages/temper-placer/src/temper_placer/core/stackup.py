"""
Deterministic JLCPCB JLC04161H-7628 4-layer stackup definition.

Delegates to the Rust temper-design-bundle implementation.
"""

from temper_design_bundle_python import (  # noqa: F401 — re-export
    LayerConfig,
    Stackup,
    characteristic_impedance_microstrip,
    jlc04161h_7628,
)
