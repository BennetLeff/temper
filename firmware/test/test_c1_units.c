/**
 * @file test_c1_units.c
 * @brief sensor-r3 C1 runtime units: runaway supervisor (pan_supervisor.c),
 *        MAX31865 code conversion (rtd_convert.c), current-sense plausibility
 *        (current_sense_check.c, D-ISENSE), the Pt100 leak check
 *        (pan_leak_check.c, D-LEAK), the setpoint-relative rim limit
 *        (pan_rim_limit.c, D-RIMLIM) and the cold-soak check
 *        (pan_cold_soak.c, D-SOAK).
 *
 * Scenario values mirror output/temper-sensor-r3/firmware/runaway_checks.py
 * (DECISIONS.md D-RUN): a preheated pan placed on the disc, an h_c drop, a
 * lowered target, a power stage stuck on with and without bus-current sense.
 */

#include <math.h>
#include <string.h>

#include "unity/unity.h"
#include "../components/control/contact_check.h"
#include "../components/control/current_sense_check.h"
#include "../components/control/pan_cold_soak.h"
#include "../components/control/pan_soak_store.h"
#include "../components/control/pan_leak_check.h"
#include "../components/control/pan_rim_limit.h"
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

/* ---- D-OPEN: sensor-failure classification -------------------------------- */

static void test_sensor_failure_open_starts_at_r_850c(void)
{
    /* R(850 degC) = 390.481 ohm -> code 29756.4: 29757 is the first code at or
     * beyond it, 29756 is still a temperature (849.9 degC). */
    TEST_ASSERT_EQUAL_INT(RTD_SENSOR_OK, rtd_convert_classify_failure(29756u, 0x80u));
    TEST_ASSERT_EQUAL_INT(RTD_SENSOR_FAIL_OPEN, rtd_convert_classify_failure(29757u, 0x80u));
    TEST_ASSERT_EQUAL_INT(RTD_SENSOR_FAIL_OPEN, rtd_convert_classify_failure(29757u, 0x00u));
    TEST_ASSERT_EQUAL_INT(RTD_SENSOR_FAIL_OPEN, rtd_convert_classify_failure(0x7FFFu, 0x80u));
    rtd_convert_params_t p;
    rtd_convert_default_params(&p);
    TEST_ASSERT_TRUE(rtd_convert_code_to_c(&p, 29756u) < 850.0f);
    TEST_ASSERT_TRUE(rtd_convert_code_to_c(&p, 29757u) > 849.9f);
}

static void test_sensor_failure_short_ends_at_r_minus_200c(void)
{
    /* R(-200 degC) = 18.52 ohm -> code 1411.3 */
    TEST_ASSERT_EQUAL_INT(RTD_SENSOR_FAIL_SHORT, rtd_convert_classify_failure(0u, 0x40u));
    TEST_ASSERT_EQUAL_INT(RTD_SENSOR_FAIL_SHORT, rtd_convert_classify_failure(1411u, 0x40u));
    TEST_ASSERT_EQUAL_INT(RTD_SENSOR_OK, rtd_convert_classify_failure(1412u, 0x40u));
}

static void test_flagged_plausible_over_temperature_is_a_temperature(void)
{
    /* 380 degC: R 241.7 ohm, code 18420, above the 360 degC high-threshold
     * word, so 07h reads RTD High (0x80): the same bit an open sets. */
    TEST_ASSERT_EQUAL_INT(RTD_SENSOR_OK, rtd_convert_classify_failure(18420u, 0x80u));
    TEST_ASSERT_EQUAL_INT(RTD_SENSOR_OK, rtd_convert_classify_failure(18420u, 0x00u));
}

static void test_register_07h_input_bits_are_a_sensor_failure(void)
{
    /* REFIN- high, REFIN- low, RTDIN- low, OV/UV: whatever the code. */
    const uint8_t bits[] = {0x20u, 0x10u, 0x08u, 0x04u, 0x84u};
    for (unsigned i = 0; i < sizeof(bits); i++) {
        TEST_ASSERT_EQUAL_INT(RTD_SENSOR_FAIL_OPEN, rtd_convert_classify_failure(13000u, bits[i]));
    }
}

/* ---- D-ISENSE: bus-current sense plausibility -------------------------------- */

static csc_t csc;

static void csc_new(void)
{
    csc_params_t p;
    csc_default_params(&p);
    TEST_ASSERT_TRUE(csc_init(&csc, &p));
}

/* Periods (0.1 s) until (a) latches at a constant command and current; 0 if never within n. */
static int csc_run_periods(float p_w, float i_a, int n)
{
    for (int k = 1; k <= n; k++) {
        if (csc_run_step(&csc, p_w, i_a)) {
            return k;
        }
    }
    return 0;
}

static void test_isense_run_latches_after_settle_and_hold(void)
{
    csc_new();
    /* 0.3 s settle, then 0.5 s with no current: the 8th period (0.8 s) */
    TEST_ASSERT_EQUAL_INT(8, csc_run_periods(306.0f, 0.0f, 50));
    TEST_ASSERT_EQUAL_INT(CSC_LATCH_RUN, csc.latched);
    csc_new();
    TEST_ASSERT_EQUAL_INT(8, csc_run_periods(1800.0f, NAN, 50));   /* not a current */
}

static void test_isense_run_ignores_commands_below_the_burst_safe_floor(void)
{
    /* Below 300 W the stage may burst at its ~160 W floor with a 20 s period
     * and read 0 A between bursts. */
    csc_new();
    TEST_ASSERT_EQUAL_INT(0, csc_run_periods(288.0f, 0.0f, 400));
    TEST_ASSERT_EQUAL_INT(0, csc_run_periods(90.0f, 0.0f, 400));
}

static void test_isense_run_accepts_any_current_above_near_zero(void)
{
    /* 300 W at 120 V, coil delivering 0.9: 2.25 A expected; 0.6 A still counts */
    csc_new();
    TEST_ASSERT_EQUAL_INT(0, csc_run_periods(306.0f, 0.6f, 400));
    TEST_ASSERT_EQUAL_INT(0, csc_run_periods(1800.0f, 13.5f, 400));
}

