"""Property tests for the dual PT100 safety-path threshold model."""

from pathlib import Path

from hypothesis import given, settings
from hypothesis import strategies as st

from temper_placer.validation.rtd_safety import (
    ADC_FULL_SCALE,
    MAX31865_CONFIG_AUTOMATIC_FAULT,
    MAX31865_FAULT_LOW_THRESHOLD,
    MAX31865_LOGIC_INPUT_CAPACITANCE_PF,
    MAX31865_SPI_RISE_FALL_LIMIT_NS,
    MAX31865_SPI_TIMING_LOAD_CAPACITANCE_PF,
    MAX31865_VBIAS_MAX_V,
    MAX31865_VBIAS_MIN_V,
    PT100_RREF_OHM,
    PT100_RREF_TOLERANCE_FRACTION,
    PT100_VALID_MAX_OHM,
    PT100_VALID_MIN_OHM,
    RTD_DRDY_TIMEOUT_CONTROL_TICKS,
    RTD_OPEN_THRESHOLD_OHM,
    RTD_SHORT_THRESHOLD_OHM,
    SPI_SERIES_RESISTOR_MAX_OHM,
    SPI_SERIES_RESISTOR_MIN_OHM,
    RtdStatus,
    SimulatedDigitalRtdService,
    VirtualRtdBoard,
    classify_code,
    classify_resistance,
    hardware_window_voltage,
    max31865_rtd_current_a,
    max31865_rtd_voltage_v,
    resistance_to_code,
    spi_rc_rise_time_ns,
    threshold_adc_codes,
    threshold_codes,
)


@st.composite
def _rref_corners(draw: st.DrawFn) -> float:
    return draw(
        st.floats(
            min_value=PT100_RREF_OHM * 0.99,
            max_value=PT100_RREF_OHM * 1.01,
        )
    )


@given(
    resistances=st.lists(
        st.floats(min_value=0, max_value=10_000), min_size=2, max_size=20
    )
)
@settings(max_examples=150, deadline=10_000)
def test_adc_code_is_monotonic(resistances: list[float]) -> None:
    ordered = sorted(resistances)
    codes = [resistance_to_code(r) for r in ordered]
    assert codes == sorted(codes)
    assert all(0 <= code < ADC_FULL_SCALE for code in codes)


@given(rref=_rref_corners())
@settings(max_examples=100, deadline=10_000)
def test_fault_code_window_remains_separated_at_rref_tolerance(rref: float) -> None:
    low, high = threshold_adc_codes(rref_ohm=rref)
    assert low < high
    assert classify_code(low, low=low, high=high) is RtdStatus.SHORT
    assert classify_code(high, low=low, high=high) is RtdStatus.OPEN
    # The nominal PT100 operating range is never classified as a fault.
    assert classify_resistance(100.0) is RtdStatus.VALID
    assert classify_resistance(194.1) is RtdStatus.VALID


def test_fault_threshold_words_encode_the_15_bit_code_in_bits_15_to_1() -> None:
    """The serial register payload must not halve the physical thresholds."""

    low_adc, high_adc = threshold_adc_codes()
    low_register, high_register = threshold_codes()
    assert (low_adc, high_adc) == (763, 22861)
    assert (low_register, high_register) == (1526, 45722)
    assert low_register == low_adc << 1
    assert high_register == high_adc << 1
    assert low_register & 1 == 0
    assert high_register & 1 == 0


@given(
    short=st.floats(min_value=0, max_value=RTD_SHORT_THRESHOLD_OHM),
    open_resistance=st.floats(min_value=RTD_OPEN_THRESHOLD_OHM, max_value=1e6),
)
@settings(max_examples=150, deadline=10_000)
def test_fault_boundaries_are_fail_safe(short: float, open_resistance: float) -> None:
    assert classify_resistance(short) is RtdStatus.SHORT
    assert classify_resistance(open_resistance) is RtdStatus.OPEN


def test_simulated_service_writes_the_production_threshold_words() -> None:
    service = SimulatedDigitalRtdService()
    high, low, config = service.threshold_register_writes()
    assert high == (0x03, 0xB29A)
    assert low == (0x05, 0x05F6)
    assert config == MAX31865_CONFIG_AUTOMATIC_FAULT


def test_esp32_spi_configuration_meets_max31865_cs_timing_at_five_mhz() -> None:
    """Static timing model for the production SPI configuration.

    The MAX31865 datasheet requires 400 ns CS setup and 100 ns CS hold at up
    to 5 MHz. Checking the configured cycle counts at the *maximum* supported
    clock makes the current 500 kHz setting a strict subset of this proof.
    """

    source = (
        Path(__file__).resolve().parents[4]
        / "firmware/components/hal/esp32/hal_spi_esp32.c"
    ).read_text(encoding="utf-8")
    assert "#define MAX31865_CS_SETUP_CYCLES 2" in source
    assert "#define MAX31865_CS_HOLD_CYCLES  1" in source
    assert ".cs_ena_pretrans = MAX31865_CS_SETUP_CYCLES" in source
    assert ".cs_ena_posttrans = MAX31865_CS_HOLD_CYCLES" in source

    max_clock_hz = 5_000_000
    cs_setup_ns = 2 / max_clock_hz * 1e9
    cs_hold_ns = 1 / max_clock_hz * 1e9
    assert cs_setup_ns >= 400
    assert cs_hold_ns >= 100


