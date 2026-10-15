/**
 * @file test_contact_check.c
 * @brief sensor-r3 contact-loss detector D1.
 *
 * Golden vectors (contact_check_vectors.h, from
 * output/temper-sensor-r3/firmware/export_vectors.py): closed-loop screen.py
 * runs for loss on 4 pans, food drop on 3 pans and nominal runs on 4 pans,
 * replayed through the C detector; the suspect and lost samples must match the
 * Python D1 decisions (to the sample), and nothing may latch on food/nominal.
 */

#include <math.h>
#include <stdio.h>
#include <string.h>

#include "unity/unity.h"
#include "../components/control/contact_check.h"
#include "contact_check_vectors.h"

/* screen.py's D1 exactly: the firmware additions D-D1a/b/c switched off. */
static cc_params_t screen_params_for(float tau_off)
{
    cc_params_t p;
    cc_default_params(&p);
    p.decay_tau_s = tau_off;
    p.decay_min_change_k = 0.0f;
    p.retry_decay_only = false;
    p.probe_min_sigma = 0.0f;
    return p;
}

static cc_params_t firmware_params_for(float tau_off)
{
    cc_params_t p;
    cc_default_params(&p);
    p.decay_tau_s = tau_off;
    return p;
}

static void test_defaults_match_screen(void)
{
    cc_params_t p;
    cc_default_params(&p);
    TEST_ASSERT_FLOAT_WITHIN(1e-6f, -0.8f, p.trig_rate_k_per_s);
    TEST_ASSERT_EQUAL_UINT(20u, p.trig_window);
    TEST_ASSERT_FLOAT_WITHIN(1e-6f, 1.0f, p.trig_hold_s);
    TEST_ASSERT_FLOAT_WITHIN(1e-6f, 0.4f, p.trig_pmin_frac);
    TEST_ASSERT_FLOAT_WITHIN(1e-6f, 5.0f, p.probe_off_s);
    TEST_ASSERT_FLOAT_WITHIN(1e-6f, 8.0f, p.probe_on_s);
    TEST_ASSERT_FLOAT_WITHIN(1e-6f, 0.5f, p.probe_p_frac);
    TEST_ASSERT_FLOAT_WITHIN(1e-6f, 3.0f, p.probe_lag_s);
    TEST_ASSERT_FLOAT_WITHIN(1e-6f, 0.25f, p.probe_frac);
    TEST_ASSERT_FLOAT_WITHIN(1e-6f, 20.0f, p.retry_s);
    TEST_ASSERT_FLOAT_WITHIN(1e-6f, 30.0f, p.holdoff_s);
    TEST_ASSERT_FLOAT_WITHIN(1e-6f, 0.5f, p.decay_rms_k);
    TEST_ASSERT_FLOAT_WITHIN(1e-6f, 25.0f, p.decay_asym_k);
    TEST_ASSERT_EQUAL_UINT(17u, p.decay_steps);
}

static void test_bounded_memory(void)
{
    cc_t c;
    cc_params_t p;
    cc_default_params(&p);
    TEST_ASSERT_TRUE(cc_init(&c, &p));
    TEST_ASSERT_EQUAL_UINT(181u, c.probe_len);       /* 18 s at 10 Hz incl. start */
    TEST_ASSERT_TRUE(c.probe_len <= CC_RING_LEN);
    TEST_ASSERT_TRUE(sizeof(cc_t) < 4096u);
    /* A probe longer than the ring is refused instead of overrunning it. */
    p.probe_on_s = 30.0f;
    TEST_ASSERT_FALSE(cc_init(&c, &p));
}

static void replay_vectors(bool firmware_defaults)
{
    printf("  -- %s --\n", firmware_defaults ? "firmware defaults (D-D1a/b/c on)" : "screen.py D1 rules");
    for (size_t i = 0; i < CCV_N_CASES; i++) {
        const ccv_case_t *v = &ccv_cases[i];
        cc_t c;
        const cc_params_t p = firmware_defaults ? firmware_params_for(v->tau_off) : screen_params_for(v->tau_off);
        TEST_ASSERT_TRUE(cc_init(&c, &p));
        int suspect = -1, lost = -1, probes = 0, lost_events = 0;
        for (uint16_t k = 0; k < v->n; k++) {
            cc_output_t o;
            cc_step(&c, v->th[k], v->y[k], v->p[k], v->a, v->ntc[k], &o);
            if (o.event == CC_EVT_SUSPECT && suspect < 0) {
                suspect = k;
            }
            if (o.event == CC_EVT_LOST) {
                lost_events++;
                if (lost < 0) {
                    lost = k;
                }
            }
        }
        probes = (int)c.probes;
        printf("  D1 vector %-30s suspect %4d (py %4d)  lost %4d (py %4d)  probes %d (py %d)  d=%.3f d_exp=%.3f rms=%.3f\n",
               v->name, suspect, v->suspect_k, lost, v->lost_k, probes, v->probes, (double)c.last_d,
               (double)c.last_d_exp, (double)c.last_decay_rms);
        TEST_ASSERT_EQUAL_INT(v->suspect_k, suspect);
        TEST_ASSERT_EQUAL_INT(v->lost_k, lost);
        TEST_ASSERT_EQUAL_INT(v->probes, probes);
        if (v->kind == CCV_LOSS) {
            TEST_ASSERT_TRUE(lost >= 0);
            TEST_ASSERT_EQUAL_INT(1, lost_events);
            /* Confirmed in the window that starts 250 s = sample 200. */
            TEST_ASSERT_TRUE(lost - 200 <= 210);
        } else {
            TEST_ASSERT_EQUAL_INT(-1, lost);   /* no false latch */
        }
        if (v->kind == CCV_NOMINAL) {
            TEST_ASSERT_EQUAL_INT(-1, suspect);
        }
    }
}

