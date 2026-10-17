#!/usr/bin/env python3
"""BIAS_GOOD boot-sample race (power board s48, B13 H2): mains-on timeline, worst-case margin, and delay-fix sizing.

Run:  python3 -I scripts/bias_race.py            (prints the tables; writes results/bias_race.json next to scripts/)
No inputs, no network. Every number below carries a class tag:
  G = datasheet guaranteed limit (min/max column), T = datasheet typical / characteristic figure,
  C = computed from G parts tolerances, S = committed project simulation, E = estimate (this analysis; bench must confirm).
Times in ms from the event named in each row.
"""
import json
import math
import os

LN = math.log
R = {}  # results


def row(name, lo, typ, hi, cls, src):
    return dict(event=name, min=lo, typ=typ, max=hi, cls=cls, src=src)


# ---------------------------------------------------------------- controller path (PS3 -> J13 -> TPS62933F -> ESP32-S3)
# PS3 MEAN WELL MPM-65-15ST, MPM-65-SPEC p.2: "SETUP, RISE TIME 1000ms, 30ms/115VAC at full load" (one value; read as max).
ps3_setup = row("PS3 setup (AC on -> output starts)", 0.0, None, 1000.0, "G(max only)", "MPM-65-SPEC p.2 SETUP 1000 ms @115 VAC full load; no min")
ps3_rise = row("PS3 rise 0 -> 15 V", 0.0, None, 30.0, "G(max only)", "MPM-65-SPEC p.2 RISE 30 ms")
# U1 TPS62933F EN divider 100 k / 12.1 k (controller.ato, branch controller-c1-crs); VEN_RISE 1.21 typ / 1.28 max (SLUSEA4D 7.5)
ven_typ, ven_max = 1.21, 1.28
vin_on_typ = ven_typ * (1 + 100 / 12.1)
vin_on_max = ven_max * (1 + 100 * 1.01 / (12.1 * 0.99))
# EN crossing inside the 30 ms PS3 ramp (linear ramp to 15 V less a 0.4 V J13 Schottky; E)
t_en_typ = 30.0 * vin_on_typ / 14.6
t_en_max = 30.0 * vin_on_max / 14.6
buck_en = row("PS3 output start -> buck EN (VIN %.1f V typ, %.1f V max)" % (vin_on_typ, vin_on_max), 0.0, t_en_typ, t_en_max, "E",
              "linear 30 ms ramp assumed; light load is faster")
# soft start tSS = CSS * VREF / ISS, CSS 10 nF +/-10 % (CL10B103KB8NNNC), ISS 4.5 / 5.5 / 6.5 uA (SLUSEA4D 7.5, Eq. 6)
tss = [10e-9 * 0.9 * 0.8 / 6.5e-6 * 1e3, 10e-9 * 0.8 / 5.5e-6 * 1e3, 10e-9 * 1.1 * 0.8 / 4.5e-6 * 1e3]
buck_ss = row("buck EN -> v3v3 at 3.3 V (soft start)", *tss, "G+C", "SLUSEA4D Eq.6, ISS 4.5-6.5 uA, CSS 10 nF +/-10 %")
# ESP32-S3 CHIP_PU: 10 k 1 % / 1 uF CL10A105KB8NNNC (X5R 50 V 0603, +/-10 %) from v3v3. Release between VIL_nRST 0.25 VDD
# (earliest possible) and VIH_nRST 0.75 VDD (guaranteed released) (ESP32-S3 datasheet v2.2 Table 5-4).
c_lo = 1e-6 * 0.9 * 0.85 * 0.85     # -10 % tol, -15 % X5R temp, ~-15 % DC bias at 3.3 V (E)
c_typ = 1e-6 * 0.9                  # ~-10 % DC bias (E)
c_hi = 1e-6 * 1.1 * 1.15
tau = [9.9e3 * c_lo, 10e3 * c_typ, 10.1e3 * c_hi]
en_rc = row("v3v3 -> CHIP_PU released (VIH 0.75 VDD)", tau[0] * LN(4) * 1e3, tau[1] * LN(4) * 1e3, tau[2] * LN(4) * 1e3, "C+E",
            "tau = R x C; t = tau ln 4; X5R derating is an estimate")
