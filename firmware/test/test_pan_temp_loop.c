/**
 * @file test_pan_temp_loop.c
 * @brief sensor-r3 C1 loop: sensor guard, plant-gain identification, rate PID
 *        and the power authority ("never chase a cold reading").
 */

#include <math.h>
#include <stdio.h>
#include <string.h>

#include "unity/unity.h"
#include "../components/control/pan_temp_loop.h"

/* ---------------------------------------------------------------- guard -- */

static void test_guard_decodes_every_max31865_bit(void)
{
    psg_diag_t d;
    TEST_ASSERT_EQUAL_INT(PSG_OK, psg_decode_max31865(0x00u, true, &d));
    TEST_ASSERT_EQUAL_INT(PSG_DIAG_NONE, d);
    TEST_ASSERT_EQUAL_INT(PSG_OK, psg_decode_max31865(0x03u, true, &d));   /* D1/D0 don't care */
    TEST_ASSERT_EQUAL_INT(PSG_FAULT_OPEN, psg_decode_max31865(0x80u, true, &d));
    TEST_ASSERT_EQUAL_INT(PSG_DIAG_REG_RTD_HIGH, d);
    TEST_ASSERT_EQUAL_INT(PSG_FAULT_SHORT, psg_decode_max31865(0x40u, true, &d));
    TEST_ASSERT_EQUAL_INT(PSG_DIAG_REG_RTD_LOW, d);
    TEST_ASSERT_EQUAL_INT(PSG_FAULT_OPEN, psg_decode_max31865(0x20u, true, &d));
    TEST_ASSERT_EQUAL_INT(PSG_DIAG_REG_REFIN_HIGH, d);
    TEST_ASSERT_EQUAL_INT(PSG_FAULT_OPEN, psg_decode_max31865(0x10u, true, &d));
    TEST_ASSERT_EQUAL_INT(PSG_DIAG_REG_REFIN_LOW, d);
    TEST_ASSERT_EQUAL_INT(PSG_FAULT_OPEN, psg_decode_max31865(0x08u, true, &d));
    TEST_ASSERT_EQUAL_INT(PSG_DIAG_REG_RTDIN_LOW, d);
    TEST_ASSERT_EQUAL_INT(PSG_FAULT_OPEN, psg_decode_max31865(0x04u, true, &d));
    TEST_ASSERT_EQUAL_INT(PSG_DIAG_REG_OVUV, d);
    /* short wins over open, as in state_machine_report_rtd_device_fault() */
    TEST_ASSERT_EQUAL_INT(PSG_FAULT_SHORT, psg_decode_max31865(0xC0u, true, &d));
    /* failed SPI read fails closed */
    TEST_ASSERT_EQUAL_INT(PSG_FAULT_OPEN, psg_decode_max31865(0x00u, false, &d));
    TEST_ASSERT_EQUAL_INT(PSG_DIAG_SPI_READ, d);
}

static psg_input_t sample(float t)
{
    psg_input_t in = {.t_pt100_c = t, .t_rim_c = 60.0f, .fresh = true, .spi_ok = true,
                      .fault_status = 0u, .heating = true};
    return in;
}

static void test_guard_range(void)
{
    psg_t g;
    psg_params_t p;
    psg_output_t o;
    psg_default_params(&p);
    TEST_ASSERT_TRUE(psg_init(&g, &p));
    psg_input_t in = sample(319.9f);
    psg_step(&g, &in, &o);
    TEST_ASSERT_EQUAL_INT(PSG_OK, o.verdict);
    in = sample(320.5f);
    psg_step(&g, &in, &o);
    TEST_ASSERT_EQUAL_INT(PSG_FAULT_OPEN, o.verdict);
    TEST_ASSERT_EQUAL_INT(PSG_DIAG_RANGE_HIGH, o.diag);
    TEST_ASSERT_FALSE(o.sample_valid);
    psg_clear(&g);
    in = sample(-20.5f);
    psg_step(&g, &in, &o);
    TEST_ASSERT_EQUAL_INT(PSG_FAULT_SHORT, o.verdict);
    TEST_ASSERT_EQUAL_INT(PSG_DIAG_RANGE_LOW, o.diag);
    psg_clear(&g);
    in = sample(NAN);
    psg_step(&g, &in, &o);
    TEST_ASSERT_EQUAL_INT(PSG_FAULT_OPEN, o.verdict);
    TEST_ASSERT_EQUAL_INT(PSG_DIAG_NOT_FINITE, o.diag);
}

