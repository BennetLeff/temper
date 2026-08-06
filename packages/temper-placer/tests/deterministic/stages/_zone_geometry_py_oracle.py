"""VERBATIM pre-migration oracle for ``deterministic/stages/zone_geometry.py``.

Wave 4, Phase 5, first slice (deterministic leaf stages). Pinned from
``packages/temper-placer/src/temper_placer/deterministic/stages/zone_geometry.py``
at the dispatch base (origin/main 6290942be). Do NOT edit: this file is the
Python arm of the differential. If it drifts, the differential proves nothing.

``Zone`` is the local frozen dataclass (name + nested bounds tuple); the
``ZoneGeometryStage`` method bodies are pinned as module-level functions.
The ``run`` orchestration (``state.board`` guard, the config-vs-default
dispatch, building the ``frozenset``) stays Python in the shim.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Zone:
    """Represents a placement zone on the board."""

    name: str
    bounds: tuple[tuple[float, float], tuple[float, float]]  # ((x_min, y_min), (x_max, y_max))


def define_zone_layout(board_width: float, board_height: float) -> list[Zone]:
    """
    Define 4-zone layout for MVP-3.

    Zones (left to right):
    - HV: 30% (high-voltage: AC input, IGBTs, gate drivers)
    - Power: 30% (power conversion: DC-DC, bulk caps)
    - Signal: 30% (control: sensing, temperature)
    - MCU: 10% (ESP32-S3 and peripherals)
    """
    zones = []

    # HV Zone: 0 to 30%
    hv_x_max = board_width * 0.3
    zones.append(Zone(name="HV", bounds=((0, 0), (hv_x_max, board_height))))

    # Power Zone: 30% to 60%
    power_x_min = hv_x_max
    power_x_max = board_width * 0.6
    zones.append(Zone(name="Power", bounds=((power_x_min, 0), (power_x_max, board_height))))

    # Signal Zone: 60% to 90%
    signal_x_min = power_x_max
    signal_x_max = board_width * 0.9
    zones.append(Zone(name="Signal", bounds=((signal_x_min, 0), (signal_x_max, board_height))))

    # MCU Zone: 90% to 100%
    mcu_x_min = signal_x_max
    zones.append(Zone(name="MCU", bounds=((mcu_x_min, 0), (board_width, board_height))))

    return zones


def scale_zone_bounds_ratio(
    name: str, ratio, board_width: float, board_height: float
) -> Zone:
    """The dict-format zone construction (verbatim body of the
    ``_define_zones_from_config`` dict branch): ``bounds_ratio`` scaled by
    the board dimensions."""
    zones = []
    r0, r1, r2, r3 = ratio[0], ratio[1], ratio[2], ratio[3]
    zones.append(
        Zone(
            name=name,
            bounds=(
                (r0 * board_width, r1 * board_height),
                (r2 * board_width, r3 * board_height),
            ),
        )
    )
    return zones[0]
