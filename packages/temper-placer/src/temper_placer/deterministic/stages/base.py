"""Pipeline stage ABC -- RETIRED as the D7 stage base, kept as a minimal shim.

Rust Orchestration Engine plan (2026-08-09-001), Phase D batch D7: the Python
``Stage`` ABC is **retired as the base of the deterministic stages** -- the
migrated ``deterministic/stages/*`` run() orchestration is implemented by the
Rust ``temper_orchestration::Stage`` trait (``stage.rs``) and each Python
stage shim delegates ``run()`` across the FFI. The Python ``Stage`` class is
NOT deleted because consumers outside the migrated deterministic batch still
subclass it and rely on its exact ABC surface:

- the router_v6 stage classes (``router_v6/{result_aggregate_stage,net_prep_stage,
  layer_capacity,stage2_orchestrator,obstacle_map,route_stage,channel_skeleton,
  constraint_model,channel_widths,occupancy_grid,routing_demand,
  stage4_orchestrator,bottleneck_analysis,grid_prep_stage,routing_space}.py`` --
  15 modules subclass ``Stage``),
- ``adapters/deterministic_adapter.py`` (the ``_WrappedDeterministicStage``
  protocol-compat wrapper),
- the public re-export seams ``temper_placer.deterministic`` and
  ``temper_placer.deterministic.stages`` (``Stage`` in ``__all__``), and
- the D1-D7 Python stage shims, which keep ``class XStage(Stage)`` so
  ``isinstance(stage, Stage)`` and the ABC contract properties keep working
  for the ``DeterministicPipeline`` runner.

The class surface below is therefore unchanged from the pre-migration module
(the ABC + the four defaulted contract properties + ``run``); only this
header records the D7 retirement decision and its evidence.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

from ..state import BoardState

if TYPE_CHECKING:
    from temper_placer.pipeline.bottleneck_report import DeclaredArtifact
    from temper_placer.validation.drc_fence import InvariantSpec


class Stage(ABC):
    """Abstract base class for pipeline stages."""

    @property
    @abstractmethod
    def name(self) -> str:
        pass

    @property
    def invariants(self) -> tuple[InvariantSpec, ...]:
        return ()

    @property
    def last_modified_regions(self) -> list[tuple[float, float, float, float]] | None:
        return None

    @property
    def declared_writes(self) -> tuple[DeclaredArtifact, ...]:
        """Artifacts this stage promises to produce. Default empty."""
        return ()

    @property
    def declared_reads(self) -> tuple[DeclaredArtifact, ...]:
        """Artifacts this stage requires from prior stages. Default empty."""
        return ()

    @property
    def is_active(self) -> bool:
        """Whether this stage runs in the current pipeline configuration.
        When False, the runner skips the stage AND its contract obligations."""
        return True

    @abstractmethod
    def run(self, state: BoardState) -> BoardState:
        """Execute stage and return new state."""
        pass
