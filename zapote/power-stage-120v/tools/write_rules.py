#!/usr/bin/env python3
"""Write <native>/section.kicad_dru: insulation and functional spacing rules.

Domains come from audit.rs (SELV_NETS) plus the HOT potential groups below.
Every net on the board must be classified; an unknown net fails. Values are
the provisional D5 basis (D5-BASIS.md, RULES-PREFLIGHT.md): 8.0 mm reinforced
PCB floor for SELV<->HOT and PE<->HOT, and IEC 60335-1 Table 18 functional
creepage (PD3, IIIa/IIIb lookup) between HOT potential groups. Values are
provisional pending the certification-lab review.

KiCad 10 evaluates creepage constraints per net pair: footprint conditions
such as memberOfFootprint() never match a creepage rule (they do match
clearance). A component's own HOT pin spacing therefore cannot be exempted
from a creepage rule. Functional HOT-HOT spacing is enforced as a clearance
rule at the creepage value instead; for same-layer copper on a slotless
board the straight-line distance never exceeds the surface path, so this is
at least as strict. Barrier rules keep both clearance and creepage.
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

UNIT = Path(__file__).resolve().parents[1]

REINFORCED_MM = 8.0          # D5 provisional PCB floor (PD3, IIIa, >125-250 V)
FUNCTIONAL_CREEPAGE_MM = 3.2  # Table 18, PD3, >125-250 V
TANK_CREEPAGE_MM = 5.0        # Table 18, PD3, >250-400 V: tank HF margin

# Single-pin no-connect nets on the SELV side of their isolator packages.
SELV_NC = {"nc10", "nc11", "nc12", "nc15", "leg_a.driver-nc_7", "leg_b.driver-nc_7"}

HOT_GROUPS: dict[str, set[str]] = {
    "MAINS_L": {"ac_l_in", "l_f", "l_filt", "tco_l"},
    "MAINS_N": {"ac_n_in", "n_filt"},
    "XBLEED": {"xbleed_mid"},
    "RECT_P": {"rect_p"},
    "RECT_N": {"rect_n"},
    "BUS_P": {"bus_p"},
    "BUS_MID": {"busbleed_mid", "vdiv_1", "vdiv_2", "vdiv_3"},
    "LOW": {
        "hv_ret", "leg_ret", "ocp_kelvin_n", "hot5", "v15_ls", "ref25", "ocp_node",
        "ocp_thresh", "ocp_ok_hot", "ovp_thresh", "ovp_ok_hot", "bus_fault_hot",
        "vsense_in", "leg_a-gate_l", "leg_a-out_l", "leg_b-gate_l", "leg_b-out_l",
        "nc", "nc2", "nc5", "nc6", "nc8",
    },
    "SW_A": {"sw_a", "coil_feed", "leg_a-boot", "leg_a-gate_h", "leg_a-out_h"},
    "SW_B": {"sw_b", "leg_b-boot", "leg_b-gate_h", "leg_b-out_h"},
    "TANK": {"res_a", "crbleed_1", "crbleed_2", "crbleed_3"},
}
PE = {"pe"}


def audit_selv_nets(audit: Path) -> set[str]:
    text = audit.read_text(encoding="utf-8")
    block = re.search(r"const SELV_NETS: &\[&str\] = &\[(.*?)\];", text, re.S)
    if block is None:
        raise ValueError("SELV_NETS not found in audit.rs")
    return set(re.findall(r'"([^"]+)"', block[1]))


def board_nets(board: str) -> set[str]:
    return {name for name in re.findall(r'\(net \d+ "([^"]*)"\)', board) if name}


def footprint_groups(board: str, group_of: dict[str, str]) -> dict[str, set[str]]:
    """Reference -> set of HOT groups its pads touch."""
    out: dict[str, set[str]] = {}
    for block in re.split(r"\n  \(footprint ", board)[1:]:
        ref = re.search(r'\(property "Reference" "([^"]+)"', block)[1]
        nets = set(re.findall(r'\(net \d+ "([^"]+)"\)', block))
        out[ref] = {group_of[n] for n in nets if n in group_of}
    return out


def any_of(side: str, nets: set[str]) -> str:
    return "(" + " || ".join(f"{side}.NetName == '{n}'" for n in sorted(nets)) + ")"


def rules(board: str, selv: set[str]) -> str:
    nets = board_nets(board)
    selv_all = selv | SELV_NC
    hot = set().union(*HOT_GROUPS.values())
    group_of = {n: g for g, members in HOT_GROUPS.items() for n in members}
    overlap = (selv_all & hot) | (selv_all & PE) | (hot & PE)
    if overlap:
        raise ValueError(f"nets in more than one domain: {sorted(overlap)}")
    unknown = sorted(nets - selv_all - hot - PE)
    if unknown:
        raise ValueError(f"unclassified board nets: {unknown}")
    stale = sorted((selv | hot | PE) - nets)
    if stale:
        raise ValueError(f"classified nets absent from the board: {stale}")
    hot_on_board = hot & nets
    selv_on_board = selv_all & nets

    same_group = " || ".join(
        f"({any_of('A', g & nets)} && {any_of('B', g & nets)})"
        for g in HOT_GROUPS.values() if g & nets
    )
    multi = sorted(r for r, gs in footprint_groups(board, group_of).items() if len(gs) > 1)
    same_fp = " || ".join(
        f"(A.memberOfFootprint('{r}') && B.memberOfFootprint('{r}'))" for r in multi
    )
    tank = HOT_GROUPS["TANK"] & nets
    a_hot, b_hot = any_of("A", hot_on_board), any_of("B", hot_on_board)
    out = ["(version 1)", ""]
    out.append(
        '(rule "SELV to HOT: reinforced, D5 provisional"\n'
        f'  (condition "{any_of("A", selv_on_board)} && {b_hot}")\n'
        f"  (constraint clearance (min {REINFORCED_MM}mm))\n"
        f"  (constraint creepage (min {REINFORCED_MM}mm)))"
    )
    out.append(
        '(rule "PE to HOT: D5 provisional floor"\n'
        f'  (condition "{any_of("A", PE)} && {b_hot}")\n'
        f"  (constraint clearance (min {REINFORCED_MM}mm))\n"
        f"  (constraint creepage (min {REINFORCED_MM}mm)))"
    )
    out.append(
        '(rule "HOT functional between potential groups"\n'
        f'  (condition "{a_hot} && {b_hot} && !({same_group})")\n'
        f"  (constraint clearance (min {FUNCTIONAL_CREEPAGE_MM}mm)))"
    )
    out.append(
        '(rule "HOT functional: tank node"\n'
        f'  (condition "{any_of("A", tank)} && {b_hot} && !{any_of("B", tank)}")\n'
        f"  (constraint clearance (min {TANK_CREEPAGE_MM}mm)))"
    )
    # Last rule wins in KiCad: a component's own pin spacing is governed by
    # its rating, so exempt HOT-HOT pairs inside one footprint. Barrier rules
    # (SELV, PE) are deliberately not exempted.
    out.append(
        '(rule "HOT pins within one component: component rating governs"\n'
        f'  (condition "({same_fp}) && {a_hot} && {b_hot}")\n'
        "  (constraint clearance (min 0.2mm)))"
    )
    return "\n\n".join(out) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("board", type=Path)
    args = parser.parse_args()
    text = rules(args.board.read_text(encoding="utf-8"), audit_selv_nets(UNIT / "audit.rs"))
    target = args.board.with_suffix(".kicad_dru")
    target.write_text(text, encoding="utf-8")
    print(target)


if __name__ == "__main__":
    main()