en_rc_earliest = tau[0] * LN(1 / 0.75) * 1e3  # CHIP_PU may already release at VIL 0.25 VDD
# CHIP_PU -> app_main (the sample is the first statement of app_main, main.c:218)
# Espressif ESP Techpedia "ESP Chip Startup Time Optimization": ESP32-S3, IDF v5.2.1, before optimization 318.8 ms (80 MHz)
# .. 318.7 ms (240 MHz); after optimization 26.9 ms. Measured typical, not a limit. This project keeps every default that
# page removes (bootloader log INFO, app log INFO, image validation on power-on, ROM log on, RTC cal 1024 cycles) and has a
# 411 kB image (build-evidence 0x64680) and a USB-Serial-JTAG console with no host (VFS 50 ms one-shot TX timeout,
# usb_serial_jtag_vfs.c TX_FLUSH_TIMEOUT_US). Range is an estimate around Espressif's typical.
boot = row("CHIP_PU -> first statement of app_main (sample)", 150.0, 318.8, 470.0, "T(typ)+E(range)",
           "Espressif techpedia 318.8 ms default S3; +/- for image size, flash, USJ, logs")
ctrl_after_v3v3 = [en_rc["min"] + boot["min"], en_rc["typ"] + boot["typ"], en_rc["max"] + boot["max"]]

# ---------------------------------------------------------------- power-board SELV side once v3v3 exists
# U32 CA-IS3720HW VDDB UVLO+ 2.375 V max, start-up tSU 15 typ / 40 us max (v1.08 tables); pump design J worst start 10.5 us
# (c24-monitor-fmea results/m1_pump_spice.json, design J, -40 C, VCC2 3.135 V); U40 LVC1G17 ns.
# J4.1 input: BIAS_GOOD -> R146 220 k 1 % -> J4.1 -> 10 k 1 % -> GPIO35, 1 M 1 % and 1 nF C0G (+/-5 %) at the pin
# (CONTROLLER-REQUEST.md addendum 3). Crosses VIH = 0.75 VDD (ESP32-S3 v2.2 Table 5-4).
def j41_t(r146, rs, rpd, c):
    rsrc = r146 + rs
    vf = rpd / (rpd + rsrc)
    t = c * (rsrc * rpd / (rsrc + rpd)) * LN(vf / (vf - 0.75))
    return vf, t * 1e3


vf_typ, t41_typ = j41_t(220e3, 10e3, 1e6, 1e-9)
vf_min, t41_max = j41_t(220e3 * 1.01, 10e3 * 1.01, 1e6 * 0.99, 1.05e-9)
vf_max, t41_min = j41_t(220e3 * 0.99, 10e3 * 0.99, 1e6 * 1.01, 0.95e-9)
bg_after_v3v3 = row("v3v3 >= 2.375 V -> GPIO35 >= VIH (HOT heartbeat already running)",
                    0.015 + t41_min, 0.015 + 0.005 + t41_typ, 0.040 + 0.0105 + t41_max, "G+S+C",
                    "CA-IS3720 tSU <= 40 us; pump J 10.5 us (SPICE); J4.1 RC final %.3f-%.3f x VDD" % (vf_min, vf_max))

# ---------------------------------------------------------------- HOT path (PS2 -> V24_RAW -> LS / HS-A / HS-B -> vote)
ps2_setup = row("PS2 setup (AC on -> output starts)", 0.0, None, 1500.0, "G(max only)", "MPM-20-SPEC 2024-10-30 p.2 SETUP 1500 ms @115 VAC full load; no min")
# LS: U26 TPS7A4700, EN tied to IN, CNR/SS 1 uF: SBVS204G Fig 5-21 "Startup Time = 65 ms, CNR = 1 uF" (typical curve only).
ls_ss = row("PS2 output start -> V15_LS in the LS window (TPS7A47, CNR 1 uF)", 40.0, 65.0, 100.0, "T(typ)+E(range)",
            "SBVS204G Fig 5-21 65 ms; no min/max published")
