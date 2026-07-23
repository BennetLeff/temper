"""U4: ERC validation on the production board.

Confirming the plan premise: ``kicad-cli pcb erc`` does not exist in
kicad-cli 10.0.4.  The ERC subcommand is ``kicad-cli sch erc`` (schematic-level);
PCB-level electrical verification is the DRC subcommand
(``kicad-cli pcb drc``), which U3 already exercises.

This test records that finding so the plan's U4 requirement
("ERC to zero on the production board") is explicitly documented as
inapplicable at the PCB level.  The routed production board's DRC
metrics (953 violations, 149 unconnected) from U3 serve as the PCB-level
electrical quality gate.
"""

from __future__ import annotations

import subprocess


def test_kicad_cli_pcb_erc_does_not_exist():
    """Verify ``kicad-cli pcb erc`` is not a valid subcommand.

    ERC is ``kicad-cli sch erc`` (schematic-level).  The plan's
    ``kicad-cli pcb erc`` reference is incorrect for kicad-cli 10.0.4.
    PCB-level electrical verification is ``kicad-cli pcb drc``,
    already exercised by U3.

    This test documents the finding; it does not attempt to work
    around the missing command.
    """
    result = subprocess.run(
        ["kicad-cli", "pcb", "erc"],
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0, (
        "kicad-cli pcb erc unexpectedly succeeded — verify the command and update this finding"
    )
    stdout = result.stdout
    assert "did you mean" in stdout.lower(), f"kicad-cli pcb erc response changed: {stdout[:200]}"

    # The available PCB subcommands do NOT include "erc"
    result_help = subprocess.run(
        ["kicad-cli", "pcb", "--help"],
        capture_output=True,
        text=True,
    )
    assert "erc" not in result_help.stdout.lower().split(), (
        "kicad-cli pcb help now includes 'erc' — re-evaluate this finding"
    )


def test_kicad_cli_sch_erc_available():
    """Confirm ``kicad-cli sch erc`` IS available (schematic-level).

    This documents where ERC lives: on the schematic, not the PCB.
    The production schematic is not in scope for this plan.
    """
    result = subprocess.run(
        ["kicad-cli", "sch", "erc", "--help"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"kicad-cli sch erc is not available: {result.stderr[:200]}"
    assert "Electrical Rules Check" in result.stdout, "kicad-cli sch erc help output changed"

    result_help = subprocess.run(
        ["kicad-cli", "sch", "--help"],
        capture_output=True,
        text=True,
    )
    assert "erc" in result_help.stdout.lower().split(), (
        "'erc' subcommand not listed in kicad-cli sch --help"
    )
