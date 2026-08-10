"""ConfigAttachStage — Attaches the parsed PlacementConstraints config to BoardState.

The stage's orchestration is implemented in Rust
(``temper-orchestration``'s ``ConfigAttachStage``, Phase D batch D1 of the
Rust Orchestration Engine plan 2026-08-09-001); this module keeps the
public API (the ``Stage`` subclass, its constructor and ``name``) and
delegates ``run`` across the FFI once per stage call. The differential
oracle for the pre-migration implementation is pinned VERBATIM in
``tests/deterministic/_config_attach_py_oracle.py``.
"""

from __future__ import annotations

import temper_orchestration as _to

from ..state import BoardState
from .base import Stage


class ConfigAttachStage(Stage):
    """Pipeline shim that copies the parsed `PlacementConstraints` config
    onto the `BoardState` so subsequent stages can read it as `state.config`.

    Without this stage, `state.config` is always None and the HvLvPartitionStage
    (and any other stage that reads `state.config`) cannot load its block from
    the YAML config.
    """

    def __init__(self, config) -> None:
        self._config = config

    @property
    def name(self) -> str:
        return "config_attach"

    def run(self, state: BoardState) -> BoardState:
        return _to.run_config_attach(state, self._config)
