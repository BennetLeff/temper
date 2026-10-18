/**
 * @file test_pan_temp_loop.c
 * @brief sensor-r3 C1 loop: sensor guard, plant-gain identification, rate PID
 *        (with the latent-plateau guard), the contact-shift window and the
 *        power authority ("never chase a cold reading").
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

/* Later setpoint steps (DECISIONS.md D-ID2): one hold-to-hold energy-balance
 * update per step. Lumped pan with a loss linear in T that the first heat-up
 * (k_loss = 0) absorbs into a low a; the later step measures the loss at both
 * holds and recovers the true a. */
typedef struct {
    float a, k_loss, T;
} lumped_t;

static void lumped_run(pg_t *g, lumped_t *m, float P, float seconds, bool gate)
{
    for (int k = 0; k < (int)(seconds * 10.0f); k++) {
        pg_update(g, m->T, P, PG_POWER_MEASURED, gate);
        m->T += m->a * (P - m->k_loss * (m->T - 25.0f)) * 0.1f;
    }
}

/* Heat at full power to t_to, then hold there at exactly the loss power. */
static void lumped_step_and_hold(pg_t *g, lumped_t *m, float t_to, float hold_s, bool gate)
{
    while (m->T < t_to) {
        lumped_run(g, m, 1800.0f, 0.1f, gate);
    }
    lumped_run(g, m, m->k_loss * (m->T - 25.0f), hold_s, gate);
}

static void first_heat_up(pg_t *g, pg_params_t *p, lumped_t *m)
{
    pg_default_params(p);
    TEST_ASSERT_TRUE(pg_init(g, p));
    pg_begin_phase(g, true);
    lumped_step_and_hold(g, m, 180.0f, 0.0f, true);
    lumped_run(g, m, m->k_loss * (m->T - 25.0f), 30.0f, false);
    TEST_ASSERT_TRUE(pg_valid(g));
}

static void test_plant_gain_later_step_recovers_a_from_hold_to_hold(void)
{
    pg_t g;
    pg_params_t p;
    lumped_t m = {.a = 1.8e-3f, .k_loss = 1.6f, .T = 25.0f};
    first_heat_up(&g, &p, &m);
    const float a_first = pg_gain(&g);
    TEST_ASSERT_TRUE(a_first < 0.95f * m.a);    /* loss absorbed: biased low */
    pg_begin_phase(&g, false);
    lumped_step_and_hold(&g, &m, 210.0f, 15.0f, true);
    TEST_ASSERT_EQUAL_UINT32(1u, g.later_updates);
    TEST_ASSERT_FLOAT_WITHIN(0.05f * m.a, m.a, pg_gain(&g));
}

static void test_plant_gain_later_step_rejects_a_boil_plateau(void)
{
    pg_t g;
    pg_params_t p;
    lumped_t m = {.a = 6e-4f, .k_loss = 1.0f, .T = 25.0f};
    pg_default_params(&p);
    TEST_ASSERT_TRUE(pg_init(&g, &p));
    pg_begin_phase(&g, true);
    lumped_step_and_hold(&g, &m, 90.0f, 0.0f, true);
    lumped_run(&g, &m, m.k_loss * (m.T - 25.0f), 30.0f, false);
    const float a_before = pg_gain(&g);
    pg_begin_phase(&g, false);
    lumped_step_and_hold(&g, &m, 100.0f, 0.0f, true);
    /* boiling: the reading sits at 100 degC while the coil runs flat out */
    for (int k = 0; k < 300; k++) {
        pg_update(&g, 100.0f, 1800.0f, PG_POWER_MEASURED, true);
    }
    TEST_ASSERT_EQUAL_UINT32(0u, g.later_updates);
    TEST_ASSERT_EQUAL_UINT32(1u, g.rejected);
    TEST_ASSERT_FLOAT_WITHIN(1e-9f, a_before, pg_gain(&g));
}

static void test_plant_gain_later_step_needs_a_clean_phase_and_a_measured_hold(void)
{
    pg_t g;
    pg_params_t p;
    lumped_t m = {.a = 1.8e-3f, .k_loss = 1.6f, .T = 25.0f};
    first_heat_up(&g, &p, &m);
    const float a_before = pg_gain(&g);
    /* the gate drops mid-step (D1 event, lifted pan): no update */
    pg_begin_phase(&g, false);
    lumped_step_and_hold(&g, &m, 195.0f, 0.0f, true);
    lumped_run(&g, &m, 0.0f, 1.0f, false);
    lumped_step_and_hold(&g, &m, 200.0f, 20.0f, true);
    TEST_ASSERT_EQUAL_UINT32(0u, g.later_updates);
    TEST_ASSERT_FLOAT_WITHIN(1e-9f, a_before, pg_gain(&g));
    /* a step that does not start from a hold: no update */
    lumped_run(&g, &m, 1800.0f, 5.0f, true);
    pg_begin_phase(&g, false);
    lumped_step_and_hold(&g, &m, m.T + 20.0f, 20.0f, true);
    TEST_ASSERT_EQUAL_UINT32(0u, g.later_updates);
    TEST_ASSERT_FLOAT_WITHIN(1e-9f, a_before, pg_gain(&g));
}

