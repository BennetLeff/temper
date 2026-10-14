#!/usr/bin/env python3
"""Derived stresses and digitised datasheet limits for the 2026-10-13 datasheet-gap pass (stdlib only).

Run: python3 -I native-21/verification/datasheet-ledger/scripts/datasheet_gap_calcs.py
Covers ledger entries TMOV20RP175E (RV1), B82726S2203A020 (L1), AMC1311BDWVR (U4), R24C2T25/R-R (U41/U42)
and ISO7710DWR (U9, U32-U34). Every input is a repo value (file:line in the comment) or a datasheet
value (document, page). Curve points were digitised from 300-500 dpi renders of the vendor PDFs and are
read to about +/-3 % of full scale; the ledger states that where they set a limit.
"""
import math

# ---- common inputs ---------------------------------------------------------------------------------
LINE_HI_VRMS = 139.7          # 127 V + 10 % (DECISIONS.md:306)
BUS_CREST_V = 198.0           # 127 V + 10 % crest (ALT-D3.md:60)
BUS_OVP_CORNER_V = 286.0      # static OVP corner (ALT-D3.md:60)
LINE_HI_VPK = LINE_HI_VRMS * math.sqrt(2)

# ---- U4 AMC1311B: bus divider 4 x 470 k over 15.8 k (elec/src/power_stage_120v.ato, r_div1..r_div4 / r_div_bot) --------
K_DIV = 15.8e3 / (4 * 470e3 + 15.8e3)
AMC_VFSR_MAX = 2.0            # SBAS786C p.6 Recommended operating conditions, VFSR max
AMC_VCLIP = 2.516             # SBAS786C p.6, VClipping typ
VSENSE_AT_CREST = BUS_CREST_V * K_DIV
VSENSE_AT_OVP = BUS_OVP_CORNER_V * K_DIV
BUS_AT_LINEAR_LIMIT = AMC_VFSR_MAX / K_DIV
BUS_AT_CLIP = AMC_VCLIP / K_DIV
# firmware marks VBUS over-range at 1210 mV ADC (firmware n21_signal.h N21_VBUS_OVERRANGE_MV, bias 0.24777 V,
# gain 0.5 x K_DIV): the controller stops trusting VBUS below the AMC1311 linear limit.
FW_OVERRANGE_BUS = (1.210 - 0.2477700693756194) / (0.5 * K_DIV)

# ---- L1 TDK B82726S2203A020: Iop/IR vs TA (datasheet 5/26 p.5, IND0372-K-E), IR = 20 A at TR = 60 C ---
L1_IR = 20.0
L1_DERATE = [(60, 1.00), (65, 0.964), (67, 0.945), (70, 0.916), (75, 0.865), (78, 0.834), (80, 0.809),
             (85, 0.754), (90, 0.690), (100, 0.543), (110, 0.365), (120, 0.160), (125.6, 0.0)]


def l1_iop(ta):
    if ta <= 60:
        return L1_IR  # curve sits above 1.0 below TR; 1.0 is used
    for (t0, k0), (t1, k1) in zip(L1_DERATE, L1_DERATE[1:]):
        if t0 <= ta <= t1:
            return L1_IR * (k0 + (k1 - k0) * (ta - t0) / (t1 - t0))
    return 0.0


def l1_max_ta(i_a, max_ratio):
    """Highest ambient at which i_a <= max_ratio * Iop(TA)."""
    t = 60.0
    while t < 125.6 and i_a <= max_ratio * l1_iop(t + 0.1):
        t += 0.1
    return round(t, 1)


# ---- RV1 Littelfuse TMOV20RP175E (TMOV/iTMOV datasheet rev. 09/14/17) --------------------------------
# p.2 row TMOV20RP175E: 175 Vrms, 225 VDC, 135 J (2 ms), ITM 10,000 A 1x / 6,500 A 2x (8/20, 85 C),
# V1mA 243-297 V, Vc 455 V at 100 A, 1400 pF. Figure 6 (p.4, 20 mm repetitive surge), at 20 us duration:
TMOV_REP_20US = {1: 10000, 2: 6500, 15: 4870, 100: 1310, 1000: 700}
MOV_SURGE_MAX_A = 750.0        # ALT-D3.md:119 (245-750 A, any clamp fitted)

# ---- U41/U42 RECOM R24C2T25/R (Rev. 1-2024 p.3 derating, note 6: 2 W average, 2.5 W for 5 s) ---------
# Drawn line: 2.5 W at ~73 C -> 1.5 W at 100 C -> ~0.6 W at 125 C; RECOM labels the 2 W knee 82 C. The
# conservative straight line through the labelled points (82 C, 2.0 W) and (100 C, 1.5 W) is used.
RECOM_P_ALLOC_W = 1.71         # ALT-BIAS.md:164


def recom_pmax(ta):
    if ta <= 82:
        return 2.0
    return 2.0 - (2.0 - 1.5) * (ta - 82) / (100 - 82)


def recom_max_ta(p_w, max_ratio):
    t = 82.0
    while t < 125 and p_w <= max_ratio * recom_pmax(t + 0.1):
        t += 0.1
    return round(t, 1)


# ---- ISO7710 crossings: CMTI event and filter (validation-results/06-controller-interface/cmti/README.md:36-38)
CMTI_EDGE_V_PER_NS = 95.0
SWING_V = 520.0
EVENT_NS = SWING_V / CMTI_EDGE_V_PER_NS            # 5.47 ns
BIAS_FILTER_LONGEST_REJECTED_NS = 5950.0          # README.md:37 (10 k x 1 nF into SN74LVC1G17)


def main():
    print(f"line high corner peak: {LINE_HI_VPK:.1f} V")
    print(f"U4 divider K = 1/{1 / K_DIV:.2f}; VSENSE {VSENSE_AT_CREST:.4f} V at {BUS_CREST_V} V, "
          f"{VSENSE_AT_OVP:.4f} V at {BUS_OVP_CORNER_V} V")
    print(f"U4 linear limit at bus {BUS_AT_LINEAR_LIMIT:.1f} V, clipping at {BUS_AT_CLIP:.1f} V, "
          f"firmware over-range at {FW_OVERRANGE_BUS:.1f} V")
    for ta in (50, 60, 67, 70, 78, 85):
        print(f"L1 Iop({ta} C) = {l1_iop(ta):.2f} A")
    for i in (13.5, 15.0, 16.5):
        print(f"L1 {i} A: max TA at 80 % {l1_max_ta(i, 0.8)} C, at 100 % {l1_max_ta(i, 1.0)} C")
    for n, a in TMOV_REP_20US.items():
        print(f"RV1 {n} pulses at 20 us: {a} A -> 750 A is {MOV_SURGE_MAX_A / a:.4f}")
    print(f"U41/U42 1.71 W: max TA at 90 % rule {recom_max_ta(RECOM_P_ALLOC_W, 0.9)} C, "
          f"at 100 % {recom_max_ta(RECOM_P_ALLOC_W, 1.0)} C")
    print(f"CMTI event {EVENT_NS:.2f} ns; U32-U34 filter rejects <= {BIAS_FILTER_LONGEST_REJECTED_NS} ns "
          f"(ratio {EVENT_NS / BIAS_FILTER_LONGEST_REJECTED_NS:.5f})")


if __name__ == "__main__":
    main()