static void test_isense_run_needs_the_full_hold(void)
{
    csc_new();
    TEST_ASSERT_EQUAL_INT(0, csc_run_periods(900.0f, 7.5f, 10));
    TEST_ASSERT_EQUAL_INT(0, csc_run_periods(900.0f, 0.0f, 4));   /* 0.4 s dropout */
    TEST_ASSERT_EQUAL_INT(0, csc_run_periods(900.0f, 7.5f, 1));
    TEST_ASSERT_EQUAL_INT(5, csc_run_periods(900.0f, 0.0f, 10));
}

static void test_isense_pulse_passes_with_current_and_fails_without(void)
{
    float cmd = 0.0f;
    csc_new();
    csc_pulse_begin(&csc);
    TEST_ASSERT_EQUAL_INT(CSC_PULSE_PENDING, csc_pulse_step(&csc, 0.0f, 0.0f, 1800.0f, &cmd));
    TEST_ASSERT_EQUAL_FLOAT(360.0f, cmd);
    csc_pulse_state_t st = CSC_PULSE_PENDING;
    int k = 0;
    while (csc_pulse_active(&csc) && k < 30) {
        st = csc_pulse_step(&csc, cmd, 3.0f, 1800.0f, &cmd);   /* 360 W / 120 V */
        k++;
    }
    TEST_ASSERT_EQUAL_INT(CSC_PULSE_PASSED, st);
    TEST_ASSERT_EQUAL_INT(10, k);
    TEST_ASSERT_EQUAL_INT(CSC_OK, csc.latched);

    csc_new();
    csc_pulse_begin(&csc);
    (void)csc_pulse_step(&csc, 0.0f, 0.0f, 1800.0f, &cmd);
    for (k = 0; csc_pulse_active(&csc) && k < 30; k++) {
        st = csc_pulse_step(&csc, cmd, 0.1f, 1800.0f, &cmd);
    }
    TEST_ASSERT_EQUAL_INT(CSC_PULSE_FAILED, st);
    TEST_ASSERT_EQUAL_INT(CSC_LATCH_PULSE, csc.latched);
}

static void test_isense_pulse_waits_while_the_command_is_held_at_zero(void)
{
    float cmd = 0.0f;
    csc_new();
    csc_pulse_begin(&csc);
    /* stage 1 holds the command at 0 for 30 s: the pulse waits, no verdict */
    for (int k = 0; k < 300; k++) {
        TEST_ASSERT_EQUAL_INT(CSC_PULSE_PENDING, csc_pulse_step(&csc, 0.0f, 0.0f, 1800.0f, &cmd));
        TEST_ASSERT_FALSE(csc_run_step(&csc, 0.0f, 0.0f));
    }
    /* zeroed half-way: it restarts */
    for (int k = 0; k < 5; k++) {
        (void)csc_pulse_step(&csc, cmd, 3.0f, 1800.0f, &cmd);
    }
    TEST_ASSERT_EQUAL_INT(CSC_PULSE_PENDING, csc_pulse_step(&csc, 0.0f, 0.0f, 1800.0f, &cmd));
    int k = 0;
    while (csc_pulse_active(&csc) && k < 30) {
        (void)csc_pulse_step(&csc, cmd, 3.0f, 1800.0f, &cmd);
        k++;
    }
    TEST_ASSERT_EQUAL_INT(10, k);
    TEST_ASSERT_EQUAL_INT(CSC_PULSE_PASSED, csc.pulse);
}

static void test_isense_pulse_is_clamped_to_the_power_limit(void)
{
    float cmd = 0.0f;
    csc_new();
    csc_pulse_begin(&csc);
    (void)csc_pulse_step(&csc, 0.0f, 0.0f, 180.0f, &cmd);   /* intensity 1 */
    TEST_ASSERT_EQUAL_FLOAT(180.0f, cmd);
}

static void test_isense_xcheck_agreeing_senses_never_latch(void)
{
    csc_new();
    for (int k = 0; k < 600; k++) {
        const float i = 15.0f * (float)(k % 100) / 100.0f;
        TEST_ASSERT_FALSE(csc_xcheck_step(&csc, i * 1.2f, i));   /* 20 % gain error */
    }
    TEST_ASSERT_FALSE(csc_xcheck_step(&csc, 0.9f, 0.0f));        /* below the floor */
}

static void test_isense_xcheck_disagreeing_senses_latch_after_hold(void)
{
    csc_new();
    for (int k = 1; k <= 4; k++) {
        TEST_ASSERT_FALSE(csc_xcheck_step(&csc, 7.5f, 0.0f));   /* bus sense dead */
    }
    TEST_ASSERT_TRUE(csc_xcheck_step(&csc, 7.5f, 0.0f));
    TEST_ASSERT_EQUAL_INT(CSC_LATCH_XCHECK, csc.latched);
    csc_new();
    for (int k = 0; k < 4; k++) {
        TEST_ASSERT_FALSE(csc_xcheck_step(&csc, 15.0f, 7.5f));   /* half-gain bus sense */
    }
    TEST_ASSERT_TRUE(csc_xcheck_step(&csc, 15.0f, 7.5f));
    csc_new();
    for (int k = 0; k < 4; k++) {
        TEST_ASSERT_FALSE(csc_xcheck_step(&csc, NAN, 7.5f));
    }
    TEST_ASSERT_TRUE(csc_xcheck_step(&csc, NAN, 7.5f));
}

/* ---- D-LEAK: element-parallel Pt100 leakage ------------------------------- */

static plc_t plc;

static void plc_new(void)
{
    plc_params_t p;
    plc_default_params(&p);
    TEST_ASSERT_TRUE(plc_init(&plc, &p));
}

/* Idle periods (no suspect, no event) at reading y, rim r. */
static bool plc_idle(int n, float y, float r)
{
    bool l = false;
    for (int k = 0; k < n; k++) {
        l = plc_step(&plc, false, CC_EVT_NONE, y, r);
    }
    return l;
}

/* One leak cycle as leak-checks.json shows it: suspect, a 6 s probe, PASSED. */
static bool plc_cycle(float y, float r)
{
    (void)plc_step(&plc, true, CC_EVT_SUSPECT, y, r);
    (void)plc_idle(60, y, r);
    return plc_step(&plc, false, CC_EVT_PROBE_PASSED, y, r);
}

