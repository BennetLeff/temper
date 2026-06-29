"""ConfigAttachStage — Attaches the parsed PlacementConstraints config to BoardState.

Some downstream stages (HvLvPartitionStage in particular) read their own
configuration block from `state.config`. The orchestrator keeps the raw config
on the pipeline; this stage is a thin pass-through that copies it onto the
state so the rest of the pipeline can read it as if it were always there.
"""
from __future__ import annotations

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
        if self._config is not None and not hasattr(state, "with_config"):
            return state
        if self._config is not None and getattr(state, "config", None) is None:
            return state.with_config(self._config)
        return state
