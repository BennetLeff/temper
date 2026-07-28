"""Machine checks for the implemented UCC21550 safety boundary."""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MODULES_RAW = (ROOT / "elec/src/modules.ato").read_text()

# Connection assertions below are substring matches against the source, so they
# must not be satisfiable by prose. `fault_or3.Y2 ~ latch.A1` appears both as a
# real connection and inside a comment; breaking the real one left the test
# green because the comment still matched. Strip comments so a connection named
# only in prose cannot stand in for one that exists.
# Use MODULES_RAW where a comment is genuinely the thing under test.
MODULES = re.sub(r"#.*", "", MODULES_RAW)
MAIN = (ROOT / "elec/src/main.ato").read_text()
PINS = (ROOT / "firmware/components/hal/include/temper_pins.h").read_text()


def test_control_and_gate_supplies_are_separate() -> None:
    assert "power_3v3.vcc ~ gate_hs.driver.VCCI_1" in MODULES
    assert "power_3v3.vcc ~ gate_hs.driver.VCCI_2" in MODULES
    assert "hb.power_3v3.vcc ~ vcc_3v3" in MAIN
    assert "hb.power_15v.vcc ~ vcc_15v" in MAIN


def test_dis_is_active_high_and_not_legacy_shutdown_n() -> None:
    assert "safety.shutdown.line ~ hb.gate_hs.driver.DIS" in MAIN
    assert 'safety.shutdown.line.override_net_name = "SHUTDOWN"' in MAIN
    assert "shutdown_n ~" not in MAIN


def test_safety_gpio_assignments_do_not_collide_with_pwm() -> None:
    assert "mcu.IO4 ~ pwm_h" in MODULES
    assert "mcu.IO5 ~ pwm_l" in MODULES
    assert "wdt_kick.line ~ mcu.IO7" in MODULES
    assert "wdt_reset_in.line ~ mcu.IO6" in MODULES
    assert "reset_n.line ~ mcu.IO14" in MODULES
    assert "runaway_cut.line ~ mcu.IO15" in MODULES


def test_firmware_pin_header_matches_schematic_safety_map() -> None:
    """The firmware header must not reintroduce a GPIO collision."""

    expected = {
        "PIN_SPI_CLK": "8",
        "PIN_SPI_MOSI": "11",
        "PIN_SPI_MISO": "12",
        "PIN_ZCD_INPUT": "13",
        "PIN_WDT_KICK": "7",
        "PIN_WDT_RESET": "6",
        "PIN_RUNAWAY_CUT": "15",
        "PIN_FAULT_OUT": "20",
        "PIN_RELAY_BYPASS": "19",
        "PIN_RESET_INPUT": "14",
        "PIN_SPI_CS_RTD2": "16",
        "PIN_I2C_SDA": "38",
        "PIN_I2C_SCL": "39",
    }
    for macro, value in expected.items():
        assert re.search(rf"^#define {macro}\s+{value}$", PINS, re.MULTILINE)
    assert "fault_status_in.line ~ mcu.IO17" in MODULES
    assert "shutdown_n_in" not in MODULES


def test_optional_buses_do_not_reuse_active_peripheral_pins() -> None:
    assert "rtd_drdy.line ~ mcu.IO9" in MODULES
    assert "i2c.sda ~ mcu.IO38" in MODULES
    assert "i2c.scl ~ mcu.IO39" in MODULES
    assert re.search(r"^#define PIN_SPI_CS_RTD2\s+(?!9$)\d+$", PINS, re.MULTILINE)


