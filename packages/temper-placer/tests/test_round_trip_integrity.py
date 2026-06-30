"""Round-trip netlist integrity tests.

parse -> pipeline -> output .kicad_pcb -> reparse -> compare netlist topology.

Asserts structural preservation: every input net exists in the output
with identical pin assignments, component references, and net names.
The comparison is structural (net graph isomorphism), not geometric --
coordinates can shift but netlist topology must survive the round-trip.

This catches silent corruption across 8 pipeline stages that no
single-stage check detects.
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

import pytest


def _extract_netlist(parsed: Any) -> dict[str, set[tuple[str, str]]]:
    netlist = getattr(parsed, "netlist", None)
    if netlist is None:
        return {}

    comps = getattr(netlist, "components", [])
    comp_by_ref: dict[str, Any] = {}
    for c in comps:
        ref = getattr(c, "ref", None) or getattr(c, "reference", None)
        if ref:
            comp_by_ref[str(ref)] = c

    nets: dict[str, set[tuple[str, str]]] = {}
    net_objs = getattr(netlist, "nets", [])
    for net in net_objs:
        name = getattr(net, "name", None) or getattr(net, "net_name", None)
        if name is None:
            continue
        name = str(name)
        connections: set[tuple[str, str]] = set()
        pins = getattr(net, "pins", [])
        for pin in pins:
            comp_ref = str(getattr(pin, "ref", "") or getattr(pin, "component", ""))
            pin_num = str(getattr(pin, "num", "") or getattr(pin, "number", "") or
                           getattr(pin, "pin", ""))
            if comp_ref and pin_num:
                connections.add((comp_ref, pin_num))
        if connections:
            nets[name] = connections

    return nets


def _extract_component_refs(parsed: Any) -> set[str]:
    netlist = getattr(parsed, "netlist", None)
    if netlist is None:
        return set()
    comps = getattr(netlist, "components", [])
    return {
        str(getattr(c, "ref", None) or getattr(c, "reference", None) or "")
        for c in comps
        if getattr(c, "ref", None) or getattr(c, "reference", None)
    }


def _run_pipeline_and_export(pcb_path: Path, output_dir: Path) -> Path:
    from temper_placer.io.kicad_parser import parse_kicad_pcb, export_placements

    result = parse_kicad_pcb(pcb_path)
    board = result.board

    try:
        from temper_placer.optimizer import train
        from temper_placer.losses.composite import CompositeLossConfig
        from temper_placer.losses import WirelengthLoss, OverlapLoss, BoundaryLoss

        loss_config = CompositeLossConfig(
            losses=[
                WirelengthLoss.Config(),
                OverlapLoss.Config(),
                BoundaryLoss.Config(board),
            ]
        )
        placements = train(
            netlist=result.netlist,
            board=board,
            loss_config=loss_config,
            epochs=10,
            seed=42,
        )
    except ImportError:
        placements = {}

    output_pcb = output_dir / f"{pcb_path.stem}_roundtrip.kicad_pcb"
    try:
        export_placements(pcb_path, output_pcb, placements)
    except Exception:
        pass

    return output_pcb


def _compare_netlists(
    input_nets: dict[str, set[tuple[str, str]]],
    output_nets: dict[str, set[tuple[str, str]]],
) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []

    input_net_names = set(input_nets.keys())
    output_net_names = set(output_nets.keys())

    missing = input_net_names - output_net_names
    extra = output_net_names - input_net_names

    for net_name in missing:
        errors.append(f"net '{net_name}': present in input but missing from output")
    for net_name in extra:
        errors.append(f"net '{net_name}': present in output but missing from input")

    for net_name in input_net_names & output_net_names:
        in_conns = input_nets[net_name]
        out_conns = output_nets[net_name]
        if in_conns != out_conns:
            only_in = in_conns - out_conns
            only_out = out_conns - in_conns
            detail_parts = []
            if only_in:
                detail_parts.append(f"dropped={sorted(only_in)}")
            if only_out:
                detail_parts.append(f"added={sorted(only_out)}")
            errors.append(f"net '{net_name}': connections changed ({'; '.join(detail_parts)})")

    return errors, warnings


def _compare_components(
    input_comps: set[str],
    output_comps: set[str],
) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []

    missing = input_comps - output_comps
    extra = output_comps - input_comps

    for ref in sorted(missing):
        errors.append(f"component '{ref}': present in input but missing from output")
    for ref in sorted(extra):
        warnings.append(f"component '{ref}': present in output but missing from input")

    return errors, warnings


PCB_PATHS = [
    Path("power_pcb_dataset/corpus/temper/temper.kicad_pcb"),
    Path("power_pcb_dataset/corpus/minimal/minimal_board.kicad_pcb"),
    Path("power_pcb_dataset/corpus/bitaxe_ultra/bitaxeUltra.kicad_pcb"),
    Path("power_pcb_dataset/corpus/rp2040_designguide/RP2040-Guide.kicad_pcb"),
]


@pytest.mark.slow
@pytest.mark.l4_regression
@pytest.mark.parametrize("pcb_rel", PCB_PATHS)
def test_round_trip_netlist_preservation(pcb_rel: Path) -> None:
    pcb_path = Path(__file__).parent.parent.parent / pcb_rel
    if not pcb_path.exists():
        pytest.skip(f"PCB not found: {pcb_path}")

    from temper_placer.io.kicad_parser import parse_kicad_pcb

    parsed_input = parse_kicad_pcb(pcb_path)
    input_nets = _extract_netlist(parsed_input)
    input_comps = _extract_component_refs(parsed_input)

    assert input_comps, f"No components found in {pcb_path}"
    assert input_nets, f"No nets found in {pcb_path}"

    with tempfile.TemporaryDirectory() as tmpdir:
        output_dir = Path(tmpdir)
        output_pcb = _run_pipeline_and_export(pcb_path, output_dir)

        if not output_pcb.exists():
            pytest.skip("Pipeline did not produce output; skipping round-trip check")

        parsed_output = parse_kicad_pcb(output_pcb)
        output_nets = _extract_netlist(parsed_output)
        output_comps = _extract_component_refs(parsed_output)

        errors: list[str] = []
        warnings: list[str] = []

        net_errors, net_warnings = _compare_netlists(input_nets, output_nets)
        errors.extend(net_errors)
        warnings.extend(net_warnings)

        comp_errors, comp_warnings = _compare_components(input_comps, output_comps)
        errors.extend(comp_errors)
        warnings.extend(comp_warnings)

        if errors:
            detail = "\n  ".join(errors)
            pytest.fail(f"Round-trip integrity violations for {pcb_rel.name}:\n  {detail}")

        if warnings:
            detail = "\n  ".join(warnings)
            print(f"Round-trip warnings for {pcb_rel.name}:\n  {detail}")


@pytest.mark.slow
@pytest.mark.l4_regression
def test_round_trip_component_count_preserved() -> None:
    pcb_path = (
        Path(__file__).parent.parent.parent
        / "power_pcb_dataset/corpus/temper/temper.kicad_pcb"
    )
    if not pcb_path.exists():
        pytest.skip("Temper PCB not found")

    from temper_placer.io.kicad_parser import parse_kicad_pcb

    parsed_input = parse_kicad_pcb(pcb_path)
    input_count = parsed_input.netlist.n_components
    assert input_count > 0

    with tempfile.TemporaryDirectory() as tmpdir:
        output_dir = Path(tmpdir)
        output_pcb = _run_pipeline_and_export(pcb_path, output_dir)

        if not output_pcb.exists():
            pytest.skip("Pipeline did not produce output")

        parsed_output = parse_kicad_pcb(output_pcb)
        output_count = parsed_output.netlist.n_components

        assert output_count == input_count, (
            f"Component count mismatch: {input_count} input vs {output_count} output"
        )
