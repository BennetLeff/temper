/**
 * @file test_c1_runtime.c
 * @brief TEMPER_PAN_CONTROL_C1 runtime: the state machine driving the C1 loop
 *        through main/pan_control.c, with the C1 runaway checks (D-RUN).
 *
 * rtd_service_latest_sample() and rim_ntc_board_hal() are stubbed here so
 * each test sets the MAX31865 conversion and the rim temperature directly;
 * the rtd_service C1 conversion path itself is covered by
 * test_c1_rtd_service.c, the rim driver by test_c1_rim_ntc.c.
 */

#include <math.h>
#include <string.h>

#include "unity/unity.h"
#include "../main/state_machine.h"
#include "../main/pan_control.h"
#include "../components/sensors/include/rim_ntc.h"
#include "../components/sensors/include/rtd_service.h"

extern void mock_sm_reset(void);
extern void mock_sm_advance_time(uint32_t ms);
extern void mock_sm_set_pan_status(int status);
extern void mock_sm_set_dc_bus_current(float amps);
extern uint32_t mock_sm_get_power_level(void);

#define MOCK_PAN_PRESENT 1

static rtd_sample_t s_smp;
static bool s_have;
static float s_rim = 40.0f;

bool rtd_service_latest_sample(rtd_sample_t *out)
{
    if (!s_have || out == NULL) {
        return false;
    }
    *out = s_smp;
    return true;
}

/* Rim NTC board HAL: the node voltage of the 104GT-2 at s_rim under the
 * 1.00 k pull-up and a 3300 mV rail, clipped as the ADC clips and rounded to
 * whole mV (the ESP-IDF calibration returns integer mV). s_rim_node_mv forces
 * a node voltage (short, open), s_rim_adc_fail fails every read. */
static float s_rim_node_mv = NAN;
static bool s_rim_adc_fail;

static bool rim_read_node(void *ctx, rim_atten_t atten, float *mv)
{
    (void)ctx;
    if (s_rim_adc_fail) {
        return false;
    }
    float v = s_rim_node_mv;
    if (!isfinite(v)) {
        const float r = rim_ntc_c_to_r(s_rim);
        v = 3300.0f * r / (r + 1000.0f);
    }
    const float clip = atten == RIM_ATTEN_0 ? 950.0f : (atten == RIM_ATTEN_2 ? 1700.0f : 3100.0f);
    *mv = roundf(v < clip ? v : clip);
    return true;
}

static bool rim_read_rail(void *ctx, float *mv)
{
    (void)ctx;
    *mv = 3300.0f;
    return true;
}

static const rim_ntc_hal_t s_rim_hal = {.read_node_mv = rim_read_node, .read_v3v3_mv = rim_read_rail, .ctx = NULL};
const rim_ntc_hal_t *rim_ntc_board_hal(void) { return &s_rim_hal; }

static void set_reading(float t_c)
{
    /* Callendar-Van Dusen T >= 0 for the resistance; the code is not used. */
    s_smp.t_c = t_c;
    s_smp.r_ohm = 100.0f * (1.0f + 3.9083e-3f * t_c - 5.775e-7f * t_c * t_c);
    s_smp.spi_ok = true;
    s_smp.fault_status = 0u;
    s_smp.seq++;
    s_have = true;
}

/* 10 ms state-machine ticks; a fresh conversion every other tick. */
static void run_ms(uint32_t ms, float (*reading)(uint32_t), uint32_t *clock)
{
    for (uint32_t t = 0; t < ms; t += 10u) {
        mock_sm_advance_time(10u);
        *clock += 10u;
        if (reading != NULL && (*clock % 20u) == 0u) {
            set_reading(reading(*clock));
        }
        state_machine_update();
    }
}

static uint32_t s_clock;
static float s_hold_t;
static float hold(uint32_t t_ms) { (void)t_ms; return s_hold_t; }

static void start(system_state_t st, float target, uint8_t intensity, float t0)
{
    mock_sm_reset();
    memset(&s_smp, 0, sizeof(s_smp));
    s_have = false;
    s_clock = 0u;
    s_rim = 40.0f;
    s_rim_node_mv = NAN;
    s_rim_adc_fail = false;
    mock_sm_advance_time(1000u);
    state_machine_init();
    mock_sm_set_pan_status(MOCK_PAN_PRESENT);
    state_machine_set_target_temp(target);
    state_machine_set_intensity(intensity);
    set_reading(t0);
    state_machine_reset_temp_baseline();
    state_machine_force_state(st);
}

