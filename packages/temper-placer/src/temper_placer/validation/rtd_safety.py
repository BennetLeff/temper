"""Small, deterministic model for the PT100/MAX31865 safety thresholds.

The MAX31865 reports the RTD code as ``R_RTD / R_REF * 32768``.  Keeping this
calculation here gives the firmware and the schematic review one executable
reference for selecting the low (short) and high (open) fault thresholds.  It
is deliberately not a temperature converter: a resistance outside the
declared electrical window is unsafe regardless of the temperature model.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from math import ceil, floor


class RtdStatus(StrEnum):
    """Electrical health classification for a PT100 input."""

    SHORT = "short"
    VALID = "valid"
    OPEN = "open"


ADC_FULL_SCALE = 1 << 15
MAX31865_THRESHOLD_REGISTER_SHIFT = 1
PT100_RREF_OHM = 430.0
PT100_RREF_TOLERANCE_FRACTION = 0.001
# The board is specified for a PT100.  0--250 C is approximately 100--194 ohm;
# the wider valid window leaves room for cable resistance and calibration error.
PT100_VALID_MIN_OHM = 50.0
PT100_VALID_MAX_OHM = 250.0
RTD_SHORT_THRESHOLD_OHM = 10.0
RTD_OPEN_THRESHOLD_OHM = 300.0

# MAX31865 VBIAS electrical-characteristics limits at the supported supply
# range. These are a voltage source feeding the series RREF + RTD network, not
# a fixed excitation-current source.
MAX31865_VBIAS_MIN_V = 1.95
MAX31865_VBIAS_MAX_V = 2.06

# Digital MAX31865 contract constants. These mirror the production driver and
# make the in-box timing/fault protocol executable without a target board.
MAX31865_CONFIG_AUTOMATIC_FAULT = 0x84
MAX31865_FAULT_HIGH_THRESHOLD = 0x80
MAX31865_FAULT_LOW_THRESHOLD = 0x40
RTD_DRDY_TIMEOUT_CONTROL_TICKS = 10

# The RTD front end has 33 ohm +/-5% series resistors on all SPI lines. The
# MAX31865 specifies 6 pF logic input capacitance and characterises SPI timing
# at 50 pF; the latter is used as the conservative lumped-load envelope here.
SPI_SERIES_RESISTOR_MIN_OHM = 33.0 * 0.95
SPI_SERIES_RESISTOR_MAX_OHM = 33.0 * 1.05
MAX31865_LOGIC_INPUT_CAPACITANCE_PF = 6.0
MAX31865_SPI_TIMING_LOAD_CAPACITANCE_PF = 50.0
MAX31865_SPI_RISE_FALL_LIMIT_NS = 200.0

# RTD_AVDD is the post-ferrite rail that powers the MAX31865 and the analogue
# window path. The rail monitor must declare a fault before a TLV3201 reaches
# its 2.7 V minimum operating voltage, while staying below the worst normal
# 3.3 V rail (3.3 V - 10%). These are interface limits, not resistor values:
# a schematic may select a monitor only when its complete threshold corners
# fit inside this interval.
RTD_WINDOW_COMPARATOR_MIN_SUPPLY_V = 2.70
RTD_AVDD_NORMAL_MIN_V = 2.97

# Populated reference/divider network for the independent analogue RTD window.
# REF2025 VBIAS is 1.25 V. Its ±0.05% initial accuracy plus 8 ppm/C over the
# -40..125 C design range is conservatively represented as ±0.13%; each thin
# film threshold resistor is ±0.1%.
REF2025_VBIAS_NOMINAL_V = 1.25
REF2025_VBIAS_TOLERANCE_FRACTION = 0.0013
RTD_WINDOW_RESISTOR_TOLERANCE_FRACTION = 0.001
RTD_LOW_WINDOW_TOP_OHM = 61_300.0
RTD_LOW_WINDOW_BOTTOM_OHM = 10_000.0
RTD_HIGH_WINDOW_TOP_OHM = 5_930.0
RTD_HIGH_WINDOW_BOTTOM_OHM = 10_000.0


@dataclass(frozen=True)
class RtdWindowCorners:
    """Parameter range for an independent RTD window-comparator design.

    This is deliberately a *design verifier*, not a fabricated comparator
    circuit. The MAX31865 bias-current range, comparator offset, and threshold
    network tolerance are inputs because they must come from the selected
    components and their measured/datasheet corners.
    """

    bias_current_min_a: float
    bias_current_max_a: float
    comparator_offset_abs_v: float
    divider_tolerance_fraction: float
    short_max_ohm: float = RTD_SHORT_THRESHOLD_OHM
    valid_min_ohm: float = 100.0
    valid_max_ohm: float = 194.1
    open_min_ohm: float = RTD_OPEN_THRESHOLD_OHM
    required_margin_fraction: float = 0.20
    supply_loss_fault: bool = True


@dataclass(frozen=True)
class RtdHardwareWindow:
    """Derived threshold window that can be evaluated at a specified corner."""

    corners: RtdWindowCorners
    low_trip_voltage_v: float
    high_trip_voltage_v: float

    def faulted(
        self,
        resistance_ohm: float,
        excitation_a: float,
        *,
        supply_present: bool = True,
        comparator_offset_v: float = 0.0,
        divider_error_fraction: float = 0.0,
    ) -> bool:
        """Return whether this hardware path must assert its fault output.

        The optional offset and divider inputs make every comparator corner
        executable. Inputs outside the declared design envelope are rejected
        rather than extrapolated into a safety claim.
        """

        if not supply_present:
            return self.corners.supply_loss_fault
        if resistance_ohm < 0.0 or excitation_a < 0.0:
            raise ValueError("resistance and excitation must be non-negative")
        if abs(comparator_offset_v) > self.corners.comparator_offset_abs_v:
            raise ValueError("comparator offset is outside the declared corner")
        if abs(divider_error_fraction) > self.corners.divider_tolerance_fraction:
            raise ValueError("divider error is outside the declared corner")

        sensed_v = hardware_window_voltage(resistance_ohm, excitation_a)
        low_trip_v = self.low_trip_voltage_v * (1.0 + divider_error_fraction)
        high_trip_v = self.high_trip_voltage_v * (1.0 + divider_error_fraction)
        low_trip_v += comparator_offset_v
        high_trip_v += comparator_offset_v
        return sensed_v <= low_trip_v or sensed_v >= high_trip_v


@dataclass(frozen=True)
class Max31865RtdWindowCorners:
    """Window-comparator corners using the actual MAX31865 VBIAS topology.

    Unlike :class:`RtdWindowCorners`, this follows the MAX31865 voltage
    source through RREF and the RTD. It establishes input-threshold feasibility
    only; an actual circuit must separately make comparator supply loss assert
    the fault OR input.
    """

    comparator_offset_abs_v: float
    divider_tolerance_fraction: float
    vbias_min_v: float = MAX31865_VBIAS_MIN_V
    vbias_max_v: float = MAX31865_VBIAS_MAX_V
    rref_nominal_ohm: float = PT100_RREF_OHM
    rref_tolerance_fraction: float = PT100_RREF_TOLERANCE_FRACTION
    short_max_ohm: float = RTD_SHORT_THRESHOLD_OHM
    valid_min_ohm: float = 100.0
    valid_max_ohm: float = 194.1
    open_min_ohm: float = RTD_OPEN_THRESHOLD_OHM
    required_margin_fraction: float = 0.20


@dataclass(frozen=True)
class Max31865RtdHardwareWindow:
    """Derived comparator thresholds for the MAX31865 VBIAS/RREF network."""

    corners: Max31865RtdWindowCorners
    low_trip_voltage_v: float
    high_trip_voltage_v: float

    def faulted(
        self,
        resistance_ohm: float,
        *,
        vbias_v: float,
        rref_ohm: float,
        comparator_offset_v: float = 0.0,
        divider_error_fraction: float = 0.0,
    ) -> bool:
        """Evaluate an explicitly bounded MAX31865 comparator corner."""

        corners = self.corners
        if resistance_ohm < 0.0:
            raise ValueError("RTD resistance must be non-negative")
        if not corners.vbias_min_v <= vbias_v <= corners.vbias_max_v:
            raise ValueError("VBIAS is outside the declared corner")
        rref_min = corners.rref_nominal_ohm * (1.0 - corners.rref_tolerance_fraction)
        rref_max = corners.rref_nominal_ohm * (1.0 + corners.rref_tolerance_fraction)
        if not rref_min <= rref_ohm <= rref_max:
            raise ValueError("RREF is outside the declared corner")
        if abs(comparator_offset_v) > corners.comparator_offset_abs_v:
            raise ValueError("comparator offset is outside the declared corner")
        if abs(divider_error_fraction) > corners.divider_tolerance_fraction:
            raise ValueError("divider error is outside the declared corner")

        sensed_v = max31865_rtd_voltage_v(resistance_ohm, vbias_v=vbias_v, rref_ohm=rref_ohm)
        low_trip_v = self.low_trip_voltage_v * (1.0 + divider_error_fraction)
        high_trip_v = self.high_trip_voltage_v * (1.0 + divider_error_fraction)
        return sensed_v <= low_trip_v + comparator_offset_v or sensed_v >= (
            high_trip_v + comparator_offset_v
        )


@dataclass(frozen=True)
class RtdAvddMonitorCorners:
    """Bounded UV trip contract for the post-ferrite RTD_AVDD rail.

    The monitor itself is powered from the upstream safety 3.3 V rail. Its
    output is the ``RTD_RAIL_OK`` permission used by the post-rail open-drain
    NAND; consequently the monitor remains defined while RTD_AVDD browns out.
    ``trip_min_v`` and ``trip_max_v`` are the *complete* circuit corners,
    including reference, divider, offset, and temperature terms.
    """

    trip_min_v: float
    trip_max_v: float
    comparator_min_supply_v: float = RTD_WINDOW_COMPARATOR_MIN_SUPPLY_V
    normal_rail_min_v: float = RTD_AVDD_NORMAL_MIN_V


def validate_rtd_avdd_monitor(corners: RtdAvddMonitorCorners) -> None:
    """Reject an RTD_AVDD UV monitor that leaves an undefined brownout gap."""

    if not (0.0 < corners.comparator_min_supply_v < corners.normal_rail_min_v):
        raise ValueError("RTD_AVDD supply limits must be positive and ordered")
    if not (corners.comparator_min_supply_v < corners.trip_min_v <= corners.trip_max_v):
        raise ValueError("RTD_AVDD monitor must trip above comparator minimum supply")
    if not corners.trip_max_v < corners.normal_rail_min_v:
        raise ValueError("RTD_AVDD monitor may false-trip at the normal rail corner")


def rtd_avdd_rail_ok(*, rtd_avdd_v: float, trip_v: float, corners: RtdAvddMonitorCorners) -> bool:
    """Return the upstream-powered rail monitor's valid permission level."""

    validate_rtd_avdd_monitor(corners)
    if rtd_avdd_v < 0.0:
        raise ValueError("RTD_AVDD cannot be negative")
    if not corners.trip_min_v <= trip_v <= corners.trip_max_v:
        raise ValueError("RTD_AVDD monitor trip is outside the declared corner")
    return rtd_avdd_v > trip_v