static void test_leak_two_chained_cycles_latch(void)
{
    plc_new();
    TEST_ASSERT_FALSE(plc_cycle(251.0f, 285.0f));
    TEST_ASSERT_FALSE(plc_idle(430, 245.0f, 286.0f));   /* 30 s hold-off + 30 s xcheck hold */
    TEST_ASSERT_TRUE(plc_cycle(244.0f, 288.0f));       /* reading lower, rim higher */
    TEST_ASSERT_TRUE(plc_idle(5, 244.0f, 288.0f));     /* sticky */
}

static void test_leak_one_cycle_or_cycles_beyond_the_gap_never_latch(void)
{
    plc_new();
    TEST_ASSERT_FALSE(plc_cycle(251.0f, 285.0f));
    TEST_ASSERT_FALSE(plc_idle(3000, 251.0f, 285.0f));
    plc_new();
    TEST_ASSERT_FALSE(plc_cycle(251.0f, 285.0f));
    TEST_ASSERT_FALSE(plc_idle(1150, 251.0f, 285.0f));  /* suspects 121 s apart */
    TEST_ASSERT_FALSE(plc_cycle(251.0f, 285.0f));
    TEST_ASSERT_FALSE(plc_idle(400, 251.0f, 285.0f));   /* ...but this one chains */
    TEST_ASSERT_TRUE(plc_cycle(251.0f, 285.0f));
}

static void test_leak_a_resolving_disturbance_breaks_the_chain(void)
{
    plc_new();   /* the reading recovers more than 2 K: food heating back up */
    TEST_ASSERT_FALSE(plc_cycle(200.0f, 240.0f));
    TEST_ASSERT_FALSE(plc_idle(400, 205.0f, 240.0f));
    TEST_ASSERT_FALSE(plc_cycle(202.5f, 240.0f));
    plc_new();   /* the rim cools more than 5 K: the glass was the hot one */
    TEST_ASSERT_FALSE(plc_cycle(200.0f, 240.0f));
    TEST_ASSERT_FALSE(plc_idle(400, 200.0f, 236.0f));
    TEST_ASSERT_FALSE(plc_cycle(200.0f, 234.5f));
}

static void test_leak_contact_doubt_or_no_rim_restarts_the_count(void)
{
    plc_new();
    TEST_ASSERT_FALSE(plc_cycle(251.0f, 285.0f));
    TEST_ASSERT_FALSE(plc_step(&plc, false, CC_EVT_LOST, 251.0f, 285.0f));
    TEST_ASSERT_FALSE(plc_cycle(251.0f, 285.0f));
    TEST_ASSERT_FALSE(plc_step(&plc, false, CC_EVT_RESTORED, 251.0f, 285.0f));
    TEST_ASSERT_FALSE(plc_cycle(251.0f, 285.0f));
    TEST_ASSERT_FALSE(plc_cycle(251.0f, NAN));         /* rim not VALID */
    TEST_ASSERT_FALSE(plc_cycle(251.0f, 285.0f));
    plc_new();   /* a probe D1 started on its own (no cross-check suspect) */
    TEST_ASSERT_FALSE(plc_cycle(251.0f, 285.0f));
    TEST_ASSERT_FALSE(plc_step(&plc, false, CC_EVT_SUSPECT, 251.0f, 285.0f));
    TEST_ASSERT_FALSE(plc_idle(60, 251.0f, 285.0f));
    TEST_ASSERT_FALSE(plc_step(&plc, false, CC_EVT_PROBE_PASSED, 251.0f, 285.0f));
    TEST_ASSERT_FALSE(plc_idle(100, 251.0f, 285.0f));
}

static void test_leak_a_probe_not_started_by_the_suspect_does_not_count(void)
{
    plc_new();
    TEST_ASSERT_FALSE(plc_cycle(251.0f, 285.0f));
    TEST_ASSERT_FALSE(plc_idle(300, 245.0f, 286.0f));
    /* the contact-shift window starts a probe; the cross-check fires during
     * it; the window's probe passes: not a leak cycle */
    TEST_ASSERT_FALSE(plc_step(&plc, false, CC_EVT_SUSPECT, 245.0f, 286.0f));
    TEST_ASSERT_FALSE(plc_idle(20, 245.0f, 286.0f));
    TEST_ASSERT_FALSE(plc_step(&plc, true, CC_EVT_NONE, 245.0f, 286.0f));
    TEST_ASSERT_FALSE(plc_idle(40, 245.0f, 286.0f));
    TEST_ASSERT_FALSE(plc_step(&plc, false, CC_EVT_PROBE_PASSED, 245.0f, 286.0f));
    /* a suspect whose probe never starts (D1 hold-off): a later PASSED of
     * some other probe that did not start after it does not count either */
    plc_new();
    TEST_ASSERT_FALSE(plc_cycle(251.0f, 285.0f));
    TEST_ASSERT_FALSE(plc_idle(300, 245.0f, 286.0f));
    TEST_ASSERT_FALSE(plc_step(&plc, true, CC_EVT_NONE, 245.0f, 286.0f));
    TEST_ASSERT_FALSE(plc_idle(40, 245.0f, 286.0f));
    TEST_ASSERT_FALSE(plc_step(&plc, false, CC_EVT_PROBE_PASSED, 245.0f, 286.0f));
    /* ...but the request held through the hold-off starts a probe later, and
     * that probe's verdict does count */
    plc_new();
    TEST_ASSERT_FALSE(plc_cycle(251.0f, 285.0f));
    TEST_ASSERT_FALSE(plc_idle(300, 245.0f, 286.0f));
    TEST_ASSERT_FALSE(plc_step(&plc, true, CC_EVT_NONE, 245.0f, 286.0f));
    TEST_ASSERT_FALSE(plc_idle(40, 245.0f, 286.0f));
    TEST_ASSERT_FALSE(plc_step(&plc, false, CC_EVT_SUSPECT, 245.0f, 286.0f));
    TEST_ASSERT_FALSE(plc_idle(60, 245.0f, 286.0f));
    TEST_ASSERT_TRUE(plc_step(&plc, false, CC_EVT_PROBE_PASSED, 245.0f, 286.0f));
}

/* ---- setpoint-relative rim limit (D-RIMLIM) ------------------------------- */

static prl_t prl;
static prl_params_t rlp;

static void prl_new(void)
{
    prl_default_params(&rlp);
    TEST_ASSERT_TRUE(prl_init(&prl, &rlp));
}

