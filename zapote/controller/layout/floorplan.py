"""Floorplan (R33): explicit poses for connectors, ICs and the power stages, plus anchor rules for passives.

World mm (layout/world.py holds every enclosure-owned number; the connector, J4 and WROOM poses
below are read from it, so an enclosure revision is one edit there). Each explicit entry is
(X, Y, rotation_deg[, "fab"|"crtyd"]): by default (X, Y) is the footprint origin (the body centre
for every SMD part used here); "fab" places the F.Fab outline centre there (connector centres)
and "crtyd" the courtyard centre (J4's body envelope). Everything not listed is a passive placed
by layout/build_board.py next to its anchor pin (ANCHOR below, else the IC/connector pin on its
most specific net).

Keys are atopile instance paths (the footprint's SourceInstance field), except connectors and the
module, whose designators are fixed in elec/src/controller.ato. Paths do not change when a
schematic edit renumbers the auto-assigned designators (R33 shifted 16 of them); build_board.py
resolves them through the frozen netlist and fails on an unknown key.

Regions (R33, world X-38..168; LAYOUT.md "Floorplan" has the picture):
  left edge    J4 (mating -X, pins 9/10 at the front end); the PERMIT gate in front of J4 at J4.9
  left         D-11 receiver at J4.11/12, ct_mon buffer at J4.14 (Y41..56); the tank-RMS converter
               and its MCP3202 in the front-left corner the R31 module used to occupy
  left-rear    interlock block (Y57..71), trip glue to its right; the read-back buffer in front of it (X22)
  rear-mid     thermal-sense block between J2 (X-20) and J1 (X55); J7 UI bus (R33) X30..62
  front-mid    3.3 V buck (X 28..50); free routing field X 40..120 between the halves
  rear-right   blower buck at X 81..102 (C28; moved off the RTD side); RTD front end X 120..156 between
               the module and J3 (L2 >= 10 mm from it); fan header J10 and RTD header J3 fixed
  right        ESP32-S3-WROOM-1U (R33 box), U.FL at its rear-right corner kept clear 3 mm
"""
from __future__ import annotations

import world