def rtd_window_fault_line_asserted(
    *,
    low_window_ok: bool,
    high_window_ok: bool,
    rtd_avdd_v: float,
    rail_monitor_trip_v: float,
    rail_monitor_corners: RtdAvddMonitorCorners,
) -> bool:
    """Model the default-high ``RTD_HW_FAULT`` circuit.

    ``RTD_HW_FAULT`` has a pull-up to upstream safety 3.3 V. A post-rail
    open-drain NAND sinks it *only* while both comparator window permissions
    and the upstream-powered ``RTD_RAIL_OK`` permission are true. Therefore
    any short/open indication, RTD_AVDD brownout, or complete post-rail power
    loss releases an active-high fault without MCU or SPI participation.
    """

    rail_ok = rtd_avdd_rail_ok(
        rtd_avdd_v=rtd_avdd_v,
        trip_v=rail_monitor_trip_v,
        corners=rail_monitor_corners,
    )
    return not (low_window_ok and high_window_ok and rail_ok)


def rtd_hardware_shutdown_asserted(
    *,
    safety_3v3_present: bool,
    low_window_ok: bool,
    high_window_ok: bool,
    rtd_avdd_v: float,
    rail_monitor_trip_v: float,
    rail_monitor_corners: RtdAvddMonitorCorners,
) -> bool:
    """Model the complete hardware outcome, including loss of safety 3.3 V.

    With safety 3.3 V present, ``RTD_HW_FAULT`` enters the SR-latch fault OR.
    With it absent, the latch may be unpowered, but the UCC21550 ``DIS``
    contract makes a floating control-side input an asserted disable. This is
    an interface claim about the gate driver, not a claim that the RTD fault
    net remains high without its pull-up supply.
    """

    if not safety_3v3_present:
        return True
    return rtd_window_fault_line_asserted(
        low_window_ok=low_window_ok,
        high_window_ok=high_window_ok,
        rtd_avdd_v=rtd_avdd_v,
        rail_monitor_trip_v=rail_monitor_trip_v,
        rail_monitor_corners=rail_monitor_corners,
    )