static void test_guard_stale_drdy(void)
{
    psg_t g;
    psg_params_t p;
    psg_output_t o;
    psg_default_params(&p);
    TEST_ASSERT_TRUE(psg_init(&g, &p));
    psg_input_t in = sample(100.0f);
    psg_step(&g, &in, &o);
    in.fresh = false;
    for (int i = 0; i < 3; i++) {
        psg_step(&g, &in, &o);
        TEST_ASSERT_EQUAL_INT(PSG_OK, o.verdict);
        TEST_ASSERT_FALSE(o.sample_valid);   /* predict-only, no fault yet */
    }
    psg_step(&g, &in, &o);
    TEST_ASSERT_EQUAL_INT(PSG_FAULT_OPEN, o.verdict);
    TEST_ASSERT_EQUAL_INT(PSG_DIAG_STALE_DRDY, o.diag);
}

static void test_guard_rate_spike_is_fault(void)
{
    psg_t g;
    psg_params_t p;
    psg_output_t o;
    psg_default_params(&p);
    TEST_ASSERT_TRUE(psg_init(&g, &p));
    const float seq[] = {150.0f, 150.1f, 155.0f, 150.2f};
    for (size_t i = 0; i < 4; i++) {
        psg_input_t in = sample(seq[i]);
        psg_step(&g, &in, &o);
    }
    TEST_ASSERT_EQUAL_INT(PSG_FAULT_OPEN, o.verdict);
    TEST_ASSERT_EQUAL_INT(PSG_DIAG_RATE_SPIKE, o.diag);
}

/* A hot pan placed on the cold disc: first-order rise of 175 K with a 0.4 s
 * time constant moves faster than 30 K/s for about 1 s. Not a fault. */
static void test_guard_hot_pan_slew_is_not_fault(void)
{
    psg_t g;
    psg_params_t p;
    psg_output_t o;
    psg_default_params(&p);
    TEST_ASSERT_TRUE(psg_init(&g, &p));
    for (int k = 0; k < 100; k++) {
        psg_input_t in = sample(25.0f + 175.0f * (1.0f - expf(-(float)k * 0.1f / 0.4f)));
        psg_step(&g, &in, &o);
        TEST_ASSERT_EQUAL_INT(PSG_OK, o.verdict);
    }
}

static void test_guard_sustained_slew_is_fault(void)
{
    psg_t g;
    psg_params_t p;
    psg_output_t o;
    psg_default_params(&p);
    TEST_ASSERT_TRUE(psg_init(&g, &p));
    int fault_k = -1;
    for (int k = 0; k < 60; k++) {
        psg_input_t in = sample(30.0f + 4.0f * (float)k);   /* 40 K/s ramp */
        psg_step(&g, &in, &o);
        if (o.verdict != PSG_OK && fault_k < 0) {
            fault_k = k;
        }
    }
    TEST_ASSERT_EQUAL_INT(PSG_DIAG_RATE_SLEW, o.diag);
    TEST_ASSERT_EQUAL_INT(31, fault_k);   /* > 3.0 s of slew */
}

static void test_guard_cross_check_requests_probe(void)
{
    psg_t g;
    psg_params_t p;
    psg_output_t o;
    psg_default_params(&p);
    TEST_ASSERT_TRUE(psg_init(&g, &p));
    int fired = -1;
    for (int k = 0; k < 400; k++) {
        psg_input_t in = sample(34.0f);   /* rim 60: 26 K below */
        psg_step(&g, &in, &o);
        if (o.suspect && fired < 0) {
            fired = k;
        }
        TEST_ASSERT_EQUAL_INT(PSG_OK, o.verdict);
    }
    TEST_ASSERT_EQUAL_INT(299, fired);
    /* 16 K below is inside the rim NTC's own error (PCB D5): never suspect. */
    psg_clear(&g);
    for (int k = 0; k < 400; k++) {
        psg_input_t in = sample(44.0f);
        psg_step(&g, &in, &o);
        TEST_ASSERT_FALSE(o.suspect);
    }
    /* Not while the reading follows the heating (a pan quenched by a cold
     * load, rising 0.2 K/s): the count restarts each time it rises 2 K. */
    psg_clear(&g);
    for (int k = 0; k < 400; k++) {
        psg_input_t in = sample(30.0f + 0.02f * (float)k);
        psg_step(&g, &in, &o);
        TEST_ASSERT_FALSE(o.suspect);
    }
    /* ... nor when it dipped first and then recovers (food drop): the rise is
     * measured from the lowest reading. */
    psg_clear(&g);
    for (int k = 0; k < 400; k++) {
        const float t = k < 100 ? 33.0f - 0.06f * (float)k : 27.0f + 0.02f * (float)(k - 100);
        psg_input_t in = sample(t);
        psg_step(&g, &in, &o);
        TEST_ASSERT_FALSE(o.suspect);
    }
    /* Not while the coil is off. */
    psg_clear(&g);
    for (int k = 0; k < 400; k++) {
        psg_input_t in = sample(34.0f);
        in.heating = false;
        psg_step(&g, &in, &o);
        TEST_ASSERT_FALSE(o.suspect);
    }
}

