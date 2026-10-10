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
  rear-right   12 V fan buck at X 87..102 (moved off the RTD side); RTD front end X 120..156 between
               the module and J3 (L2 >= 10 mm from it); fan header J10 and RTD header J3 fixed
  right        ESP32-S3-WROOM-1U (R33 box), U.FL at its rear-right corner kept clear 3 mm
"""
from __future__ import annotations

import world

PLACE = {
    # ---- connectors, J4 and the module: from the parameter table
    **{ref: (x, y, 0, "fab") for ref, (x, y) in world.CONNECTORS.items()},
    "J4": ((world.J4_BODY[0] + world.J4_BODY[2]) / 2, (world.J4_BODY[1] + world.J4_BODY[3]) / 2,
           90 if world.J4_MATING == "-X" else -90, "crtyd"),
    # WROOM-1U: antenna/U.FL end (footprint -y) toward world +Y, body top edge on the R33 box's rear edge
    "U4": ((world.WROOM[0] + world.WROOM[2]) / 2, world.WROOM[3] - world.WROOM_BODY_YSPAN / 2, 0, "fab"),
    "J11": (138.0, 19.0, 90, "fab"),                # bring-up header, next to the module's USB pins
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
    "u_rail": (27.0, 68.5, 0),
    "u_live": (33.0, 68.5, 0),
    "u_rail_inv": (39.0, 68.5, 0),
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
    # ---- 12 V fan buck (same cluster), X 90..105 so L2 stays >= 10 mm from the RTD front end
    "u_12": (92.0, 80.75, 0),
    "l_12": (98.3, 76.4, 0),
    "c_bst_12": (94.1, 79.7, -90),
    "c_in12b": (89.8, 78.1, -90),
    "c_in12a": (87.8, 77.9, -90),
    # ---- RTD front end (rtd_pan) and the runaway comparator, between the module and J3
    "rtd_pan.adc": (149.0, 76.5, 90),
    "rtd_pan.reference": (140.0, 78.5, 0),
    "rtd_pan.low_window": (138.0, 70.5, 0),
    "rtd_pan.high_window": (131.0, 70.5, 0),
    "rtd_pan.fault_nand": (124.0, 70.5, 0),
    "rtd_pan.window_and": (131.0, 77.5, 0),
    "rtd_pan.rail_monitor": (124.0, 77.5, 0),
    "u_runaway": (118.0, 74.0, 0),
    # ---- rim NTC (R36): follower beside J12; divider and filter at its input, ADC RC at the module
    "u_buf3": (119.5, 81.5, 0),
}

# Board text (world mm, size): ID and SELV mark on F.Silkscreen in the free front-middle area
SILK = [("TEMPER CONTROLLER", 98.0, 24.0, 2.5), ("SELV  15 V max  -  NO MAINS", 98.0, 20.0, 1.5),
        ("zapote/controller  rev L2 (enclosure R33)", 98.0, 30.0, 1.2)]

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
    "rtd_pan.c_vdd": "rtd_pan.adc", "rtd_pan.c_dvdd": "rtd_pan.adc",
    "rtd_pan.c_reference": "rtd_pan.reference", "rtd_pan.c_low_window": "rtd_pan.low_window",
    "rtd_pan.c_high_window": "rtd_pan.high_window", "rtd_pan.c_window_and": "rtd_pan.window_and",
    "rtd_pan.c_rail_monitor": "rtd_pan.rail_monitor", "rtd_pan.c_fault_nand": "rtd_pan.fault_nand",
    "interlock.fault_inv_bypass": "interlock.fault_inv", "interlock.control_inv_bypass": "interlock.control_inv",
    "interlock.aggregate_bypass": "interlock.aggregate", "interlock.latch_bypass": "interlock.latch",
    "interlock.watchdog_bypass": "interlock.watchdog", "interlock.common_bypass": "interlock.common",
    "c_rail_inv": "u_rail_inv", "c_live": "u_live", "c_runaway": "u_runaway", "c_rb": "u_rb",
    "c_rx": "u_rx", "c_buf1": "u_buf1", "c_buf2": "u_buf2",
    "c_rms_vcc": "u_rms", "c_rms_vcc2": "u_rms", "c_adc": "u_adc",
    "c_mcu_bulk": "U4", "c_mcu_hf": "U4", "c_io": "u_io",
    "c_v5_in": "u_v5", "c_v5_out": "u_v5",
    "c_esd_ui1": "u_esd_ui1", "c_esd_ui2": "u_esd_ui2", "c_buf3": "u_buf3",
    "d_rim": "J12", "r_rim_pu": "u_buf3", "c_rim_filt": "u_buf3", "r_rim_adc": "U4",
    # thermal-sense node parts stay in the block (the net also reaches the buffer at J4)
    "thermal.hs_fixed": "thermal.hs_comp", "thermal.hs_filter": "thermal.hs_comp",
    "thermal.coil_fixed": "thermal.coil_comp", "thermal.coil_filter": "thermal.coil_comp",
    # series / pull parts at the connector end
    "r_ct_zc": "J4", "r_line_zc": "J4", "r_tach_pu": "J10", "r_fan_off_pd": "q_fan_off", "q_fan_off": "u_12",
    # J7 (R33): 100 ohm series at the connector end; CS pull-ups at the module
    "rs_ui_sck": "J7", "rs_ui_mosi": "J7", "rs_ui_miso": "J7", "rs_ui_cs_oled": "J7", "rs_ui_cs_exp": "J7",
    "rs_ui_dc": "J7", "r_cs_oled_pu": "U4", "r_cs_exp_pu": "U4",
    # RTD SPI 33 ohm series resistors belong to the RTD block (at the MAX31865)
    "rtd_pan.r_sclk": "rtd_pan.adc", "rtd_pan.r_mosi": "rtd_pan.adc", "rtd_pan.r_cs": "rtd_pan.adc",
    "rtd_pan.r_miso": "rtd_pan.adc",
    # ADC anti-kick RC at the ESP32 pad
    "r_vbus_adc": "U4", "r_hs_adc": "U4", "r_coil_adc": "U4", "r_m12_adc": "U4",
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
}

# Routing channels kept free of auto-placed parts (world rects). R33 moved the module to the
# right, so the R31 channels around it are gone; none are needed now.
CHANNELS: list[tuple[float, float, float, float]] = []
