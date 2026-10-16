"""Own dissipation of every part on the 73 unrated BOM lines (W per ref), from the s47 circuit (elec/src/*.ato, read only)
and the B3 heat basis. Every value is a bound or a stated operating point; the basis string says which.

Constants mirror b3_ratings_gate.py (V_PN, V_SPLIT) and b3/make_heat_sources.py (Q_DECK, Q_CGS_EXTRA, F_WIN, R_BR, I_CH).
"""
V_PN = 17.0 * 1.03                    # b3_ratings_gate.V_PN: span rail bound (p - n)
V_SPLIT = 1.24 * (1 + 6.2 / 10.0)     # b3_ratings_gate.V_SPLIT: src - n = 2.01 V
V_HI = V_PN - V_SPLIT                 # gate-on level, p - src = 15.5 V
V33, V5, V24 = 3.3 * 1.05, 5.15, 24.0 * 1.05
F_WIN = 60e3                          # make_heat_sources.F_WIN (60 kHz control-window top)
Q_EDGE = 382.6e-9 + 61e-9             # Q_DECK + Q_CGS_EXTRA[4.7 nF], per FET per edge
R_ON, R_BR = 68.0, 1.0 + 0.1          # turn-on 68 ohm 2512; PMEG branch 1 ohm + 0.1 ohm (make_heat_sources.R_BR)
I_CH = Q_EDGE * F_WIN + 0.0044 + 0.003 + 0.0015 + 0.014    # make_heat_sources.I_CH, per channel (A)


def pmeg_w(vf):
    """PMEG6030EP turn-off diode: the turn-off charge share through the diode branch x VF x f."""
    share = R_ON / (R_ON + R_BR)
    return Q_EDGE * share * F_WIN * vf


def r_w(v, ohm):
    return v * v / ohm