/* Exact parity with the Python reference decisions. */
static void test_golden_vectors_match_python_d1(void)
{
    replay_vectors(false);
}

/* The firmware defaults reach the same suspect / lost samples on every
 * screen vector: the additions change no screen decision. */
static void test_golden_vectors_firmware_defaults(void)
{
    replay_vectors(true);
}

/* Drive a synthetic fall with high power: trigger after 1 s hold, then the
 * exact 5/8/5 s off/on/off pattern at 50 % of P_MAX. */
static void test_probe_power_pattern(void)
{
    cc_t c;
    cc_params_t p;
    cc_default_params(&p);
    TEST_ASSERT_TRUE(cc_init(&c, &p));
    float th = 200.0f;
    int k_start = -1;
    int on = 0, off = 0;
    for (int k = 0; k < 400; k++) {
        cc_output_t o;
        th -= 0.15f;   /* -1.5 K/s */
        cc_step(&c, th, th, 1500.0f, 1e-3f, 60.0f, &o);
        if (o.event == CC_EVT_SUSPECT) {
            k_start = k;
        }
        if (k_start >= 0 && k - k_start < 180) {
            TEST_ASSERT_TRUE(o.override);
            if (o.p_override_w > 0.0f) {
                TEST_ASSERT_FLOAT_WITHIN(1e-3f, 900.0f, o.p_override_w);
                TEST_ASSERT_TRUE(k - k_start >= 50 && k - k_start < 130);
                on++;
            } else {
                off++;
            }
            TEST_ASSERT_TRUE(o.reset_integrator);
        }
        if (k_start >= 0 && k - k_start >= 180) {
            break;
        }
    }
    /* 2 s slope window (20 samples present > 20 needed) + 1 s hold */
    TEST_ASSERT_EQUAL_INT(30, k_start);
    TEST_ASSERT_EQUAL_INT(80, on);
    TEST_ASSERT_EQUAL_INT(100, off);
}

/* No trigger below 40 % mean power, however fast the fall. */
static void test_no_trigger_at_low_power(void)
{
    cc_t c;
    cc_params_t p;
    cc_default_params(&p);
    TEST_ASSERT_TRUE(cc_init(&c, &p));
    float th = 200.0f;
    for (int k = 0; k < 600; k++) {
        cc_output_t o;
        th -= 0.3f;
        cc_step(&c, th, th, 0.39f * 1800.0f, 1e-3f, 60.0f, &o);
        TEST_ASSERT_EQUAL_INT(CC_NORMAL, o.state);
        TEST_ASSERT_FALSE(o.override);
    }
}

/* Lost contact: the reading decays freely toward the rim and ignores the coil.
 * Expect LOST at the end of the probe, zero power, a retry every 20 s and the
 * LOST event raised once. */
static void test_lost_then_retry_cycle(void)
{
    cc_t c;
    cc_params_t p;
    cc_default_params(&p);
    TEST_ASSERT_TRUE(cc_init(&c, &p));
    const float rim = 70.0f;
    float y = 200.0f;
    int lost_k = -1, retry_k = -1, lost_events = 0;
    float p_applied = 1500.0f;
    for (int k = 0; k < 900; k++) {
        cc_output_t o;
        /* free decay toward the rim with tau = C_cap/G_leak */
        y = rim + (y - rim) * expf(-0.1f / p.decay_tau_s);
        const float th = y - 2.0f * (k < 40 ? (float)k * 0.1f : 4.0f);  /* falling estimate */
        cc_step(&c, th, y, p_applied, 1e-3f, rim, &o);
        p_applied = o.override ? o.p_override_w : 1500.0f;
        if (o.event == CC_EVT_LOST) {
            lost_events++;
            lost_k = k;
            TEST_ASSERT_TRUE(o.override);
            TEST_ASSERT_FLOAT_WITHIN(1e-6f, 0.0f, o.p_override_w);
        }
        if (lost_k >= 0 && o.state == CC_RETRY && retry_k < 0) {
            retry_k = k;
        }
        if (o.state == CC_LOST) {
            TEST_ASSERT_FLOAT_WITHIN(1e-6f, 0.0f, o.p_override_w);
        }
    }
    TEST_ASSERT_TRUE(lost_k > 0);
    TEST_ASSERT_EQUAL_INT(1, lost_events);
    TEST_ASSERT_EQUAL_INT(lost_k + 200, retry_k);
}