static void test_no_runaway_latch_before_the_first_conversion(void)
{
    mock_sm_reset();
    memset(&s_smp, 0, sizeof(s_smp));
    s_have = false;
    state_machine_init();
    state_machine_force_state(STATE_IDLE);
    run_ms(1000u, NULL, &s_clock);
    TEST_ASSERT_EQUAL_INT(STATE_IDLE, state_machine_get_state());
}

static uint32_t s_place_ms;
static float placed_hot_pan(uint32_t t_ms)
{
    if (t_ms < s_place_ms) {
        return 25.0f;
    }
    return 240.0f - 215.0f * expf(-(float)(t_ms - s_place_ms) / 1350.0f);
}

static void test_hot_pan_placed_in_idle_does_not_latch_runaway(void)
{
    start(STATE_IDLE, 200.0f, 10u, 25.0f);
    s_place_ms = s_clock + 1000u;
    run_ms(20000u, placed_hot_pan, &s_clock);
    TEST_ASSERT_TRUE(state_machine_get_state() != STATE_RUNAWAY_FAULT);
    TEST_ASSERT_EQUAL_INT(FAULT_NONE, state_machine_get_fault());
}

static void test_absolute_300_still_latches_runaway(void)
{
    start(STATE_HEATING, 200.0f, 10u, 200.0f);
    s_hold_t = 305.0f;
    run_ms(30u, hold, &s_clock);
    TEST_ASSERT_EQUAL_INT(STATE_RUNAWAY_FAULT, state_machine_get_state());
    TEST_ASSERT_EQUAL_INT(FAULT_RUNAWAY_BOUNDARY, state_machine_get_fault());
}

static void test_preheat_heats_and_hands_over_on_the_estimate(void)
{
    start(STATE_PREHEAT, 200.0f, 10u, 25.0f);
    s_hold_t = 25.0f;
    run_ms(500u, hold, &s_clock);
    TEST_ASSERT_EQUAL_INT(STATE_PREHEAT, state_machine_get_state());
    TEST_ASSERT_TRUE(mock_sm_get_power_level() > 0u);
    s_hold_t = 195.0f;
    run_ms(5000u, hold, &s_clock);
    TEST_ASSERT_EQUAL_INT(STATE_HEATING, state_machine_get_state());
    TEST_ASSERT_TRUE(pan_control_t_hat() >= 190.0f);
}

static void test_intensity_limits_the_loop_power(void)
{
    start(STATE_PREHEAT, 200.0f, 3u, 25.0f);
    s_hold_t = 25.0f;
    for (int i = 0; i < 20; i++) {
        run_ms(100u, hold, &s_clock);
        TEST_ASSERT_TRUE(mock_sm_get_power_level() <= 30u);
    }
    TEST_ASSERT_TRUE(mock_sm_get_power_level() > 0u);
}

static void test_reading_over_target_plus_10_holds_power_off_without_latching(void)
{
    /* h_c drop: T_c up to target + 13 K (legacy latched FAULT_THERMAL_RUNAWAY) */
    start(STATE_HEATING, 200.0f, 10u, 200.0f);
    s_hold_t = 213.0f;
    run_ms(30000u, hold, &s_clock);
    TEST_ASSERT_EQUAL_INT(STATE_HEATING, state_machine_get_state());
    TEST_ASSERT_EQUAL_INT(FAULT_NONE, state_machine_get_fault());
    TEST_ASSERT_EQUAL_UINT32(0u, mock_sm_get_power_level());
}

static void test_lowered_target_does_not_latch(void)
{
    start(STATE_HEATING, 200.0f, 10u, 200.0f);
    s_hold_t = 200.0f;
    run_ms(2000u, hold, &s_clock);
    state_machine_set_target_temp(170.0f);
    for (int i = 0; i < 300; i++) {
        s_hold_t -= 0.1f;   /* cooling with the power off */
        run_ms(100u, hold, &s_clock);
    }
    TEST_ASSERT_EQUAL_INT(STATE_HEATING, state_machine_get_state());
    TEST_ASSERT_EQUAL_INT(FAULT_NONE, state_machine_get_fault());
}

static void test_power_stage_drawing_current_with_power_off_latches_thermal_runaway(void)
{
    start(STATE_HEATING, 200.0f, 10u, 200.0f);
    s_hold_t = 215.0f;
    run_ms(1000u, hold, &s_clock);
    TEST_ASSERT_EQUAL_INT(STATE_HEATING, state_machine_get_state());
    mock_sm_set_dc_bus_current(10.0f);
    run_ms(1500u, hold, &s_clock);
    TEST_ASSERT_EQUAL_INT(STATE_FAULT, state_machine_get_state());
    TEST_ASSERT_EQUAL_INT(FAULT_THERMAL_RUNAWAY, state_machine_get_fault());
}