def derive_max31865_hardware_window(
    corners: Max31865RtdWindowCorners,
) -> Max31865RtdHardwareWindow:
    """Derive a MAX31865-specific comparator window or reject overlap."""

    if not (0.0 < corners.vbias_min_v <= corners.vbias_max_v):
        raise ValueError("VBIAS range must be positive and ordered")
    if corners.comparator_offset_abs_v < 0.0:
        raise ValueError("comparator offset must be non-negative")
    if not (0.0 <= corners.divider_tolerance_fraction < 1.0):
        raise ValueError("divider tolerance must be in [0, 1)")
    if not (0.0 <= corners.rref_tolerance_fraction < 1.0):
        raise ValueError("RREF tolerance must be in [0, 1)")
    if not (0.0 <= corners.required_margin_fraction < 1.0):
        raise ValueError("required margin must be in [0, 1)")
    if not (
        0.0
        <= corners.short_max_ohm
        < corners.valid_min_ohm
        <= corners.valid_max_ohm
        < corners.open_min_ohm
    ):
        raise ValueError("RTD resistance ranges must be ordered and non-overlapping")

    rref_min = corners.rref_nominal_ohm * (1.0 - corners.rref_tolerance_fraction)
    rref_max = corners.rref_nominal_ohm * (1.0 + corners.rref_tolerance_fraction)
    offset = corners.comparator_offset_abs_v
    divider_low = 1.0 - corners.divider_tolerance_fraction
    divider_high = 1.0 + corners.divider_tolerance_fraction
    margin = 1.0 + corners.required_margin_fraction

    short_voltage_max = max31865_rtd_voltage_v(
        corners.short_max_ohm, vbias_v=corners.vbias_max_v, rref_ohm=rref_min
    )
    valid_voltage_min = max31865_rtd_voltage_v(
        corners.valid_min_ohm, vbias_v=corners.vbias_min_v, rref_ohm=rref_max
    )
    valid_voltage_max = max31865_rtd_voltage_v(
        corners.valid_max_ohm, vbias_v=corners.vbias_max_v, rref_ohm=rref_min
    )
    open_voltage_min = max31865_rtd_voltage_v(
        corners.open_min_ohm, vbias_v=corners.vbias_min_v, rref_ohm=rref_max
    )

    low_nominal_min = (short_voltage_max + offset) / divider_low
    low_nominal_max = (valid_voltage_min / margin - offset) / divider_high
    high_nominal_min = (valid_voltage_max * margin + offset) / divider_low
    high_nominal_max = (open_voltage_min - offset) / divider_high
    if low_nominal_min > low_nominal_max:
        raise ValueError("no low threshold satisfies MAX31865 corners and margin")
    if high_nominal_min > high_nominal_max:
        raise ValueError("no high threshold satisfies MAX31865 corners and margin")
    return Max31865RtdHardwareWindow(
        corners=corners,
        low_trip_voltage_v=(low_nominal_min + low_nominal_max) / 2.0,
        high_trip_voltage_v=(high_nominal_min + high_nominal_max) / 2.0,
    )