PLACE = {
    # ---- connectors, J4 and the module: from the parameter table
    **{ref: (x, y, world.CONNECTOR_ROT.get(ref, 0), "fab") for ref, (x, y) in world.CONNECTORS.items()},
    "J4": ((world.J4_BODY[0] + world.J4_BODY[2]) / 2, (world.J4_BODY[1] + world.J4_BODY[3]) / 2,
           90 if world.J4_MATING == "-X" else -90, "crtyd"),
    # WROOM-1U: antenna/U.FL end (footprint -y) toward world +Y, body top edge on the R33 box's rear edge
    "U4": ((world.WROOM[0] + world.WROOM[2]) / 2, world.WROOM[3] - world.WROOM_BODY_YSPAN / 2, 0, "fab"),
    "J11": (138.0, 19.0, 90, "fab"),                # C41: TC2050 flush land, next to the module's USB pins
    # ---- PERMIT gate at J4.9, in front of J4
    "u_permit": (-32.0, 24.5, 90),
    # ---- J4 analog
    "u_rx": (-13.0, 44.0, 0),
    "u_ref": (-19.4, 48.4, 90),
    "u_buf1": (-13.0, 52.5, 0),
    "u_rms": (-11.0, 31.0, 0),
    "u_adc": (-1.0, 29.0, 0),
    # ---- interlock block (U20-U25) with the read-back buffer, and the trip glue
    "interlock.latch": (-18.0, 59.5, 0),
    "interlock.watchdog": (-10.0, 59.5, 0),
    "interlock.common": (-2.0, 59.5, 0),
    "interlock.fault_inv": (-16.0, 67.0, 90),
    "interlock.aggregate": (8.0, 67.0, 90),
    "interlock.control_inv": (18.5, 66.0, 90),
    "u_rb": (22.0, 50.0, 0),       # read-back buffer: in front of the block, outputs toward the module
    # C53: the row moves 3 mm left (from X 27/33/39; U3 2.2 mm, held off U24) to open an escape channel for U50's SPI pins 14-17
    "u_rail": (24.8, 68.5, 0),
    "u_live": (30.0, 68.5, 0),
    "u_rail_inv": (36.0, 68.5, 0),
    # ---- MCU support: expander between the read-back buffer and the module
    "u_io": (118.0, 44.0, 0),
    # ---- J7 UI bus (R33): ESD arrays in front of the header, +5 V LDO beside it
    "u_esd_ui1": (40.0, 53.5, 0),
    "u_esd_ui2": (52.0, 53.5, 0),
    "u_v5": (68.0, 62.0, 0),
    # ---- thermal-sense block
    "thermal.hs_comp": (-6.0, 81.0, 0),
    "thermal.hs_open_comp": (2.0, 81.0, 0),
    "thermal.hs_or": (-6.0, 86.5, 0),
    "thermal.coil_comp": (30.0, 81.0, 0),
    "thermal.coil_open_comp": (21.0, 81.0, 0),
    "thermal.coil_or": (30.0, 86.5, 0),
    "u_buf2": (11.0, 76.0, 0),
    # ---- 3.3 V buck (cluster: L right of U, SW pour band below; input caps and bulk to the left)
    "u_3v3": (40.0, 22.75, 0),
    "l_3v3": (46.3, 18.4, 0),
    "c_bst_3v3": (42.1, 21.7, -90),
    "c_in3b": (37.8, 20.1, -90),
    "c_in3a": (35.8, 19.9, -90),
    "c_in_bulk": (28.0, 21.0, 180),
    # ---- blower buck (C28, same cluster; 12.5 mm SWRB1205S inductor), X 81..102 so L2 stays
    #      >= 10 mm from the RTD front end
    #      stage 16: the cluster moved 5.5 mm forward so J13 (PS3 feed) sits at the rear edge behind
    #      U2; the 100 uF bulk sits left of the input caps, between J13 and U2
    "u_12": (86.0, 75.25, 0),
    "l_12": (95.75, 70.9, 0),
    "c_bst_12": (88.1, 74.2, -90),
    "c_in12b": (83.8, 72.6, -90),
    "c_in12a": (81.8, 72.4, -90),
    "c_blw_bulk": (72.6, 72.0, 180),       # + pad toward the input caps (feed strip)
    "c_in12c": (79.4, 72.4, -90),
    # FB divider in the strip between U2/L2 and J13, next to the FB pin (pin 8, rear-right)
    "r_fb12_bot": (88.9, 78.45, 0),
    "r_fb12_top": (88.9, 80.05, 0),
    "r_fan_inj": (92.1, 80.05, 0),
    # ---- RTD front end (rtd_pan) and the runaway comparator, between the module and J3
    "rtd_pan.adc": (149.0, 75.2, 90),       # C53: 1.3 mm forward; the 5.3 mm SSOP land (C51 U30 fix) reached the J3 strip
    # C53: supply bypasses at U30's pin-1 end, pad 1 (the rail) toward the pin row. The RTD unit's rule is <= 3 mm pad
    # edge to pad edge (zapote-drc DRC.RTD.LOCAL_DECOUPLING; check_layout rtd_decoupling). Auto-placed, C30 (DVDD, pin 2)
    # landed at the top of that end, 3.10 mm from its pin.
    "rtd_pan.c_dvdd": (144.28, 75.655, 90),  # DVDD pin 2: 2.51 mm
    "rtd_pan.c_vdd": (144.28, 72.465, 90),   # VDD (RTD_AVDD) pin 3: 2.43 mm
    "rtd_pan.reference": (140.0, 78.5, 0),
    "rtd_pan.low_window": (138.0, 70.5, 0),
    "rtd_pan.high_window": (131.0, 70.5, 0),
    "rtd_pan.fault_nand": (124.0, 70.5, 0),
    "rtd_pan.window_and": (131.0, 77.5, 0),
    "rtd_pan.rail_monitor": (124.0, 77.5, 0),
    "u_runaway": (118.0, 74.0, 0),
    # C34: the 1 nF differential filter across the MAX31865's RTDIN+ (pin 10) / RTDIN- (pin 11) end,
    # pad 1 (rtd_sense_p) toward pin 10; the RTD unit's locality rule is <= 3 mm pad to pin
    "rtd_pan.c_rtd_input": (155.6, 75.2, 90),   # C53: follows U30 forward   # C37: now the 100 nF C0G 1206 (sensor-r3 CR-1)
    # ---- C37 (sensor-r3 CR-1) J3 protection and the two-stage sense filter. J3's XH body reaches
    #      3.4 mm in front of its pin row and the MAX31865 sits 2.6 mm in front of that, so the 220 nF /
    #      TVS pairs take the strip between them (TVS upright, caps flat), the force-line pair for
    #      J3.4 the strip right of J3 (behind the Ø8 hole keep-out); the filter the two rows right of
    #      the MAX31865 in front of that keep-out: R1 (r_s1) and R2 (r_s2) in the rear row, the 1206 C1
    #      (c_s1) in front of R1 with the 499 k pull-ups at the ends of that row; c_rtd_input bridges
    #      pins 10/11. (A first run with the pull-ups behind the keep-out routed J3.2's net along the
    #      board edge.)
    "rtd_pan.c_j_fp": (143.65, 81.5, 0),
    "rtd_pan.d_j_fp": (146.0, 81.33, 90),
    "rtd_pan.c_j_sp": (148.55, 81.85, 0),
    "rtd_pan.d_j_sp": (150.85, 81.33, 90),
    "rtd_pan.c_j_sn": (153.2, 81.85, 0),
    "rtd_pan.d_j_sn": (155.5, 81.33, 90),
    "rtd_pan.c_cm_n": (157.5, 80.75, 90),
    "rtd_pan.c_j_fn": (159.9, 86.6, 90),
    "rtd_pan.d_j_fn": (161.7, 86.6, 90),
    "rtd_pan.r_rtdin_p_bias": (165.6, 71.3, 90),
    "rtd_pan.r_rtdin_n_bias": (157.4, 71.6, 0),
    "rtd_pan.r_s2n": (157.75, 74.4, 90),
    "rtd_pan.r_s2p": (159.5, 74.4, 90),
    "rtd_pan.r_s1n": (161.25, 74.4, 90),
    "rtd_pan.r_s1p": (163.0, 74.4, 90),
    "rtd_pan.c_s1": (162.3, 71.3, 0),
    # ---- rim NTC (R36): follower beside J12; divider and filter at its input, ADC RC at the module
    "u_buf3": (118.3, 81.0, 0),           # C40: 0.7 mm left for the 3-pin J12
    # ---- C38 (sensor-r3 CR-5): rim trip comparator and the RUNAWAY_FAULT OR, in the free column
    #      between the keep-apart band and the RTD block (rim_filt runs down to it; RUNAWAY_FAULT
    #      leaves left for the interlock)
    "u_rim_trip": (116.5, 56.5, 0),
    "u_runaway_or": (116.5, 61.5, 0),
    # the runaway divider and the RTD pull-ups around it kept at their C36 poses: with U41 in the
    # column the auto-placer pushed r_runaway_top to 7.8 mm from L2 (partition gate >= 10 mm) and
    # r_runaway_bot to the rear edge (C44)
    "r_runaway_top": (116.21, 66.97, 90),
    "r_runaway_bot": (113.78, 66.45, -90),
    "rtd_pan.r_rail_ok_pullup": (115.87, 70.25, 0),
    "rtd_pan.r_fault_pullup": (122.9, 61.35, 90),
    "rtd_pan.r_high_bottom": (122.35, 64.59, 180),
    "rtd_pan.r_window_ok_pulldown": (119.06, 65.87, -90),
    "rtd_pan.r_avdd_top": (114.22, 75.76, 90),
    "rtd_pan.r_avdd_bottom": (113.7, 80.24, 90),
    # ---- C39 capacitive-mode detector: in the free field at the front edge right of the X65 hole,
    #      south of the MCU-to-J4 signal bus. A first placement inside the bus (X93-112, Y33-44)
    #      left one pair open in two of two make.py runs (DECISIONS C44); its nets now cross the
    #      bus on B.Cu (vertical) instead of the bus bending round five ICs
    "u_cm_ff": (83.0, 24.0, 0),
    "u_cm_inv_ha": (89.6, 27.0, 0),
    "u_cm_inv_la": (89.6, 21.5, 0),
    "u_cm_pol": (76.4, 26.5, 0),
    "u_cm_or": (76.4, 21.0, 0),
    # ---- C53: food-probe RTD channel (C51 U50) in front of J9 (43.5, 86, rotated 180: pins 4..1 = F-, S-, S+, F+ at
    #      X 39.75, 42.25, 44.75, 47.25). C51 layout rule: the 100 nF entry capacitors sit at the pins, between J9 and
    #      the BAV199 clamps (they take the ESD impulse first). U50 rotated 180 puts pins 11 (S-) / 10 (S+) at its rear
    #      end, left / right, under the matching J9 pins.
    "rtd_food.c_fn": (39.75, 81.0, 90),
    "rtd_food.c_sn": (42.25, 81.0, 90),
    "rtd_food.c_sp": (44.75, 81.0, 90),
    "rtd_food.c_fp": (47.25, 81.0, 90),
    # clamp row: the BAV199s (SOT-23 rotated so pin 3, the line, faces its capacitor) outside, and the first filter
    #      stage between the sense clamps: R1n, C1 (1206 across the mid nodes, pad 1 = S+ mid on the right), R1p, each
    #      resistor's pad 1 (the J9 side) to the rear
    "rtd_food.d_fn": (34.43, 76.6, 90),
    "rtd_food.d_sn": (37.98, 76.6, 90),
    "rtd_food.r_s1n": (40.58, 76.6, -90),
    "rtd_food.c_s1": (43.8, 76.6, 180),
    "rtd_food.r_s1p": (47.0, 76.6, -90),
    "rtd_food.d_sp": (49.62, 76.6, 90),
    "rtd_food.d_fp": (53.17, 76.6, 90),
    "rtd_food.adc": (46.0, 68.3, 180),
    # C53: U50's bypasses fixed beside its pin-1 end (auto-placed, C111 was 2.97 mm from DVDD pin 2; rule 3 mm).
    # Review m1: the DVDD cap is the inner one, its rail pad level with pin 2, so build_board's locked F.Cu stub joins
    # them directly (the In2 v3v3 pour can split, so a pour-only connection is not a local bypass)
    "rtd_food.c_dvdd": (51.945, 65.245, -90), # DVDD pin 2: 1.02 mm, pad 1 level with it
    "rtd_food.c_vdd": (53.54, 67.025, 90),    # VDD (RTD2_AVDD) pin 3: 2.62 mm
    # second filter stage in the 2.5 mm row between U50's pin 10/11 end (Y 71.2) and the clamps: R2n, C2 (1206 across
    # the sense pair, pad 1 = S+ on the right), R2p; the common-mode caps beside pins 11 (left) and 10 (right)
    "rtd_food.r_s2n": (42.0, 73.41, 0),
    "rtd_food.c_s2": (46.0, 73.41, 180),
    "rtd_food.r_s2p": (50.0, 73.41, 180),
    "rtd_food.c_cm_n": (39.0, 71.4, 0),
    "rtd_food.c_cm_p": (52.4, 71.0, 90),
    # open-lead 1 M pull-ups (sense ext nodes to rtd2_bias) at the ends of that row
    "rtd_food.r_bias_n": (38.5, 73.41, 0),
    "rtd_food.r_bias_p": (53.5, 73.41, 0),
    # SPI series resistors and the CS pull-up, explicit. Anchored to U50, r_cs landed at (36.5, 80.6) by J9 and its
    # 13 mm stub through the clamp row stayed open in runs 1 and 3 of the first C53 route; with r_cs moved, the
    # anchor put r_sdo in that spot instead. The second route still left cs_n and sclk open: U12 sat 1 mm from
    # U50's SPI pins 14-17 and its vias filled their escape. The U3/U11/U12 row now sits further left (above).
    # r_cs sits under pins 18-20 (GND, GND, NC), 4 mm from pin 16. U12's cap C57 takes r_cs's old spot, its 3V3
    # pad 4 mm from U12 pin 5, so that X 38.1..41.5, Y 66..72 stays free for the escape. The other three keep
    # the poses that routed in the first route
    "rtd_food.r_cs": (39.6, 65.1, 0),
    "c_rail_inv": (35.9, 65.1, -90),
    "rtd_food.r_sdi": (32.86, 65.11, 0),
    "rtd_food.r_sdo": (28.36, 65.58, 180),
    "rtd_food.r_sck": (30.56, 72.32, 0),
    "rtd_food.r_cs_pu": (60.92, 70.45, 0),
    # ---- C53: face-fan 12 V buck (U51, L3) in the free field in front of the blower buck, > 10 mm from both RTD
    #      channels; EMC2301 (U52) and the PWM cascode / tach parts at J15 (104.5, 86; pins 1..5 at X 99.5..109.5)
    "bay_fan.u_buck": (82.0, 54.0, 0),
    "bay_fan.l": (89.0, 54.0, 0),
    # C53 review M3: the face-fan buck gets the blower buck's power-stage layout (build_board.buck_pours: SW band to L3
    # pad 1, VIN pour left of pin 3). The caps sit at U2's offsets: the 100 nF HF input cap next to pins 3/4, the bulk
    # cap beside it, both with pad 1 on the VIN pour; the bootstrap cap's SW pad on the SW band
    "bay_fan.c_in_b": (79.8, 51.35, -90),
    "bay_fan.c_in_a": (77.8, 51.15, -90),
    "bay_fan.c_bst": (84.1, 52.95, -90),
    "bay_fan.u_fan": (106.0, 76.0, 90),
    "bay_fan.q_pwm": (110.4, 79.6, 0),
    "bay_fan.d_tach": (104.5, 81.2, 90),
    "bay_fan.d_pwm": (107.0, 81.2, 90),
    # tach pull-up and series R left of D15 (anchored, the keep-apart band pushed them into the RTD block); the PWM
    # pull-up beside Q2
    "bay_fan.r_tach_pu": (102.1, 81.6, 0),
    "bay_fan.r_tach": (102.1, 79.9, 0),
    "bay_fan.r_pwm": (110.6, 75.6, 90),
    # CLK and ALERT# resistors in the strip between L2 and U52 (anchored, they took the blower buck's SS / EN spots)
    "bay_fan.r_alert": (103.3, 77.0, 90),
    "bay_fan.r_clk": (103.3, 73.8, 90),
}