# HS-A/HS-B: RECOM R24C2T25/R-R UVLO rising 19-21 V, soft start 3 ms; CTRL = 24 V x 27/127 (f6_bias.ato HighBias)
hs_up = row("PS2 output start -> HS P-N up (UVLO 19-21 V on the 30 ms ramp + 3 ms)", 0.0 + 3.0, 30 * 20 / 24 + 3.0, 30 * 21 / 24 + 3.0, "G+E",
            "R24C2T25/R Rev.1-2024 p.4: UVLO 19/20/21 V, soft start 3 ms")
# monitor LDOs U37-U39 TPS70950: EN divider from P, tSTR 500 typ / 1500 us max (SBVS186H 6.5); LM2901 / ISO6721 / LVC1G132 us
mon = row("rail up -> its monitor 5 V and 'good' (TPS70950 tSTR + comparators)", 0.0, 0.5, 1.5, "G", "SBVS186H tSTR <= 1500 us")
hot_chain = [max(ls_ss["min"], hs_up["min"]) + mon["min"], max(ls_ss["typ"], hs_up["typ"]) + mon["typ"],
             max(ls_ss["max"], hs_up["max"]) + mon["max"]]
ctrl_chain = [buck_en["min"] + buck_ss["min"], buck_en["typ"] + buck_ss["typ"], buck_en["max"] + buck_ss["max"]]

# ---------------------------------------------------------------- race
# D = (PS2 setup) - (PS3 setup). BIAS_GOOD reaches VIH at max(T_hot, T_v3v3) + bg_after_v3v3; the sample is at
# T_v3v3 + ctrl_after_v3v3. Win needs D > D_req = ctrl_chain + ctrl_after_v3v3 + t41 - hot_chain.
d_req = dict(
    min=ctrl_chain[0] + ctrl_after_v3v3[0] + bg_after_v3v3["min"] - hot_chain[2],
    typ=ctrl_chain[1] + ctrl_after_v3v3[1] + bg_after_v3v3["typ"] - hot_chain[1],
    max=ctrl_chain[2] + ctrl_after_v3v3[2] + bg_after_v3v3["max"] - hot_chain[0])
d_range_datasheet = (-ps3_setup["max"], ps2_setup["max"])  # setups have no published minimum (0 assumed)
# Worst case: HOT good before v3v3 (any D <= D_req - ctrl_after...): the margin is then independent of D
worst_margin = dict(latest_sample=bg_after_v3v3["max"] - ctrl_after_v3v3[2], typ=bg_after_v3v3["typ"] - ctrl_after_v3v3[1],
                    earliest_sample=bg_after_v3v3["min"] - ctrl_after_v3v3[0],
                    zero_time_firmware=bg_after_v3v3["max"] - en_rc_earliest)


def margin_vs_d(d, k):
    t_v3 = ctrl_chain[k]
    t_hot = d + hot_chain[k]
    t_bg = max(t_hot, t_v3) + [bg_after_v3v3["min"], bg_after_v3v3["typ"], bg_after_v3v3["max"]][k]
    t_s = t_v3 + ctrl_after_v3v3[k]
    return t_bg - t_s


sweep = [(d, round(margin_vs_d(d, 1), 1)) for d in (-1000, -300, 0, 100, 200, 300, 500, 1000, 1500)]