def test_fault_bus_includes_watchdog_and_sr_feedback() -> None:
    """Every fault, including the independent RTD path, reaches the SR latch."""

    assert "fault_or.Y1 ~ fault_or.A2" in MODULES
    assert "wdt.reset_n.line ~ latch.A4" in MODULES
    assert "latch.Y4 ~ fault_or.B2" in MODULES
    assert "latch.Y1 ~ latch.A2" in MODULES
    assert "latch.Y3 ~ latch.B2" in MODULES
    assert "latch.Y2 ~ latch.B3" in MODULES
    assert "runaway_cut.line ~ fault_or.C2" in MODULES
    assert "fault_or.Y2 ~ fault_any_or.A1" in MODULES
    assert "rtd_hw_fault.line ~ fault_any_or.B1" in MODULES
    # The SET bus reaches latch.A1 through a third OR stage, not directly.
    # `fault_any_or` ran out of fan-in when UVL-02's fault was wired in, so
    # `fault_or3` was added between it and the latch (see
    # docs/evidence/2026-07-27-fault-tree-capacity-expansion.md). Both hops are
    # asserted so the path is still pinned end to end -- dropping either would
    # let the SET bus be silently orphaned from the latch.
    assert "fault_any_or.Y1 ~ fault_or3.A2" in MODULES
    assert "fault_or3.Y2 ~ latch.A1" in MODULES
    assert "fault_any_or.Y1 ~ fault_any_or.A2" in MODULES
    assert "reset_n_in.line ~ fault_any_or.B2" in MODULES
    assert "fault_any_or.Y2 ~ latch.A3" in MODULES


def test_rtd_fault_path_is_default_high_and_not_mcu_mediated() -> None:
    """The only clear state requires both the local window and healthy rail."""

    expected_connections = {
        "adc.REFIN_N ~ low_window.INP",
        "adc.REFIN_N ~ high_window.INN",
        "low_window.OUT ~ window_and.A",
        "high_window.OUT ~ window_and.B",
        "window_and.Y ~ r_window_ok_pulldown.p1",
        "r_window_ok_pulldown.p2 ~ power.gnd",
        "window_and.Y ~ fault_nand.A",
        "rail_monitor.OUTA ~ fault_nand.B",
        "power.vcc ~ r_fault_pullup.p1",
        "r_fault_pullup.p2 ~ rtd_hw_fault.line",
        "fault_nand.Y ~ rtd_hw_fault.line",
        "rtd_pan.rtd_hw_fault.line ~ safety.rtd_hw_fault.line",
    }
    for connection in expected_connections:
        assert connection in MODULES or connection in MAIN

    assert "fault_nand = new SN74LVC1G38" in MODULES
    assert "fault_nand.VCC ~ fb_power.p2" in MODULES
    assert "rail_monitor = new TPS3700" in MODULES
    assert "rail_monitor.VDD ~ power.vcc" in MODULES
    assert "rtd_hw_fault.line ~ runaway_cut.line" not in MODULES


def test_set_dominant_nand_truth_table() -> None:
    """Q=NAND(S_bar,Q_bar), Q_bar=NAND(R_bar,Q)."""

    def step(s_bar: bool, r_bar: bool, q_bar: bool) -> tuple[bool, bool]:
        q = False
        for _ in range(3):
            q = not (s_bar and q_bar)
            q_bar = not (r_bar and q)
        return q, q_bar

    # Fault asserted: S_bar=0 forces shutdown Q=1.
    q, q_bar = step(False, True, True)
    assert (q, q_bar) == (True, False)
    # Clearing the fault leaves Q latched high.
    q, q_bar = step(True, True, q_bar)
    assert (q, q_bar) == (True, False)
    # Only the explicit active-low reset clears the latch.
    q, q_bar = step(True, False, q_bar)
    assert (q, q_bar) == (False, True)


def test_dt_uses_resistor_and_keeps_measurement_deferred() -> None:
    assert "dt_res.value = 34kohm" in MODULES
    assert "dt_res.p1 ~ gate_hs.driver.DT" in MODULES
    assert "t_dead_time: time = 305.4ns" in MODULES
    assert "t_dt_hw_nominal: time = 305.4ns" in MAIN
    assert "scope verification remains required" in MODULES_RAW.lower()


def test_max31865_four_wire_reference_and_current_sense_are_not_floating() -> None:
    """Require the MAX31865 datasheet 4-wire connection topology.

    These assertions are intentionally source-level as well as the generated
    netlist check below: source review must reject a disconnected REFIN/ISENSOR
    leg before an outdated generated netlist can mask the error.
    """

    expected_connections = {
        "adc.BIAS ~ adc.REFIN_P",
        "adc.REFIN_P ~ r_ref.p1",
        "r_ref.p2 ~ adc.REFIN_N",
        "adc.ISENSOR ~ adc.REFIN_N",
        "adc.FORCE2 ~ power.gnd",
        "adc.FORCE_P ~ rtd_force_p",
        "adc.RTDIN_P ~ rtd_sense_p",
        "adc.FORCE_N ~ rtd_force_n",
        "adc.RTDIN_N ~ rtd_sense_n",
    }
    for connection in expected_connections:
        assert connection in MODULES
    assert "adc.BIAS ~ r_ref.p1" not in MODULES
    assert "adc.REFIN_P ~ adc.FORCE_P" not in MODULES


