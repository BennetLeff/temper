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
``_parse_priority``) moved into the crate with the rest of the logic.

Three boundaries stay on the Python side of the pyo3 call, all deliberately
(see ``loaders.rs`` and ``packages/temper-design-bundle/VERIFICATION.md``):
``yaml.safe_load`` remains the tokenizer, because PyYAML implements YAML 1.1
and ``serde_yaml`` implements YAML 1.2 and the two genuinely disagree
(``net: on`` → ``True`` vs ``"on"``, ``1_000`` → ``1000`` vs a string);
``pathlib.Path.glob`` remains the directory matcher; and ``yaml.dump``
remains the emitter, since its byte output is the contract. Everything else
— field mapping, defaults, ``str()``/``float()`` coercion, case-insensitive
enum resolution, every error string, README skipping, error wrapping with
cause chaining, and the save-dict field selection — is Rust.

Verification: bit-identical parity against the pinned pre-migration
implementation is asserted by ``tests/io/test_loaders_rust_differential.py``
(oracle: ``tests/io/_loop_loader_py_oracle.py``), including byte-for-byte
equality of every file ``save_loop_to_yaml`` writes; the properties and
metamorphic relations live in ``tests/io/test_loaders_pbt.py`` and the
structural proof in ``packages/temper-design-bundle/VERIFICATION.md``.

API note (deliberate, documented deviation): ``LoopLoadError`` is now
defined in Rust. It still subclasses ``Exception`` and still reports
``__module__ == "temper_placer.io.loop_loader"``, so ``except
LoopLoadError``, ``pytest.raises`` and tracebacks read exactly as before —
but it is not the same class *object* the pre-migration module defined, so
pickling the class or comparing it by identity against a separately-imported
copy would observe the change. No consumer does (verified 2026-08-04).
"""

from __future__ import annotations

import temper_design_bundle_python as _tdb

LoopLoadError = _tdb.LoopLoadError
load_loop_from_dict = _tdb.load_loop_from_dict
load_loop_template = _tdb.load_loop_template
load_loop_collection = _tdb.load_loop_collection
save_loop_to_yaml = _tdb.save_loop_to_yaml

__all__ = [
    "LoopLoadError",
    "load_loop_collection",
    "load_loop_from_dict",
    "load_loop_template",
    "save_loop_to_yaml",
]
