"""Regression and property tests for generated-netlist to KiCad safety parity."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest
from hypothesis import given
from hypothesis import strategies as st

from temper_placer.validation.real_board_inventory import (
    REQUIRED_SAFETY_COMPONENTS,
    REQUIRED_SAFETY_NETS,
    BoardParityError,
    validate_kicad_safety_parity,
)

ROOT = Path(__file__).resolve().parents[4]
NETLIST = ROOT / "elec/build/default.net"


def _board_text(*, nets: set[str], component_counts: dict[str, int]) -> str:
    lines = ["(kicad_pcb"]
    lines.extend(f'  (net {index + 1} "{name}")' for index, name in enumerate(sorted(nets)))
    index = 0
    for family, count in sorted(component_counts.items()):
        for _ in range(count):
            index += 1
            lines.extend(
                [
                    '  (footprint "Test:Part" (layer "F.Cu")',
                    f'    (property "Reference" "U{index}")',
                    f'    (property "Value" "{family}")',
                    f"    (at {index} 1)",
                    "  )",
                ]
            )
    lines.append(")")
    return "\n".join(lines)


def _valid_component_counts() -> dict[str, int]:
    return dict(REQUIRED_SAFETY_COMPONENTS)


def test_legacy_board_is_rejected_before_routing() -> None:
    with pytest.raises(BoardParityError, match="RTD_HW_FAULT"):
        validate_kicad_safety_parity(NETLIST, ROOT / "pcb/temper.kicad_pcb")


def test_complete_import_ready_board_is_accepted(tmp_path: Path) -> None:
    board = tmp_path / "temper.kicad_pcb"
    board.write_text(
        _board_text(nets=set(REQUIRED_SAFETY_NETS), component_counts=_valid_component_counts()),
        encoding="utf-8",
    )

    parity = validate_kicad_safety_parity(NETLIST, board)

    assert parity.generated_safety_nets == REQUIRED_SAFETY_NETS
    assert parity.board_safety_nets == REQUIRED_SAFETY_NETS
    assert parity.component_counts == _valid_component_counts()


@given(st.sampled_from(sorted(REQUIRED_SAFETY_NETS)))
def test_every_required_safety_net_is_mandatory(missing_net: str) -> None:
    with tempfile.TemporaryDirectory() as temporary_directory:
        board = Path(temporary_directory) / "temper.kicad_pcb"
        board.write_text(
            _board_text(
                nets=set(REQUIRED_SAFETY_NETS) - {missing_net},
                component_counts=_valid_component_counts(),
            ),
            encoding="utf-8",
        )
        with pytest.raises(BoardParityError, match=missing_net):
            validate_kicad_safety_parity(NETLIST, board)


@given(st.sampled_from(sorted(REQUIRED_SAFETY_COMPONENTS)))
def test_every_required_safety_component_count_is_mandatory(missing_family: str) -> None:
    with tempfile.TemporaryDirectory() as temporary_directory:
        board = Path(temporary_directory) / "temper.kicad_pcb"
        counts = _valid_component_counts()
        counts[missing_family] -= 1
        board.write_text(
            _board_text(nets=set(REQUIRED_SAFETY_NETS), component_counts=counts),
            encoding="utf-8",
        )
        with pytest.raises(BoardParityError, match=missing_family):
            validate_kicad_safety_parity(NETLIST, board)