def _net_block_with_node(netlist: str, reference: str, pin: int) -> str:
    """Return the generated KiCad net block containing one component pin."""

    net_blocks = re.findall(r"    \(net \(code .*?(?=\n    \(net |\n  \)\n\))", netlist, re.DOTALL)
    node = rf'\(node \(ref "{re.escape(reference)}"\) \(pin "{pin}"\)'
    matches = [block for block in net_blocks if re.search(node, block)]
    assert len(matches) == 1, f"{reference} pin {pin} must occur in one net"
    return matches[0]


def _component_ref_with_sheetpath(netlist: str, sheetpath: str) -> str:
    """Resolve a component reference without crossing into the next comp."""

    match = re.search(
        rf'\(comp \(ref "(?P<ref>[A-Z]+\d+)"\)(?:(?!\n    \(comp ).)*?'
        rf"{re.escape(sheetpath)}",
        netlist,
        re.DOTALL,
    )
    assert match is not None, f"component with sheetpath {sheetpath!r} is missing"
    return match.group("ref")


def test_generated_netlist_keeps_max31865_reference_and_force2_connected() -> None:
    """Catch a compiler/netlist regression that disconnects the RTD front end."""

    netlist = (ROOT / "elec/build/default.net").read_text()
    adc_ref = _component_ref_with_sheetpath(netlist, "rtd_pan.adc")
    rref_ref = _component_ref_with_sheetpath(netlist, "rtd_pan.r_ref")

    ref_plus = _net_block_with_node(netlist, adc_ref, 5)
    assert re.search(rf'\(node \(ref "{re.escape(adc_ref)}"\) \(pin "4"\)', ref_plus)
    assert re.search(rf'\(node \(ref "{re.escape(rref_ref)}"\) \(pin "1"\)', ref_plus)

    ref_minus = _net_block_with_node(netlist, adc_ref, 6)
    assert re.search(rf'\(node \(ref "{re.escape(adc_ref)}"\) \(pin "7"\)', ref_minus)
    assert re.search(rf'\(node \(ref "{re.escape(rref_ref)}"\) \(pin "2"\)', ref_minus)

    # FORCE2 must return to SELV `gnd`, NOT to `PWR_RTN`.
    #
    # Do not "fix" this back to pwr_rtn. That assertion was correct only while
    # the star-point join (`power_return ~ gnd`) merged the two into one
    # compiled net; 7f3a11d9 changed it to pwr_rtn on 2026-07-17 for exactly
    # that reason. Commit 6976ef44 floated the SELV control domain and removed
    # the join, so they are separate nets now.
    #
    # elec/domain_manifest.yaml places PWR_RTN in the HV domain (the doubler
    # midpoint) and gnd in SELV. The MAX31865 is SELV-side, so requiring its
    # FORCE2 return on PWR_RTN would demand a direct HV-to-SELV crossing on a
    # sensing pin -- the very short the isolation redesign eliminated.
    force2 = _net_block_with_node(netlist, adc_ref, 9)
    assert 'name "gnd"' in force2.lower()


def test_generated_netlist_carries_default_high_rtd_fault_to_aggregate_or() -> None:
    """The built netlist—not only the source—must preserve the safety path."""

    netlist = (ROOT / "elec/build/default.net").read_text()
    fault_nand_ref = _component_ref_with_sheetpath(netlist, "rtd_pan.fault_nand")
    fault_any_ref = _component_ref_with_sheetpath(netlist, "safety.fault_any_or")
    rtd_fault = _net_block_with_node(netlist, fault_nand_ref, 4)

    assert 'name "RTD_HW_FAULT"' in rtd_fault
    assert re.search(rf'\(node \(ref "{re.escape(fault_any_ref)}"\) \(pin "2"\)', rtd_fault)