/* n periods at setpoint sp, t_hat th, rim rim0 + slope * t (VALID); returns
 * the first latch time in s from the start of this call, or -1. */
static float prl_run_ramp(int n, float sp, float th, float rim0, float slope)
{
    for (int k = 0; k < n; k++) {
        if (prl_step(&prl, sp, th, true, rim0 + slope * 0.1f * (float)k)) {
            return 0.1f * (float)k;
        }
    }
    return -1.0f;
}

static void test_rimlim_limit_is_the_glass_envelope_plus_the_hot_stack(void)
{
    prl_default_params(&rlp);
    /* flat pan, hottest eye: 0.9554 * 250 + 0.0446 * 139.7 = 245.08 degC of
     * glass, plus the rim hot stack there (15.71 K, between the 200 and
     * 250 degC knots of PRL_TOL_K) */
    TEST_ASSERT_FLOAT_WITHIN(0.02f, 260.79f, prl_limit_c(&rlp, 250.0f));
    TEST_ASSERT_FLOAT_WITHIN(0.02f, 210.41f, prl_limit_c(&rlp, 200.0f));
    /* below the eye air the glass can be hotter than the pan (0.5 mm gap) */
    TEST_ASSERT_FLOAT_WITHIN(0.02f, 125.09f, prl_limit_c(&rlp, 100.0f));
    /* D-RIM's constant 19.1 K stack */
    rlp.tol_table = false;
    TEST_ASSERT_FLOAT_WITHIN(0.02f, 264.18f, prl_limit_c(&rlp, 250.0f));
}

static void test_rimlim_a_rising_rim_above_the_limit_latches_after_sustain(void)
{
    prl_new();
    /* a leak at a 200 degC setpoint: the reading (t_hat) stays at 200 while
     * the glass climbs 0.2 K/s through the 210.4 degC limit (at 52.1 s) */
    const float t = prl_run_ramp(3000, 200.0f, 200.0f, 200.0f, 0.2f);
    TEST_ASSERT_FLOAT_WITHIN(0.25f, 57.1f, t);
    TEST_ASSERT_TRUE(prl_step(&prl, 200.0f, 200.0f, false, NAN));   /* sticky */
}

static void test_rimlim_a_steady_rim_just_under_the_limit_never_latches(void)
{
    prl_new();
    TEST_ASSERT_EQUAL_FLOAT(-1.0f, prl_run_ramp(36000, 250.0f, 250.0f, 260.5f, 0.0f));
}

static void test_rimlim_a_falling_glass_above_the_limit_never_latches(void)
{
    prl_new();
    /* a cold pan on glass left at 260 degC, setpoint 100: the glass cools
     * toward the envelope for a 100 degC pan (114 degC) */
    for (int k = 0; k < 6000; k++) {
        const float g = 114.0f + 146.0f * expf(-0.1f * (float)k / 106.0f);
        TEST_ASSERT_FALSE(prl_step(&prl, 100.0f, 25.0f + 0.01f * (float)k, true, g));
    }
    /* the setpoint lowered 250 -> 150 under a hot glass, decaying with the
     * slowest study-08 lag: the reference decays slower still */
    prl_new();
    TEST_ASSERT_EQUAL_FLOAT(-1.0f, prl_run_ramp(600, 250.0f, 250.0f, 245.0f, 0.0f));
    for (int k = 0; k < 6000; k++) {
        const float g = 140.0f + 105.0f * expf(-0.1f * (float)k / 106.0f);
        TEST_ASSERT_FALSE(prl_step(&prl, 150.0f, 150.0f, true, g));
    }
}

static void test_rimlim_needs_a_full_fall_window_and_the_full_sustain(void)
{
    prl_new();
    /* far above the limit but the rim drops out every 25 s: never 30 s of history */
    for (int i = 0; i < 20; i++) {
        TEST_ASSERT_EQUAL_FLOAT(-1.0f, prl_run_ramp(250, 200.0f, 200.0f, 260.0f, 0.0f));
        TEST_ASSERT_FALSE(prl_step(&prl, 200.0f, 200.0f, false, NAN));
    }
    prl_new();
    TEST_ASSERT_EQUAL_FLOAT(-1.0f, prl_run_ramp(310, 200.0f, 200.0f, 210.0f, 0.0f));   /* history */
    for (int i = 0; i < 10; i++) {   /* 4.9 s over, then 0.1 s under: never 5 s */
        TEST_ASSERT_EQUAL_FLOAT(-1.0f, prl_run_ramp(49, 200.0f, 200.0f, 230.0f, 0.0f));
        TEST_ASSERT_EQUAL_FLOAT(-1.0f, prl_run_ramp(1, 200.0f, 200.0f, 210.0f, 0.0f));
    }
}

static void test_rimlim_rejects_bad_parameters(void)
{
    prl_default_params(&rlp);
    rlp.fall_window_s = 100.0f;
    TEST_ASSERT_FALSE(prl_init(&prl, &rlp));
    prl_default_params(&rlp);
    rlp.w_lo = 0.99f;
    TEST_ASSERT_FALSE(prl_init(&prl, &rlp));
    prl_default_params(&rlp);
    rlp.tau_dec_s = 0.0f;
    TEST_ASSERT_FALSE(prl_init(&prl, &rlp));
}


/* ---- cold-soak check (pan_cold_soak.c, D-SOAK) ---------------------------- */

static pcs_t soak;

static void soak_new(uint32_t t0_ms)
{
    pcs_params_t p;
    pcs_default_params(&p);
    TEST_ASSERT_TRUE(pcs_init(&soak, &p, t0_ms));
}

/* 1 s notes from t0 for n_s seconds with constant readings. */
static uint32_t soak_feed(uint32_t t0_ms, uint32_t n_s, float pt, bool hs_valid, float hs)
{
    uint32_t t = t0_ms;
    for (uint32_t k = 0; k < n_s; k++, t += 1000u) {
        pcs_note(&soak, t, false, pt, hs_valid, hs);
    }
    return t;
}

