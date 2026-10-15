/**
 * @file test_c1_runtime.c
 * @brief TEMPER_PAN_CONTROL_C1 runtime: the state machine driving the C1 loop
 *        through main/pan_control.c, with the C1 runaway checks (D-RUN).
 *
 * rtd_service_latest_sample() and read_rim_ntc_temperature() are stubbed here
 * so each test sets the MAX31865 conversion directly; the rtd_service C1
 * conversion path itself is covered by test_c1_rtd_service.c.
 */

#include <math.h>
#include <string.h>

#include "unity/unity.h"
#include "../main/state_machine.h"
#include "../main/pan_control.h"
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

float read_rim_ntc_temperature(void) { return s_rim; }

/* The converter service is not linked here; it is running whenever a
 * conversion has been set (test_c1_rtd_service.c covers it stopping). */
bool rtd_service_is_ready(void) { return s_have; }

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
}
