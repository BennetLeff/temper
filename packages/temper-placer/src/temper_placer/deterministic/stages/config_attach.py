"""ConfigAttachStage -- import-path shim for the collapsed adapter.

Shim-debt cleanup (2026-08-20): the ``ConfigAttachStage`` class (its
constructor state and its ``run``) moved to ``stages/__init__.py`` as a
:class:`~stages.base.RustFunctionStage` parameterized adapter over
``temper_orchestration.run_config_attach`` (Phase D batch D1 of the Rust
Orchestration Engine plan 2026-08-09-001).

This module survives ONLY because the pinned VERBATIM pipeline oracle
(``tests/deterministic/_deterministic_pipeline_py_oracle.py``) imports
``ConfigAttachStage`` from this module path inside its pinned body -- the
oracle bytes cannot be edited, so the path must keep resolving. It is a
one-line re-export of the adapter class; it carries no constructor state
and no ``run`` implementation of its own.
"""

from temper_placer.deterministic.stages import ConfigAttachStage

__all__ = ["ConfigAttachStage"]