static int sink_short, sink_open, sink_calls;
static void fake_sink(bool short_fault, bool open_fault, void *ctx)
{
    (void)ctx;
    sink_calls++;
    sink_short = short_fault;
    sink_open = open_fault;
}

static void test_guard_reports_into_rtd_fault_sink(void)
{
    sink_calls = 0;
    psg_report(PSG_OK, fake_sink, NULL);
    TEST_ASSERT_EQUAL_INT(0, sink_calls);
    psg_report(PSG_FAULT_SHORT, fake_sink, NULL);
    TEST_ASSERT_EQUAL_INT(1, sink_calls);
    TEST_ASSERT_TRUE(sink_short && !sink_open);
    psg_report(PSG_FAULT_OPEN, fake_sink, NULL);
    TEST_ASSERT_TRUE(!sink_short && sink_open);
}

/* ----------------------------------------------------------- plant gain -- */

/* Ideal lumped pan dT/dt = a P: the identified gain converges to a, and the
 * estimate records which power source built it. */
static void test_plant_gain_identifies_lumped_pan(void)
{
    pg_t g;
    pg_params_t p;
    pg_default_params(&p);
    TEST_ASSERT_TRUE(pg_init(&g, &p));
    pg_begin_phase(&g, true);
    const float a = 7.7e-4f;
    float T = 25.0f;
    TEST_ASSERT_FLOAT_WITHIN(1e-9f, p.a0_k_per_j, pg_gain(&g));
    for (int k = 0; k < 2000; k++) {
        const float P = 1200.0f + 300.0f * sinf(0.01f * (float)k);
        pg_update(&g, T, P, PG_POWER_MEASURED, true);
        T += a * P * 0.1f;
    }
    TEST_ASSERT_TRUE(pg_valid(&g));
    TEST_ASSERT_FLOAT_WITHIN(0.02f * a, a, pg_gain(&g));
    TEST_ASSERT_EQUAL_UINT(PG_SRC_MASK_MEASURED, pg_source_mask(&g));
}

static void test_plant_gain_gate_and_clamps(void)
{
    pg_t g;
    pg_params_t p;
    pg_default_params(&p);
    TEST_ASSERT_TRUE(pg_init(&g, &p));
    pg_begin_phase(&g, true);
    float T = 25.0f;
    /* Gate closed: no learning however much data. */
    for (int k = 0; k < 2000; k++) {
        pg_update(&g, T, 1500.0f, PG_POWER_ESTIMATED, false);
        T += 2e-4f * 1500.0f * 0.1f;
    }
    TEST_ASSERT_FALSE(pg_valid(&g));
    TEST_ASSERT_EQUAL_UINT(0u, g.updates);
    TEST_ASSERT_FLOAT_WITHIN(1e-9f, p.a0_k_per_j, pg_gain(&g));
    /* Estimated power is tracked as such. */
    pg_begin_phase(&g, true);
    for (int k = 0; k < 2000; k++) {
        pg_update(&g, T, 1500.0f, PG_POWER_ESTIMATED, true);
        T += 2e-4f * 1500.0f * 0.1f;
    }
    TEST_ASSERT_TRUE(pg_valid(&g));
    TEST_ASSERT_EQUAL_UINT(PG_SRC_MASK_ESTIMATED, pg_source_mask(&g));
    TEST_ASSERT_FLOAT_WITHIN(0.02f * 2e-4f, 2e-4f, pg_gain(&g));
    /* Non-finite input never corrupts the estimate. */
    pg_update(&g, NAN, 1500.0f, PG_POWER_ESTIMATED, true);
    TEST_ASSERT_TRUE(isfinite(pg_gain(&g)));
    /* Clamp. */
    g.theta = 1.0f;
    TEST_ASSERT_FLOAT_WITHIN(1e-9f, p.a_max_k_per_j, pg_gain(&g));
    g.theta = -1.0f;
    TEST_ASSERT_FLOAT_WITHIN(1e-9f, p.a_min_k_per_j, pg_gain(&g));
}

