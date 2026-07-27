"""
Real-board placement fixture for REQ-SAFE-01 integration tests.

Combines two real, independently-sourced data sets rather than inventing a
synthetic fixture:

- Component **positions** come from the committed, routed board,
  ``pcb/temper.kicad_pcb`` (via ``temper_placer.io.kicad_parser.parse_kicad_pcb``).
  Positions are keyed by reference designator, which is stable across a net
  rename -- unlike net names, a ref does not change when the schematic is
  edited to rename or re-scope a net.
- Net **domain classification** comes from ``elec/build/default.net``
  (produced by ``make netlist`` from the current ``elec/src/*.ato``), parsed
  directly here rather than trusting the copper's own embedded net names.

This split exists because, as verified directly (not assumed) while building
this fixture: **``pcb/temper.kicad_pcb`` is stale relative to the current
schematic source.** Its embedded net list still has ``+340V_BUS`` (the
pre-SELV-redesign name; the current source renamed it to ``+170V_BUS``, see
docs/hardware/SELV_ISOLATION_REDESIGN.md Sec 5) and has **no ``gnd``,
``ZCD_ISO``, or ``pe`` net at all** -- its SELV-side nodes are still the
fragmented, per-instance micro-nets (``rtd_pan.r_high_top-inp``,
``hb.gate_hs.driver-p1``, etc.) that ``make netlist`` on the current source
now merges into the single named ``gnd`` net (80 pins, per the redesign
doc's own netlist evidence). Classifying domains from the PCB's own net
names would silently find zero components on a net called ``gnd`` (it
doesn't exist there) and report a vacuous "0 violations" pass -- exactly the
inspects-nothing-and-passes failure mode this task instructs against. Using
``default.net`` for classification, joined back to the PCB by reference
designator, avoids that trap.

Per docs/hardware/SELV_ISOLATION_REDESIGN.md Sec 6/Sec 1, per-net
classification used here (asserted from that document + a direct read of
``elec/build/default.net``, not invented):

- ``LV_CONTROL`` (SELV): ``gnd``, ``+15V`` (vcc_15v, off the AuxSupply
  secondary), ``+3V3`` (vcc_3v3), ``ZCD_ISO`` (opto output side).
- ``DC_BUS`` (HV, doubler-referenced): ``+170V_BUS`` (dc_bus_plus, the
  positive half-bus), ``PWR_RTN`` (power_return, the doubler midpoint),
  ``DC_BUS_RTN`` (dc_bus_minus), ``zcd`` (the pre-opto HV-side ZCD divider
  tap, referenced to dc_bus.gnd_ref per Sec 4 row 2).
- ``MAINS``: ``ac_l``, ``ac_n`` (raw AC line/neutral, present as named nets
  in this build).
- Not classified (no matrix entry / not resolvable from net name alone):
  ``+15V_LS`` (floats on ``hv_minus``, closest to the ``BOOTSTRAP`` enum
  value but excluded here because IEC60335_REQUIREMENTS has no BOOTSTRAP
  row to check it against), and ``pe``. **``pe`` is UNVERIFIED / absent
  from this classification**: it does not appear as a named net anywhere in
  ``elec/build/default.net`` at all (confirmed by direct grep for `"pe"` as
  a net name -- zero matches), consistent with
  docs/hardware/IEC60335_CRITICAL_COMPONENTS.md's finding that no physical
  AC mains inlet/PE connector is instantiated in ``elec/src`` -- so ``pe``
  has no pad-bearing pins to export. ``VoltageDomain.ISOLATED`` is also not
  populated by this loader: no net name in this design corresponds 1:1 to
  "the floating side of a declared isolator" the way the enum intends it,
  so the (MAINS, ISOLATED, REINFORCED) matrix row is checked but will
  always report zero candidate components -- an honest gap, not a silent
  pass dressed up as compliance.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from temper_placer.io.kicad_parser import parse_kicad_pcb
from tests.requirements.validators.clearance import VoltageDomain

_REPO_ROOT = Path(__file__).resolve().parents[5]
_PCB_PATH = _REPO_ROOT / "pcb" / "temper.kicad_pcb"
_NETLIST_PATH = _REPO_ROOT / "elec" / "build" / "default.net"

# Net name -> domain, asserted from docs/hardware/SELV_ISOLATION_REDESIGN.md
# (see module docstring for the citation per net).
_NET_DOMAINS: dict[str, VoltageDomain] = {
    "gnd": VoltageDomain.LV_CONTROL,
    "+15V": VoltageDomain.LV_CONTROL,
    "+3V3": VoltageDomain.LV_CONTROL,
    "ZCD_ISO": VoltageDomain.LV_CONTROL,
    "+170V_BUS": VoltageDomain.DC_BUS,
    "PWR_RTN": VoltageDomain.DC_BUS,
    "DC_BUS_RTN": VoltageDomain.DC_BUS,
    "zcd": VoltageDomain.DC_BUS,
    "ac_l": VoltageDomain.MAINS,
    "ac_n": VoltageDomain.MAINS,
}


class RealBoardUnavailable(RuntimeError):
    """Raised when the real-board fixture inputs are missing.

    Callers should skip (not fail/pass) the test that needs this fixture --
    "no PCB/netlist available" is a different, honest condition from "zero
    violations found."
    """


def _parse_default_net(netlist_path: Path) -> dict[str, list[str]]:
    """Parse the ``(nets ...)`` block of a KiCad-format netlist export.

    Returns ``{net_name: [ref, ...]}`` -- the set of reference designators
    with at least one pin on that net (duplicates from multiple pins on the
    same ref collapsed). Intentionally minimal: only ``(net (name "X") ...
    (node (ref "Y") ...))`` structure is extracted; pin numbers and
    ``libsource``/footprint identity fields are not read here (per the
    task's own footprint-aliasing warning, identity is not this function's
    job -- connectivity is).
    """
    text = netlist_path.read_text()
    nets_start = text.index("(nets")
    nets_text = text[nets_start:]

    net_to_refs: dict[str, list[str]] = {}
    # Split on each top-level `(net (code "N") (name "X")` header.
    net_header_re = re.compile(r'\(net \(code "\d+"\) \(name "([^"]*)"\)')
    node_re = re.compile(r'\(node \(ref "([^"]+)"\)')

    headers = list(net_header_re.finditer(nets_text))
    for i, match in enumerate(headers):
        net_name = match.group(1)
        block_start = match.end()
        block_end = headers[i + 1].start() if i + 1 < len(headers) else len(nets_text)
        block = nets_text[block_start:block_end]
        refs = sorted(set(node_re.findall(block)))
        net_to_refs[net_name] = refs

    return net_to_refs


def load_real_board_placement() -> tuple[dict[str, Any], dict[str, VoltageDomain], dict[str, Any]]:
    """Build a (placement, voltage_domains, stats) tuple from the real board.

    Returns:
        placement: {"components": [...], "nets": {...}} in the shape
            consumed by check_domain_clearance / check_creepage_path /
            verify_iec60335_compliance.
        voltage_domains: {net_name: VoltageDomain} for the classified nets
            actually present, for verify_iec60335_compliance's second arg.
        stats: diagnostic counts (refs matched, nets classified, etc.) for
            reporting -- not used by the validators themselves.

    Raises:
        RealBoardUnavailable: if the PCB or netlist file is missing (e.g.
            ``make netlist`` was never run). Callers should ``pytest.skip``
            on this, not treat it as a passing or failing check.
    """
    if not _PCB_PATH.exists():
        raise RealBoardUnavailable(f"PCB not found: {_PCB_PATH}")
    if not _NETLIST_PATH.exists():
        raise RealBoardUnavailable(
            f"Netlist not found: {_NETLIST_PATH} -- run `make netlist` first."
        )

    net_to_refs = _parse_default_net(_NETLIST_PATH)

    pcb_result = parse_kicad_pcb(_PCB_PATH)
    ref_to_position = {
        c.ref: c.initial_position
        for c in pcb_result.netlist.components
        if c.initial_position is not None
    }

    # ref -> list of classified net names that ref touches
    ref_to_domain_nets: dict[str, list[str]] = {}
    classified_nets_present: dict[str, VoltageDomain] = {}
    for net_name, domain in _NET_DOMAINS.items():
        refs = net_to_refs.get(net_name)
        if not refs:
            continue  # net not present in this build; skip rather than guess
        classified_nets_present[net_name] = domain
        for ref in refs:
            ref_to_domain_nets.setdefault(ref, []).append(net_name)

    components = []
    matched_refs = 0
    for ref, position in ref_to_position.items():
        nets = ref_to_domain_nets.get(ref)
        if not nets:
            continue  # ref has no pin on a classified net; irrelevant to REQ-SAFE-01
        matched_refs += 1
        components.append({"ref": ref, "position": position, "nets": nets})

    nets_dict = {name: {"domain": domain} for name, domain in classified_nets_present.items()}
    placement = {"components": components, "nets": nets_dict}
    voltage_domains = dict(classified_nets_present)

    stats = {
        "pcb_components": len(ref_to_position),
        "netlist_refs_on_classified_nets": len(ref_to_domain_nets),
        "matched_components_in_placement": matched_refs,
        "classified_nets_present": sorted(classified_nets_present),
        "classified_nets_requested_but_absent": sorted(
            set(_NET_DOMAINS) - set(classified_nets_present)
        ),
    }
    return placement, voltage_domains, stats