# ---------------------------------------------------------------- fix S: TPS3808G30 on U46.A (gate), referenced to v3v3
# TPS3808 SBVS050N 6.6: td CT = VDD 180/300/420 ms; CT = 180 nF 0.62/1.03/1.44 s; Eq.1 CT(nF) = (tD - 0.5 ms) x 175
# (220 nA into 1.23 V). Other CT: the 180 nF row scaled by C (Eq.1 is linear in C); X7R +/-10 % tolerance, +/-15 %
# temperature, -3 % DC bias at 1.23 V (E). VIT G30 2.79 V +/-1.5 % (Table 4-1, 6.5).
def td_ct(c_nf):
    lo = 0.62 * (c_nf * 0.9 * 0.85 * 0.97) / 180
    ty = c_nf / 175 + 0.0005
    hi = 1.44 * (c_nf * 1.1 * 1.15) / 180
    return lo, ty, hi


sample_after_v3v3_max = ctrl_after_v3v3[2] / 1e3  # s
fix_rows = []
for label, c_nf, line in [("CT = VDD (no cap)", None, "none (CT via 100 k to VDD, existing 0603WAF1003T5E)"),
                          ("CT 100 nF", 100, "CC0603KRX7R9BB104 (existing line)"),
                          ("CT 2 x 100 nF", 200, "CC0603KRX7R9BB104 x 2 (existing line)"),
                          ("CT 330 nF", 330, "CC0603KRX7R8BB334 C107070 (Extended, new line)"),
                          ("CT 470 nF", 470, "CL10B474KA8NNNC C1623 (Basic, new line)"),
                          ("CT 1 uF", 1000, "GRM188R71E105KA12D (existing line)")]:
    lo, ty, hi = (0.180, 0.300, 0.420) if c_nf is None else td_ct(c_nf)
    fix_rows.append(dict(option=label, cap_line=line, td_min_s=round(lo, 3), td_typ_s=round(ty, 3), td_max_s=round(hi, 3),
                         margin_vs_app_main_sample_s=round(lo - sample_after_v3v3_max, 3),
                         margin_vs_bootloader_hook_s=round(lo - (en_rc["max"] + 40.0) / 1e3, 3),
                         readiness_max_s=round(hi + ctrl_chain[2] / 1e3, 2)))
# TPS3808 output on U46.A: VOL <= 0.4 V at 1 mA (SBVS050N 6.5) vs LVC1G132 VT- >= 0.84 V at VCC 3 V (SCES546E 5.5);
# pull-up = existing rgate 10 k (TPS3808 recommends 10 k..1 M); sink 0.35 mA.
vol_ok = 0.4 < 0.84

# ---------------------------------------------------------------- fix R (comparison): RC on U46.A from existing lines
# LVC1G132 VT+ at VCC 3 V 1.50-1.87, 4.5 V 2.16-2.74 (SCES546E 5.5), interpolated to v3v3 3.135-3.465 V; II +/-1 uA.
def vtp(vcc):
    f = (vcc - 3.0) / 1.5
    return 1.50 + f * (2.16 - 1.50), 1.87 + f * (2.74 - 1.87)


rc_rows = []
for r_k, c_u in ((100, 10), (220, 10)):
    lo_v, hi_v = 3.465, 3.135
    vtp_lo, _ = vtp(lo_v)
    _, vtp_hi = vtp(hi_v)
    r_lo, r_hi = r_k * 1e3 * 0.99, r_k * 1e3 * 1.01
    c_lo2, c_hi2 = c_u * 1e-6 * 0.9 * 0.85, c_u * 1e-6 * 1.1 * 1.15
    vf_lo = lo_v + 1e-6 * r_lo            # leakage helping
    vf_hi = hi_v - 1e-6 * r_hi            # leakage against
    tmin = r_lo * c_lo2 * LN(vf_lo / (vf_lo - vtp_lo))
    tmax = r_hi * c_hi2 * LN(vf_hi / (vf_hi - vtp_hi))
    rc_rows.append(dict(rc="%d k / %d uF" % (r_k, c_u), t_min_s=round(tmin, 3), t_max_s=round(tmax, 3),
                        note="excludes reset-diode reverse leakage (BAT54S at hot can be comparable to the charge current)"))

