/**
 * @file test_c1_units.c
 * @brief sensor-r3 C1 runtime units: runaway supervisor (pan_supervisor.c)
 *        and MAX31865 code conversion (rtd_convert.c).
 *
 * Scenario values mirror output/temper-sensor-r3/firmware/runaway_checks.py
 * (DECISIONS.md D-RUN): a preheated pan placed on the disc, an h_c drop, a
 * lowered target, a power stage stuck on with and without bus-current sense.
 */

#include <math.h>

#include "unity/unity.h"
#include "../components/control/pan_supervisor.h"
#include "../components/sensors/include/rtd_convert.h"

static psup_t sup;
static psup_params_t prm;

static void sup_new(void)
{
    psup_default_params(&prm);
    TEST_ASSERT_TRUE(psup_init(&sup, &prm));
}

/* ---- R1 sustained rise ---------------------------------------------------- */

/* Feed 10 ms readings of temp(t) for n_ms; returns the first trip time or 0. */
static uint32_t r1_feed(float (*temp)(uint32_t), uint32_t t0_ms, uint32_t n_ms)
{
    for (uint32_t t = t0_ms; t < t0_ms + n_ms; t += 10u) {
        if (psup_rate_sample(&sup, temp(t), t)) {
            return t;
        }
    }
    return 0u;
}

static float placed_hot_pan(uint32_t t_ms)
{
    /* 25 degC disc, pan at 240 degC placed at 2 s; disc tau63 1.35 s. */
    if (t_ms < 2000u) {
        return 25.0f;
    }
    return 240.0f - 215.0f * expf(-(float)(t_ms - 2000u) / 1350.0f);
}

static float heavy_heating(uint32_t t_ms) { return 25.0f + 3.2f * (float)t_ms / 1000.0f; }
static float runaway_20k_per_s(uint32_t t_ms) { return 25.0f + 20.0f * (float)t_ms / 1000.0f; }

static void test_r1_ignores_hot_pan_placement_that_the_10ms_check_trips(void)
{
    sup_new();
    /* The legacy 10 ms check: 215 K over the first 10 ms after placement. */
    TEST_ASSERT_TRUE((placed_hot_pan(2010u) - placed_hot_pan(2000u)) / 0.01f > 15.0f);
    TEST_ASSERT_EQUAL_UINT32(0u, r1_feed(placed_hot_pan, 0u, 20000u));
}

static void test_r1_ignores_the_fastest_real_heating(void)
{
    sup_new();
    TEST_ASSERT_EQUAL_UINT32(0u, r1_feed(heavy_heating, 0u, 60000u));
}

static void test_r1_trips_a_sustained_15k_per_s_rise_on_the_fifth_block(void)
{
    sup_new();
    const uint32_t t = r1_feed(runaway_20k_per_s, 0u, 20000u);
    /* first block closes at 1 s (no previous), rises counted at 2..6 s */
    TEST_ASSERT_TRUE(t >= 5990u && t <= 6010u);
}

static void test_r1_reset_forgets_history(void)
{
    sup_new();
    TEST_ASSERT_EQUAL_UINT32(0u, r1_feed(runaway_20k_per_s, 0u, 4500u));
    psup_rate_reset(&sup);
    TEST_ASSERT_EQUAL_UINT32(0u, r1_feed(runaway_20k_per_s, 4500u, 4400u));
}

static void test_r1_non_finite_reading_is_left_to_the_absolute_check(void)
{
    sup_new();
    TEST_ASSERT_FALSE(psup_rate_sample(&sup, NAN, 0u));
}

/* ---- R2 over-target supervision ------------------------------------------- */

static psup_output_t r2(float t, float sp, float p_cmd, float i_bus, bool valid)
{
    const psup_input_t in = {.t_hat_c = t, .t_raw_c = t, .setpoint_c = sp, .p_cmd_w = p_cmd,
                             .bus_current_a = i_bus, .current_valid = valid};
    psup_output_t o;
    psup_step(&sup, &in, &o);
    return o;
}

