# ORACLE COPY -- DO NOT EDIT, DO NOT "FIX".
#
# Verbatim copy of the pre-migration source of
#   packages/temper-placer/src/temper_placer/deterministic/stages/config_attach.py
# at the D1 dispatch base (origin/main, 58af20b9). Relative imports are
# adapted to absolute paths so the oracle imports from the test tree; every
# other line is the verbatim pre-migration source.
#
# This is the R1a behavioural oracle for the D1 Rust Stage-engine port in
# packages/temper-orchestration (plan 2026-08-09-001, Phase D batch D1). It
# must keep the ORIGINAL pure-Python semantics forever, including any warts.
# If a differential test fails, the Rust side is wrong until proven
# otherwise -- never edit this file to make a test pass.
#
# test_deterministic_d1_rust_differential.py recomputes the sha256 of
# everything below the marker and fails if this file drifts.
# --- BEGIN PINNED BODY ---
"""ConfigAttachStage — Attaches the parsed PlacementConstraints config to BoardState.

Some downstream stages (HvLvPartitionStage in particular) read their own
configuration block from `state.config`. The orchestrator keeps the raw config
on the pipeline; this stage is a thin pass-through that copies it onto the
state so the rest of the pipeline can read it as if it were always there.
"""

from __future__ import annotations

from temper_placer.deterministic.state import BoardState
from temper_placer.deterministic.stages.base import Stage


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
