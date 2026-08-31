#!/usr/bin/env python3
"""Classify ERC `endpoint_off_grid` warnings by electrical consequence.

`endpoint_off_grid` is the single largest ERC warning class on this board
(163 of 498 warnings on `pcb/temper.kicad_sch` as of 2026-08-07, KiCad
10.0.5) and `docs/STRATEGY.md` explicitly singles it out as worth checking
rather than bulk-suppressing: on a mains-connected board, "off-grid" could
in principle mean two wires that *look* joined in the schematic viewer but
are not electrically the same net. This script answers that question
mechanically instead of by eyeballing coordinates.

It does NOT re-run kicad-cli itself (a working kicad-cli is not reliably
available in every environment this repo's agents run in -- see
`docs/evidence/2026-08-07-erc-off-grid-endpoint-analysis.md` for how a
10.0.5 build was obtained in a no-root sandbox). Instead it consumes three
already-exported artifacts and cross-checks them:

  1. An ERC JSON report for `pcb/temper.kicad_sch`
     (`kicad-cli sch erc --format json --severity-all -o <out> pcb/temper.kicad_sch`).
     Running `sch erc` on the top-level sheet walks its full hierarchy
     (Power_Input, Half_Bridge, Power_Management, Safety_Interlock,
     Sensing, MCU) in one pass, so `pcb/mcu.kicad_sch` does not need a
     separate run to be covered by this check -- it only adds
     hierarchy-context-dependent noise (isolated_pin_label /
     pin_not_connected for hierarchical labels that only resolve inside
     the parent sheet) when run standalone, not new off-grid endpoints.
  2. A KiCad-exported schematic netlist in kicadxml format
     (`kicad-cli sch export netlist --format kicadxml -o <out> pcb/temper.kicad_sch`).
     This reflects EXACT-coordinate connectivity as KiCad's own engine
     computes it -- independent of the visual/snap grid `endpoint_off_grid`
     complains about.
  3. The atopile-compiled netlist (`elec/build/default.net`, from
     `make netlist`) -- the design's stated intent, independent of how
     `scripts/gen_schematics.py` happened to lay pins out on the page.

For every (reference, pin) that ERC flagged as `endpoint_off_grid`, this
script checks whether the schematic's actual net membership (source 2)
matches the atopile net's membership (source 3) member-for-member. A
mismatch means the off-grid pin sits on a schematic net that doesn't
contain the parts the design says it should (or contains extras) --
exactly the "looks connected, isn't" failure mode. It also classifies each
off-grid pin's net by domain (HV/mains, SELV/control, protection/fault
chain, or other) using `elec/domain_manifest.yaml`, the repo's canonical
HV/SELV declaration, so a mismatch (if any) can be triaged by consequence
immediately instead of requiring a second pass.

Regenerating the inputs, from repo root:

    make netlist                                                    # (3)
    <kicad-cli> sch erc --format json --severity-all \\
        -o /tmp/temper_erc.json pcb/temper.kicad_sch                # (1)
    <kicad-cli> sch export netlist --format kicadxml \\
        -o /tmp/temper_netlist.xml pcb/temper.kicad_sch              # (2)

Exit codes:
  0 - PASSED: every endpoint_off_grid pin's schematic net matches its
      atopile net member-for-member, AND every endpoint_off_grid pin
      exists in the atopile-compiled netlist in the first place. Cosmetic
      warning class, confirmed.
  1 - FAILED: at least one endpoint_off_grid pin sits on a schematic net
      that diverges from design intent (MISMATCH) -- a real connectivity
      defect riding on this warning class -- OR at least one
      endpoint_off_grid pin has no atopile net at all (NO_ATOPILE_NET).
      NO_ATOPILE_NET means this script cannot answer the question it
      exists to answer for that pin: the design's stated intent (the
      atopile netlist) says nothing about it, so member-for-member
      agreement can't be checked. On a mains-connected board that is not
      a milder form of "matches" -- it is the one case this gate
      structurally cannot verify, and is treated as a failure rather than
      folded into the same green verdict as a checked, passing pin (see
      docs/evidence/2026-08-11-gate-vacuity-audit.md finding 1). Both
      classes are printed, with net domain, for triage.
  2 - GATE ERROR: an input file is missing, empty, or unparsable. Never
      treated as "0 mismatches" -- see check_domain_partition.py's own
      fail-closed rationale, which this mirrors.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
import xml.etree.ElementTree as ET

try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None


def die(msg: str) -> None:
    print(f"GATE ERROR: {msg}", file=sys.stderr)
    sys.exit(2)


def parse_sexpr(text: str):
    """Minimal S-expression tokenizer/parser, sufficient for kicad .net files."""
    tokens = re.findall(r'\(|\)|"(?:[^"\\]|\\.)*"|[^\s()]+', text)
    pos = 0

    def parse():
        nonlocal pos
        if pos >= len(tokens) or tokens[pos] != '(':
            raise ValueError(f"expected '(' at token {pos}")
        pos += 1
        node = []
        while tokens[pos] != ')':
            if tokens[pos] == '(':
                node.append(parse())
            else:
                tok = tokens[pos]
                if tok.startswith('"'):
                    tok = tok[1:-1]
                node.append(tok)
                pos += 1
        pos += 1
        return node

    return parse()


def load_atopile_nets(path: Path) -> dict[str, frozenset]:
    text = path.read_text()
    if not text.strip():
        die(f"{path} is empty")
    tree = parse_sexpr(text)

    def find(node, tag):
        for item in node:
            if isinstance(item, list) and item and item[0] == tag:
                return item
        return None

    nets_node = find(tree, 'nets')
    if nets_node is None:
        die(f"{path}: no (nets ...) block found -- not a valid kicad netlist export")

    nets: dict[str, frozenset] = {}
    for net in nets_node[1:]:
        name = None
        members = []
        for field in net[1:]:
            if field[0] == 'name':
                name = field[1]
            elif field[0] == 'node':
                ref = pin = None
                for f2 in field[1:]:
                    if f2[0] == 'ref':
                        ref = f2[1]
                    elif f2[0] == 'pin':
                        pin = f2[1]
                members.append((ref, pin))
        nets[name] = frozenset(members)
    if not nets:
        die(f"{path}: parsed 0 nets -- treat as a build failure, not '0 violations'")
    return nets


def load_schematic_nets(path: Path) -> dict[str, frozenset]:
    if not path.exists() or path.stat().st_size == 0:
        die(f"{path} is missing or empty")
    root = ET.parse(path).getroot()
    nets_el = root.find('nets')
    if nets_el is None:
        die(f"{path}: no <nets> element -- not a kicadxml netlist export")
    nets = {}
    for net in nets_el:
        name = net.attrib['name'].lstrip('/')
        members = frozenset((node.attrib['ref'], node.attrib['pin']) for node in net)
        nets[name] = members
    if not nets:
        die(f"{path}: parsed 0 nets")
    return nets


def normalize_sch_name(name: str, ato_names: set[str]) -> str:
    """KiCad's schematic netlist export prefixes sheet-local net names with
    their owning sheet ('Half_Bridge/SW_NODE'); atopile emits the bare local
    name ('SW_NODE'). Strip one leading '<Sheet>/' if that resolves to a
    name atopile actually has -- this is a naming-convention difference,
    not a connectivity question, and conflating the two would manufacture
    false mismatches for every sheet-local net in the design."""
    if name in ato_names:
        return name
    if '/' in name:
        stripped = name.split('/', 1)[1]
        if stripped in ato_names:
            return stripped
    return name


def load_off_grid_pins(erc_json_paths: list[Path]) -> list[dict]:
    entries = []
    seen = set()
    for p in erc_json_paths:
        if not p.exists() or p.stat().st_size == 0:
            die(f"{p} is missing or empty")
        d = json.loads(p.read_text())
        sheets = d.get('sheets')
        if not sheets:
            die(f"{p}: no 'sheets' key -- not a kicad-cli ERC JSON report")
        for sheet in sheets:
            for v in sheet.get('violations', []):
                if v.get('type') != 'endpoint_off_grid':
                    continue
                for item in v.get('items', []):
                    m = re.match(r'Symbol (\S+) Pin (\S+)', item.get('description', ''))
                    if not m:
                        continue  # off-grid *wire* endpoint, not a symbol pin; not net-checkable this way
                    key = (m.group(1), m.group(2))
                    if key in seen:
                        continue
                    seen.add(key)
                    entries.append({'ref': m.group(1), 'pin': m.group(2), 'source': str(p)})
    if not entries:
        die("0 endpoint_off_grid pin entries parsed across all inputs -- "
            "if ERC genuinely reports zero, that is real news and should be "
            "stated as such, not silently treated as gate-pass")
    return entries


def classify_domain(net_name: str | None, hv: set[str], selv: set[str]) -> str:
    if net_name is None:
        return 'UNKNOWN (no atopile net -- pin not in compiled design)'
    if net_name in hv:
        return 'HV/mains'
    if net_name in selv:
        return 'SELV/control (declared)'
    if net_name.startswith('safety.'):
        return f'protection/fault-chain ({net_name.split(".", 2)[0]}.{net_name.split(".", 2)[1] if "." in net_name else ""})'
    if net_name.startswith('discharge.'):
        return 'discharge/relay (HV-adjacent, undeclared in manifest)'
    if net_name.startswith('thermal.'):
        return 'thermal (fan/aux, undeclared in manifest)'
    return 'other/undeclared in manifest'


def load_backlogged_nets(path: Path) -> dict[str, dict]:
    """``{net: entry}`` for every ``backlog: true`` entry in the
    netlist-stage gate's allowlist.

    Read from THAT gate's file rather than duplicated here, deliberately.
    ``ac_l`` is the worked example: this gate reports it as a mismatch
    (atopile net has 1 member, the schematic has 0) and
    ``check_netlist_stage_checks.py`` reports it as a single-pin net. Same
    fact -- no AC inlet connector exists anywhere in ``elec/src``, so mains
    entry is unwired at the schematic level. That gate tolerates it as a
    dated backlog item; this one failed closed on it, and the disagreement
    was the anomaly rather than the tolerance.

    Copying the entry across would have re-introduced that divergence the
    next time either side moved.
    """
    if not path.exists():
        return {}
    data = yaml.safe_load(path.read_text()) or {}
    return {
        str(e["net"]): e
        for e in (data.get("allowlist") or [])
        if isinstance(e, dict) and e.get("backlog") and e.get("net")
    }


def is_backlogged(detail: str, ato_name: str, backlog: dict[str, dict]) -> bool:
    """Is this the already-documented "absent from the schematic" shape?

    Deliberately NOT a per-net exemption. It suppresses only the divergence
    the backlog entry actually describes -- members missing from the
    schematic and nothing unexpected present. A backlogged net that grows an
    ``extra_in_schematic`` member is a different defect (something is wired
    that should not be) and still fails this gate.
    """
    return ato_name in backlog and "extra_in_schematic=[]" in detail


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--erc-json', action='append', required=True,
                     help='ERC JSON report(s) to scan for endpoint_off_grid. Repeatable.')
    ap.add_argument('--sch-netlist-xml', required=True,
                     help='kicadxml netlist export of pcb/temper.kicad_sch')
    ap.add_argument('--atopile-net', default='elec/build/default.net',
                     help='atopile-compiled netlist (default: elec/build/default.net)')
    ap.add_argument('--domain-manifest', default='elec/domain_manifest.yaml',
                     help='canonical HV/SELV declaration (default: elec/domain_manifest.yaml)')
    ap.add_argument('--netlist-stage-allowlist', default='netlist-stage-checks-allowlist.yaml',
                     help='netlist-stage gate allowlist; its `backlog: true` nets are '
                          'reported here but do not block '
                          '(default: netlist-stage-checks-allowlist.yaml)')
    args = ap.parse_args()

    if yaml is None:
        die("PyYAML not importable -- run under an environment with pyyaml (e.g. `uv run`)")

    ato_path = Path(args.atopile_net)
    sch_path = Path(args.sch_netlist_xml)
    manifest_path = Path(args.domain_manifest)
    if not manifest_path.exists():
        die(f"{manifest_path} missing")

    manifest = yaml.safe_load(manifest_path.read_text())
    hv_nets = set(manifest.get('domains', {}).get('HV', {}).get('nets', []))
    selv_nets = set(manifest.get('domains', {}).get('SELV', {}).get('nets', []))
    if not hv_nets or not selv_nets:
        die(f"{manifest_path}: HV or SELV domain net list is empty -- manifest looks stale/malformed")

    ato_nets = load_atopile_nets(ato_path)
    sch_nets_raw = load_schematic_nets(sch_path)
    ato_names = set(ato_nets)

    sch_nets: dict[str, frozenset] = {}
    for raw_name, members in sch_nets_raw.items():
        norm = normalize_sch_name(raw_name, ato_names)
        sch_nets[norm] = sch_nets.get(norm, frozenset()) | members

    ato_pin_to_net: dict[tuple[str, str], str] = {}
    for name, members in ato_nets.items():
        for m in members:
            ato_pin_to_net[m] = name

    sch_pin_to_nets: dict[tuple[str, str], set[str]] = defaultdict(set)
    for name, members in sch_nets.items():
        for m in members:
            sch_pin_to_nets[m].add(name)

    off_grid = load_off_grid_pins([Path(p) for p in args.erc_json])

    mismatches = []
    # NO_ATOPILE_NET pins: the atopile-compiled netlist -- the design's
    # stated intent -- says nothing about this pin at all, so this gate
    # structurally cannot verify member-for-member agreement for it. That
    # is NOT a milder form of "matches" (docs/evidence/
    # 2026-08-11-gate-vacuity-audit.md finding 1): it is treated as a
    # failure, same as a confirmed MISMATCH, rather than folded into an
    # unqualified "PASSED".
    unverifiable = []
    domain_counts: Counter = Counter()
    rows = []
    for e in off_grid:
        key = (e['ref'], e['pin'])
        ato_name = ato_pin_to_net.get(key)
        domain = classify_domain(ato_name, hv_nets, selv_nets)
        domain_counts[domain] += 1

        status = 'OK'
        detail = ato_name
        if ato_name is None:
            status = 'NO_ATOPILE_NET'
            detail = ('no atopile net for this pin -- the compiled design '
                       'never declares it, so member-for-member agreement '
                       'cannot be checked')
            unverifiable.append((key, domain, detail))
        else:
            sch_names_for_pin = sch_pin_to_nets.get(key, set())
            if ato_name not in sch_names_for_pin:
                status = 'MISMATCH'
                a_members = ato_nets[ato_name]
                s_members = sch_nets.get(ato_name, frozenset())
                detail = (f"atopile net {ato_name!r} has {len(a_members)} members; "
                          f"schematic net of that name has {len(s_members)} members; "
                          f"missing_in_schematic={sorted(a_members - s_members)} "
                          f"extra_in_schematic={sorted(s_members - a_members)}")
                mismatches.append((key, domain, detail, ato_name))
        rows.append((e['ref'], e['pin'], ato_name, domain, status))

    rows.sort(key=lambda r: (r[4] == 'OK', r[3], r[0]))
    print(f"{'ref':8} {'pin':5} {'net':40} {'domain':45} status")
    for r in rows:
        print(f"{r[0]:8} {r[1]:5} {str(r[2]):40} {r[3]:45} {r[4]}")

    print(f"\nendpoint_off_grid pins checked: {len(off_grid)}")
    print("\nDomain breakdown:")
    for k, v in domain_counts.most_common():
        print(f"  {v:4}  {k}")

    backlog = load_backlogged_nets(Path(args.netlist_stage_allowlist))
    backlogged = [m for m in mismatches if is_backlogged(m[2], m[3], backlog)]
    mismatches = [m for m in mismatches if not is_backlogged(m[2], m[3], backlog)]

    # Printed on EVERY run, pass or fail. The sibling gate's contract:
    # "Backlog entries still suppress the exit code ... but are never
    # invisible". A gate that quietly drops a finding is one edit away from
    # being trusted about something it stopped looking at.
    if backlogged:
        print(f"\nBacklog: {len(backlogged)} documented open question(s), reported and "
              f"NOT blocking (source: {args.netlist_stage_allowlist}):")
        for key, domain, detail, ato_name in backlogged:
            entry = backlog[ato_name]
            print(f"  {key} [{domain}] net {ato_name!r} -- seeded {entry.get('seeded', '?')}")
            print(f"      {detail}")
            reason = " ".join(str(entry.get("reason", "")).split())
            if reason:
                print(f"      reason: {reason}")

    if mismatches:
        print(f"\n{len(mismatches)} MISMATCH(ES) -- schematic net diverges from design intent:")
        for key, domain, detail, _ato in mismatches:
            print(f"  {key} [{domain}]: {detail}")

    if unverifiable:
        print(f"\n{len(unverifiable)} UNVERIFIABLE (NO_ATOPILE_NET) -- endpoint_off_grid "
              f"pin(s) absent from the atopile-compiled netlist; member-for-member "
              f"agreement cannot be checked for these:")
        for key, domain, detail in unverifiable:
            print(f"  {key} [{domain}]: {detail}")

    if mismatches or unverifiable:
        print(f"\nFAILED: {len(mismatches)} non-backlogged mismatch(es), "
              f"{len(unverifiable)} unverifiable (no atopile net) "
              f"endpoint_off_grid pin(s). A pin this gate cannot verify is not "
              f"evidence it is safe -- see "
              f"docs/evidence/2026-08-11-gate-vacuity-audit.md finding 1.")
        return 1

    print("\nPASSED: every endpoint_off_grid pin's schematic net matches its "
          "atopile net member-for-member, and every endpoint_off_grid pin "
          "exists in the atopile-compiled netlist. No electrical "
          "disconnection or unintended short rides on this warning class.")
    return 0


if __name__ == '__main__':
    sys.exit(main())