def reference_divider_voltage_v(*, reference_v: float, top_ohm: float, bottom_ohm: float) -> float:
    """Return a grounded two-resistor threshold derived from REF2025 VBIAS."""

    if reference_v < 0.0 or top_ohm < 0.0 or bottom_ohm <= 0.0:
        raise ValueError("reference and divider values must be non-negative")
    return reference_v * bottom_ohm / (top_ohm + bottom_ohm)


def populated_rtd_window_thresholds_v(
    *,
    reference_v: float = REF2025_VBIAS_NOMINAL_V,
    low_top_ohm: float = RTD_LOW_WINDOW_TOP_OHM,
    low_bottom_ohm: float = RTD_LOW_WINDOW_BOTTOM_OHM,
    high_top_ohm: float = RTD_HIGH_WINDOW_TOP_OHM,
    high_bottom_ohm: float = RTD_HIGH_WINDOW_BOTTOM_OHM,
) -> tuple[float, float]:
    """Return the actual low/high thresholds of the captured component circuit."""

    return (
        reference_divider_voltage_v(
            reference_v=reference_v, top_ohm=low_top_ohm, bottom_ohm=low_bottom_ohm
        ),
        reference_divider_voltage_v(
            reference_v=reference_v,
            top_ohm=high_top_ohm,
            bottom_ohm=high_bottom_ohm,
        ),
    )


