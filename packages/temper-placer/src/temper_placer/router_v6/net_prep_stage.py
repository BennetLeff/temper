"""
NetPrepStage: Extract pad centers, THT locations, compute routing order.
Stage 4.1 of the Router V6 pipeline.
Part of feat/stage4-astar-strangler.
"""

from __future__ import annotations

from dataclasses import replace

from temper_placer.deterministic.state import BoardState
from temper_placer.deterministic.stages.base import Stage
from temper_placer.router_v6.stage_validators import (
    StageDRCFailure,
    register_validator,
)


class NetPrepStage(Stage):
    """Stage 4.1: Extract pad centers, THT locations, compute net ordering."""

    @property
    def name(self) -> str:
        return "NetPrep"

    def run(self, state: BoardState) -> BoardState:
        from temper_placer.router_v6.astar_grid import (
            _build_tht_pad_locations,
            _extract_pad_centers_per_net,
        )

        pcb = state._parsed_pcb
        if pcb is None:
            return state

        tht_locations = _build_tht_pad_locations(pcb)
        pad_centers_per_net = _extract_pad_centers_per_net(pcb)

        return replace(
            state,
            tht_locations=frozenset(tht_locations),
            pad_centers_per_net=pad_centers_per_net,
        )


@register_validator("NetPrep")
def validate_net_prep(state: BoardState) -> list[StageDRCFailure]:
    """Validate net prep invariants."""
    failures: list[StageDRCFailure] = []
    tht = getattr(state, "tht_locations", None)
    if tht is None or (hasattr(tht, "__len__") and len(tht) == 0):
        # Treat None AND empty container as "no THT pads computed" so
        # a freshly-constructed BoardState triggers the validator.
        failures.append(StageDRCFailure(
            field="tht_locations",
            value=tht,
            reason="THT pad locations not computed",
            stage="NetPrep",
        ))
    return failures