static void test_still_rising_with_power_off_latches_thermal_runaway(void)
{
    /* stuck-on stage and a current sense reading 0: 2b after 20 s */
    start(STATE_HEATING, 200.0f, 10u, 200.0f);
    s_hold_t = 211.0f;
    uint32_t elapsed = 0u;
    while (state_machine_get_state() == STATE_HEATING && elapsed < 60000u) {
        s_hold_t += 0.03f;    /* 3 K/s */
        run_ms(10u, hold, &s_clock);
        elapsed += 10u;
    }
    TEST_ASSERT_EQUAL_INT(STATE_FAULT, state_machine_get_state());
    TEST_ASSERT_EQUAL_INT(FAULT_THERMAL_RUNAWAY, state_machine_get_fault());
    TEST_ASSERT_TRUE(elapsed >= 20000u && elapsed <= 21000u);
}

static void test_rtd_resistance_interlock_uses_the_c1_window(void)
{
    start(STATE_HEATING, 200.0f, 10u, 200.0f);
    s_hold_t = 200.0f;
    run_ms(200u, hold, &s_clock);
    /* 80 ohm: inside the legacy 10..300 ohm window, below the C1 84.27 ohm */
    s_smp.r_ohm = 80.0f;
    s_smp.t_c = -50.0f;
    s_smp.seq++;
    mock_sm_advance_time(10u);
    state_machine_update();
    TEST_ASSERT_EQUAL_INT(STATE_FAULT, state_machine_get_state());
    TEST_ASSERT_EQUAL_INT(FAULT_PROBE_SHORT, state_machine_get_fault());
}

static void test_leaving_heating_stops_the_loop(void)
{
    start(STATE_HEATING, 200.0f, 10u, 150.0f);
    s_hold_t = 150.0f;
    run_ms(500u, hold, &s_clock);
    TEST_ASSERT_TRUE(pan_control_is_running());
    state_machine_force_state(STATE_COOLDOWN);
    TEST_ASSERT_FALSE(pan_control_is_running());
    TEST_ASSERT_EQUAL_UINT32(0u, mock_sm_get_power_level());
}


/* ---- rim NTC in the loop (DECISIONS.md D-XCHK, D-RIM) ------------------ */

static float s_ramp_t0;
static uint32_t s_ramp_ms0;
static float s_ramp_k_per_s;
static float ramp(uint32_t t_ms)
{
    return s_ramp_t0 + s_ramp_k_per_s * (float)(t_ms - s_ramp_ms0) / 1000.0f;
}

/* A Pt100 that reads low and does not follow the heating (stuck, or
 * element-parallel leakage at a hold), with the rim NTC valid and hot. */
static void test_rim_cross_check_fires_on_a_low_flat_pt100(void)
{
    start(STATE_HEATING, 200.0f, 10u, 180.0f);
    s_rim = 215.0f;               /* reading 180 < 215 - 25 */
    s_hold_t = 180.0f;
    run_ms(29000u, hold, &s_clock);
    TEST_ASSERT_EQUAL_UINT32(0u, pan_control_xcheck_suspects());
    run_ms(2500u, hold, &s_clock);
    TEST_ASSERT_EQUAL_UINT32(1u, pan_control_xcheck_suspects());
    rim_ntc_reading_t rd;
    TEST_ASSERT_TRUE(pan_control_rim_reading(&rd));
    TEST_ASSERT_FLOAT_WITHIN(0.3f, 215.0f, read_rim_ntc_temperature());
    /* A suspect asks D1 for a probe; it is not a fault. */
    TEST_ASSERT_EQUAL_INT(FAULT_NONE, state_machine_get_fault());
}

/* Cold-food quench: the reading sits 40 K below the hot rim but rises as the
 * loop reheats the load, so the count keeps restarting. */
static void test_rim_cross_check_ignores_a_cold_food_quench(void)
{
    start(STATE_HEATING, 200.0f, 10u, 150.0f);
    s_rim = 190.0f;
    s_ramp_t0 = 150.0f;
    s_ramp_ms0 = s_clock;
    s_ramp_k_per_s = 0.25f;       /* 7.5 K per 30 s: rising, as a reheating load does */
    run_ms(50000u, ramp, &s_clock);
    /* still below rim - 25 K after 50 s, with the power on for 40 s of it */
    TEST_ASSERT_TRUE(ramp(s_clock) < 190.0f - 25.0f);
    TEST_ASSERT_EQUAL_UINT32(0u, pan_control_xcheck_suspects());
    TEST_ASSERT_TRUE(mock_sm_get_power_level() > 0u);   /* no probe either */
    TEST_ASSERT_EQUAL_INT(FAULT_NONE, state_machine_get_fault());
}