# Board text (world mm, size): ID and SELV mark on F.Silkscreen in the free front-middle area
SILK = [("TEMPER CONTROLLER", 115.0, 24.0, 2.5), ("SELV  15 V max  -  NO MAINS", 115.0, 20.0, 1.5),
        ("zapote/controller  C53 (C51, 6 layers)", 115.0, 30.0, 1.2)]  # C44: X98 -> X115, clear of the C39 group

# Passive -> anchor IC/connector (pin chosen automatically: the anchor pin on the passive's
# non-ground net). Listed where the automatic "most specific net" choice would pick the wrong
# end (decoupling, ADC RC filters at the MCU, interlock pull-ups at the interlock, etc.).
ANCHOR = {
    # decoupling at every IC supply pin
    "c_out3a": "l_3v3", "c_out3b": "l_3v3", "c_out3c": "l_3v3",
    "c_out12a": "l_12", "c_out12b": "l_12",
    "c_rail": "u_rail",
    "thermal.hs_bypass": "thermal.hs_comp", "thermal.coil_bypass": "thermal.coil_comp",
    "thermal.hs_open_bypass": "thermal.hs_open_comp", "thermal.coil_open_bypass": "thermal.coil_open_comp",
    "thermal.hs_or_bypass": "thermal.hs_or", "thermal.coil_or_bypass": "thermal.coil_or",
    "rtd_pan.c_reference": "rtd_pan.reference", "rtd_pan.c_low_window": "rtd_pan.low_window",
    "rtd_pan.c_high_window": "rtd_pan.high_window", "rtd_pan.c_window_and": "rtd_pan.window_and",
    "rtd_pan.c_rail_monitor": "rtd_pan.rail_monitor", "rtd_pan.c_fault_nand": "rtd_pan.fault_nand",
    "interlock.fault_inv_bypass": "interlock.fault_inv", "interlock.control_inv_bypass": "interlock.control_inv",
    "interlock.aggregate_bypass": "interlock.aggregate", "interlock.latch_bypass": "interlock.latch",
    "interlock.watchdog_bypass": "interlock.watchdog", "interlock.common_bypass": "interlock.common",
    "c_live": "u_live", "c_runaway": "u_runaway", "c_rb": "u_rb",
    "c_rx": "u_rx", "c_buf1": "u_buf1", "c_buf2": "u_buf2",
    "c_rms_vcc": "u_rms", "c_rms_vcc2": "u_rms", "c_adc": "u_adc",
    "c_mcu_bulk": "U4", "c_mcu_hf": "U4", "c_io": "u_io",
    "c_v5_in": "u_v5", "c_v5_out": "u_v5",
    "c_esd_ui1": "u_esd_ui1", "c_esd_ui2": "u_esd_ui2", "c_buf3": "u_buf3", "c_in12c": "u_12",
    # blower speed injection at the FB pin; tach parts at J10 (C28)
    "r_fan_inj": "u_12", "c_fan_ctl": "r_fan_inj", "r_fan_pwm_filt": "c_fan_ctl",
    # stage 16 BLW_PG divider at J13, so only the 3.9 V-max node runs to the expander
    "r_blw_pg_top": "J13", "r_blw_pg_bot": "r_blw_pg_top",
    # J13 rail merge: the Schottky beside J13 (V15_BLW side); the J4.1 BIAS_GOOD TVS and pull-down at J4
    "d_merge": "J13", "r_bias_ser": "U4", "c_bias": "r_bias_ser", "r_bias_pd": "r_bias_ser",
    "r_tach_pu": "J10", "d_tach": "J10", "r_tach_series": "J10", "c_tach": "r_tach_series",
    # NTC input RCs at their buffers (C29)
    "r_hs_filt": "u_buf1", "c_hs_filt": "u_buf1", "r_coil_filt": "u_buf2", "c_coil_filt": "u_buf2",
    "r_rim_filt": "u_buf3",
    "d_rim": "J12", "r_rim_pu": "u_buf3", "c_rim_filt": "u_buf3", "r_rim_adc": "U4",
    # thermal-sense node parts stay in the block (the net also reaches the buffer at J4)
    "thermal.hs_fixed": "thermal.hs_comp", "thermal.hs_filter": "thermal.hs_comp",
    "thermal.coil_fixed": "thermal.coil_comp", "thermal.coil_filter": "thermal.coil_comp",
    # series / pull parts at the connector end
    "r_ct_zc": "J4", "r_line_zc": "J4", "r_fan_off_pd": "q_fan_off", "q_fan_off": "u_12",
    # J7 (R33): 100 ohm series at the connector end; CS pull-ups at the module
    "rs_ui_sck": "J7", "rs_ui_mosi": "J7", "rs_ui_miso": "J7", "rs_ui_cs_oled": "J7", "rs_ui_cs_exp": "J7",
    "rs_ui_dc": "J7", "r_cs_oled_pu": "U4", "r_cs_exp_pu": "U4",
    # RTD SPI 33 ohm series resistors belong to the RTD block (at the MAX31865)
    "rtd_pan.r_ref": "rtd_pan.adc",        # C53: Rref at its converter (C49 left it 24 mm away, unanchored)
    "rtd_pan.r_sclk": "rtd_pan.adc", "rtd_pan.r_mosi": "rtd_pan.adc", "rtd_pan.r_cs": "rtd_pan.adc",
    "rtd_pan.r_miso": "rtd_pan.adc",
    # ADC anti-kick RC at the ESP32 pad
    "r_vbus_adc": "U4", "r_hs_adc": "U4", "r_coil_adc": "U4", "r_bay_adc": "U4",
    # C51 bay NTC (J14): TVS and pull-up at the connector, the 159 Hz RC at its buffer (u_buf2 B), ADC RC at the module
    "d_bay": "J14", "r_bay_pu": "J14", "r_bay_filt": "u_buf2", "c_bay_filt": "u_buf2", "c_bay_adc": "r_bay_adc",
    # C53 food RTD (U50): supply, Rref, SPI 1 k series (C51: every SPI line has 1 k at U50) and the second filter stage
    # at the converter; the open-lead pull-ups and the first filter stage at J9
    "rtd_food.c_avdd_bulk": "rtd_food.adc",
    "rtd_food.fb": "rtd_food.adc", "rtd_food.r_ref": "rtd_food.adc",
    # C53 face fan: buck parts at U51 / L3, EMC2301 parts at U52, tach pull-up and series R at J15
    "bay_fan.c_ss": "bay_fan.u_buck", "bay_fan.r_en_top": "bay_fan.u_buck", "bay_fan.r_en_bot": "bay_fan.u_buck",
    "bay_fan.r_fb_top": "bay_fan.u_buck", "bay_fan.r_fb_bot": "bay_fan.u_buck",
    "bay_fan.c_out_a": "bay_fan.l", "bay_fan.c_out_b": "bay_fan.l",
    "bay_fan.c_fan": "bay_fan.u_fan", "bay_fan.c_tach": "bay_fan.u_fan", 
    "r_hs_adc_bot": "U4",            # C45 (CR-8): the divider's bottom R at the ADC pad, beside c_hs_adc
    # interlock pull-ups / pull-downs in the interlock region
    "interlock.ocp_pullup": "interlock.fault_inv", "interlock.ovp_pullup": "interlock.fault_inv",
    "interlock.hs_pullup": "interlock.fault_inv", "interlock.coil_pullup": "interlock.fault_inv",
    "interlock.rtd_pullup": "interlock.fault_inv", "interlock.runaway_pullup": "interlock.fault_inv",
    "interlock.aux_pullup": "interlock.control_inv", "interlock.reset_pullup": "interlock.control_inv",
    "interlock.live_pulldown": "interlock.control_inv", "interlock.permit_pulldown": "interlock.latch",
    "interlock.wdi_pulldown": "interlock.watchdog",
    "r_rail_pu": "u_rail", "r_rail_sense": "u_rail",
    # PERMIT gate (C23): bypass at the gate, RUN_EN pull-down at the gate, PERMIT pull-down at J4.9
    "c_permit": "u_permit", "r_run_en_pd": "u_permit", "r_permit_pd": "u_permit",
    # +5 V UI LDO droppers next to the LDO
    "r_v5_drop2": "u_v5", "r_v5_drop": "r_v5_drop2",
    "r_scl_pu": "u_io", "r_sda_pu": "u_io", "r_dc_pd": "U4", "r_en": "U4",
    "r_adc_cs_pu": "u_adc", "d_rms_clamp": "u_adc", "r_rms_adc": "u_adc",
    # C37 (sensor-r3 CR-1): connector-side protection and the first filter stage at J3; the second
    # stage and the CM caps at the MAX31865's RTDIN pins
    "rtd_pan.c_j_fp": "rtd_pan.j_rtd1", "rtd_pan.c_j_sp": "rtd_pan.j_rtd1",
    "rtd_pan.c_j_sn": "rtd_pan.j_rtd1", "rtd_pan.c_j_fn": "rtd_pan.j_rtd1",
    "rtd_pan.d_j_fp": "rtd_pan.j_rtd1", "rtd_pan.d_j_sp": "rtd_pan.j_rtd1",
    "rtd_pan.d_j_sn": "rtd_pan.j_rtd1", "rtd_pan.d_j_fn": "rtd_pan.j_rtd1",
    "rtd_pan.r_s1p": "rtd_pan.j_rtd1", "rtd_pan.r_s1n": "rtd_pan.j_rtd1",
    "rtd_pan.r_rtdin_p_bias": "rtd_pan.j_rtd1", "rtd_pan.r_rtdin_n_bias": "rtd_pan.j_rtd1",
    "rtd_pan.c_s1": "rtd_pan.r_s1p",
    "rtd_pan.r_s2p": "rtd_pan.adc", "rtd_pan.r_s2n": "rtd_pan.adc",
    "rtd_pan.c_cm_p": "rtd_pan.adc", "rtd_pan.c_cm_n": "rtd_pan.adc",
    "rtd_pan.c_window": "rtd_pan.low_window",
    # C38 rim trip and runaway OR
    "r_rim_th_top": "u_rim_trip", "r_rim_th_bot": "u_rim_trip", "c_rim_th": "u_rim_trip",
    "c_rim_trip": "u_rim_trip", "c_runaway_or": "u_runaway_or",
    # C39 detector
    "c_cm_inv_ha": "u_cm_inv_ha", "c_cm_inv_la": "u_cm_inv_la", "c_cm_pol": "u_cm_pol", "c_cm_ff": "u_cm_ff",
    "c_cm_or": "u_cm_or", "r_cm_pol": "u_cm_pol", "r_cm_pol_pu": "u_cm_pol",
    "r_cm_ha_rb": "u_cm_ff", "r_cm_la_rb": "u_cm_ff",
}

