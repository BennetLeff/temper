#!/usr/bin/env python3
"""Derive RTDSensingC1 (sensor-r3 CR-1, DECISIONS C37) from the byte-locked RTDSensing.

The RTD library (`elec/src/modules.ato`) stays byte-identical to the RTD unit's source-04 set
(`verify_controller.py sources`). RTDSensingC1 is that module's text with:
  * the module renamed;
  * EDITS: exact line replacements (each must match exactly once), which move J3, the open-lead
    pull-ups, the window branch and the low-window return to the connector-side sense nodes and
    change c_rtd_input / the pull-up values as CR-1 specifies;
  * C1_SECTION appended: the 2-pole sense filter, the converter-pin CM capacitors, the window
    capacitor and the cable-entry 220 nF + ESD5Z3.3 on every J3 pin.
Everything else (MAX31865, REF2025, window comparators, AND/NAND, TPS3890, SPI resistors, ferrite,
Rref RG2012V-431-W-T1 0.05 % 5 ppm: CR-2) is the library text, byte for byte.

``--check`` proves the committed elec/src/rtd_c1_block.ato equals this transform of the current
library, so the "byte-identical library copy" rule now covers RTDSensingC1 too.

Usage: python3 tools/port_rtd_c1.py [--check]
"""
from __future__ import annotations

import argparse
import hashlib
import sys
from pathlib import Path

UNIT = Path(__file__).resolve().parents[1]
SOURCE = UNIT / "elec/src/modules.ato"
TARGET = UNIT / "elec/src/rtd_c1_block.ato"

IMPORTS = """#pragma experiment("MODULE_TEMPLATING")
#pragma experiment("TRAITS")
import Resistor from "components.ato"
import Capacitor from "components.ato"
import MAX31865 from "components.ato"
import REF2025 from "components.ato"
import TLV3201 from "components.ato"
import TPS3890 from "components.ato"
import SN74LVC1G08 from "components.ato"
import SN74LVC1G38 from "components.ato"
import JST_XH_B4B_XH_A from "components.ato"
import ElectricPower from "generics/interfaces.ato"
import SPI from "generics/interfaces.ato"
import ElectricLogic from "generics/interfaces.ato"
from "controller_parts.ato" import EsdTvs3v3

"""

# (old line, new line): exact, each old line must occur exactly once in the module.
EDITS = [
    ("module RTDSensing:\n", "module RTDSensingC1:\n"),
    # C1 (CR-1): the connector-side and filter mid nodes, declared before the library lines use them
    ("    rtd_sense_n.required = true\n",
     "    rtd_sense_n.required = true\n"
     "    # C1 (CR-1): J3.2 / J3.3 land here; rtd_sense_p/n stay the converter pins (adc.RTDIN_P/N)\n"
     "    signal rtd_sense_p_ext\n"
     "    signal rtd_sense_n_ext\n"
     "    signal rtd_sense_p_mid\n"
     "    signal rtd_sense_n_mid\n"),
    # Mark the two library comments this block supersedes (they describe the 1 nF / 1 M design)
    ("    c_rtd_input = new Capacitor\n",
     "    # C1 (CR-1): the comment above is the library's 1 nF / 1 M design. This block uses 100 nF C0G\n"
     "    # here, the 2-pole filter and 499 k connector-side pull-ups below (open lead caught in\n"
     "    # <= 33 ms by comparator crossing, evidence/sensor-r3-checks).\n"
     "    c_rtd_input = new Capacitor\n"),
    ("    r_rtdin_p_bias = new Resistor\n",
     "    # C1 (CR-1): 499 k 1 %, on the connector-side node rtd_sense_p_ext (not the converter pin).\n"
     "    r_rtdin_p_bias = new Resistor\n"),
    # C51: MAX31865AAP is the 5.3 mm SSOP-20 (JLC C779509 / C89608: L7.2 W5.3 P0.65 LS7.8); the library's
    # 3.9 mm QSOP land does not meet its leads. +T is the tape-and-reel code of the same part.
    ("    adc = new MAX31865\n",
     "    adc = new MAX31865\n"
     "    # C51: 5.3 mm SSOP-20 land and the tape-and-reel MPN (tools/check_land_patterns.py)\n"
     '    adc.mpn = "MAX31865AAP+T"\n'
     '    adc.footprint = "Package_SO:SSOP-20_5.3x7.2mm_P0.65mm"\n'),
    # CR-1: 100 nF C0G 1206 across the converter pins (was 1 nF 0603)
    ("    c_rtd_input.value = 1nF\n", "    c_rtd_input.value = 100nF +/- 5%\n"),
    ('    c_rtd_input.mpn = "C0603C102J5GACTU"\n', '    c_rtd_input.mpn = "GRM31C5C1H104JA01L"\n'),
    ('    c_rtd_input.footprint = "Capacitor_SMD:C_0603_1608Metric"\n',
     '    c_rtd_input.footprint = "Capacitor_SMD:C_1206_3216Metric"\n'),
    # CR-1: open-lead pull-ups 499 k 1 %, on the connector side (no DC across the filter)
    ("    r_rtdin_p_bias.value = 1Mohm +/- 5%\n", "    r_rtdin_p_bias.value = 499kohm +/- 1%\n"),
    ('    r_rtdin_p_bias.mpn = "RC0603JR-071ML"\n', '    r_rtdin_p_bias.mpn = "RC0603FR-07499KL"\n'),
    ("    adc.RTDIN_P ~ r_rtdin_p_bias.p1\n", "    rtd_sense_p_ext ~ r_rtdin_p_bias.p1\n"),
    ("    r_rtdin_n_bias.value = 1Mohm +/- 5%\n", "    r_rtdin_n_bias.value = 499kohm +/- 1%\n"),
    ('    r_rtdin_n_bias.mpn = "RC0603JR-071ML"\n', '    r_rtdin_n_bias.mpn = "RC0603FR-07499KL"\n'),
    ("    adc.RTDIN_N ~ r_rtdin_n_bias.p1\n", "    rtd_sense_n_ext ~ r_rtdin_n_bias.p1\n"),
    # CR-1: window / runaway branch and the low-window return tap the connector side
    ("    adc.RTDIN_P ~ r_window_sense_p.p1\n", "    rtd_sense_p_ext ~ r_window_sense_p.p1\n"),
    ("    r_low_bottom.p2 ~ adc.RTDIN_N\n", "    r_low_bottom.p2 ~ rtd_sense_n_ext\n"),
    # CR-1: J3 lands on the connector-side sense nodes (pinout unchanged)
    ("    j_rtd1.p2 ~ rtd_sense_p   # Sense+ = MAX31865 RTDIN+\n",
     "    j_rtd1.p2 ~ rtd_sense_p_ext   # Sense+ -> 2-pole filter -> MAX31865 RTDIN+ (C1 CR-1)\n"),
    ("    j_rtd1.p3 ~ rtd_sense_n   # Sense- = MAX31865 RTDIN-\n",
     "    j_rtd1.p3 ~ rtd_sense_n_ext   # Sense- -> 2-pole filter -> MAX31865 RTDIN- (C1 CR-1)\n"),
]