static void test_free_decay_fit(void)
{
    cc_params_t p;
    cc_default_params(&p);
    float y[181];
    for (int i = 0; i < 181; i++) {
        y[i] = 70.0f + 130.0f * expf(-(float)i * 0.1f / p.decay_tau_s);
    }
    TEST_ASSERT_TRUE(cc_free_decay_rms(&p, y, 181, 70.0f, NULL) < 0.01f);
    /* a decay can only head below the data; a rim reading above the data
     * leaves no admissible asymptote, so the hypothesis is rejected */
    TEST_ASSERT_TRUE(cc_free_decay_rms(&p, y, 181, 250.0f, NULL) > 1e8f);
}

static void test_probe_regression_sees_power(void)
{
    cc_params_t p;
    cc_default_params(&p);
    float y[181], pw[181];
    const float a = 1e-3f;  /* K/J */
    float e = 0.0f, e_lag = 0.0f, e_prev = 0.0f;
    for (int i = 0; i < 181; i++) {
        pw[i] = (i >= 50 && i < 130) ? 900.0f : 0.0f;
        if (i > 0) {
            e_lag += 0.1f / 3.0f * (e_prev - e_lag);
        }
        e += pw[i] * 0.1f / 1000.0f;
        e_prev = e;
        y[i] = 180.0f - 0.2f * (float)i * 0.1f + a * 1000.0f * e_lag;
    }
    float d, d_exp, rms;
    TEST_ASSERT_TRUE(cc_probe_says_contact(&p, y, pw, 181, a, 70.0f, p.probe_lag_s, true, &d, &d_exp, &rms, NULL));
    TEST_ASSERT_FLOAT_WITHIN(0.01f, 1.0f, d);
    TEST_ASSERT_FLOAT_WITHIN(1e-6f, 1.0f, d_exp);
}

/* D-D1a: a flat, unresponsive reading near the rim (a pan quenched by a heavy
 * cold load) is no evidence of a free decay. A probe from NORMAL must not
 * latch LOST on it; a retry from LOST keeps the reference rule and stays lost. */
static void test_flat_reading_is_not_evidence_of_loss(void)
{
    cc_params_t p;
    cc_default_params(&p);
    float y[181], pw[181];
    for (int i = 0; i < 181; i++) {
        pw[i] = (i >= 50 && i < 130) ? 900.0f : 0.0f;
        y[i] = 45.0f + 0.004f * (float)i;   /* +0.7 K over 18 s */
    }
    float d, d_exp, rms, change;
    TEST_ASSERT_TRUE(cc_probe_says_contact(&p, y, pw, 181, 1.6e-3f, 61.0f, p.probe_lag_s, true, &d, &d_exp, &rms, &change));
    TEST_ASSERT_TRUE(rms <= p.decay_rms_k);
    TEST_ASSERT_TRUE(change < p.decay_min_change_k);
    TEST_ASSERT_FALSE(cc_probe_says_contact(&p, y, pw, 181, 1.6e-3f, 61.0f, p.probe_lag_s, false, &d, &d_exp, &rms, &change));
    /* A real detached sensor 16 K below the rim rises toward it: evidence. */
    for (int i = 0; i < 181; i++) {
        y[i] = 58.0f - 13.0f * expf(-(float)i * 0.1f / p.decay_tau_s);
    }
    TEST_ASSERT_FALSE(cc_probe_says_contact(&p, y, pw, 181, 1.6e-3f, 61.0f, p.probe_lag_s, true, &d, &d_exp, &rms, &change));
    TEST_ASSERT_TRUE(change >= p.decay_min_change_k);
}

static void test_external_request_starts_probe(void)
{
    cc_t c;
    cc_params_t p;
    cc_default_params(&p);
    TEST_ASSERT_TRUE(cc_init(&c, &p));
    cc_output_t o;
    cc_step(&c, 150.0f, 150.0f, 0.0f, 1e-3f, 60.0f, &o);
    TEST_ASSERT_EQUAL_INT(CC_NORMAL, o.state);
    cc_request_probe(&c);
    cc_step(&c, 150.0f, 150.0f, 0.0f, 1e-3f, 60.0f, &o);
    TEST_ASSERT_EQUAL_INT(CC_PROBE, o.state);
    TEST_ASSERT_EQUAL_INT(CC_EVT_SUSPECT, o.event);
}

void run_contact_check_tests(void)
{
    RUN_TEST(test_defaults_match_screen);
    RUN_TEST(test_bounded_memory);
    RUN_TEST(test_golden_vectors_match_python_d1);
    RUN_TEST(test_golden_vectors_firmware_defaults);
    RUN_TEST(test_probe_power_pattern);
    RUN_TEST(test_no_trigger_at_low_power);
    RUN_TEST(test_lost_then_retry_cycle);
    RUN_TEST(test_free_decay_fit);
    RUN_TEST(test_probe_regression_sees_power);
    RUN_TEST(test_flat_reading_is_not_evidence_of_loss);
    RUN_TEST(test_external_request_starts_probe);
}
