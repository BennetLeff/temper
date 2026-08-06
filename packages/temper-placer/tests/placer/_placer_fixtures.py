"""Shared mock board/netlist fixtures for the placer differential + PBT suites.

These mirror the mocks in ``tests/placer/test_deterministic_unit.py`` (the
pre-existing unit tests), which is exactly the duck-typed surface the
oracle consumes: ``board.zones[].name/.bounds``, ``board.width/height``,
``netlist.components[].ref/.fixed``, ``netlist.n_components``.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class MockZone:
    name: str
    bounds: tuple[float, float, float, float]


@dataclass
class MockBoard:
    zones: list[MockZone] = field(default_factory=list)
    width: float = 100.0
    height: float = 100.0


@dataclass
class MockComponent:
    ref: str
    fixed: bool = False


@dataclass
class MockNetlist:
    components: list[MockComponent] = field(default_factory=list)

    @property
    def n_components(self):
        return len(self.components)


def make_netlist(refs: list[str], fixed: set[str] | None = None) -> MockNetlist:
    fixed = fixed or set()
    return MockNetlist(components=[MockComponent(r, r in fixed) for r in refs])


def power_board() -> MockBoard:
    return MockBoard(
        zones=[MockZone("power_zone", (0, 0, 50, 50)), MockZone("logic_zone", (50, 50, 100, 100))]
    )


POWER_REFS = ["Q1", "Q2", "D1", "D2", "C1", "U1"]


def power_netlist() -> MockNetlist:
    return make_netlist(POWER_REFS)