C1_SECTION = '''
    # ---- sensor-r3 CR-1 (DECISIONS C37): C1 cartridge front end -----------------------------
    # Generated by tools/port_rtd_c1.py. Numbers: evidence/sensor-r3-checks (checks.py on the
    # as-built values). rtd_sense_p/n stay the converter-pin nets (== adc.RTDIN_P/N); J3 now
    # lands on rtd_sense_p_ext / rtd_sense_n_ext (declared at the top of the module).

    # 2-pole differential filter: 1.00 k / 100 nF C0G across the pair / 1.00 k / 100 nF C0G
    # (c_rtd_input) across RTDIN+-; no series R in FORCE+/- (it would move the runaway trip).
    r_s1p = new Resistor
    r_s1p.value = 1kohm +/- 0.1%
    r_s1p.mpn = "RT0603BRD071KL"
    rtd_sense_p_ext ~ r_s1p.p1
    r_s1p.p2 ~ rtd_sense_p_mid
    r_s1n = new Resistor
    r_s1n.value = 1kohm +/- 0.1%
    r_s1n.mpn = "RT0603BRD071KL"
    rtd_sense_n_ext ~ r_s1n.p1
    r_s1n.p2 ~ rtd_sense_n_mid
    c_s1 = new Capacitor
    c_s1.value = 100nF +/- 5%
    c_s1.dielectric = "C0G"
    c_s1.voltage_rating = 50V
    c_s1.mpn = "GRM31C5C1H104JA01L"
    c_s1.footprint = "Capacitor_SMD:C_1206_3216Metric"
    rtd_sense_p_mid ~ c_s1.p1
    c_s1.p2 ~ rtd_sense_n_mid
    r_s2p = new Resistor
    r_s2p.value = 1kohm +/- 0.1%
    r_s2p.mpn = "RT0603BRD071KL"
    rtd_sense_p_mid ~ r_s2p.p1
    r_s2p.p2 ~ rtd_sense_p
    r_s2n = new Resistor
    r_s2n.value = 1kohm +/- 0.1%
    r_s2n.mpn = "RT0603BRD071KL"
    rtd_sense_n_mid ~ r_s2n.p1
    r_s2n.p2 ~ rtd_sense_n

    # 1 nF C0G from each converter pin to ground (common mode)
    c_cm_p = new Capacitor
    c_cm_p.value = 1nF +/- 5%
    c_cm_p.dielectric = "C0G"
    c_cm_p.voltage_rating = 50V
    c_cm_p.mpn = "C0603C102J5GACTU"
    adc.RTDIN_P ~ c_cm_p.p1
    c_cm_p.p2 ~ power.gnd
    c_cm_n = new Capacitor
    c_cm_n.value = 1nF +/- 5%
    c_cm_n.dielectric = "C0G"
    c_cm_n.voltage_rating = 50V
    c_cm_n.mpn = "C0603C102J5GACTU"
    adc.RTDIN_N ~ c_cm_n.p1
    c_cm_n.p2 ~ power.gnd

    # Window / runaway node: 10 nF C0G to ground, tau 1 ms with the 100 k branch
    c_window = new Capacitor
    c_window.value = 10nF +/- 5%
    c_window.dielectric = "C0G"
    c_window.voltage_rating = 50V
    c_window.mpn = "GRM1885C1H103JA01D"
    window_rtdin_p ~ c_window.p1
    c_window.p2 ~ power.gnd

    # Cable entry, every J3 pin: 220 nF X7R + ESD5Z3.3 to ground (each within 3 mm of its pad)
    c_j_fp = new Capacitor
    c_j_fp.value = 220nF +/- 10%
    c_j_fp.dielectric = "X7R"
    c_j_fp.voltage_rating = 50V
    c_j_fp.mpn = "CC0603KRX7R9BB224"
    rtd_force_p ~ c_j_fp.p1
    c_j_fp.p2 ~ power.gnd
    c_j_sp = new Capacitor
    c_j_sp.value = 220nF +/- 10%
    c_j_sp.dielectric = "X7R"
    c_j_sp.voltage_rating = 50V
    c_j_sp.mpn = "CC0603KRX7R9BB224"
    rtd_sense_p_ext ~ c_j_sp.p1
    c_j_sp.p2 ~ power.gnd
    c_j_sn = new Capacitor
    c_j_sn.value = 220nF +/- 10%
    c_j_sn.dielectric = "X7R"
    c_j_sn.voltage_rating = 50V
    c_j_sn.mpn = "CC0603KRX7R9BB224"
    rtd_sense_n_ext ~ c_j_sn.p1
    c_j_sn.p2 ~ power.gnd
    c_j_fn = new Capacitor
    c_j_fn.value = 220nF +/- 10%
    c_j_fn.dielectric = "X7R"
    c_j_fn.voltage_rating = 50V
    c_j_fn.mpn = "CC0603KRX7R9BB224"
    rtd_force_n ~ c_j_fn.p1
    c_j_fn.p2 ~ power.gnd
    d_j_fp = new EsdTvs3v3
    rtd_force_p ~ d_j_fp.K
    d_j_fp.A ~ power.gnd
    d_j_sp = new EsdTvs3v3
    rtd_sense_p_ext ~ d_j_sp.K
    d_j_sp.A ~ power.gnd
    d_j_sn = new EsdTvs3v3
    rtd_sense_n_ext ~ d_j_sn.K
    d_j_sn.A ~ power.gnd
    d_j_fn = new EsdTvs3v3
    rtd_force_n ~ d_j_fn.K
    d_j_fn.A ~ power.gnd
'''