def spi_rc_rise_time_ns(
    *, driver_output_ohm: float, series_resistor_ohm: float, load_capacitance_pf: float
) -> float:
    """Return the 10--90% lumped-RC rise time for one MAX31865 SPI line.

    This intentionally excludes transmission-line reflection and supply-noise
    terms. Those require routed geometry and measured ESP32 output impedance;
    callers must not interpret this as an extracted-board waveform.
    """

    if driver_output_ohm < 0.0 or series_resistor_ohm < 0.0 or load_capacitance_pf < 0.0:
        raise ValueError("SPI resistance and capacitance must be non-negative")
    # ohm * pF is ps, so divide by 1000 to return ns.
    return 2.2 * (driver_output_ohm + series_resistor_ohm) * load_capacitance_pf / 1000.0


@dataclass
class SimulatedDigitalRtdService:
    """Executable model of the board-owned MAX31865 DRDY service.

    It deliberately models only the digital protocol contract: boot writes the
    threshold words and starts automatic detection, DRDY permits exactly one
    status service, and an absent completion or transport failure fails closed.
    This is not a substitute for observing SPI signal integrity or GPIO15 on
    the assembled board.
    """

    ready: bool = False
    bootstrap_failed: bool = False
    drdy_wait_ticks: int = 0
    latched_fault: RtdStatus | None = None

    def bootstrap(self, *, transport_ready: bool) -> None:
        self.ready = transport_ready
        self.bootstrap_failed = not transport_ready
        self.drdy_wait_ticks = 0
        self.latched_fault = None

    def threshold_register_writes(self) -> tuple[tuple[int, int], tuple[int, int], int]:
        """Return high/low register words and the automatic-cycle config byte."""

        low_word, high_word = threshold_codes()
        return (0x03, high_word), (0x05, low_word), MAX31865_CONFIG_AUTOMATIC_FAULT

    def control_tick(
        self,
        *,
        drdy: bool = False,
        fault_status: int = 0,
        read_ok: bool = True,
        rearm_ok: bool = True,
    ) -> RtdStatus | None:
        """Advance one 10 ms control tick and return a newly latched fault."""

        if self.latched_fault is not None:
            return self.latched_fault
        if self.bootstrap_failed:
            self.latched_fault = RtdStatus.OPEN
            return self.latched_fault
        if not self.ready:
            return None
        if not drdy:
            self.drdy_wait_ticks += 1
            if self.drdy_wait_ticks >= RTD_DRDY_TIMEOUT_CONTROL_TICKS:
                self.ready = False
                self.latched_fault = RtdStatus.OPEN
            return self.latched_fault

        self.drdy_wait_ticks = 0
        if not read_ok or not rearm_ok:
            self.ready = False
            self.latched_fault = RtdStatus.OPEN
        elif fault_status & MAX31865_FAULT_LOW_THRESHOLD:
            self.latched_fault = RtdStatus.SHORT
        elif fault_status:
            self.latched_fault = RtdStatus.OPEN
        return self.latched_fault


