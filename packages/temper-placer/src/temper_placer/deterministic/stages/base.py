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
  protocol-compat wrapper), and
- the D1-D7 Python stage shims, which keep ``class XStage(Stage)`` so
  ``isinstance(stage, Stage)`` and the ABC contract properties keep working
  for the ``DeterministicPipeline`` runner.

Shim-debt cleanup 2026-08-19 (Phase 1.4): the ``Stage`` re-export seams on
``temper_placer.deterministic`` and ``temper_placer.deterministic.stages``
were removed -- an AST-verified zero importer count on both (nobody imports
``Stage`` from either package seam; consumers use ``.stages.base`` or the
``stages`` module directly). ``Stage`` itself stays (the router_v6 stage
classes and the remaining shims above subclass it).

The class surface below is therefore unchanged from the pre-migration module
(the ABC + the four defaulted contract properties + ``run``); only this
header records the D7 retirement decision and its evidence.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable
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


class RustFunctionStage(Stage):
    """Generic pipeline stage whose ``run`` forwards to a Rust pyfunction.

    Shim-debt cleanup (2026-08-19): the per-stage one-line shim modules
    (``deterministic/stages/zone_assignment.py`` and
    ``deterministic/stages/apply_placements.py``) were deleted. The stage
    class names that survive in ``stages/__init__.py`` (the pinned U-E
    pipeline oracle and the ``temper-orchestration`` stage factory construct
    them by name) are now this adapter parameterized with the
    ``temper-orchestration`` pyfunction -- one generic adapter instead of
    one shim class per stage. The Rust pyfunction is the single source of
    truth; the adapter only preserves the ``Stage`` ABC surface (``name``,
    ``invariants``, ``last_modified_regions``) the pipeline runner relies on.

    Shim-debt cleanup (2026-08-20): the adapter was extended with
    ``*fn_args`` / ``**fn_kwargs`` so stages whose shims threaded constructor
    state into ``run`` (``config_attach``, ``net_ordering``, ``setup``,
    ``zone_geometry``, ``slot_generation``, ``drc_sweep``,
    ``via_validation``) can collapse onto it too: the per-class
    ``__init__`` stores the constructor state exactly as the old shim did
    and forwards it as the pyfunction's extra positional/keyword arguments.
    ``run`` remains a single shared implementation -- the constructor state
    never appears in stage-run bytecode.
    """

    def __init__(
        self,
        name: str,
        fn: Callable[..., BoardState],
        *fn_args: object,
        **fn_kwargs: object,
    ) -> None:
        self._name = name
        self._fn = fn
        self._fn_args = fn_args
        self._fn_kwargs = fn_kwargs

    @property
    def name(self) -> str:
        return self._name

    def run(self, state: BoardState) -> BoardState:
        """Forward ``run`` straight to the Rust pyfunction (FFI).

        The pyfunction's extra constructor-state arguments (positional
        ``*fn_args`` and keyword ``**fn_kwargs``) follow the ``state`` the
        pipeline runner passes in.
        """
        return self._fn(state, *self._fn_args, **self._fn_kwargs)