def resistor_powers():
    P = {}
    def put(refs, w, basis):
        for r in refs:
            P[r] = (w, basis)
    put(["R1", "R2"], 0.0493, "ledger stress: 69.85 V rms over 99 k (1206W4F1003T5E entry)")
    put(["R3", "R4"], 0.093, "ledger stress: 143 V^2 / 220 k at the 286 V static OVP (RC1206FR-07220KL entry)")
    put(["R130"], 0.302, "ledger stress: 1.42 A PS3 input x 0.15 ohm (AC05 entry)")
    put(["R6", "R14"], 1e-7, "100 ohm series into the NAND input (R7 100 k to ground): 33 uA -> 0.1 uW")
    put(["R7", "R15"], r_w(V33, 100e3), "3.47 V over 100 k")
    put(["R62", "R128"], r_w(V24 * 100 / 127, 100e3), "EN divider 100 k / 27 k from V24_RAW 25.2 V: 19.8 V over 100 k")
    put(["R127", "R129"], r_w(V24 * 27 / 127, 27e3), "EN divider bottom: 5.36 V over 27 k")
    put(["R9", "R17", "R133"], r_w(V33, 49.9e3), "bound: 3.47 V over 49.9 k (DT pin / hold node <= 3.3 V rail)")
    i_rms = 2 * I_CH
    put(["R51", "R52", "R55", "R56"], i_rms ** 2 * 0.68,
        f"bias damp: channel current {I_CH * 1e3:.1f} mA mean (make_heat_sources I_CH), RMS bounded at 2x mean")
    put(["R71", "R72", "R74", "R75"], r_w(V_HI, 4990.0),
        f"split bleed p -> src: (V_PN - V_SPLIT) = {V_HI:.2f} V over 4.99 k (b3_ratings_gate MONITOR_SELF['tlvh431'] basis)")
    put(["R131"], r_w(V5, 4990.0), "heartbeat RC: bound 5.15 V over 4.99 k at full duty")
    put(["R73", "R76", "R135"], r_w(V33, 10e3), "3.47 V pull-up over 10 k (output low)")
    put(["R11", "R13", "R19", "R21"], 0.5 * r_w(V_HI, 10e3) + 0.5 * r_w(V_SPLIT, 10e3),
        f"gate-source hold-off: {V_HI:.2f} V on / -{V_SPLIT:.2f} V off at <= 50 % on-duty (half-bridge, each FET)")
    put(["R91", "R109", "R124"], r_w(V5, 10e3), "good pull-up, 5.15 V over 10 k (fault state)")
    put(["R30"], 1e-6, "Kelvin sense series into the comparator input: uA")
    put(["R31"], r_w(V5 - 2.4838, 5600 * 0.99), "REF25 bias: (5.15 - 2.484) V over 5.54 k")
    # stage 49 (S23 B'-1.02 V, c49-c34-bank): R32 10 k + R33 7.5 k from REF25 to ocp_kelvin_n (bounded at -0.2 V, the
    # ledger49.py shunt bound), R34 16 k + R35 11 k from REF25; was 10 k + 10 k and 12.6 k + 11.7 k
    i_ocp = (2.5162 + 0.2) / 17.5e3
    put(["R32"], i_ocp ** 2 * 10e3, "OCP divider 10 k + 7.5 k: (REF25 2.5162 V + 0.2 V shunt bound) over 17.5 k")
    put(["R33"], i_ocp ** 2 * 7.5e3, "OCP divider 10 k + 7.5 k: (REF25 2.5162 V + 0.2 V shunt bound) over 17.5 k")
    i_ovp = 2.5162 / 150e3
    put(["R36"], i_ovp ** 2 * 10e3, "OVP divider 10 k + 140 k from REF25")
    put(["R37"], i_ovp ** 2 * 140e3, "OVP divider 10 k + 140 k from REF25")
    i_th = 2.5162 / 27e3
    put(["R34"], i_th ** 2 * 16e3, "OCP threshold 16 k + 11 k from REF25 2.5162 V max")
    put(["R35"], i_th ** 2 * 11e3, "OCP threshold 16 k + 11 k from REF25 2.5162 V max")
    i_ct = V33 / 12.21e3
    put(["R44", "R45"], i_ct ** 2 * 10e3, "CT reference 2.21 k + 10 k across 3.47 V")
    put(["R43", "R46"], i_ct ** 2 * 2.21e3, "CT reference 2.21 k + 10 k across 3.47 V")
    i_uv = V5 / 115e3
    put(["R48"], i_uv ** 2 * 105e3, "HOT5 UV divider 105 k + 10 k")
    put(["R49"], i_uv ** 2 * 10e3, "HOT5 UV divider 105 k + 10 k")
    put(["R50"], r_w(V5, 10e3), "bound: 5.15 V over 10 k")
    # monitor and split dividers on the s47 values (the gate's MON_R table still has the s42 values, see results.md)
    put(["R77", "R95", "R110"], r_w(V_SPLIT - 1.24, 6.2e3), "split feedback top: src - fb = 0.77 V over 6.2 k")
    put(["R78", "R96", "R111"], r_w(1.24, 10e3), "split feedback bottom: 1.24 V over 10 k")
    i_h = 2.495 / 14.42e3
    put(["R79", "R97", "R112"], i_h ** 2 * 4.42e3, "halfref 4.42 k + 10 k across Vref 2.495 V")
    put(["R80", "R98", "R113"], i_h ** 2 * 10e3, "halfref 4.42 k + 10 k across Vref 2.495 V")
    i_u = V_SPLIT / 10.75e3
    put(["R81", "R99", "R114"], i_u ** 2 * 750, "neg-UV tap 750 + 10 k across V_SPLIT 2.01 V")
    put(["R82", "R100", "R115"], i_u ** 2 * 10e3, "neg-UV tap 750 + 10 k across V_SPLIT 2.01 V")
    i_o = V_SPLIT / 12.94e3
    put(["R83", "R101", "R116"], i_o ** 2 * 2.94e3, "neg-OV tap 2.94 k + 10 k across V_SPLIT 2.01 V")
    put(["R84", "R102", "R117"], i_o ** 2 * 10e3, "neg-OV tap 2.94 k + 10 k across V_SPLIT 2.01 V")
    i_su = V_PN / 101.9e3
    put(["R85", "R103", "R118"], i_su ** 2 * 90.9e3, "span-UV 90.9 k + 11 k across V_PN 17.51 V")
    put(["R86", "R104", "R119"], i_su ** 2 * 11e3, "span-UV 90.9 k + 11 k across V_PN 17.51 V")
    i_so = V_PN / 115e3
    put(["R87", "R105", "R120"], i_so ** 2 * 104e3, "span-OV 104 k + 11 k across V_PN 17.51 V")
    put(["R88", "R106", "R121"], i_so ** 2 * 11e3, "span-OV 104 k + 11 k across V_PN 17.51 V")
    i_fb = V_PN / 74.4e3
    put(["R92", "R94"], i_fb ** 2 * 63.4e3, "HS module feedback 63.4 k + 11 k across V_PN 17.51 V (bound)")
    put(["R93", "R61"], i_fb ** 2 * 11e3, "HS module feedback 63.4 k + 11 k across V_PN 17.51 V (bound)")
    put(["R59", "R63", "R65"], r_w(V_PN - 2.495, 2200.0), "TL431 reference feed: (V_PN - Vref) over 2.2 k (b3 gate row value)")
    put(["R38"], 0.0, "0 ohm PE-SELV link: no current in operation (functional bond)")
    put(["R40", "R41"], r_w(V33 / 2, 1e3), "CT bias midpoint 1 k / 1 k across 3.47 V")
    put(["R42", "R47"], r_w(1.25, 1e3), "CT sense series 1 k: bound 1.25 V (burden peak at the 29.4 A trip) across it")
    put(["R134"], 1e-4, "logic series 1 k into an RC filter: transient only")
    put(["R132"], 0.0113 ** 2 * 220, "heartbeat pump: the 11.3 mA SPICE peak (ledger BAT54S) taken as RMS, bound")
    put(["R125"], r_w(V33, 33e3), "ZC pull-up 3.47 V over 33 k")
    # stage 48 (c48-ldo-en-ref-watch; the s48 re-base): the LDO EN dividers 100 k / 27 k, bounded at the span-OV corner
    # IN (U3 16.68 V, U37-U39 18.643 V: ledger48.py LDOS), the REF25 watchdog 63.4 k + 11.7 k at VR max 2.5162 V, and R146
    # 220 k with J4.1 shorted to selv_gnd at 3.6 V (audit.rs stage48)
    put(["R136"], r_w(16.68 * 100 / 127, 100e3), "U3 EN divider top: 13.13 V over 100 k (IN 16.68 V, span-OV corner)")
    put(["R137"], r_w(16.68 * 27 / 127, 27e3), "U3 EN divider bottom: 3.55 V over 27 k (IN 16.68 V)")
    put(["R138", "R140", "R142"], r_w(18.643 * 100 / 127, 100e3),
        "monitor LDO EN divider top: 14.68 V over 100 k (IN 18.643 V, span-OV corner)")
    put(["R139", "R141", "R143"], r_w(18.643 * 27 / 127, 27e3), "monitor LDO EN divider bottom: 3.96 V over 27 k")
    i_wd = 2.5162 / 75.1e3
    put(["R144"], i_wd ** 2 * 63.4e3, "REF25 watchdog 63.4 k + 11.7 k from REF25 2.5162 V max")
    put(["R145"], i_wd ** 2 * 11.7e3, "REF25 watchdog 63.4 k + 11.7 k from REF25 2.5162 V max")
    put(["R146"], r_w(3.6, 220e3), "BIAS_GOOD readback: 3.6 V over 220 k (J4.1 shorted to selv_gnd)")
    return P