@dataclass(frozen=True)
class VirtualRtdBoardState:
    """Observable in-box signals from one virtual-board control tick."""

    mcu_gpio15: bool
    rtd_hardware_fault: bool
    shutdown: bool
    shutdown_bar: bool


def _set_dominant_nand_latch_step(
    s_bar: bool, r_bar: bool, q: bool, q_bar: bool
) -> tuple[bool, bool]:
    """Settle the fault-qualified NAND latch used by the UCC21550 contract."""

    for _ in range(8):
        next_q = not (s_bar and q_bar)
        next_q_bar = not (r_bar and next_q)
        q, q_bar = next_q, next_q_bar
    return q, q_bar


@dataclass
class VirtualRtdBoard:
    """Tie MAX31865/DRDY, GPIO15, and the shutdown latch into one model.

    The analogue comparator path is represented by its fault-bus output only;
    its electrical corner proof remains in :class:`RtdHardwareWindow`. This
    model proves system-level logic and timing, not board parasitics or EMI.
    """

    digital_service: SimulatedDigitalRtdService = field(default_factory=SimulatedDigitalRtdService)
    shutdown: bool = False
    shutdown_bar: bool = True

    def bootstrap(self, *, transport_ready: bool) -> None:
        self.digital_service.bootstrap(transport_ready=transport_ready)
        self.shutdown = False
        self.shutdown_bar = True

    def control_tick(
        self,
        *,
        drdy: bool = False,
        fault_status: int = 0,
        read_ok: bool = True,
        rearm_ok: bool = True,
        comparator_fault: bool = False,
        comparator_supply_present: bool = True,
        other_hardware_fault: bool = False,
        reset_request: bool = False,
    ) -> VirtualRtdBoardState:
        """Advance the virtual board by one 10 ms control tick."""

        mcu_gpio15 = (
            self.digital_service.control_tick(
                drdy=drdy,
                fault_status=fault_status,
                read_ok=read_ok,
                rearm_ok=rearm_ok,
            )
            is not None
        )
        rtd_hardware_fault = rtd_hardware_fault_asserted(
            comparator_fault=comparator_fault,
            comparator_supply_present=comparator_supply_present,
        )
        fault = mcu_gpio15 or rtd_hardware_fault or other_hardware_fault
        self.shutdown, self.shutdown_bar = _set_dominant_nand_latch_step(
            not fault,
            fault or not reset_request,
            self.shutdown,
            self.shutdown_bar,
        )
        return VirtualRtdBoardState(
            mcu_gpio15=mcu_gpio15,
            rtd_hardware_fault=rtd_hardware_fault,
            shutdown=self.shutdown,
            shutdown_bar=self.shutdown_bar,
        )


