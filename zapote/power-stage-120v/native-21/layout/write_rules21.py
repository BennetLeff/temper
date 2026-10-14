#!/usr/bin/env python3
"""Write native-21/section.kicad_dru with tools/write_rules.py's rule logic and native-21 net groups.

    python3 native-21/layout/write_rules21.py

Same D5 provisional values (8.0 mm SELV/PE<->HOT reinforced, 3.2 mm functional
between HOT potential groups, 5.0 mm around tank nodes). Grouping principle
unchanged (same group only when joined by a conductor/low impedance and within
~30 V). Native-21 additions:
- LOW also holds the whole LS bias domain referenced to LEG_RET: N_LS (-2 V),
  V15_LS, V24_RAW (+22 V), the SN6507 switch/snubber nodes (<= 48 V p-p), the
  LS rail monitor (HOT side) and low-side gate drive incl. F6 nodes. The 48 V
  switch nodes exceed the ~30 V guideline; Table 18 functional spacing for
  <= 50 V is well under the 0.2 mm manufacturing floor, so grouping them is
  conservative in practice and recorded here.
- SW_A / SW_B also hold each high-side bias island (transformer secondary,
  rectifier, split, monitor HOT side) and the high-side F6 nodes.
- Line zero-cross resistor-string taps are separate groups (like divider taps); the AC-input
  opto's two LED nodes (LED1, LED2) share one group (they differ by one LED drop).
- Stage 18 (DECISIONS items 7, 18): RES_A is 297 V rms / 656 V pk to earth in normal use at 28 A,
  so its reinforced creepage to SELV/PE at PD3 / IIIa is 12.6 mm (Table 17 x 2, >250-400 V band).
  A last rule raises RES_A to SELV/PE to 12.6 mm clearance and creepage on the OUTER layers only;
  inner-layer copper is embedded in laminate (solid insulation) and keeps the 8.0 mm floor. Every
  other HOT net is <= 250 V rms and keeps 8.0 mm.
"""
import importlib.util
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
UNIT = HERE.parents[1]
spec = importlib.util.spec_from_file_location("wr", UNIT / "tools/write_rules.py")
wr = importlib.util.module_from_spec(spec)
spec.loader.exec_module(wr)
sys.path.insert(0, str(HERE))
from domains import SELV  # noqa: E402

BOARD = UNIT / "native-21/section.kicad_pcb"
RES_A_NETS = {"res_a"}
RES_A_CREEPAGE_MM = 12.6     # IEC 60335-1 Table 17 x 2, PD3, IIIa, >250-400 V (DECISIONS item 7)
nets = wr.board_nets(BOARD.read_text())


def side1_nc(n):
    return re.search(r"\.(iso|verdict)-nc(2|5|6|8)$", n) or n.endswith(("ldo5-nc", "-p2", "-p6", "-p11", "-p12", "-p17", "-p18", "-p19"))


groups = {k: set(v) for k, v in wr.HOT_GROUPS.items()}
# stage 16: the blower-supply tap after F2 is its own group (F2 can open, like AC_L_IN against l_f)
groups["BLW_L"] = {"blw_l", "blw_lr"}   # stage 28: the limiter R130 between them drops < 0.3 V
groups["LOW"] |= {"ocp_kelvin_p", "n_ls", "v24_raw", "bias_sw1", "bias_sw2", "bias_sn1", "bias_sn2",
                  "hot5_ok_hot", "hot5_uv_raw", "hot5_uv_sense", "ocp_kelvin_n",
                  # stage 14: module enable, the LS TPS7A47's NR node and unused ANY-OUT pins (unique names
                  # now that only the LS split has an LDO), and each bias module's primary-side PG pin
                  "bias_ha-en", "bias_hb-en", "ldo_nr", "p2", "p6", "p11", "p12", "p17", "p18", "p19",
                  "bias_ha.iso-p3", "bias_hb.iso-p3",
                  # stage 30 (DECISIONS 33): LS monitor 5 V (feeds the HS-A link and the heartbeat), the HS-A verdict
                  # after its ISO6721FB link, the vote diode's open half, and the heartbeat's LS side
                  "ls_v5", "mon_good_ha", "vote_nc", "hb_tx", "hb_rc", "hb.iso-nc2", "hb.iso-nc5", "hb.iso-nc6",
                  "hb.iso-nc8"}