static void test_soak_leak_after_the_soak_and_not_before(void)
{
    soak_new(0u);
    uint32_t t = soak_feed(0u, 1799u, 15.0f, true, 35.0f);
    pcs_result_t r = pcs_evaluate(&soak, t, 15.0f, true, 35.0f, true);
    TEST_ASSERT_EQUAL_INT(PCS_SKIP_NOT_SOAKED, r.verdict);   /* power-up counts as coil-on */
    t = soak_feed(t, 2u, 15.0f, true, 35.0f);
    r = pcs_evaluate(&soak, t, 15.0f, true, 35.0f, true);
    TEST_ASSERT_EQUAL_INT(PCS_LEAK, r.verdict);
    TEST_ASSERT_FLOAT_WITHIN(1e-3f, 20.0f, r.gap_k);
    /* 19.4 K is the threshold: 19.3 K passes, 19.5 K latches */
    /* the window and the present reading must both be over the threshold */
    r = pcs_evaluate(&soak, t, 15.7f, true, 35.0f, true);
    TEST_ASSERT_EQUAL_INT(PCS_PASS, r.verdict);
    soak_new(0u);
    t = soak_feed(0u, 1900u, 15.7f, true, 35.0f);
    TEST_ASSERT_EQUAL_INT(PCS_PASS, pcs_evaluate(&soak, t, 15.7f, true, 35.0f, true).verdict);
    soak_new(0u);
    t = soak_feed(0u, 1900u, 15.5f, true, 35.0f);
    TEST_ASSERT_EQUAL_INT(PCS_LEAK, pcs_evaluate(&soak, t, 15.5f, true, 35.0f, true).verdict);
}

static void test_soak_coil_activity_restarts_the_soak_and_the_history(void)
{
    soak_new(0u);
    uint32_t t = soak_feed(0u, 3000u, 15.0f, true, 35.0f);
    pcs_note(&soak, t, true, 15.0f, true, 35.0f);
    t = soak_feed(t + 1000u, 1700u, 15.0f, true, 35.0f);
    TEST_ASSERT_EQUAL_INT(PCS_SKIP_NOT_SOAKED, pcs_evaluate(&soak, t, 15.0f, true, 35.0f, true).verdict);
    t = soak_feed(t, 200u, 15.0f, true, 35.0f);
    TEST_ASSERT_EQUAL_INT(PCS_LEAK, pcs_evaluate(&soak, t, 15.0f, true, 35.0f, true).verdict);
}

static void test_soak_skips_on_a_saturated_or_warm_or_drifting_reference(void)
{
    /* the heatsink not VALID (saturated: above range, or an open sensor) for one minute of the window */
    soak_new(0u);
    uint32_t t = soak_feed(0u, 1500u, 15.0f, true, 35.0f);
    t = soak_feed(t, 60u, 15.0f, false, NAN);
    t = soak_feed(t, 300u, 15.0f, true, 35.0f);
    TEST_ASSERT_EQUAL_INT(PCS_SKIP_HS_INVALID, pcs_evaluate(&soak, t, 15.0f, true, 35.0f, true).verdict);
    TEST_ASSERT_EQUAL_INT(PCS_SKIP_HS_INVALID, pcs_evaluate(&soak, t, 15.0f, false, NAN, true).verdict);
    /* above 45 degC */
    soak_new(0u);
    t = soak_feed(0u, 1900u, 15.0f, true, 46.0f);
    TEST_ASSERT_EQUAL_INT(PCS_SKIP_HS_WARM, pcs_evaluate(&soak, t, 15.0f, true, 46.0f, true).verdict);
    /* still cooling: 1.2 K over the window */
    soak_new(0u);
    t = 0u;
    for (uint32_t k = 0; k < 1900u; k++, t += 1000u) {
        pcs_note(&soak, t, false, 15.0f, true, 40.0f - (float)k * (1.2f / 900.0f));
    }
    TEST_ASSERT_EQUAL_INT(PCS_SKIP_HS_DRIFT, pcs_evaluate(&soak, t, 15.0f, true, 37.5f, true).verdict);
}

static void test_soak_slow_heatsink_does_not_false_latch(void)
{
    /* A slow tail can fit inside the 1 K range while its offset still looks
     * like leakage. F3: tau_h 3600 s, measured rail, a cold room. */
    soak_new(0u);
    const float pt = 4.3f;
    float hs = 0.0f;
    uint32_t t = 0u;
    for (uint32_t k = 0u; k <= 10870u; k++, t += 1000u) {
        hs = 18.0f + 67.0f * expf(-(float)k / 3600.0f);
        pcs_note_rail(&soak, t, k == 0u, pt, true, hs, true);
    }
    TEST_ASSERT_TRUE(hs - pt > PCS_THRESHOLD_MEASURED_K);
    TEST_ASSERT_EQUAL_INT(PCS_SKIP_HS_DRIFT,
                         pcs_evaluate_rail(&soak, t - 1000u, pt, true, hs, true, true).verdict);
    /* Once the reference settles, the original check runs again. */
    for (uint32_t k = 10871u; k <= 18000u; k++, t += 1000u) {
        hs = 18.0f + 67.0f * expf(-(float)k / 3600.0f);
        pcs_note_rail(&soak, t, false, pt, true, hs, true);
    }
    TEST_ASSERT_EQUAL_INT(PCS_PASS,
                         pcs_evaluate_rail(&soak, t - 1000u, pt, true, hs, true, true).verdict);
}

static void test_soak_rate_keeps_leaks_below_limit_and_skips_both_directions(void)
{
    for (int measured = 0; measured <= 1; measured++) {
        for (int sign = -1; sign <= 1; sign += 2) {
            for (int over = 0; over <= 1; over++) {
                soak_new(0u);
                const float rate = (float)sign * (over ? 0.021f : 0.019f) / 60.0f;
                float hs = 0.0f;
                uint32_t t = 0u;
                for (uint32_t k = 0u; k < 2400u; k++, t += 1000u) {
                    hs = 35.0f + rate * (float)k;
                    pcs_note_rail(&soak, t, false, 10.0f, true, hs, measured != 0);
                }
                const pcs_result_t r = pcs_evaluate_rail(&soak, t, 10.0f, true, hs, true,
                                                          measured != 0);
                TEST_ASSERT_EQUAL_INT(over ? PCS_SKIP_HS_DRIFT : PCS_LEAK, r.verdict);
            }
        }
    }
}