@given(
    driver_output_ohm=st.floats(min_value=0.0, max_value=1_000.0),
    series_resistor_ohm=st.floats(
        min_value=SPI_SERIES_RESISTOR_MIN_OHM,
        max_value=SPI_SERIES_RESISTOR_MAX_OHM,
    ),
    load_capacitance_pf=st.floats(
        min_value=MAX31865_LOGIC_INPUT_CAPACITANCE_PF,
        max_value=MAX31865_SPI_TIMING_LOAD_CAPACITANCE_PF,
    ),
)
@settings(max_examples=200, deadline=10_000)
def test_spi_damping_network_meets_rise_time_limit_in_declared_rc_envelope(
    driver_output_ohm: float,
    series_resistor_ohm: float,
    load_capacitance_pf: float,
) -> None:
    """The 33 ohm network meets 200 ns with a deliberately weak 1 kohm driver.

    This is a bounded RC result, not a claim about reflection/EMI on an
    unrouted board; those terms are explicitly outside the model.
    """

    assert (
        spi_rc_rise_time_ns(
            driver_output_ohm=driver_output_ohm,
            series_resistor_ohm=series_resistor_ohm,
            load_capacitance_pf=load_capacitance_pf,
        )
        <= MAX31865_SPI_RISE_FALL_LIMIT_NS
    )


@given(
    resistance_ohm=st.floats(
        min_value=PT100_VALID_MIN_OHM,
        max_value=PT100_VALID_MAX_OHM,
    ),
    vbias_v=st.floats(min_value=MAX31865_VBIAS_MIN_V, max_value=MAX31865_VBIAS_MAX_V),
    rref_ohm=st.floats(
        min_value=PT100_RREF_OHM * (1.0 - PT100_RREF_TOLERANCE_FRACTION),
        max_value=PT100_RREF_OHM * (1.0 + PT100_RREF_TOLERANCE_FRACTION),
    ),
)
@settings(max_examples=200, deadline=10_000)
def test_max31865_pt100_excitation_model_respects_vbias_and_rref_corners(
    resistance_ohm: float, vbias_v: float, rref_ohm: float
) -> None:
    """The VBIAS/RREF divider model is monotonic and physically bounded."""

    current_a = max31865_rtd_current_a(
        resistance_ohm, vbias_v=vbias_v, rref_ohm=rref_ohm
    )
    voltage_v = max31865_rtd_voltage_v(
        resistance_ohm, vbias_v=vbias_v, rref_ohm=rref_ohm
    )
    assert current_a > 0.0
    assert 0.0 < voltage_v < vbias_v
    assert voltage_v == resistance_ohm * current_a


@given(
    drdy_delay_ticks=st.integers(min_value=0, max_value=30),
    fault_status=st.integers(min_value=0, max_value=0xFF),
    read_ok=st.booleans(),
    rearm_ok=st.booleans(),
)
@settings(max_examples=300, deadline=10_000)
def test_digital_rtd_service_fails_closed_for_all_cycle_outcomes(
    drdy_delay_ticks: int,
    fault_status: int,
    read_ok: bool,
    rearm_ok: bool,
) -> None:
    """Generated DRDY/status schedules cannot leave an unsafe path unlatched."""

    service = SimulatedDigitalRtdService()
    service.bootstrap(transport_ready=True)
    for _ in range(drdy_delay_ticks):
        service.control_tick()

    if drdy_delay_ticks >= RTD_DRDY_TIMEOUT_CONTROL_TICKS:
        assert service.latched_fault is RtdStatus.OPEN
        return

    result = service.control_tick(
        drdy=True,
        fault_status=fault_status,
        read_ok=read_ok,
        rearm_ok=rearm_ok,
    )
    if not read_ok or not rearm_ok:
        assert result is RtdStatus.OPEN
    elif fault_status & MAX31865_FAULT_LOW_THRESHOLD:
        assert result is RtdStatus.SHORT
    elif fault_status:
        assert result is RtdStatus.OPEN
    else:
        assert result is None


@given(transport_ready=st.booleans())
def test_digital_rtd_bootstrap_is_fail_closed(transport_ready: bool) -> None:
    service = SimulatedDigitalRtdService()
    service.bootstrap(transport_ready=transport_ready)
    result = service.control_tick()
    if transport_ready:
        assert result is None
    else:
        assert result is RtdStatus.OPEN


@st.composite
def _virtual_board_event(draw: st.DrawFn) -> dict[str, bool | int]:
    return {
        "drdy": draw(st.booleans()),
        "fault_status": draw(st.integers(min_value=0, max_value=0xFF)),
        "read_ok": draw(st.booleans()),
        "rearm_ok": draw(st.booleans()),
        "comparator_fault": draw(st.booleans()),
        "comparator_supply_present": draw(st.booleans()),
        "other_hardware_fault": draw(st.booleans()),
        "reset_request": draw(st.booleans()),
    }


@given(events=st.lists(_virtual_board_event(), min_size=1, max_size=50))
@settings(max_examples=250, deadline=10_000)
def test_virtual_board_faults_reach_latched_shutdown(
    events: list[dict[str, bool | int]],
) -> None:
    """Generated SPI/DRDY/comparator sequences cannot bypass shutdown."""

    board = VirtualRtdBoard()
    board.bootstrap(transport_ready=True)
    for event in events:
        state = board.control_tick(**event)
        if (
            state.mcu_gpio15
            or state.rtd_hardware_fault
            or bool(event["other_hardware_fault"])
        ):
            assert state.shutdown is True
        assert state.shutdown_bar is (not state.shutdown)


@given(
    lower=st.floats(min_value=0, max_value=1e6),
    delta=st.floats(min_value=0, max_value=1e6),
    excitation=st.floats(min_value=0, max_value=0.01),
)
@settings(max_examples=150, deadline=10_000)
def test_redundant_window_voltage_is_monotonic(
    lower: float, delta: float, excitation: float
) -> None:
    """The analogue monitor cannot turn a larger resistance into a lower V."""

    upper = lower + delta
    assert hardware_window_voltage(upper, excitation) >= hardware_window_voltage(
        lower, excitation
    )