HEADER = (
    "# GENERATED for zapote/controller by tools/port_rtd_c1.py from elec/src/modules.ato RTDSensing\n"
    "# (library sha256 {sha}; module text sha256 {msha}). sensor-r3 CR-1 / CR-2\n"
    "# (DECISIONS C37): {n} exact line edits plus the appended C1 section. Do not edit by hand.\n"
)


def module_text(lib: str) -> str:
    lines = lib.splitlines(keepends=True)
    start = lines.index("module RTDSensing:\n")
    end = start + 1
    while end < len(lines) and not lines[end].startswith(("module ", "component ", "interface ")):
        end += 1
    while lines[end - 1].strip() == "":
        end -= 1
    return "".join(lines[start:end])


def derive() -> str:
    lib = SOURCE.read_text(encoding="utf-8")
    mod = module_text(lib)
    for old, new in EDITS:
        n = mod.count(old)
        if n != 1:
            raise SystemExit(f"edit anchor occurs {n}x (want 1): {old!r}")
        mod = mod.replace(old, new)
    header = HEADER.format(sha=hashlib.sha256(lib.encode()).hexdigest(),
                           msha=hashlib.sha256(module_text(lib).encode()).hexdigest(), n=len(EDITS))
    return header + IMPORTS + mod + C1_SECTION


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args()
    text = derive()
    if a.check:
        ok = TARGET.exists() and TARGET.read_text(encoding="utf-8") == text
        print(f"rtd_c1: {'OK' if ok else 'DIFFERS'} ({len(EDITS)} edits + C1 section)")
        return 0 if ok else 1
    TARGET.write_text(text, encoding="utf-8")
    print(f"wrote {TARGET.relative_to(UNIT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