for n in nets:
    if n in SELV or n in wr.SELV_NC or re.search(r"\.(iso|verdict)-nc(10|11|12|15)$", n):
        continue
    if n.startswith(("bias_ls", "monitor_ls")) or re.match(r"leg_[ab]-(gate_l|out_l|off_l)$", n) \
            or re.match(r"leg_[ab]\.bias_l-damp$", n) or n in ("clk", "ss", "sr", "dc", "en"):
        groups["LOW"].add(n)
    for leg in ("a", "b"):
        if n in (f"p_h{leg}", f"n_h{leg}", f"leg_{leg}-off_h", f"leg_{leg}.bias_h-damp") or \
                (n.startswith(f"bias_h{leg}") and not n.endswith(("_bad", ".iso-p3", "-en"))):
            groups[f"SW_{leg.upper()}"].add(n)
groups["SW_A"] |= {"outa_nc"} & nets   # stage 30: U43's open reverse-channel output (HS-A side 1)
for n in sorted(nets):   # sorted: group order (hence the DRU text) must not follow the hash seed
    if n.startswith("line_zc-") and n not in SELV or n in ("r1mid", "r2mid"):
        groups[f"ZC_{n}"] = {n}
# The VOL628A is an AC-input opto (pins AC1/AC2, f6_parts.ato LineOpto): antiparallel LEDs, so
# LED1 and LED2 never differ by more than one LED drop (< 1.5 V): one potential group.
groups["ZC_led"] = {n for n in ("led1", "led2") if n in nets}
# drop native-20-only nets so the writer's stale check passes; keep groups non-empty
for g in list(groups):
    groups[g] &= nets
    if not groups[g]:
        del groups[g]
wr.HOT_GROUPS = groups
wr.TANK = {"res_a", "crbleed_1", "crbleed_2", "crbleed_3"} & nets
wr.SELV_NC = wr.SELV_NC | {n for n in nets if re.search(r"\.(iso|verdict)-nc(10|11|12|15)$", n)} | \
    {"line_zc.buffer-nc", "leg_a.driver-nc_7", "leg_b.driver-nc_7"}
groups["LOW"] |= {n for n in nets if n in ("outb", "u_hot5_schmitt-nc", "u_ldo-nc", "u_ref-nc")
                  or re.fullmatch(r"u_iso-nc(2|5|6|8)", n)}
wr.SELV_NC |= {n for n in nets if n == "u_bias_flt-nc" or re.fullmatch(r"u_iso-nc(10|11|12|15)", n)}
hot_all = set().union(*groups.values())
for n in nets:
    if side1_nc(n) and n not in hot_all:
        groups.setdefault("LOW", set()).add(n) if n.startswith(("bias_ls", "monitor_ls")) else None
unknown = sorted(nets - SELV - wr.SELV_NC - set().union(*groups.values()) - wr.PE)
if unknown:
    print("UNCLASSIFIED:", unknown)
    sys.exit(1)
if __name__ == "__main__":
    text = wr.rules(BOARD.read_text(), SELV)
    barrier = (SELV | wr.SELV_NC | wr.PE) & nets
    # last rule wins in KiCad, so this follows the SELV/PE floors and every component exception
    text += ('\n(rule "RES_A to SELV/PE: reinforced 12.6 mm, outer layers (stage 18)"\n'
             '  (layer outer)\n'
             f'  (condition "{wr.any_of("A", RES_A_NETS & nets)} && {wr.any_of("B", barrier)}")\n'
             f'  (constraint clearance (min {RES_A_CREEPAGE_MM}mm))\n'
             f'  (constraint creepage (min {RES_A_CREEPAGE_MM}mm)))\n')
    (UNIT / "native-21/section.kicad_dru").write_text(text)
    print("wrote section.kicad_dru:", len(groups), "HOT groups,", len(nets), "nets")
