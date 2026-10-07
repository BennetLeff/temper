"""Native-21 net -> isolation domain (shared by render.py and the rule writer).

SELV: audit.rs SELV_NETS. SW_A / SW_B: nets that ride a switch node (high-side
bias islands, high-side gate drive). MAINS: line-side nets before the bridge
rectifier. HOT: every other HOT net (bus, LS bias, protection, tank).
"""
import re
from pathlib import Path

UNIT = Path(__file__).resolve().parents[2]


def selv_nets():
    t = (UNIT / "audit.rs").read_text()
    body = t[t.index("const SELV_NETS"):]
    body = body[:body.index("];")]
    return set(re.findall(r'"([^"]+)"', body))


SELV = selv_nets()
MAINS_PREFIX = ("ac_l_in", "ac_n_in", "l_f", "n_f", "l_filt", "n_filt", "tco_l", "led1", "led2",
                "line_zc-r", "busbleed")


def domain(net: str) -> str:
    if net in SELV or net.endswith(("-nc10", "-nc11", "-nc12", "-nc15")) or \
            net in ("line_zc.buffer-nc", "u_bias_flt-nc", "leg_a.driver-nc_7", "leg_b.driver-nc_7"):
        return "SELV"
    if net == "pe":
        return "PE"
    for leg, sw, b in (("a", "sw_a", "bias_ha"), ("b", "sw_b", "bias_hb")):
        if net in (sw, f"p_h{leg}", f"n_h{leg}") or (net.startswith(b) and not net.endswith("_bad")) \
                or net in (f"leg_{leg}-gate_h", f"leg_{leg}-out_h", f"leg_{leg}-off_h", f"leg_{leg}.bias_h-damp"):
            return f"SW_{leg.upper()}"
    if net.startswith(MAINS_PREFIX) or net in ("l_mid", "n_mid"):
        return "MAINS"
    return "HOT"