static void test_plant_gain_never_mixes_power_sources_in_a_window(void)
{
    pg_t g;
    pg_params_t p;
    pg_default_params(&p);
    TEST_ASSERT_TRUE(pg_init(&g, &p));
    pg_begin_phase(&g, true);
    float T = 25.0f;
    for (int k = 0; k < 2000; k++) {
        /* alternate provenance every 15 s: no window is ever pure */
        const pg_power_source_t s = ((k / 150) % 2) ? PG_POWER_ESTIMATED : PG_POWER_MEASURED;
        pg_update(&g, T, 1000.0f, s, true);
        T += 1e-3f * 1000.0f * 0.1f;
    }
    TEST_ASSERT_EQUAL_UINT(0u, g.updates);
}

/* -------------------------------------------------------------- rate PID -- */

static void test_rate_pid_matches_reference_law(void)
{
    prp_t c;
    prp_params_t p;
    prp_default_params(&p);
    TEST_ASSERT_TRUE(prp_init(&c, &p));
    const float a = 1e-3f;
    prp_start(&c, 25.0f);
    /* sp 200: sp_eff ramps 0.1 K per step from 25 */
    float P = prp_step(&c, 200.0f, 25.0f, a);
    TEST_ASSERT_FLOAT_WITHIN(1e-4f, 25.1f, prp_sp_eff(&c));
    /* e = 0.1, |e| < 10: integ = 0.002*0.1*0.1 = 2e-5; dTf = 0 */
    TEST_ASSERT_FLOAT_WITHIN(1e-3f, (0.1f * 0.1f + 2e-5f) / a, P);
    /* derivative filter: a 1 K jump -> dTf = 0.05 * (10 - 0) = 0.5 K/s */
    P = prp_step(&c, 200.0f, 26.0f, a);
    TEST_ASSERT_FLOAT_WITHIN(1e-4f, 0.5f, c.dtf);
    TEST_ASSERT_FLOAT_WITHIN(1e-6f, 0.0f, P);   /* 0.1*(-0.8) + I - 0.5 < 0 -> 0 */
    /* far below: saturates at P_MAX, integrator frozen outside the band */
    prp_start(&c, 25.0f);
    c.sp_eff = 200.0f;
    const float integ_before = c.integ;
    P = prp_step(&c, 200.0f, 25.0f, a);
    TEST_ASSERT_FLOAT_WITHIN(1e-3f, 1800.0f, P);
    TEST_ASSERT_FLOAT_WITHIN(1e-9f, integ_before, c.integ);
    /* setpoint drops apply at once */
    prp_step(&c, 100.0f, 25.0f, a);
    TEST_ASSERT_FLOAT_WITHIN(1e-6f, 100.0f, prp_sp_eff(&c));
    TEST_ASSERT_FALSE(prp_ramping(&c));
}

static void test_rate_pid_integrator_clamp_scales_with_gain(void)
{
    prp_t c;
    prp_params_t p;
    prp_default_params(&p);
    TEST_ASSERT_TRUE(prp_init(&c, &p));
    prp_start(&c, 195.0f);
    c.sp_eff = 200.0f;
    for (int k = 0; k < 100000; k++) {
        (void)prp_step(&c, 200.0f, 195.0f, 1e-4f);
    }
    TEST_ASSERT_FLOAT_WITHIN(1e-6f, 1800.0f * 1e-4f, c.integ);
}

/* ------------------------------------------------------- loop authority -- */

static ptl_input_t loop_in(float y, float sp, float p_applied)
{
    ptl_input_t in = {.t_pt100_c = y, .t_rim_c = 60.0f, .fresh = true, .spi_ok = true, .fault_status = 0u,
                      .setpoint_c = sp, .power_applied_w = p_applied, .power_source = PG_POWER_MEASURED};
    return in;
}