static void test_r2_stage1_forces_zero_above_target_plus_10_without_latching(void)
{
    sup_new();
    /* h_c drop: the reading settles 13 K over target for a minute, power off */
    for (int k = 0; k < 600; k++) {
        const psup_output_t o = r2(213.0f, 200.0f, 900.0f, 0.0f, true);
        TEST_ASSERT_TRUE(o.force_zero);
        TEST_ASSERT_EQUAL_INT(PSUP_OK, o.latch);
    }
    TEST_ASSERT_FALSE(r2(209.0f, 200.0f, 900.0f, 0.0f, true).force_zero);
}

static void test_r2_lowered_target_cooling_pan_never_latches(void)
{
    sup_new();
    float t = 230.0f;
    for (int k = 0; k < 1200; k++) {
        t -= 0.02f;   /* cooling with the command at 0 */
        TEST_ASSERT_EQUAL_INT(PSUP_OK, r2(t, 200.0f, 0.0f, 0.0f, true).latch);
    }
}

static void test_r2_2a_current_while_commanded_off_latches_after_settle_and_hold(void)
{
    sup_new();
    int k = 0;
    for (; k < 7; k++) {
        TEST_ASSERT_EQUAL_INT(PSUP_OK, r2(205.0f, 200.0f, 0.0f, 0.4f, true).latch);
    }
    /* 0.3 s settle then 0.5 s of > 0.5 A */
    psup_latch_t l = PSUP_OK;
    for (k = 0; k < 9 && l == PSUP_OK; k++) {
        l = r2(205.0f, 200.0f, 0.0f, 3.0f, true).latch;
    }
    TEST_ASSERT_EQUAL_INT(PSUP_LATCH_DISOBEY, l);
    TEST_ASSERT_TRUE(k >= 5);
}

static void test_r2_2a_current_far_above_the_command_latches(void)
{
    sup_new();
    /* 400 W commanded (4 A at 100 V), 1800 W stuck on (15 A at 120 V) */
    psup_latch_t l = PSUP_OK;
    int k = 0;
    for (; k < 20 && l == PSUP_OK; k++) {
        l = r2(195.0f, 200.0f, 400.0f, 15.0f, true).latch;
    }
    TEST_ASSERT_EQUAL_INT(PSUP_LATCH_DISOBEY, l);
    TEST_ASSERT_TRUE(k <= 10);
}

static void test_r2_2a_current_matching_a_falling_command_does_not_latch(void)
{
    sup_new();
    /* command steps 1800 -> 0 W; the stage follows one period late */
    float prev = 1800.0f;
    for (int k = 0; k < 50; k++) {
        const float cmd = k < 10 ? 1800.0f : 0.0f;
        TEST_ASSERT_EQUAL_INT(PSUP_OK, r2(190.0f, 200.0f, cmd, 1.1f * prev / 120.0f, true).latch);
        prev = cmd;
    }
}

static void test_r2_2a_needs_a_valid_current(void)
{
    sup_new();
    for (int k = 0; k < 100; k++) {
        TEST_ASSERT_EQUAL_INT(PSUP_OK, r2(205.0f, 200.0f, 0.0f, 15.0f, false).latch);
    }
}

static void test_r2_2b_still_rising_with_no_command_latches_after_hold(void)
{
    sup_new();
    /* stuck on, current sense reading 0: 3 K/s over target, command forced 0 */
    float t = 211.0f;
    int k = 0;
    psup_latch_t l = PSUP_OK;
    for (; k < 1000 && l == PSUP_OK; k++) {
        t += 0.3f;
        l = r2(t, 200.0f, 1800.0f, 0.0f, true).latch;
    }
    TEST_ASSERT_EQUAL_INT(PSUP_LATCH_RISING, l);
    /* rise_hold_s = 20 s at 10 Hz */
    TEST_ASSERT_TRUE(k >= 200 && k <= 202);
}