# Routing channels kept free of auto-placed parts (world rects; decoupling capacitors excepted).
# L3: the module's front and left pin rows. Its right-column nets (pins 27-39) all head left and
# wrap round the front edge, so a band in front of the module and a strip along its left side
# keep room for those wraps and for the front/left pins' own escapes (LAYOUT.md "Convergence").
CHANNELS: list[tuple[float, float, float, float]] = [
    (137.0, 41.0, 163.0, 49.6),     # in front of the module (its pin row is at Y ~50.3)
    (134.5, 49.6, 140.4, 68.0),     # along its left pin column (X 141)
    (102.8, 64.0, 112.8, 85.0),     # keep-apart band: blower buck L2 >= 10 mm from the RTD parts
    (82.3, 75.4, 84.6, 84.4),       # stage 16: the J13 -> VIN feed band (BLW_FEED below)
    (74.0, 72.9, 80.6, 74.9),       # stage 16: the feed strip over the bulk/input-cap + pads
]

# Stage 16 (C33): F.Cu V15_BLW feed band from J13.1 (world ~(86.0, 86.35)) down the left of U2 into the
# blower buck VIN pour (world Y ~72.4-75.0, left of U2). 1.7 mm wide along X 82.6-84.3; the top
# reaches J13.1. The CHANNELS entry above keeps auto-placed parts out of it.
BLW_FEED: list[tuple[float, float, float, float]] = [(82.6, 74.6, 84.3, 84.6),   # band down the left of U2
                                                     (81.4, 84.0, 87.95, 88.5),  # top: J13.1 and the BLW_PG top R (C53 review m2: past the pad on +X/+Y/-Y so all four spokes form; was one)
                                                     (74.0, 72.9, 82.6, 74.9)]   # strip: bulk + and input caps