/* A saturated (cold) rim carries no information: no cross-check, even with a
 * flat reading below the saturation bound minus 25 K. */
static void test_saturated_rim_never_cross_checks(void)
{
    start(STATE_HEATING, 200.0f, 10u, 60.0f);
    s_rim = 80.0f;                /* below the ~92 degC saturation bound */
    s_hold_t = 60.0f;
    run_ms(35000u, hold, &s_clock);
    rim_ntc_reading_t rd;
    TEST_ASSERT_FALSE(pan_control_rim_reading(&rd));
    TEST_ASSERT_EQUAL_INT(RIM_NTC_SATURATED, rd.state);
    TEST_ASSERT_TRUE(isnan(read_rim_ntc_temperature()));
    TEST_ASSERT_EQUAL_UINT32(0u, pan_control_xcheck_suspects());
    TEST_ASSERT_TRUE(isfinite(pan_control_t_hat()));
}

static void test_rim_short_latches_probe_short_and_cuts_power(void)
{
    start(STATE_HEATING, 200.0f, 10u, 190.0f);
    s_rim = 170.0f;
    s_hold_t = 190.0f;
    run_ms(2000u, hold, &s_clock);
    TEST_ASSERT_TRUE(mock_sm_get_power_level() > 0u);
    s_rim_node_mv = 120.0f;       /* < 0.25 V */
    run_ms(200u, hold, &s_clock); /* two periods: still a candidate */
    TEST_ASSERT_EQUAL_INT(STATE_HEATING, state_machine_get_state());
    run_ms(200u, hold, &s_clock);
    TEST_ASSERT_EQUAL_INT(STATE_FAULT, state_machine_get_state());
    TEST_ASSERT_EQUAL_INT(FAULT_PROBE_SHORT, state_machine_get_fault());
    TEST_ASSERT_EQUAL_UINT32(0u, mock_sm_get_power_level());
}

static void test_rim_open_latches_probe_open_after_600s_hot(void)
{
    start(STATE_HEATING, 200.0f, 10u, 200.0f);
    s_rim_node_mv = 3300.0f;      /* open bead: full scale */
    s_hold_t = 200.0f;
    run_ms(598000u, hold, &s_clock);
    TEST_ASSERT_EQUAL_INT(STATE_HEATING, state_machine_get_state());
    run_ms(3000u, hold, &s_clock);
    TEST_ASSERT_EQUAL_INT(STATE_FAULT, state_machine_get_state());
    TEST_ASSERT_EQUAL_INT(FAULT_PROBE_OPEN, state_machine_get_fault());
}

static void test_rim_adc_failure_latches_probe_open(void)
{
    start(STATE_HEATING, 200.0f, 10u, 190.0f);
    s_rim = 170.0f;
    s_hold_t = 190.0f;
    run_ms(1000u, hold, &s_clock);
    s_rim_adc_fail = true;
    run_ms(900u, hold, &s_clock);  /* nine periods: held */
    TEST_ASSERT_EQUAL_INT(STATE_HEATING, state_machine_get_state());
    run_ms(200u, hold, &s_clock);
    TEST_ASSERT_EQUAL_INT(STATE_FAULT, state_machine_get_state());
    TEST_ASSERT_EQUAL_INT(FAULT_PROBE_OPEN, state_machine_get_fault());
}

void run_c1_runtime_tests(void)
{
    RUN_TEST(test_no_runaway_latch_before_the_first_conversion);
    RUN_TEST(test_hot_pan_placed_in_idle_does_not_latch_runaway);
    RUN_TEST(test_absolute_300_still_latches_runaway);
    RUN_TEST(test_preheat_heats_and_hands_over_on_the_estimate);
    RUN_TEST(test_intensity_limits_the_loop_power);
    RUN_TEST(test_reading_over_target_plus_10_holds_power_off_without_latching);
    RUN_TEST(test_lowered_target_does_not_latch);
    RUN_TEST(test_power_stage_drawing_current_with_power_off_latches_thermal_runaway);
    RUN_TEST(test_still_rising_with_power_off_latches_thermal_runaway);
    RUN_TEST(test_rtd_resistance_interlock_uses_the_c1_window);
    RUN_TEST(test_leaving_heating_stops_the_loop);
    RUN_TEST(test_rim_cross_check_fires_on_a_low_flat_pt100);
    RUN_TEST(test_rim_cross_check_ignores_a_cold_food_quench);
    RUN_TEST(test_saturated_rim_never_cross_checks);
    RUN_TEST(test_rim_short_latches_probe_short_and_cuts_power);
    RUN_TEST(test_rim_open_latches_probe_open_after_600s_hot);
    RUN_TEST(test_rim_adc_failure_latches_probe_open);
}