static void test_loop_fault_forces_zero_power(void)
{
    ptl_t l;
    ptl_params_t p;
    ptl_default_params(&p);
    TEST_ASSERT_TRUE(ptl_init(&l, &p, 25.0f));
    ptl_output_t o;
    float P = 0.0f;
    for (int k = 0; k < 50; k++) {
        ptl_input_t in = loop_in(25.0f, 200.0f, P);
        ptl_step(&l, &in, &o);
        P = o.p_cmd_w;
    }
    TEST_ASSERT_TRUE(o.p_cmd_w > 0.0f);
    ptl_input_t in = loop_in(25.0f, 200.0f, P);
    in.fault_status = PSG_MAX31865_REFIN_LOW;
    ptl_step(&l, &in, &o);
    TEST_ASSERT_EQUAL_INT(PSG_FAULT_OPEN, o.fault);
    TEST_ASSERT_FLOAT_WITHIN(1e-6f, 0.0f, o.p_cmd_w);
    TEST_ASSERT_TRUE(o.p_pid_w > 0.0f);   /* the PID still asks: authority wins */
    /* latched: stays off with a clean register afterwards */
    in.fault_status = 0u;
    for (int k = 0; k < 20; k++) {
        ptl_step(&l, &in, &o);
        TEST_ASSERT_FLOAT_WITHIN(1e-6f, 0.0f, o.p_cmd_w);
    }
}

/* The pan is lifted while heating: the reading decays freely toward the rim.
 * D1 must take over (probe power, then zero) although the PID asks for full
 * power, raise LOST once, and show the UI message. */
static void test_loop_never_chases_a_cold_reading(void)
{
    ptl_t l;
    ptl_params_t p;
    ptl_default_params(&p);
    p.identify_gain = false;
    p.fixed_gain_k_per_j = 1.7e-3f;
    TEST_ASSERT_TRUE(ptl_init(&l, &p, 200.0f));
    ptl_output_t o;
    float y = 200.0f, P = 1800.0f;
    int lost_k = -1, lost_events = 0;
    bool pid_wanted_full_while_lost = false;
    for (int k = 0; k < 1200; k++) {
        y = 62.0f + (y - 62.0f) * expf(-0.1f / 50.5f);
        ptl_input_t in = loop_in(y, 230.0f, P);
        ptl_step(&l, &in, &o);
        P = o.p_cmd_w;
        if (o.cc_event == CC_EVT_LOST) {
            lost_events++;
            lost_k = k;
        }
        if (o.cc_state == CC_LOST) {
            TEST_ASSERT_FLOAT_WITHIN(1e-6f, 0.0f, o.p_cmd_w);
            TEST_ASSERT_TRUE(o.ui_pan_must_touch);
            if (o.p_pid_w >= 1799.0f) {
                pid_wanted_full_while_lost = true;
            }
        }
        if (o.cc_state == CC_PROBE || o.cc_state == CC_RETRY) {
            TEST_ASSERT_TRUE(o.p_cmd_w == 0.0f || fabsf(o.p_cmd_w - 900.0f) < 1e-3f);
        }
    }
    TEST_ASSERT_TRUE(lost_k > 0);
    TEST_ASSERT_EQUAL_INT(1, lost_events);
    TEST_ASSERT_TRUE(pid_wanted_full_while_lost);
}

void run_pan_temp_loop_tests(void)
{
    RUN_TEST(test_guard_decodes_every_max31865_bit);
    RUN_TEST(test_guard_range);
    RUN_TEST(test_guard_stale_drdy);
    RUN_TEST(test_guard_rate_spike_is_fault);
    RUN_TEST(test_guard_hot_pan_slew_is_not_fault);
    RUN_TEST(test_guard_sustained_slew_is_fault);
    RUN_TEST(test_guard_cross_check_requests_probe);
    RUN_TEST(test_guard_reports_into_rtd_fault_sink);
    RUN_TEST(test_plant_gain_identifies_lumped_pan);
    RUN_TEST(test_plant_gain_gate_and_clamps);
    RUN_TEST(test_plant_gain_never_mixes_power_sources_in_a_window);
    RUN_TEST(test_rate_pid_matches_reference_law);
    RUN_TEST(test_rate_pid_integrator_clamp_scales_with_gain);
    RUN_TEST(test_loop_fault_forces_zero_power);
    RUN_TEST(test_loop_never_chases_a_cold_reading);
}
