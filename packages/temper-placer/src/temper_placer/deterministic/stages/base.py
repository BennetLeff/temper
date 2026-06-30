from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

from ..state import BoardState

if TYPE_CHECKING:
    from temper_placer.validation.drc_fence import InvariantSpec

    from temper_placer.pipeline.bottleneck_report import DeclaredArtifact

class Stage(ABC):
    '''Abstract base class for pipeline stages.'''

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
        '''Execute stage and return new state.'''
        pass