def resistance_to_code(resistance_ohm: float, rref_ohm: float = PT100_RREF_OHM) -> int:
    """Return the MAX31865 15-bit resistance code for a non-negative input."""

    if resistance_ohm <= 0.0:
        return 0
    if rref_ohm <= 0.0:
        raise ValueError("rref_ohm must be positive")
    return min(
        ADC_FULL_SCALE - 1,
        floor(ADC_FULL_SCALE * resistance_ohm / rref_ohm),
    )


def max31865_rtd_current_a(
    resistance_ohm: float,
    *,
    vbias_v: float,
    rref_ohm: float = PT100_RREF_OHM,
) -> float:
    """Return RTD excitation current from the MAX31865 voltage-source topology."""

    if resistance_ohm < 0.0 or vbias_v < 0.0 or rref_ohm <= 0.0:
        raise ValueError("RTD resistance/VBIAS must be non-negative and RREF positive")
    return vbias_v / (rref_ohm + resistance_ohm)


def max31865_rtd_voltage_v(
    resistance_ohm: float,
    *,
    vbias_v: float,
    rref_ohm: float = PT100_RREF_OHM,
) -> float:
    """Return local ``REFIN-``/``ISENSOR`` RTD-drop voltage for this front end."""

    return resistance_ohm * max31865_rtd_current_a(
        resistance_ohm, vbias_v=vbias_v, rref_ohm=rref_ohm
    )


def threshold_adc_codes(
    *,
    rref_ohm: float = PT100_RREF_OHM,
    short_ohm: float = RTD_SHORT_THRESHOLD_OHM,
    open_ohm: float = RTD_OPEN_THRESHOLD_OHM,
) -> tuple[int, int]:
    """Return inclusive low/high 15-bit ADC codes for a MAX31865.

    Rounding is conservative: a code at or below the low threshold is a short
    and a code at or above the high threshold is an open.  The caller must
    preserve ``low < high`` when applying component tolerances.
    """

    if not (0.0 < short_ohm < open_ohm):
        raise ValueError("short_ohm must be positive and below open_ohm")
    low = ceil(ADC_FULL_SCALE * short_ohm / rref_ohm)
    high = floor(ADC_FULL_SCALE * open_ohm / rref_ohm)
    if low >= high:
        raise ValueError("fault thresholds overlap")
    return low, high


def threshold_codes(
    *,
    rref_ohm: float = PT100_RREF_OHM,
    short_ohm: float = RTD_SHORT_THRESHOLD_OHM,
    open_ohm: float = RTD_OPEN_THRESHOLD_OHM,
) -> tuple[int, int]:
    """Return 16-bit MAX31865 low/high fault-register words.

    The MAX31865 threshold registers store the 15-bit resistance code in bits
    15:1; bit 0 is always zero.  This function is therefore suitable for a
    direct SPI write.  Use :func:`threshold_adc_codes` when classifying the
    15-bit value extracted from the RTD data register.
    """

    low, high = threshold_adc_codes(
        rref_ohm=rref_ohm,
        short_ohm=short_ohm,
        open_ohm=open_ohm,
    )
    return (
        low << MAX31865_THRESHOLD_REGISTER_SHIFT,
        high << MAX31865_THRESHOLD_REGISTER_SHIFT,
    )


def classify_resistance(
    resistance_ohm: float,
    *,
    short_ohm: float = RTD_SHORT_THRESHOLD_OHM,
    open_ohm: float = RTD_OPEN_THRESHOLD_OHM,
) -> RtdStatus:
    """Classify a measured resistance using inclusive fault boundaries."""

    if resistance_ohm <= short_ohm:
        return RtdStatus.SHORT
    if resistance_ohm >= open_ohm:
        return RtdStatus.OPEN
    return RtdStatus.VALID


def classify_code(code: int, *, low: int, high: int) -> RtdStatus:
    """Classify an integer MAX31865 code using inclusive thresholds."""

    if code <= low:
        return RtdStatus.SHORT
    if code >= high:
        return RtdStatus.OPEN
    return RtdStatus.VALID