static void test_r2_2b_hot_pan_placement_transient_does_not_latch(void)
{
    sup_new();
    /* pan at sp + 40 placed on the cold disc: the reading climbs for a few
     * seconds, then the pan cools at 0.1 K/s */
    for (int k = 0; k < 1200; k++) {
        const float ts = (float)k * 0.1f;
        const float t = 240.0f - 215.0f * expf(-ts / 1.35f) - 0.1f * ts;
        TEST_ASSERT_EQUAL_INT(PSUP_OK, r2(t, 200.0f, 0.0f, 0.0f, true).latch);
    }
}

/* ---- rtd_convert ------------------------------------------------------------ */

static uint16_t code_for(double r_ohm) { return (uint16_t)lround(r_ohm / 430.0 * 32768.0); }

static void test_rtd_convert_split_and_fault_flag(void)
{
    bool f = false;
    TEST_ASSERT_EQUAL_UINT16(0x2929u, rtd_convert_split(0x52u, 0x53u, &f));
    TEST_ASSERT_TRUE(f);
    TEST_ASSERT_EQUAL_UINT16(0x2929u, rtd_convert_split(0x52u, 0x52u, &f));
    TEST_ASSERT_FALSE(f);
}

static void test_rtd_convert_cvd_points_within_half_an_lsb(void)
{
    rtd_convert_params_t p;
    rtd_convert_default_params(&p);
    /* IEC 60751: 100.00 ohm at 0, 138.5055 at 100, 175.856 at 200, 80.306 at -50 */
    const struct { double r, t; } pts[] = {{100.0, 0.0}, {138.5055, 100.0}, {175.856, 200.0}, {80.306, -50.0}};
    for (unsigned i = 0; i < 4; i++) {
        const float t = rtd_convert_code_to_c(&p, code_for(pts[i].r));
        TEST_ASSERT_FLOAT_WITHIN(0.03f, (float)pts[i].t - 0.061f, t);
    }
}

static void test_rtd_convert_loading_correction_cr7(void)
{
    rtd_convert_params_t p;
    rtd_convert_default_params(&p);
    p.loading_correction = true;
    const uint16_t c = code_for(175.856);
    const double r = (double)c / 32768.0 * 430.0;
    TEST_ASSERT_FLOAT_WITHIN(1e-3f, (float)(r - (7.86e-4 * r - 0.0331)), rtd_convert_code_to_ohm(&p, c));
}

static void test_rtd_convert_zero_code_is_not_a_temperature(void)
{
    rtd_convert_params_t p;
    rtd_convert_default_params(&p);
    TEST_ASSERT_TRUE(isnan(rtd_convert_code_to_c(&p, 0u)));
}

void run_c1_units_tests(void)
{
    RUN_TEST(test_r1_ignores_hot_pan_placement_that_the_10ms_check_trips);
    RUN_TEST(test_r1_ignores_the_fastest_real_heating);
    RUN_TEST(test_r1_trips_a_sustained_15k_per_s_rise_on_the_fifth_block);
    RUN_TEST(test_r1_reset_forgets_history);
    RUN_TEST(test_r1_non_finite_reading_is_left_to_the_absolute_check);
    RUN_TEST(test_r2_stage1_forces_zero_above_target_plus_10_without_latching);
    RUN_TEST(test_r2_lowered_target_cooling_pan_never_latches);
    RUN_TEST(test_r2_2a_current_while_commanded_off_latches_after_settle_and_hold);
    RUN_TEST(test_r2_2a_current_far_above_the_command_latches);
    RUN_TEST(test_r2_2a_current_matching_a_falling_command_does_not_latch);
    RUN_TEST(test_r2_2a_needs_a_valid_current);
    RUN_TEST(test_r2_2b_still_rising_with_no_command_latches_after_hold);
    RUN_TEST(test_r2_2b_hot_pan_placement_transient_does_not_latch);
    RUN_TEST(test_rtd_convert_split_and_fault_flag);
    RUN_TEST(test_rtd_convert_cvd_points_within_half_an_lsb);
    RUN_TEST(test_rtd_convert_loading_correction_cr7);
    RUN_TEST(test_rtd_convert_zero_code_is_not_a_temperature);
}
