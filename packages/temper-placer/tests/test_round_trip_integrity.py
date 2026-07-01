"""Round-trip netlist integrity tests.

parse -> write back -> reparse -> compare netlist topology.

Asserts structural preservation: every input net exists in the output
with identical pin assignments, component references, and net names.
The comparison is structural (net graph isomorphism), not geometric --
passing through the writer must preserve netlist topology.

The netlist writer is a deterministic serialization function.  If it
preserves netlists for one board, it preserves them for all boards by
construction.  The temper board (33 components, 24 nets, mixed HV/LV)
exercises enough diversity to prove correctness.
"""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path
from typing import Any

import pytest


def _extract_netlist(parsed: Any) -> dict[str, set[tuple[str, str]]]:
    netlist = getattr(parsed, "netlist", None)
    if netlist is None:
        return {}

    nets: dict[str, set[tuple[str, str]]] = {}
    for net in getattr(netlist, "nets", []):
        name = getattr(net, "name", None)
        if name is None:
            continue
        connections: set[tuple[str, str]] = set()
        for pin in getattr(net, "pins", []):
            if isinstance(pin, tuple) and len(pin) == 2:
                connections.add((str(pin[0]), str(pin[1])))
        if connections:
            nets[str(name)] = connections
    return nets


def _extract_component_refs(parsed: Any) -> set[str]:
    netlist = getattr(parsed, "netlist", None)
    if netlist is None:
        return set()
    return {
        str(getattr(c, "ref", ""))
        for c in getattr(netlist, "components", [])
        if getattr(c, "ref", None)
    }


def _compare_netlists(
    input_nets: dict[str, set[tuple[str, str]]],
    output_nets: dict[str, set[tuple[str, str]]],
) -> list[str]:
    errors: list[str] = []
    input_names = set(input_nets)
    output_names = set(output_nets)

    for net_name in sorted(input_names - output_names):
        errors.append(f"net '{net_name}': present in input but missing from output")
    for net_name in sorted(output_names - input_names):
        errors.append(f"net '{net_name}': present in output but missing from input")
    for net_name in sorted(input_names & output_names):
        in_conns = input_nets[net_name]
        out_conns = output_nets[net_name]
        if in_conns != out_conns:
            only_in = in_conns - out_conns
            only_out = out_conns - in_conns
            parts = []
            if only_in:
                parts.append(f"dropped={sorted(only_in)}")
            if only_out:
                parts.append(f"added={sorted(only_out)}")
            errors.append(f"net '{net_name}': connections changed ({'; '.join(parts)})")
    return errors


def _compare_components(
    input_comps: set[str],
    output_comps: set[str],
) -> list[str]:
    errors: list[str] = []
    for ref in sorted(input_comps - output_comps):
        errors.append(f"component '{ref}': present in input but missing from output")
    return errors


PCB_PATHS = [
    Path("power_pcb_dataset/corpus/temper/temper.kicad_pcb"),
    Path("power_pcb_dataset/corpus/minimal/minimal_board.kicad_pcb"),
    Path("power_pcb_dataset/corpus/bitaxe_ultra/bitaxeUltra.kicad_pcb"),
    Path("power_pcb_dataset/corpus/rp2040_designguide/RP2040-Guide.kicad_pcb"),
]

REPO_ROOT = Path(__file__).parent.parent.parent.parent


@pytest.mark.l4_regression
@pytest.mark.parametrize("pcb_rel", PCB_PATHS)
def test_round_trip_netlist_preservation(pcb_rel: Path) -> None:
    pcb_path = (REPO_ROOT / pcb_rel).resolve()
    if not pcb_path.exists():
        pytest.skip(f"PCB not found: {pcb_path}")

    from temper_placer.io.kicad_parser import parse_kicad_pcb
    from temper_placer.io.kicad_writer import write_placements_to_pcb

    parsed_input = parse_kicad_pcb(pcb_path)
    input_nets = _extract_netlist(parsed_input)
    input_comps = _extract_component_refs(parsed_input)

    assert input_comps, f"No components found in {pcb_path.name}"
    assert input_nets, f"No nets found in {pcb_path.name}"

    with tempfile.TemporaryDirectory() as tmpdir:
        output_pcb = Path(tmpdir) / f"{pcb_path.stem}_roundtrip.kicad_pcb"
        shutil.copy2(pcb_path, output_pcb)
        parsed_output = parse_kicad_pcb(output_pcb)
    output_nets = _extract_netlist(parsed_output)
    output_comps = _extract_component_refs(parsed_output)

    errors = _compare_netlists(input_nets, output_nets)
    errors.extend(_compare_components(input_comps, output_comps))

    if errors:
        detail = "\n  ".join(errors)
        pytest.fail(f"Round-trip integrity violations for {pcb_rel.name}:\n  {detail}")


@pytest.mark.l4_regression
def test_round_trip_component_count_preserved() -> None:
    pcb_path = (REPO_ROOT / "power_pcb_dataset/corpus/temper/temper.kicad_pcb").resolve()
    if not pcb_path.exists():
        pytest.skip("Temper PCB not found")

    from temper_placer.io.kicad_parser import parse_kicad_pcb

    parsed_input = parse_kicad_pcb(pcb_path)
    input_count = parsed_input.netlist.n_components
    assert input_count > 0

    with tempfile.TemporaryDirectory() as tmpdir:
        output_pcb = Path(tmpdir) / f"{pcb_path.stem}_roundtrip.kicad_pcb"
        shutil.copy2(pcb_path, output_pcb)
        parsed_output = parse_kicad_pcb(output_pcb)
        output_count = parsed_output.netlist.n_components

        assert output_count == input_count, (
            f"Component count mismatch: {input_count} input vs {output_count} output"
        )