static void test_plant_gain_later_step_limits_a_decrease(void)
{
    pg_t g;
    pg_params_t p;
    lumped_t m = {.a = 1.8e-3f, .k_loss = 1.6f, .T = 25.0f};
    first_heat_up(&g, &p, &m);
    pg_begin_phase(&g, false);
    lumped_step_and_hold(&g, &m, 210.0f, 15.0f, true);
    const float a0 = pg_gain(&g);
    /* food adds a third to the heat capacity (a x 0.75, inside the 1/1.5
     * plausibility band); one phase may lower a only to 1/1.25 */
    m.a *= 0.75f;
    lumped_run(&g, &m, m.k_loss * (m.T - 25.0f), 15.0f, false);
    pg_begin_phase(&g, false);
    lumped_step_and_hold(&g, &m, 240.0f, 15.0f, true);
    TEST_ASSERT_EQUAL_UINT32(2u, g.later_updates);
    TEST_ASSERT_FLOAT_WITHIN(1e-3f * a0, a0 / 1.25f, pg_gain(&g));
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

/* Latent-plateau guard (DECISIONS.md D-LPG): T_hat flat in the boiling band
 * well below the setpoint limits the PID to lpg_rate / a once the energy
 * budget (a * E >= sp - T_hat since entering the band from below) is spent;
 * at once when the reading fell into the band; outside the band, while rising,
 * or near the setpoint it does nothing. */
static void test_rate_pid_latent_plateau_guard(void)
{
    prp_t c;
    prp_params_t p;
    prp_default_params(&p);
    TEST_ASSERT_TRUE(p.lpg_enable);
    TEST_ASSERT_TRUE(p.lpg_budget);
    TEST_ASSERT_TRUE(prp_init(&c, &p));
    const float a = 1e-3f;
    prp_start(&c, 100.0f);
    c.sp_eff = 200.0f;
    float P = 0.0f;
    for (int k = 0; k < 100; k++) {
        P = prp_step(&c, 200.0f, 100.0f, a);
        TEST_ASSERT_FALSE(prp_lpg_active(&c));   /* needs lpg_n earlier samples */
    }
    TEST_ASSERT_FLOAT_WITHIN(1e-3f, 1800.0f, P);
    /* budget: (200 - 100) / a = 1e5 J at 1800 W = 55.6 s */
    int k_cap = -1;
    for (int k = 0; k < 1000 && k_cap < 0; k++) {
        P = prp_step(&c, 200.0f, 100.0f, a);
        if (prp_lpg_active(&c)) {
            k_cap = k;
        }
    }
    TEST_ASSERT_TRUE(k_cap >= 550 && k_cap <= 560);
    TEST_ASSERT_FLOAT_WITHIN(1e-3f, 0.2f / a, P);

    /* the reading fell into the band from 150 C: no budget, limited once flat */
    TEST_ASSERT_TRUE(prp_init(&c, &p));
    prp_start(&c, 150.0f);
    c.sp_eff = 200.0f;
    for (int k = 0; k < 100; k++) {
        (void)prp_step(&c, 200.0f, 150.0f, a);
    }
    k_cap = -1;
    for (int k = 0; k < 300 && k_cap < 0; k++) {
        P = prp_step(&c, 200.0f, 100.0f, a);
        if (prp_lpg_active(&c)) {
            k_cap = k;
        }
    }
    TEST_ASSERT_TRUE(k_cap >= 0 && k_cap <= 100);
    TEST_ASSERT_FLOAT_WITHIN(1e-3f, 0.2f / a, P);

    /* the same flat history at 150 C (out of the band): no limit */
    TEST_ASSERT_TRUE(prp_init(&c, &p));
    prp_start(&c, 150.0f);
    c.sp_eff = 200.0f;
    for (int k = 0; k < 150; k++) {
        P = prp_step(&c, 200.0f, 150.0f, a);
        TEST_ASSERT_FALSE(prp_lpg_active(&c));
    }
    /* rising through the band at 0.3 K/s: no limit */
    TEST_ASSERT_TRUE(prp_init(&c, &p));
    prp_start(&c, 90.0f);
    c.sp_eff = 200.0f;
    for (int k = 0; k < 600; k++) {   /* 90 -> 108 C */
        P = prp_step(&c, 200.0f, 90.0f + 0.03f * (float)k, a);
        TEST_ASSERT_FALSE(prp_lpg_active(&c));
    }
    /* flat at 100 C with the setpoint at 103 C (a simmer hold): no limit */
    TEST_ASSERT_TRUE(prp_init(&c, &p));
    prp_start(&c, 100.0f);
    for (int k = 0; k < 150; k++) {
        P = prp_step(&c, 103.0f, 100.0f, a);
        TEST_ASSERT_FALSE(prp_lpg_active(&c));
    }
    /* disabled */
    p.lpg_enable = false;
    TEST_ASSERT_TRUE(prp_init(&c, &p));
    prp_start(&c, 100.0f);
    c.sp_eff = 200.0f;
    for (int k = 0; k < 150; k++) {
        P = prp_step(&c, 200.0f, 100.0f, a);
    }
    TEST_ASSERT_FALSE(prp_lpg_active(&c));
    TEST_ASSERT_FLOAT_WITHIN(1e-3f, 1800.0f, P);
}

/* ------------------------------------------------- contact-shift window -- */

/* Cartridge truth with the estimator's own constants (pte model, 5 Euler
 * substeps): the pan centre follows t_pan, the contact is g_c W/K. */
typedef struct {
    double tcap, tel;
} cart_t;

static void cart_step(cart_t *m, const pte_params_t *k, double g_c, double t_pan, double t_sink)
{
    const double h = 0.1 / 5.0;
    for (int i = 0; i < 5; i++) {
        const double dcap = (g_c * (t_pan - m->tcap) - k->g_leak_w_per_k * (m->tcap - t_sink) -
                             k->g_bond_w_per_k * (m->tcap - m->tel)) / k->c_cap_j_per_k;
        const double dele = k->g_bond_w_per_k * (m->tcap - m->tel) / k->c_el_j_per_k;
        m->tcap += h * dcap;
        m->tel += h * dele;
    }
}

typedef struct {
    int opens_down, accepts, escalates, reverts;
    float h_accept, t_hat_end;
    int first_open_k;
} csw_run_t;

/* A pan held at 200 C (sink 60 C, constant power p_w until k_pdrop, then
 * p_after_w); the contact steps from h0 to h1 at k_step. Deterministic
 * +-0.05 K dither on the reading. allow_until_k: gate drops after that. */
static csw_run_t csw_run(float h0, float h1, int k_step, float p_w, int k_pdrop, float p_after_w, int allow_until_k,
                         int n)
{
    pte_params_t kp;
    pte_default_params(&kp);
    csw_params_t cp;
    csw_default_params(&cp);
    static csw_t c;
    pte_t est;
    TEST_ASSERT_TRUE(pte_init(&est, &kp, 200.0f));
    TEST_ASSERT_TRUE(csw_init(&c, &cp, &kp));
    const double area = kp.contact_area_m2;
    cart_t m = {200.0, 200.0};
    csw_run_t r = {0};
    r.first_open_k = -1;
    for (int k = 0; k < n; k++) {
        const double g = (k < k_step ? h0 : h1) * area;
        const double t_sink = 60.0;
        /* settle the truth at the steady offset before the run */
        if (k == 0) {
            for (int i = 0; i < 3000; i++) {
                cart_step(&m, &kp, h0 * area, 200.0, t_sink);
            }
        }
        cart_step(&m, &kp, g, 200.0, t_sink);
        const float y = (float)m.tel + ((k % 2) ? 0.05f : -0.05f);
        const float pw = (k < k_pdrop) ? p_w : p_after_w;
        csw_output_t o;
        csw_step(&c, &est, y, (float)t_sink, pw, k < allow_until_k, true, &o);
        switch (o.event) {
        case CSW_EVT_OPEN_DOWN:
            r.opens_down++;
            if (r.first_open_k < 0) {
                r.first_open_k = k;
            }
            break;
        case CSW_EVT_ACCEPT:
            r.accepts++;
            r.h_accept = o.h_model_w_per_m2k;
            break;
        case CSW_EVT_ESCALATE:
            r.escalates++;
            break;
        case CSW_EVT_REVERT:
            r.reverts++;
            break;
        default:
            break;
        }
        r.t_hat_end = o.t_hat_c;
    }
    return r;
}

/* An abrupt drop 1300 -> 400 W/m2K at a constant 200 C pan: the window opens
 * within 1.5 s, accepts a contact within 30 % of the truth, and the estimate
 * returns to the pan temperature (the fixed-contact KF reads low by the
 * change in the static offset, about 3 K). */
static void test_csw_lowers_contact_after_abrupt_drop(void)
{
    const csw_run_t r = csw_run(1300.0f, 400.0f, 600, 300.0f, 1 << 30, 300.0f, 1 << 30, 1200);
    TEST_ASSERT_EQUAL_INT(1, r.opens_down);
    TEST_ASSERT_TRUE(r.first_open_k >= 600 && r.first_open_k <= 615);
    TEST_ASSERT_EQUAL_INT(1, r.accepts);
    TEST_ASSERT_TRUE(r.h_accept > 400.0f * 0.7f && r.h_accept < 400.0f * 1.3f);
    TEST_ASSERT_FLOAT_WITHIN(1.0f, 200.0f, r.t_hat_end);

    /* the same run with the window disabled reads low */
    pte_params_t kp;
    pte_default_params(&kp);
    pte_t est;
    TEST_ASSERT_TRUE(pte_init(&est, &kp, 200.0f));
    cart_t m = {200.0, 200.0};
    for (int i = 0; i < 3000; i++) {
        cart_step(&m, &kp, 1300.0 * kp.contact_area_m2, 200.0, 60.0);
    }
    float t_hat = 0.0f;
    for (int k = 0; k < 1200; k++) {
        cart_step(&m, &kp, (k < 600 ? 1300.0 : 400.0) * kp.contact_area_m2, 200.0, 60.0);
        t_hat = pte_step(&est, (float)m.tel + ((k % 2) ? 0.05f : -0.05f), 60.0f);
    }
    TEST_ASSERT_TRUE(t_hat < 198.5f);
}

/* A power cut explains a falling reading: no window. */
static void test_csw_power_change_vetoes_the_trigger(void)
{
    const csw_run_t r = csw_run(1300.0f, 400.0f, 600, 1000.0f, 590, 0.0f, 1 << 30, 900);
    TEST_ASSERT_EQUAL_INT(0, r.opens_down);
    TEST_ASSERT_EQUAL_INT(0, r.accepts);
}

/* Contact loss (h -> 2): faster than any partial contact -> ESCALATE (the
 * loop requests a D1 probe), and the model keeps the old contact. */
static void test_csw_escalates_on_contact_loss(void)
{
    const csw_run_t r = csw_run(1300.0f, 2.0f, 600, 300.0f, 1 << 30, 300.0f, 1 << 30, 700);
    TEST_ASSERT_EQUAL_INT(1, r.opens_down);
    TEST_ASSERT_EQUAL_INT(1, r.escalates);
    TEST_ASSERT_EQUAL_INT(0, r.accepts);
}

/* The gate drops mid-window (D1 left NORMAL): REVERT, contact unchanged;
 * csw_reset_contact returns the model to nominal. */
static void test_csw_gate_reverts_and_reset_returns_nominal(void)
{
    const csw_run_t r = csw_run(1300.0f, 400.0f, 600, 300.0f, 1 << 30, 300.0f, 620, 700);
    TEST_ASSERT_EQUAL_INT(1, r.opens_down);
    TEST_ASSERT_EQUAL_INT(1, r.reverts);
    TEST_ASSERT_EQUAL_INT(0, r.accepts);

    pte_params_t kp;
    pte_default_params(&kp);
    csw_params_t cp;
    csw_default_params(&cp);
    static csw_t c;
    pte_t est;
    TEST_ASSERT_TRUE(pte_init(&est, &kp, 200.0f));
    TEST_ASSERT_TRUE(csw_init(&c, &cp, &kp));
    c.g = 400.0 * kp.contact_area_m2;
    TEST_ASSERT_TRUE(pte_set_contact(&est, 400.0f));
    csw_reset_contact(&c, &est);
    TEST_ASSERT_FLOAT_WITHIN(1e-3f, kp.h_nom_w_per_m2k, csw_h_model(&c));
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
    RUN_TEST(test_plant_gain_later_step_recovers_a_from_hold_to_hold);
    RUN_TEST(test_plant_gain_later_step_rejects_a_boil_plateau);
    RUN_TEST(test_plant_gain_later_step_needs_a_clean_phase_and_a_measured_hold);
    RUN_TEST(test_plant_gain_later_step_limits_a_decrease);
    RUN_TEST(test_rate_pid_matches_reference_law);
    RUN_TEST(test_rate_pid_integrator_clamp_scales_with_gain);
    RUN_TEST(test_rate_pid_latent_plateau_guard);
    RUN_TEST(test_csw_lowers_contact_after_abrupt_drop);
    RUN_TEST(test_csw_power_change_vetoes_the_trigger);
    RUN_TEST(test_csw_escalates_on_contact_loss);
    RUN_TEST(test_csw_gate_reverts_and_reset_returns_nominal);
    RUN_TEST(test_loop_fault_forces_zero_power);
    RUN_TEST(test_loop_never_chases_a_cold_reading);
}