static void test_soak_rate_uses_complete_buckets(void)
{
    soak_new(0u);
    uint32_t t = soak_feed(0u, 2400u, 10.0f, true, 35.0f);
    /* One sample in the current minute must not stand for a whole minute.
     * The existing 1 K range check still bounds this excursion. */
    pcs_note(&soak, t, false, 10.0f, true, 35.4f);
    TEST_ASSERT_EQUAL_INT(PCS_LEAK, pcs_evaluate(&soak, t, 10.0f, true, 35.4f, true).verdict);
}

static void test_soak_skips_when_the_pt100_moved_or_the_rim_is_warm(void)
{
    /* a cold pan placed 5 min before the evaluation: the reading stepped */
    soak_new(0u);
    uint32_t t = soak_feed(0u, 1600u, 34.5f, true, 35.0f);
    t = soak_feed(t, 300u, 5.0f, true, 35.0f);
    TEST_ASSERT_EQUAL_INT(PCS_SKIP_PT_DRIFT, pcs_evaluate(&soak, t, 5.0f, true, 35.0f, true).verdict);
    /* 0.3 K of drift over 15 min is more than 0.25 K */
    soak_new(0u);
    t = 0u;
    for (uint32_t k = 0; k < 1900u; k++, t += 1000u) {
        pcs_note(&soak, t, false, 15.0f + (float)k * (0.3f / 900.0f), true, 35.0f);
    }
    TEST_ASSERT_EQUAL_INT(PCS_SKIP_PT_DRIFT, pcs_evaluate(&soak, t, 15.6f, true, 35.0f, true).verdict);
    /* no Pt100 reading for a moment */
    soak_new(0u);
    t = soak_feed(0u, 1700u, 15.0f, true, 35.0f);
    t = soak_feed(t, 1u, NAN, true, 35.0f);
    t = soak_feed(t, 200u, 15.0f, true, 35.0f);
    TEST_ASSERT_EQUAL_INT(PCS_SKIP_PT_INVALID, pcs_evaluate(&soak, t, 15.0f, true, 35.0f, true).verdict);
    /* the glass still warm under the rim NTC */
    soak_new(0u);
    t = soak_feed(0u, 1900u, 15.0f, true, 35.0f);
    TEST_ASSERT_EQUAL_INT(PCS_SKIP_RIM_WARM, pcs_evaluate(&soak, t, 15.0f, true, 35.0f, false).verdict);
}

static void test_soak_needs_the_whole_window_and_survives_clock_steps(void)
{
    /* soaked, but notes only for the last 10 min (e.g. a gap): history */
    soak_new(0u);
    pcs_note(&soak, 0u, false, 15.0f, true, 35.0f);
    uint32_t t = soak_feed(1300000u, 600u, 15.0f, true, 35.0f);
    TEST_ASSERT_EQUAL_INT(PCS_SKIP_HISTORY, pcs_evaluate(&soak, t, 15.0f, true, 35.0f, true).verdict);
    /* the clock going backwards restarts the soak instead of wrapping */
    soak_new(5000000u);
    t = soak_feed(1000u, 1000u, 15.0f, true, 35.0f);
    TEST_ASSERT_EQUAL_INT(PCS_SKIP_NOT_SOAKED, pcs_evaluate(&soak, t, 15.0f, true, 35.0f, true).verdict);
    t = soak_feed(t, 900u, 15.0f, true, 35.0f);
    TEST_ASSERT_EQUAL_INT(PCS_LEAK, pcs_evaluate(&soak, t, 15.0f, true, 35.0f, true).verdict);
    /* the coil-off time is held, not wrapped, over a long idle (60 days) */
    soak_new(0u);
    t = 0u;
    for (uint32_t k = 0; k < 60u * 24u * 60u; k++, t += 60000u) {
        pcs_note(&soak, t, false, 15.0f, true, 35.0f);
    }
    t = soak_feed(t, 1000u, 15.0f, true, 35.0f);
    TEST_ASSERT_EQUAL_INT(PCS_LEAK, pcs_evaluate(&soak, t, 15.0f, true, 35.0f, true).verdict);
}

static void test_soak_agreement_and_parameters(void)
{
    soak_new(0u);
    TEST_ASSERT_TRUE(pcs_agrees(&soak, 30.0f, true, 35.0f));
    TEST_ASSERT_TRUE(pcs_agrees(&soak, 15.7f, true, 35.0f));
    TEST_ASSERT_FALSE(pcs_agrees(&soak, 15.5f, true, 35.0f));
    TEST_ASSERT_FALSE(pcs_agrees(&soak, 34.0f, false, NAN));
    TEST_ASSERT_FALSE(pcs_agrees(&soak, NAN, true, 35.0f));
    pcs_params_t p;
    pcs_default_params(&p);
    TEST_ASSERT_EQUAL_FLOAT(19.4f, p.threshold_k);
    TEST_ASSERT_EQUAL_FLOAT(1800.0f, p.soak_n_s);
    p.window_s = 3000.0f;   /* more than PCS_BUCKET_MAX minutes, and longer than the soak */
    TEST_ASSERT_FALSE(pcs_init(&soak, &p, 0u));
    pcs_default_params(&p);
    p.threshold_k = 0.0f;
    TEST_ASSERT_FALSE(pcs_init(&soak, &p, 0u));
}

/* D-RAIL: the measured-rail threshold applies only when the rail was measured
 * at every note through the window and now; one unknown note -> fallback. */
