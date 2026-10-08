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
import os
import re
import subprocess
from pathlib import Path

UNIT = Path(__file__).resolve().parents[1]

REINFORCED_MM = 8.0          # D5 provisional PCB floor (PD3, IIIa, >125-250 V)
FUNCTIONAL_CREEPAGE_MM = 3.2  # Table 18, PD3, >125-250 V
TANK_CREEPAGE_MM = 5.0        # Table 18, PD3, >250-400 V: tank HF margin

# Single-pin no-connect nets on the SELV side of their isolator packages.
SELV_NC = {"nc10", "nc11", "nc12", "nc15", "leg_a.driver-nc_7", "leg_b.driver-nc_7"}

# HOT potential groups. Nets share a group only when (a) they are joined by a
# conductor or low-impedance element that is not expected to open (not a
# fuse, thermal cutoff, switch or divider resistor), and (b) their
# normal-operation difference is at most ~30 V. Every pair of nets in
# different groups gets the functional spacing rule; a same-group pair is
# exempt. Divider and bleed taps are therefore each their own group.
HOT_GROUPS: dict[str, set[str]] = {
    "AC_L_IN": {"ac_l_in"},                   # F1 can open: line vs l_f
    "L_F": {"l_f", "l_filt"},                 # CMC winding: milliohms
    "TCO_L": {"tco_l"},                       # thermal cutoff can open
    "MAINS_N": {"ac_n_in", "n_filt"},         # CMC winding
    "XBLEED": {"xbleed_mid"},                 # X-cap bleed tap (~line/2)
    "RECT_P": {"rect_p"},                     # bring-up link can be open
    "RECT_N": {"rect_n"},
    "BUS_P": {"bus_p"},
    "BUSBLEED": {"busbleed_mid"},             # bus/2
    "VDIV_1": {"vdiv_1"},                     # bus x 3/4 (divider taps
    "VDIV_2": {"vdiv_2"},                     #  differ by ~50-70 V each)
    "VDIV_3": {"vdiv_3"},
    "LOW": {                                  # <= 15 V from LEG_RET; the
        "hv_ret", "leg_ret", "ocp_kelvin_n",  # shunt is 1 mOhm
        "hot5", "v15_ls", "ref25", "ocp_node",
        "ocp_thresh", "ocp_ok_hot", "ovp_thresh", "ovp_ok_hot", "bus_fault_hot",
        "vsense_in", "leg_a-gate_l", "leg_a-out_l", "leg_b-gate_l", "leg_b-out_l",
        "nc", "nc2", "nc5", "nc6", "nc8",
    },
    "SW_A": {"sw_a", "coil_feed", "leg_a-boot", "leg_a-gate_h", "leg_a-out_h"},  # T1 primary is one turn
    "SW_B": {"sw_b", "leg_b-boot", "leg_b-gate_h", "leg_b-out_h"},
    "RES_A": {"res_a"},                       # tank node
    "CRBLEED_1": {"crbleed_1"},               # resonant-bleed taps
    "CRBLEED_2": {"crbleed_2"},
    "CRBLEED_3": {"crbleed_3"},
}
TANK = {"res_a", "crbleed_1", "crbleed_2", "crbleed_3"}
PE = {"pe"}


def audit_selv_nets(audit: Path) -> set[str]:
    text = audit.read_text(encoding="utf-8")
    block = re.search(r"const SELV_NETS: &\[&str\] = &\[(.*?)\];", text, re.S)
    if block is None:
        raise ValueError("SELV_NETS not found in audit.rs")
    return set(re.findall(r'"([^"]+)"', block[1]))


def board_nets(board: str) -> set[str]:
    return {name for name in re.findall(r'\(net (?:\d+ )?"([^"]*)"\)', board) if name}


def sexpr_at(text: str, start: int) -> str:
    """Return one KiCad S-expression, respecting strings and escaped quotes."""
    depth = 0
    quoted = False
    escaped = False
    for end in range(start, len(text)):
        char = text[end]
        if quoted:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                quoted = False
        elif char == '"':
            quoted = True
        elif char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
            if depth == 0:
                return text[start : end + 1]
    raise ValueError("unterminated KiCad S-expression")


def footprint_nets(board: str) -> dict[str, set[str]]:
    """Reference -> set of nets on its pads."""
    out: dict[str, set[str]] = {}
    # Only parse complete footprint and pad expressions. KiCad writes routed
    # tracks after the final footprint, so splitting on footprint starts can
    # silently assign every track net on the board to that last component.
    for match in re.finditer(r"\n[ \t]+\(footprint\s", board):
        block = sexpr_at(board, match.start() + match[0].index("(footprint"))
        reference = re.search(r'\(property "Reference" "([^"]+)"', block)
        if reference is None:
            raise ValueError("footprint without Reference property")
        ref = reference[1]
        if ref in out:
            raise ValueError(f"duplicate footprint Reference {ref}")
        nets = set()
        for pad_match in re.finditer(r"\n[ \t]+\(pad\s", block):
            pad = sexpr_at(block, pad_match.start() + pad_match[0].index("(pad"))
            net = re.search(r'\(net (?:\d+ )?"([^"]+)"\)', pad)
            if net is not None:
                nets.add(net[1])
        out[ref] = nets
    return out


def any_of(side: str, nets: set[str]) -> str:
    return "(" + " || ".join(f"{side}.NetName == '{n}'" for n in sorted(nets)) + ")"


def rules(board: str, selv: set[str], pad_escape_rules: str = "") -> str:
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
    fp_nets = footprint_nets(board)
    multi = sorted(r for r, ns in fp_nets.items() if len({group_of[n] for n in ns if n in group_of}) > 1)
    if not multi:
        raise ValueError("no multi-group footprints found; board parse failed")
    same_fp = " || ".join(
        f"(A.memberOfFootprint('{r}') && B.memberOfFootprint('{r}'))" for r in multi
    )
    # Only the component's actual pads inherit its certified pin spacing.
    # intersectsCourtyard() matches a whole track that merely touches the
    # courtyard, including copper outside it, and cannot bound pad escapes.
    tank = TANK & nets
    a_hot, b_hot = any_of("A", hot_on_board), any_of("B", hot_on_board)
    out = ["(version 1)", ""]
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
    if pad_escape_rules:
        out.append(pad_escape_rules)
    # KiCad's last matching rule wins. Keep both barrier floors after every
    # component-local exception, even if a future escape request is misfiled.
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
    return "\n\n".join(out) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("board", type=Path)
    args = parser.parse_args()
    board = args.board.read_text(encoding="utf-8")
    escape_rules = ""
    if re.search(r'\(name "PE_', board):
        # Rust validates the physical pad geometry, explicit net contract,
        # and *entire* named rule-area polygons on every regeneration. KiCad
        # zone refills can rewrite the board without changing those shapes.
        kicad_python = os.environ.get(
            "KICAD_PYTHON",
            "/Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/Current/bin/python3",
        )
        verified = subprocess.run(
            [kicad_python, str(UNIT / "tools" / "pad_escape.py"), "--verify", str(args.board)],
            capture_output=True, text=True, check=True,
        )
        escape_rules = verified.stdout
    text = rules(board, audit_selv_nets(UNIT / "audit.rs"), escape_rules)
    target = args.board.with_suffix(".kicad_dru")
    target.write_text(text, encoding="utf-8")
    print(target)


if __name__ == "__main__":
    main()
