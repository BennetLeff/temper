"""
Footprint library for PCB component bounds and properties.

Delegation shim — the implementation migrated to Rust (``temper_io_types``,
``footprint_library.rs``) under Wave 4 Phase 3, candidate 5. PyYAML
(``yaml.safe_load``) is called back across the boundary; bounds validation,
coercion order and error strings are Rust. The public surface is unchanged.

Implements temper-1my.1.2: Footprint Library for Temper Components
"""

from __future__ import annotations

from temper_io_types import (
    FootprintLibrary,
    FootprintSpec,
    load_footprint_library,
)

__all__ = ["FootprintLibrary", "FootprintSpec", "load_footprint_library"]