# C34: the RTD unit's analog signal family (zapote/rtd unit profile geometry.sensitive_nets, mapped to the
# controller's net names by evidence/block-validators/mappings/rtd_pan.json). The router keeps them on
# F.Cu and In2.Cu, the two layers whose reference plane is the solid selv_gnd plane on In1.Cu (B.Cu's
# neighbour In2 is the v3v3 plane), and lets them change layer only at a via that has a selv_gnd plane
# via within RTD_RETURN_VIA_MM: the analog return then stays in one filled In1 corridor (the unit's
# DRC.RTD.NATIVE_GEOMETRY "analog_return" check).
RTD_ANALOG_NETS = ["rtd_sense_p", "rtd_sense_n", "rtd_force_p", "rtd_force_n", "p1", "refin_n",
                   "rtd_pan.low_window-inp", "vbias",
                   # C37: the connector-side and mid-filter sense nodes (sensor-r3 CR-1)
                   "rtd_sense_p_ext", "rtd_sense_n_ext", "rtd_sense_p_mid", "rtd_sense_n_mid",
                   # C53: the food-probe channel (U50) under the same layer and return rule
                   "rtd2_force_p", "rtd2_force_n", "rtd2_sense_p", "rtd2_sense_n", "rtd2_sense_p_ext",
                   "rtd2_sense_n_ext", "rtd2_sense_p_mid", "rtd2_sense_n_mid", "rtd2_bias", "rtd2_refin_n"]
