"""SlotGenerationStage -- import-path shim for the collapsed adapter.

Shim-debt cleanup (2026-08-20): the ``SlotGenerationStage`` class (its
constructor state, its ``run`` and the ``_generate_slots_for_zone``
delegation helper) moved to ``stages/__init__.py`` as a
:class:`~stages.base.RustFunctionStage` parameterized adapter over
``temper_orchestration.run_slot_generation`` (Phase D batch D2 of the Rust
Orchestration Engine plan 2026-08-09-001).

This module survives ONLY because the pinned VERBATIM zone-aware oracle
(``tests/deterministic/_zone_aware_slot_generation_run_py_oracle.py``)
imports ``SlotGenerationStage`` from this module path and SUBCLASSES it --
the oracle bytes cannot be edited, so the path must keep resolving. It is
a one-line re-export of the adapter class; it carries no constructor state
and no ``run`` implementation of its own.
"""

from temper_placer.deterministic.stages import SlotGenerationStage

__all__ = ["SlotGenerationStage"]
