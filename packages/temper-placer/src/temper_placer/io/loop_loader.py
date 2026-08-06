"""
Loop definition loader for YAML-based loop templates.

This module provides functions to load loop definitions from YAML files,
supporting both individual loop templates and collections of loops.

Example usage:
    >>> from temper_placer.io.loop_loader import load_loop_template, load_loop_collection
    >>>
    >>> # Load a single loop template
    >>> loop = load_loop_template("configs/templates/loops/commutation.yaml")
    >>> print(loop.name, loop.priority)
    commutation LoopPriority.CRITICAL
    >>>
    >>> # Load all loops in a directory
    >>> collection = load_loop_collection("configs/templates/loops/")
    >>> print(len(collection))
    5

The loader is implemented in Rust as pyo3 functions in the
``temper-design-bundle`` crate (the ``temper_design_bundle_python``
extension, ``src/loaders.rs``) — the Wave 4 Phase 3 formats/IO migration,
candidate 2
(``docs/plans/2026-08-02-001-feat-wave4-phase3-formats-io-plan.md``, R5).
This module keeps the pre-migration public API unchanged and re-exports the
Rust symbols directly (the pure-delegation pattern established by
``core/priority.py`` / ``core/loop.py``). The private helpers
(``_parse_events``, ``_parse_pins``, ``_parse_loop_type``,
``_parse_priority``) moved into the crate with the rest of the load logic.

Two boundaries stay on the Python side of the pyo3 call, both deliberately
(see ``loaders.rs`` and ``packages/temper-design-bundle/VERIFICATION.md``):
``yaml.safe_load`` remains the tokenizer, because PyYAML implements YAML 1.1
and ``serde_yaml`` implements YAML 1.2 and the two genuinely disagree
(``net: on`` → ``True`` vs ``"on"``, ``1_000`` → ``1000`` vs a string); and
``pathlib.Path.glob`` remains the directory matcher. Everything else in the
load path — field mapping, defaults, ``str()``/``float()`` coercion,
case-insensitive enum resolution, every error string, README skipping, and
error wrapping with cause chaining — is Rust.

The save path — ``save_loop_to_yaml`` — stays **Python-side in this shim**,
per KTD7 of the first-pulls plan (U3): the loaders' migration scope is the
load path, and PyYAML's dumper formatting is not in the parity surface. The
function below is the pre-migration implementation operating on the Rust
``Loop`` pyclass surface; the differential pins a Rust-loaded loop re-saved
by this Python save path re-loading identically, and the emitter's output is
compared byte-for-byte against the pinned oracle.

Verification: bit-identical parity against the pinned pre-migration
implementation is asserted by ``tests/io/test_loaders_rust_differential.py``
(oracle: ``tests/io/_loop_loader_py_oracle.py``), including byte-for-byte
equality of every file the save path writes; the properties and metamorphic
relations live in ``tests/io/test_loaders_pbt.py`` and the structural proof
in ``packages/temper-design-bundle/VERIFICATION.md``.

API note (deliberate, documented deviation): ``LoopLoadError`` is now
defined in Rust. It still subclasses ``Exception`` and still reports
``__module__ == "temper_placer.io.loop_loader"``, so ``except
LoopLoadError``, ``pytest.raises`` and tracebacks read exactly as before —
but it is not the same class *object* the pre-migration module defined, so
pickling the class or comparing it by identity against a separately-imported
copy would observe the change. No consumer does (verified 2026-08-04).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import temper_design_bundle_python as _tdb
import yaml  # type: ignore[import-untyped]

from temper_placer.core.loop import Loop

LoopLoadError = _tdb.LoopLoadError
load_loop_from_dict = _tdb.load_loop_from_dict
load_loop_template = _tdb.load_loop_template
load_loop_collection = _tdb.load_loop_collection


def save_loop_to_yaml(loop: Loop, path: str | Path) -> None:
    """Save a Loop to a YAML file.

    Kept Python-side per KTD7 (the loaders' migration scope is the load
    path). Operates on the Rust ``Loop`` pyclass surface; PyYAML's
    ``yaml.dump`` remains the emitter because its byte output is the
    contract and its formatting is not reimplementable bit-exactly.

    Args:
        loop: Loop object to save.
        path: Output file path.

    Example:
        >>> save_loop_to_yaml(my_loop, "output/my_loop.yaml")
    """
    path = Path(path)

    # Build dictionary representation
    data: dict[str, Any] = {
        "name": loop.name,
        "loop_type": loop.loop_type.value,
        "description": loop.description,
    }

    # Components list
    if loop.components:
        data["components"] = loop.components

    # Pins (if defined)
    if loop.pins:
        data["pins"] = [
            {
                "component": pin.component_ref,
                "pin": pin.pin_name,
                **({"net": pin.net_name} if pin.net_name else {}),
            }
            for pin in loop.pins
        ]

    # Nets
    if loop.nets:
        data["nets"] = loop.nets

    # Constraints
    data["max_area_mm2"] = loop.max_area_mm2
    data["priority"] = loop.priority.value

    # Events (only include non-None values; 0.0 is falsy but NOT None and
    # must survive — this is the `is not None` guard, not truthiness)
    events = {}
    if loop.events.di_dt is not None:
        events["di_dt"] = loop.events.di_dt
    if loop.events.dv_dt is not None:
        events["dv_dt"] = loop.events.dv_dt
    if loop.events.frequency_hz is not None:
        events["frequency_hz"] = loop.events.frequency_hz
    if loop.events.peak_current_a is not None:
        events["peak_current_a"] = loop.events.peak_current_a
    if loop.events.rms_current_a is not None:
        events["rms_current_a"] = loop.events.rms_current_a
    if loop.events.ringing_freq_hz is not None:
        events["ringing_freq_hz"] = loop.events.ringing_freq_hz
    if events:
        data["events"] = events

    # Return path info
    if loop.return_layer:
        data["return_layer"] = loop.return_layer
    if loop.return_net:
        data["return_net"] = loop.return_net

    # Write to file
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        yaml.dump(data, f, default_flow_style=False, sort_keys=False, allow_unicode=True)

__all__ = [
    "LoopLoadError",
    "load_loop_collection",
    "load_loop_from_dict",
    "load_loop_template",
    "save_loop_to_yaml",
]