def hardware_window_voltage(resistance_ohm: float, excitation_a: float) -> float:
    """Voltage seen by a high-impedance redundant window comparator.

    This is the only analogue assumption in the companion SPICE model.  The
    actual MAX31865 bias current must be measured or taken from the selected
    datasheet corner before populating comparator thresholds.
    """

    if resistance_ohm < 0.0 or excitation_a < 0.0:
        raise ValueError("resistance and excitation must be non-negative")
    return resistance_ohm * excitation_a


def derive_hardware_window(corners: RtdWindowCorners) -> RtdHardwareWindow:
    """Derive a fault-safe comparator window or reject an unsafe envelope.

    The low comparator faults below its trip voltage; the high comparator
    faults above its trip voltage. Both the RTD excitation and threshold
    network are swept independently. The required margin is measured from the
    nearest valid signal to the corresponding worst-case threshold.
    """

    if not (0.0 < corners.bias_current_min_a <= corners.bias_current_max_a):
        raise ValueError("bias-current range must be positive and ordered")
    if corners.comparator_offset_abs_v < 0.0:
        raise ValueError("comparator offset must be non-negative")
    if not (0.0 <= corners.divider_tolerance_fraction < 1.0):
        raise ValueError("divider tolerance must be in [0, 1)")
    if not (0.0 <= corners.required_margin_fraction < 1.0):
        raise ValueError("required margin must be in [0, 1)")
    if not corners.supply_loss_fault:
        raise ValueError("supply loss must assert RTD_HW_FAULT")
    if not (
        0.0
        <= corners.short_max_ohm
        < corners.valid_min_ohm
        <= corners.valid_max_ohm
        < corners.open_min_ohm
    ):
        raise ValueError("RTD resistance ranges must be ordered and non-overlapping")

    current_min = corners.bias_current_min_a
    current_max = corners.bias_current_max_a
    offset = corners.comparator_offset_abs_v
    divider_low = 1.0 - corners.divider_tolerance_fraction
    divider_high = 1.0 + corners.divider_tolerance_fraction
    margin = 1.0 + corners.required_margin_fraction

    short_voltage_max = hardware_window_voltage(corners.short_max_ohm, current_max)
    valid_voltage_min = hardware_window_voltage(corners.valid_min_ohm, current_min)
    valid_voltage_max = hardware_window_voltage(corners.valid_max_ohm, current_max)
    open_voltage_min = hardware_window_voltage(corners.open_min_ohm, current_min)

    # A short must be below even the minimum actual low threshold; a valid
    # cold PT100 must sit above even the maximum actual low threshold.
    low_nominal_min = (short_voltage_max + offset) / divider_low
    low_nominal_max = (valid_voltage_min / margin - offset) / divider_high

    # A valid hot PT100 must sit below even the minimum actual high threshold;
    # an open circuit must exceed even the maximum actual high threshold.
    high_nominal_min = (valid_voltage_max * margin + offset) / divider_low
    high_nominal_max = (open_voltage_min - offset) / divider_high

    if low_nominal_min > low_nominal_max:
        raise ValueError("no low-threshold window satisfies fault coverage and margin")
    if high_nominal_min > high_nominal_max:
        raise ValueError("no high-threshold window satisfies fault coverage and margin")

    return RtdHardwareWindow(
        corners=corners,
        low_trip_voltage_v=(low_nominal_min + low_nominal_max) / 2.0,
        high_trip_voltage_v=(high_nominal_min + high_nominal_max) / 2.0,
    )


def rtd_hardware_fault_asserted(*, comparator_fault: bool, comparator_supply_present: bool) -> bool:
    """Model the asynchronous RTD contribution to the hardware fault bus.

    This deliberately accepts neither an MCU state nor an SPI status: the
    comparator path must remain independent of both. Loss of comparator power
    is itself a fault so the downstream OR/latch cannot be deasserted by a
    failed sensor-front-end supply.
    """

    return comparator_fault or not comparator_supply_present
