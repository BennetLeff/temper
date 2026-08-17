#!/usr/bin/env python3
"""Cross-reference the 2026-08-15 root-cause doc's per-net mechanism
table (M1-M5, appendix A of docs/evidence/2026-08-15-unrouted-nets-
rootcause.md) against this task's fresh 2026-08-17 live measurement
(61/139, .scratch/live-route-summary.json) to see which nets moved
between mechanism classes now that M1/M2/M3 have landed on main.
"""
import json
from pathlib import Path

WT = Path("/home/bennet/Desktop/temper-wt-agent-routing-completeness-recon")

# old doc appendix A: net -> (old_status, old_mechanism)
# old_status in {connected, zone_dependent, broken}
OLD = {
    "+15V": ("broken", "M1"), "+15V_LS": ("broken", "M3(2/3)"),
    "+170V_BUS": ("zone_dependent", "M2+M2b"), "+3V3": ("broken", "M1(+M4)"),
    "DC_BUS_RTN": ("zone_dependent", "M2+M2b"), "DISCHARGE_CTRL": ("connected", "OK"),
    "GATE_HS": ("broken", "M1"), "GATE_LS": ("broken", "M1+M3(2/3)"),
    "I_SENSE": ("broken", "M3(2/7)"), "OCP2_VREF_2V5": ("broken", "M3(2/3)"),
    "PWM_HS": ("broken", "M1"), "PWM_LS": ("broken", "M1"),
    "PWR_RTN": ("zone_dependent", "M2+M2b"), "RELAY_CTRL": ("broken", "M4"),
    "RTD_CS_N": ("broken", "M1"), "RTD_DRDY": ("broken", "M1"),
    "RTD_HW_FAULT": ("broken", "M1"), "RTD_SCK": ("broken", "M4"),
    "RTD_SDI": ("broken", "M1"), "RTD_SDO": ("connected", "OK"),
    "SHUTDOWN": ("broken", "M3(2/6)"), "SW_NODE": ("zone_dependent", "M2+M2b"),
    "V_BUS_SENSE": ("broken", "M1"), "WDT_KICK": ("connected", "OK"),
    "WDT_RESET_N": ("broken", "M1"), "a3": ("connected", "OK(1pad)"),
    "ac_l": ("connected", "OK(1pad)"), "ac_n": ("zone_dependent", "M2+M2b"),
    "b3": ("connected", "OK(1pad)"), "bias": ("broken", "M1"),
    "boot": ("connected", "OK"), "c3": ("connected", "OK(1pad)"),
    "cs_n": ("broken", "M1"), "discharge.k_dis1-coil1": ("broken", "M1"),
    "discharge.k_dis1-coil2": ("broken", "M1"), "discharge.k_dis1-nc": ("broken", "M3(2/4)"),
    "discharge.k_dis1-no": ("connected", "OK"), "discharge.k_dis2-coil1": ("broken", "M1"),
    "discharge.k_dis2-nc": ("broken", "M3(2/4)"), "discharge.k_dis2-no": ("connected", "OK"),
    "discharge.q_dis_drv-g": ("broken", "M3(2/3)"), "discharge.r_dis1a-p2": ("connected", "OK"),
    "discharge.r_dis2a-p2": ("connected", "OK"), "discharge.r_snub1-p2": ("connected", "OK"),
    "discharge.r_snub2-p2": ("broken", "M4"), "en": ("broken", "M3(2/4)"),
    "fb": ("broken", "M4"), "gnd": ("broken", "M4(pour-vs-trace)"),
    "gpio18": ("connected", "OK(1pad)"), "gpio21": ("connected", "OK(1pad)"),
    "gpio35": ("connected", "OK(1pad)"), "gpio36": ("connected", "OK(1pad)"),
    "gpio37": ("connected", "OK(1pad)"), "hb-gnd": ("broken", "M1"),
    "hb.gate_hs.driver-p1": ("connected", "OK"), "hb.gate_hs.driver-p1-1": ("broken", "M3(2/4)"),
    "hb.gate_hs.driver-p2": ("broken", "M3(2/4)"), "hb.power_loop.q_high-g": ("broken", "M3(2/3)"),
    "i2c_scl_ui": ("connected", "OK"), "i2c_sda_ui": ("connected", "OK"),
    "ina": ("broken", "M1"), "inb": ("broken", "M1"), "input": ("connected", "OK"),
    "io0": ("broken", "M3(2/3)"), "io13": ("connected", "OK(1pad)"),
    "io40": ("connected", "OK(1pad)"), "io41": ("connected", "OK(1pad)"),
    "io42": ("connected", "OK(1pad)"), "io45": ("connected", "OK(1pad)"),
    "io46": ("connected", "OK(1pad)"), "io48": ("connected", "OK(1pad)"),
    "nc3": ("connected", "OK(1pad)"), "nc_7": ("connected", "OK(1pad)"),
    "power_in.bypass_relay-coil1": ("broken", "M3(2/3)+M1"),
    "power_in.bypass_relay-coil2": ("broken", "M1"),
    "power_in.ntc-no": ("zone_dependent", "M2+M2b"),
    "power_in.q_relay_drv-g": ("broken", "M4"), "refin_n": ("broken", "M1"),
    "rtd_force_n": ("connected", "OK"), "rtd_force_p": ("connected", "OK"),
    "rtd_pan.high_window-out": ("connected", "OK"), "rtd_pan.low_window-out": ("connected", "OK"),
    "rtd_pan.r_high_top-inp": ("broken", "M3(2/3)"), "rtd_pan.r_low_top-inn": ("broken", "M1"),
    "rtd_pan.rail_monitor-ina_p": ("broken", "M1"), "rtd_pan.rail_monitor-outa": ("broken", "M1"),
    "rtd_pan.rail_monitor-outb": ("connected", "OK(1pad)"), "rtd_sense_n": ("connected", "OK"),
    "rtd_sense_p": ("connected", "OK"), "rx": ("connected", "OK(1pad)"),
    "s1": ("broken", "M4"), "safety-line": ("broken", "M3(2/4)"),
    "safety-line-1": ("broken", "M3(2/3)+M1"), "safety-line-2": ("connected", "OK"),
    "safety-line-3": ("connected", "OK"), "safety.coil_thermal-line": ("broken", "M4"),
    "safety.coil_thermal.comp-inp": ("broken", "M1"), "safety.fault_any_or-a2": ("broken", "M1"),
    "safety.fault_any_or-y2": ("connected", "OK"), "safety.fault_any_or-y3": ("connected", "OK(1pad)"),
    "safety.fault_or-a2": ("connected", "OK"), "safety.fault_or-b2": ("connected", "OK"),
    "safety.fault_or-y2": ("broken", "M4"), "safety.fault_or-y3": ("connected", "OK(1pad)"),
    "safety.fault_or3-b2": ("connected", "OK"), "safety.fault_or3-y2": ("connected", "OK"),
    "safety.fault_or3-y3": ("connected", "OK(1pad)"), "safety.latch-b2": ("connected", "OK"),
    "safety.ocp-line": ("connected", "OK"), "safety.ocp.comp-inn": ("broken", "M3(2/3)"),
    "safety.ocp2-line": ("broken", "M3(2/3)"), "safety.ovp-line": ("broken", "M3(2/3)"),
    "safety.ovp.comp-inp": ("broken", "M3(2/4)"),
    "safety.ovp.r_adc_top1-p2": ("connected", "OK"), "safety.ovp.r_adc_top2-p2": ("connected", "OK"),
    "safety.ovp.r_div_top1-p2": ("connected", "OK"), "safety.ovp.r_div_top2-p2": ("connected", "OK"),
    "safety.thermal-line": ("broken", "M1"), "safety.thermal.comp-inp": ("broken", "M3(2/4)"),
    "safety.uvlo_logic-line": ("broken", "M3(2/4)"), "safety.uvlo_logic.mon-ina_p": ("broken", "M1"),
    "safety.uvlo_logic.mon-outa": ("broken", "M3(2/4)"), "safety.uvlo_logic.mon-outb": ("connected", "OK(1pad)"),
    "sclk": ("broken", "M1"), "sdi": ("broken", "M4"), "sdo": ("broken", "M4"),
    "sw": ("broken", "M1"), "tank-out": ("connected", "OK"),
    "tank.c_tank1-p2": ("zone_dependent", "M2+M2b"), "thermal.j_fan-p1": ("connected", "OK"),
    "tx": ("connected", "OK(1pad)"), "usb_dn": ("connected", "OK(1pad)"),
    "usb_dp": ("connected", "OK(1pad)"), "vbias": ("broken", "M1"),
    "vcc": ("broken", "M1"), "w1_1": ("zone_dependent", "M2+M2b"),
    "w1_2": ("zone_dependent", "M2+M2b"), "y": ("broken", "M3(2/3)"),
    "y1": ("connected", "OK"),
}