RTD_RETURN_VIA_MM = 2.5          # the unit's required_locality_mm is 3.0
# C34: selv_gnd stitching vias on a pitch grid over the RTD analog region (world rects), where no plane
# via sits within half a pitch already: every point of the region then has a return via within reach
# of RTD_RETURN_VIA_MM, so the analog nets can change layer next to one (the module body is skipped)
RTD_STITCH: list[tuple[float, float, float, float]] = [(115.0, 55.0, 167.0, 89.0),
                                                       (35.0, 63.5, 56.0, 89.0)]     # C53: food channel, J9 to U50
RTD_STITCH_PITCH = 3.0
# C53 review m6: a coarse selv_gnd stitching grid over the whole board ties the In1 and In4 planes together where no
# part fan-out does (12 % of the board was > 10 mm from a ground via; worst 25 mm). Skipped where a ground via is
# within half the pitch; the module body is skipped as for RTD_STITCH.
GND_STITCH_PITCH = 10.0
# C53 review m7: three fiducials (1 mm copper, 2 mm mask opening) for JLC's placement vision, at the free spots nearest
# three board corners (the WROOM module fills the fourth); world mm. A 1.5 mm copper keep-out keeps the mask opening bare.
FIDUCIALS = [(-32.55, 84.55), (-23.55, 19.55), (153.95, 20.05)]

# C34: net-pair clearances above the net classes (KiCad custom rules, pcb/controller.kicad_dru, and the
# router). The block validators see the shared plane nets' whole copper, so the thermal-sense unit's
# 0.20 mm floor applies to every selv_gnd / v3v3 pair on the board, not only inside its block.
PAIR_CLEARANCE: list[tuple[str, str, float]] = [("selv_gnd", "v3v3", 0.20)]