def ic_powers(ds):
    """ICs and diodes without a B3 body model. ds: datasheet numbers (see ratings_table)."""
    P = {}
    def put(refs, w, basis):
        for r in refs:
            P[r] = (w, basis)
    put(["U22", "U23", "U8", "U13", "U15", "U24", "U40"], ds["lvc_icc_w"], "LVC1G static ICC x VCC + output into CMOS/10 k loads (bound)")
    put(["U45", "U46"], 5e-3, "heartbeat oscillator / pump driver: Cpd V^2 f + the pump load (bound 5 mW)")
    put(["U6", "U7", "U10", "U11", "U12"], ds["tlv3201_w"], "TLV3201 IQ max x 5.15 V")
    put(["U14"], ds["tps3700_w"], "TPS3700 IDD max x supply")
    put(["U4"], ds["amc1311_w"], "AMC1311 IDD1 max x 5.15 V + IDD2 max x 3.47 V")
    put(["U43", "U44"], ds["iso6721_w"], "ISO6721 ICC1 + ICC2 max at 5.5 V (bound)")
    put(["U9", "U32"], ds["cais3720_w"], "CA-IS3720 IDD1 + IDD2 max x supply")
    put(["U36"], ds["vol628a_w"], "VOL628A LED: 2.1 mA RMS (140 V over 4 x 16.5 k) x VF max; transistor side negligible")
    put(["D6", "D7", "D8", "D9"], pmeg_w(ds["pmeg_vf"]),
        f"turn-off charge {Q_EDGE * 1e9:.1f} nC x {R_ON / (R_ON + R_BR):.3f} branch share x 60 kHz x VF {ds['pmeg_vf']} V")
    put(["D18", "D20"], 0.5e-3 * 0.4, "LS good-node pull-down: <= 0.5 mA (10 k from 5 V) x 0.4 V")
    put(["D19"], 0.5 * 0.0113 * 0.5, "heartbeat pump: 11.3 mA peak, mean <= half, x VF 0.5 V (bound)")
    put(["D4", "D5"], 1e-5, "CT clamp: no conduction in operation (leakage only)")
    put(["D3", "D17"], 143 * 5e-6, "TVS standby: 143 V x IR 5 uA at VRWM (ledger stress basis)")
    return P