d = json.loads((WT / ".scratch" / "live-route-summary.json").read_text())
fully = set(d["fully_connected_nets"])
s = d["net_route_result_summary"]
partial = set(s["partial"])
zone_dep = set(s["zone_dependent"])
failed = set(s["failed"])

def new_status(n):
    if n in fully:
        return "connected"
    if n in partial:
        return "partial"
    if n in zone_dep:
        return "zone_dependent"
    if n in failed:
        return "failed"
    return "MISSING-FROM-NEW-RUN"

all_nets = sorted(set(OLD) | fully | partial | zone_dep | failed)
print(f"{'net':<32} {'old_status':<14} {'old_mech':<20} {'new_status':<14}")
transitions = {}
for n in all_nets:
    old_status, old_mech = OLD.get(n, ("UNKNOWN", "UNKNOWN"))
    ns = new_status(n)
    key = (old_status, ns)
    transitions.setdefault(key, []).append(n)
    print(f"{n:<32} {old_status:<14} {old_mech:<20} {ns:<14}")

print("\n=== TRANSITION SUMMARY ===")
for key, nets in sorted(transitions.items(), key=lambda kv: -len(kv[1])):
    print(f"{key[0]:>14} -> {key[1]:<14} : {len(nets):3d}  {nets if len(nets)<=40 else nets[:5]+['...']}")