static void test_soak_threshold_follows_the_rail_through_the_window(void)
{
    const float pt = 35.0f - 18.0f;   /* gap 18 K: over 16.9, under 19.4 */
    soak_new(0u);
    uint32_t t = 0u;
    for (uint32_t k = 0; k < 1900u; k++, t += 1000u) {
        pcs_note_rail(&soak, t, false, pt, true, 35.0f, true);
    }
    pcs_result_t r = pcs_evaluate_rail(&soak, t, pt, true, 35.0f, true, true);
    TEST_ASSERT_EQUAL_INT(PCS_LEAK, r.verdict);
    TEST_ASSERT_TRUE(r.rail_measured);
    TEST_ASSERT_EQUAL_FLOAT(PCS_THRESHOLD_MEASURED_K, r.threshold_k);
    /* the rail unknown now: fallback threshold, pass */
    r = pcs_evaluate_rail(&soak, t, pt, true, 35.0f, true, false);
    TEST_ASSERT_EQUAL_INT(PCS_PASS, r.verdict);
    TEST_ASSERT_FALSE(r.rail_measured);
    TEST_ASSERT_EQUAL_FLOAT(PCS_THRESHOLD_K, r.threshold_k);
    /* pcs_evaluate() (no rail information) is the fallback */
    TEST_ASSERT_EQUAL_INT(PCS_PASS, pcs_evaluate(&soak, t, pt, true, 35.0f, true).verdict);
    /* one note inside the window with the rail unknown: fallback */
    soak_new(0u);
    t = 0u;
    for (uint32_t k = 0; k < 1900u; k++, t += 1000u) {
        pcs_note_rail(&soak, t, false, pt, true, 35.0f, k != 1500u);
    }
    r = pcs_evaluate_rail(&soak, t, pt, true, 35.0f, true, true);
    TEST_ASSERT_EQUAL_INT(PCS_PASS, r.verdict);
    TEST_ASSERT_EQUAL_FLOAT(PCS_THRESHOLD_K, r.threshold_k);
    /* the same note before the window: measured again */
    soak_new(0u);
    t = 0u;
    for (uint32_t k = 0; k < 1900u; k++, t += 1000u) {
        pcs_note_rail(&soak, t, false, pt, true, 35.0f, k != 100u);
    }
    TEST_ASSERT_EQUAL_INT(PCS_LEAK, pcs_evaluate_rail(&soak, t, pt, true, 35.0f, true, true).verdict);
    /* clearing a latch uses the reading's own rail state */
    TEST_ASSERT_FALSE(pcs_agrees_rail(&soak, pt, true, 35.0f, true));
    TEST_ASSERT_TRUE(pcs_agrees_rail(&soak, pt, true, 35.0f, false));
    /* the measured threshold may not exceed the fallback */
    pcs_params_t p;
    pcs_default_params(&p);
    TEST_ASSERT_TRUE(p.threshold_measured_k < p.threshold_k);
    p.threshold_measured_k = p.threshold_k + 1.0f;
    TEST_ASSERT_FALSE(pcs_init(&soak, &p, 0u));
}

/* D-SOAKNV: a credit moves the last activity back; the window still starts now. */
static void test_soak_credit_counts_coil_off_time_but_not_history(void)
{
    soak_new(5000u);
    pcs_credit_off(&soak, 5000u, 900u);
    TEST_ASSERT_FLOAT_WITHIN(1e-3f, 900.0f, pcs_off_s(&soak, 5000u));
    uint32_t t = soak_feed(5000u, 900u, 15.0f, true, 35.0f);
    /* 15 min of uptime: off >= 30 min, but the history is one bucket short */
    TEST_ASSERT_EQUAL_INT(PCS_SKIP_HISTORY, pcs_evaluate(&soak, t, 15.0f, true, 35.0f, true).verdict);
    t = soak_feed(t, 61u, 15.0f, true, 35.0f);
    TEST_ASSERT_EQUAL_INT(PCS_LEAK, pcs_evaluate(&soak, t, 15.0f, true, 35.0f, true).verdict);
    /* without the credit the same unit is not soaked */
    soak_new(5000u);
    t = soak_feed(5000u, 961u, 15.0f, true, 35.0f);
    TEST_ASSERT_EQUAL_INT(PCS_SKIP_NOT_SOAKED, pcs_evaluate(&soak, t, 15.0f, true, 35.0f, true).verdict);
    /* a smaller credit never shortens a longer coil-off time */
    soak_new(0u);
    t = soak_feed(0u, 1200u, 15.0f, true, 35.0f);
    pcs_credit_off(&soak, t, 900u);
    TEST_ASSERT_TRUE(pcs_off_s(&soak, t) >= 1199.0f);
}

/* ---- coil-off token store (pan_soak_store.c, D-SOAKNV) --------------------- */

static struct {
    bool present;
    uint32_t v;
    bool fail_load, fail_save, fail_clear, clear_lies;
    unsigned saves, clears;
} nv;

static bool nv_load(void *c, uint32_t *v) { (void)c; if (nv.fail_load || !nv.present) return false; *v = nv.v; return true; }
static bool nv_save(void *c, uint32_t v) { (void)c; nv.saves++; if (nv.fail_save) return false; nv.present = true; nv.v = v; return true; }
static bool nv_clear(void *c)
{
    (void)c;
    nv.clears++;
    if (nv.fail_clear) return false;
    if (!nv.clear_lies) nv.present = false;   /* clear_lies: reports success, the token stays */
    return true;
}
static const pss_hal_t nv_hal = {.load = nv_load, .save = nv_save, .clear = nv_clear, .ctx = NULL};

static void test_store_writes_once_per_off_period_and_revokes_before_power(void)
{
    memset(&nv, 0, sizeof(nv));
    pss_t st;
    TEST_ASSERT_EQUAL_UINT32(0u, pss_boot(&st, &nv_hal));   /* nothing stored: unknown */
    for (int s = 0; s < 899; s++) {
        pss_note(&st, &nv_hal, false, (float)s);
    }
    TEST_ASSERT_EQUAL_UINT(0u, nv.saves);
    for (int s = 900; s < 4000; s++) {
        pss_note(&st, &nv_hal, false, (float)s);
    }
    TEST_ASSERT_EQUAL_UINT(1u, nv.saves);                  /* once, not periodically */
    TEST_ASSERT_TRUE(nv.present);
    TEST_ASSERT_EQUAL_UINT32(PSS_TOKEN_OFF_S, nv.v);
    TEST_ASSERT_EQUAL_UINT32(PSS_TOKEN_OFF_S, pss_credit_s(&st));
    /* power cycle: the token credits 900 s; the period already has its token */
    TEST_ASSERT_EQUAL_UINT32(PSS_TOKEN_OFF_S, pss_boot(&st, &nv_hal));
    for (int s = 0; s < 4000; s++) {
        pss_note(&st, &nv_hal, false, 900.0f + (float)s);
    }
    TEST_ASSERT_EQUAL_UINT(1u, nv.saves);
    /* before power: revoked and verified */
    TEST_ASSERT_TRUE(pss_revoke(&st, &nv_hal));
    TEST_ASSERT_FALSE(nv.present);
    TEST_ASSERT_EQUAL_UINT32(0u, pss_credit_s(&st));
    /* coil activity with no token: no flash traffic */
    const unsigned c0 = nv.clears;
    for (int k = 0; k < 100; k++) {
        pss_note(&st, &nv_hal, true, 0.0f);
    }
    TEST_ASSERT_EQUAL_UINT(c0, nv.clears);
    /* the next off period writes again */
    pss_note(&st, &nv_hal, false, 950.0f);
    TEST_ASSERT_EQUAL_UINT(2u, nv.saves);
    /* a power cycle mid-cook would find no token: revoke came first */
    TEST_ASSERT_TRUE(pss_revoke(&st, &nv_hal));
    TEST_ASSERT_EQUAL_UINT32(0u, pss_boot(&st, &nv_hal));
}

