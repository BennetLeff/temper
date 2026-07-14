"""Property-based checks for the bounded UCC21550 DT model."""

from hypothesis import given
from hypothesis import strategies as st
from ucc21550_dt_sim import (
    DTCorners,
    corner_results,
    corner_summary,
    effective_dead_time_ns,
    meets_programmed_dead_time,
    programmed_dead_time_ns,
    recommended_resistor_for_requirement,
    resistor_at_temperature,
)


def test_34k_nominal_and_corners_are_reported_explicitly() -> None:
    assert programmed_dead_time_ns(34.0) == 305.4
    minimum, maximum = corner_summary()
    assert 270.0 < minimum < 271.0
    assert 343.0 < maximum < 344.0
    # The 34-kOhm choice is a nominal starting point, not a 300-ns
    # all-corners guarantee under the stated +/-10% device envelope.
    assert not meets_programmed_dead_time()


def test_39k_clears_300ns_under_stated_assumptions() -> None:
    corners = DTCorners(resistor_kohm=39.0)
    assert meets_programmed_dead_time(corners=corners)
    recommendation = recommended_resistor_for_requirement()
    # The cold corner is the minimum resistance for the positive 100-ppm/°C
    # TCR assumption.  A hot-only calculation would incorrectly return about
    # 37.16 kΩ; the complete -40/25/150 °C sweep requires about 37.87 kΩ.
    assert 37.8 < recommendation < 37.9
    assert recommendation < 39.0


def test_recommendation_meets_requirement_at_every_temperature_corner() -> None:
    recommendation = recommended_resistor_for_requirement()
    corners = DTCorners(resistor_kohm=recommendation)
    assert meets_programmed_dead_time(corners=corners)


def test_recommendation_rejects_empty_temperature_envelope() -> None:
    try:
        recommended_resistor_for_requirement(temperatures_c=())
    except ValueError as exc:
        assert "temperatures_c" in str(exc)
    else:
        raise AssertionError("empty temperature envelope must be rejected")


def test_300ns_mcpwm_dead_time_remains_the_system_floor() -> None:
    # TI specifies that the output interval is the longer of the programmed
    # DT and the input signal's own dead time.  Thus the existing 300-ns
    # MCPWM setting still enforces a 300-ns *system* floor, even though 34 kΩ
    # is not sufficient to guarantee a 300-ns hardware-only floor.
    effective = [effective_dead_time_ns(value, 300.0) for value in corner_results()]
    assert min(effective) == 300.0


@given(
    resistor_kohm=st.floats(min_value=1.7, max_value=100.0, allow_nan=False),
    scale=st.floats(min_value=0.5, max_value=1.5, allow_nan=False),
)
def test_programmed_dead_time_is_monotonic_in_resistance(
    resistor_kohm: float, scale: float
) -> None:
    assert programmed_dead_time_ns(resistor_kohm, scale) >= programmed_dead_time_ns(
        1.7, scale
    )


@given(
    programmed=st.floats(min_value=0.0, max_value=2_000.0, allow_nan=False),
    input_dead_time=st.floats(min_value=0.0, max_value=2_000.0, allow_nan=False),
)
def test_driver_uses_the_longer_programmed_or_input_dead_time(
    programmed: float, input_dead_time: float
) -> None:
    effective = effective_dead_time_ns(programmed, input_dead_time)
    assert effective >= programmed
    assert effective >= input_dead_time


@given(
    nominal=st.floats(min_value=1.7, max_value=100.0, allow_nan=False),
    tolerance=st.floats(min_value=0.0, max_value=0.1, allow_nan=False),
    tcr=st.floats(min_value=0.0, max_value=500.0, allow_nan=False),
    temperature=st.floats(min_value=-40.0, max_value=150.0, allow_nan=False),
)
def test_resistor_model_stays_positive(
    nominal: float, tolerance: float, tcr: float, temperature: float
) -> None:
    resistance = resistor_at_temperature(nominal, tolerance, tcr, temperature)
    assert resistance > 0.0


@given(
    tcr=st.floats(min_value=-500.0, max_value=500.0, allow_nan=False),
    temperatures=st.lists(
        st.floats(min_value=-40.0, max_value=150.0, allow_nan=False),
        min_size=1,
        max_size=8,
    ),
)
def test_recommendation_is_sound_for_all_supplied_tcr_temperature_corners(
    tcr: float, temperatures: list[float]
) -> None:
    recommendation = recommended_resistor_for_requirement(
        tcr_ppm_per_c=tcr,
        temperatures_c=tuple(temperatures),
    )
    programmed_corners = [
        programmed_dead_time_ns(
            resistor_at_temperature(recommendation, 0.01, tcr, temperature),
            0.90,
        )
        for temperature in temperatures
    ]
    assert min(programmed_corners) >= 300.0 - 1e-9