R = dict(
    controller=[ps3_setup, ps3_rise, buck_en, buck_ss, en_rc, boot],
    controller_after_v3v3_ms=[round(x, 1) for x in ctrl_after_v3v3],
    ps3_to_v3v3_ms=[round(x, 2) for x in ctrl_chain],
    selv_bias_good_after_v3v3=bg_after_v3v3,
    j41_final_fraction=dict(min=round(vf_min, 4), typ=round(vf_typ, 4), max=round(vf_max, 4)),
    hot=[ps2_setup, ls_ss, hs_up, mon],
    ps2_to_hot_good_ms=[round(x, 1) for x in hot_chain],
    D_required_ms={k: round(v, 1) for k, v in d_req.items()},
    D_datasheet_range_ms=d_range_datasheet,
    worst_case_margin_ms={k: round(v, 2) for k, v in worst_margin.items()},
    chip_pu_earliest_release_ms=round(en_rc_earliest, 2),
    margin_typ_vs_D=sweep,
    fix_tps3808g30=fix_rows,
    fix_tps3808_vol_ok=vol_ok,
    fix_rc_existing_lines=rc_rows,
)


def fmt(v):
    return "-" if v is None else ("%.2f" % v if abs(v) < 10 else "%.1f" % v)


if __name__ == "__main__":
    print("Controller path (ms)")
    for r in R["controller"]:
        print("  %-62s %8s %8s %8s  %-16s %s" % (r["event"], fmt(r["min"]), fmt(r["typ"]), fmt(r["max"]), r["cls"], r["src"]))
    print("  PS3 output start -> v3v3 up: %s ms; v3v3 -> sample: %s ms" % (R["ps3_to_v3v3_ms"], R["controller_after_v3v3_ms"]))
    print("Power board (ms)")
    b = bg_after_v3v3
    print("  %-62s %8s %8s %8s  %-16s %s" % (b["event"], fmt(b["min"]), fmt(b["typ"]), fmt(b["max"]), b["cls"], b["src"]))
    for r in R["hot"]:
        print("  %-62s %8s %8s %8s  %-16s %s" % (r["event"], fmt(r["min"]), fmt(r["typ"]), fmt(r["max"]), r["cls"], r["src"]))
    print("  PS2 output start -> HOT vote good: %s ms" % R["ps2_to_hot_good_ms"])
    print("Race: win needs D = PS2 setup - PS3 setup > D_req %s ms; datasheets allow D in %s ms" % (R["D_required_ms"], R["D_datasheet_range_ms"]))
    print("  worst-case margin (HOT good before v3v3): %s ms" % R["worst_case_margin_ms"])
    print("  CHIP_PU earliest release (0.25 VDD, fastest RC): %.2f ms" % en_rc_earliest)
    print("  typical-chain margin vs D:", sweep)
    print("Fix S: TPS3808G30 (VIT 2.79 V) RESET -> U46.A, rgate 10 k as pull-up; VOL<=0.4 V < VT- 0.84 V:", vol_ok)
    for f in fix_rows:
        print("  %-18s td %.3f / %.3f / %.3f s  margin(app_main) %+.3f s  margin(bootloader hook) %+.3f s  ready <= %.2f s  [%s]" % (
            f["option"], f["td_min_s"], f["td_typ_s"], f["td_max_s"], f["margin_vs_app_main_sample_s"],
            f["margin_vs_bootloader_hook_s"], f["readiness_max_s"], f["cap_line"]))
    print("Fix R (comparison): RC on U46.A from existing lines")
    for r in rc_rows:
        print("  %s: %.3f .. %.3f s (%s)" % (r["rc"], r["t_min_s"], r["t_max_s"], r["note"]))
    out = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "results")
    os.makedirs(out, exist_ok=True)
    with open(os.path.join(out, "bias_race.json"), "w") as fh:
        json.dump(R, fh, indent=1, default=str)