static void test_store_failures_are_unknown_never_soaked(void)
{
    pss_t st;
    /* implausible token: ignored and removed */
    memset(&nv, 0, sizeof(nv));
    nv.present = true;
    nv.v = 100000u;
    TEST_ASSERT_EQUAL_UINT32(0u, pss_boot(&st, &nv_hal));
    TEST_ASSERT_FALSE(nv.present);
    nv.present = true;
    nv.v = 0u;
    TEST_ASSERT_EQUAL_UINT32(0u, pss_boot(&st, &nv_hal));
    /* unreadable: unknown */
    memset(&nv, 0, sizeof(nv));
    nv.present = true;
    nv.v = 900u;
    nv.fail_load = true;
    TEST_ASSERT_EQUAL_UINT32(0u, pss_boot(&st, &nv_hal));
    /* no HAL: unknown, disabled */
    TEST_ASSERT_EQUAL_UINT32(0u, pss_boot(&st, NULL));
    TEST_ASSERT_TRUE(st.disabled);
    /* a failed write: no token, the store disabled for the session */
    memset(&nv, 0, sizeof(nv));
    nv.fail_save = true;
    (void)pss_boot(&st, &nv_hal);
    pss_note(&st, &nv_hal, false, 1000.0f);
    pss_note(&st, &nv_hal, false, 1001.0f);
    TEST_ASSERT_EQUAL_UINT(1u, nv.saves);
    TEST_ASSERT_TRUE(st.disabled);
    TEST_ASSERT_EQUAL_UINT32(0u, pss_credit_s(&st));
    /* a failed or unverified erase: reported, the store disabled */
    memset(&nv, 0, sizeof(nv));
    (void)pss_boot(&st, &nv_hal);
    pss_note(&st, &nv_hal, false, 1000.0f);
    nv.fail_clear = true;
    TEST_ASSERT_FALSE(pss_revoke(&st, &nv_hal));
    TEST_ASSERT_TRUE(st.disabled);
    memset(&nv, 0, sizeof(nv));
    (void)pss_boot(&st, &nv_hal);
    pss_note(&st, &nv_hal, false, 1000.0f);
    nv.clear_lies = true;
    TEST_ASSERT_FALSE(pss_revoke(&st, &nv_hal));   /* read back: still there */
    TEST_ASSERT_EQUAL_UINT32(1u, st.failures);
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
    RUN_TEST(test_sensor_failure_open_starts_at_r_850c);
    RUN_TEST(test_sensor_failure_short_ends_at_r_minus_200c);
    RUN_TEST(test_flagged_plausible_over_temperature_is_a_temperature);
    RUN_TEST(test_register_07h_input_bits_are_a_sensor_failure);
    RUN_TEST(test_isense_run_latches_after_settle_and_hold);
    RUN_TEST(test_isense_run_ignores_commands_below_the_burst_safe_floor);
    RUN_TEST(test_isense_run_accepts_any_current_above_near_zero);
    RUN_TEST(test_isense_run_needs_the_full_hold);
    RUN_TEST(test_isense_pulse_passes_with_current_and_fails_without);
    RUN_TEST(test_isense_pulse_waits_while_the_command_is_held_at_zero);
    RUN_TEST(test_isense_pulse_is_clamped_to_the_power_limit);
    RUN_TEST(test_isense_xcheck_agreeing_senses_never_latch);
    RUN_TEST(test_isense_xcheck_disagreeing_senses_latch_after_hold);
    RUN_TEST(test_leak_two_chained_cycles_latch);
    RUN_TEST(test_leak_one_cycle_or_cycles_beyond_the_gap_never_latch);
    RUN_TEST(test_leak_a_resolving_disturbance_breaks_the_chain);
    RUN_TEST(test_leak_contact_doubt_or_no_rim_restarts_the_count);
    RUN_TEST(test_leak_a_probe_not_started_by_the_suspect_does_not_count);
    RUN_TEST(test_rimlim_limit_is_the_glass_envelope_plus_the_hot_stack);
    RUN_TEST(test_rimlim_a_rising_rim_above_the_limit_latches_after_sustain);
    RUN_TEST(test_rimlim_a_steady_rim_just_under_the_limit_never_latches);
    RUN_TEST(test_rimlim_a_falling_glass_above_the_limit_never_latches);
    RUN_TEST(test_rimlim_needs_a_full_fall_window_and_the_full_sustain);
    RUN_TEST(test_rimlim_rejects_bad_parameters);
    RUN_TEST(test_soak_leak_after_the_soak_and_not_before);
    RUN_TEST(test_soak_coil_activity_restarts_the_soak_and_the_history);
    RUN_TEST(test_soak_skips_on_a_saturated_or_warm_or_drifting_reference);
    RUN_TEST(test_soak_slow_heatsink_does_not_false_latch);
    RUN_TEST(test_soak_rate_keeps_leaks_below_limit_and_skips_both_directions);
    RUN_TEST(test_soak_rate_uses_complete_buckets);
    RUN_TEST(test_soak_skips_when_the_pt100_moved_or_the_rim_is_warm);
    RUN_TEST(test_soak_needs_the_whole_window_and_survives_clock_steps);
    RUN_TEST(test_soak_agreement_and_parameters);
    RUN_TEST(test_soak_threshold_follows_the_rail_through_the_window);
    RUN_TEST(test_soak_credit_counts_coil_off_time_but_not_history);
    RUN_TEST(test_store_writes_once_per_off_period_and_revokes_before_power);
    RUN_TEST(test_store_failures_are_unknown_never_soaked);
}
