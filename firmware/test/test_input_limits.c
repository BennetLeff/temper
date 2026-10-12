#include "input_limits.h"
#include <assert.h>
#include <math.h>
#include <stdio.h>
static unsigned tests;
#define N 64
/* One half line cycle of an unsmoothed bus: V_bus = Vpk |sin|, tank current proportional to it. */
static void half_cycle(input_sample_t *s, float vpk, float ipk_rms, float cos_phi)
{
    for (int j = 0; j < N; j++) {
        float x = fabsf(sinf(3.14159265f * (j + 0.5f) / N));
        s[j] = (input_sample_t){ vpk * x, ipk_rms * x, cos_phi, 0.0f };
    }
}
static void test_config(void)
{
    input_limits_cfg_t c = input_limits_native21();
    assert(input_limits_config_ok(&c));
    input_limits_cfg_t bad = c; bad.eta_min = 1.2f; assert(!input_limits_config_ok(&bad));
    bad = c; bad.est_error = NAN; assert(!input_limits_config_ok(&bad));
    bad = c; bad.tank_limit_a = 0; assert(!input_limits_config_ok(&bad));
    /* Stage 15: the ceiling ships at 22 A and may be commissioned up to the 28 A hardware basis. */
    assert(c.tank_limit_a == 22.0f);
    input_limits_cfg_t ok = c; ok.tank_limit_a = 28.0f; assert(input_limits_config_ok(&ok));
    bad = c; bad.tank_limit_a = 28.01f; assert(!input_limits_config_ok(&bad));
    bad = c; bad.tank_limit_a = 44.0f; assert(!input_limits_config_ok(&bad));   /* was accepted */
    bad = c; bad.tank_limit_a = NAN; assert(!input_limits_config_ok(&bad));
    assert(!input_limits_config_ok(NULL));
    tests++;
}
static void test_power_and_bound(void)
{
    input_limits_cfg_t c = input_limits_native21();
    input_sample_t s[N]; input_estimate_t e;
    half_cycle(s, 170.0f, 30.0f, 0.95f);
    assert(input_limits_half_cycle(&c, s, N, 120.0f, &e));
    /* mean of |sin|^2 over a half cycle is 1/2 */
    double p = 0.900316316 * 170.0 * 30.0 * 0.95 * 0.5;
    assert(fabs(e.p_inv_w - p) < 0.01 * p);
    assert(fabs(e.p_in_w - e.p_inv_w / c.eta_min) < 1e-3f * e.p_in_w);
    assert(fabs(e.i_ps_a - e.p_in_w / 120.0f) < 1e-4f);
    assert(fabs(e.inlet_bound_a - (e.i_ps_a * 1.10f + c.aux_max_a)) < 1e-4f);
    /* A scheduled allowance (stage 16) replaces the worst case inside [aux_min_a, aux_max_a]. */
    input_estimate_t e2;
    assert(input_limits_half_cycle_aux(&c, s, N, 120.0f, 2.0f, &e2));
    assert(fabsf(e2.inlet_bound_a - (e.i_ps_a * 1.10f + 2.0f)) < 1e-4f && e2.i_ps_a == e.i_ps_a);
    assert(input_limits_half_cycle_aux(&c, s, N, 120.0f, NAN, &e2) && e2.inlet_bound_a == e.inlet_bound_a);
    assert(fabs(e.tank_rms_a - 30.0f / sqrtf(2.0f)) < 0.05f);
    tests++;
}
static void test_tank_ceiling(void)
{
    input_limits_cfg_t c = input_limits_native21();
    input_sample_t s[N]; input_estimate_t e;
    for (int j = 0; j < N; j++) s[j] = (input_sample_t){ 160.0f, 25.0f, 0.9f, 0.0f };
    assert(input_limits_half_cycle(&c, s, N, 120.0f, &e));
    assert(e.tank_ceiling_w < e.p_inv_w);                                   /* above 22 A: cut */
    assert(fabsf(e.tank_ceiling_w - e.p_inv_w * (22.0f / 25.0f) * (22.0f / 25.0f)) < 0.01f * e.p_inv_w);
    for (int j = 0; j < N; j++) s[j].tank_rms_a = 10.0f;
    assert(input_limits_half_cycle(&c, s, N, 120.0f, &e) && e.tank_ceiling_w > e.p_inv_w); /* below: room */
    for (int j = 0; j < N; j++) s[j].tank_rms_a = 0;
    assert(input_limits_half_cycle(&c, s, N, 120.0f, &e) && isinf(e.tank_ceiling_w) && e.p_inv_w == 0);
    /* At a 28 A ceiling the same 25 A half has room: the ceiling power scales with (28/25)^2. */
    input_limits_cfg_t c28 = c; c28.tank_limit_a = 28.0f;
    for (int j = 0; j < N; j++) s[j].tank_rms_a = 25.0f;
    assert(input_limits_half_cycle(&c28, s, N, 120.0f, &e) && e.tank_ceiling_w > e.p_inv_w);
    assert(fabsf(e.tank_ceiling_w - e.p_inv_w * (28.0f / 25.0f) * (28.0f / 25.0f)) < 0.01f * e.p_inv_w);
    /* The half-cycle RMS is the quantity the binding trips on (1.05 x ceiling, not per sample):
     * an envelope with a 32 A crest is a 22.6 A half. */
    half_cycle(s, 170.0f, 32.0f, 0.5f);
    assert(input_limits_half_cycle(&c, s, N, 120.0f, &e) && fabsf(e.tank_rms_a - 32.0f / sqrtf(2.0f)) < 0.05f);
    assert(e.tank_rms_a < 1.05f * c.tank_limit_a);
    tests++;
}
static void test_rejects(void)
{
    input_limits_cfg_t c = input_limits_native21();
    input_sample_t s[N]; input_estimate_t e;
    half_cycle(s, 170.0f, 20.0f, 0.9f);
    assert(!input_limits_half_cycle(&c, s, 7, 120.0f, &e));        /* too few samples */
    assert(!input_limits_half_cycle(&c, s, N, 99.0f, &e));         /* line out of range */
    assert(!input_limits_half_cycle(&c, s, N, NAN, &e));
    s[5].cos_phi = 1.5f; assert(!input_limits_half_cycle(&c, s, N, 120.0f, &e)); s[5].cos_phi = 0.9f;
    s[9].tank_rms_a = -1; assert(!input_limits_half_cycle(&c, s, N, 120.0f, &e)); s[9].tank_rms_a = 1;
    s[3].bus_v = NAN; assert(!input_limits_half_cycle(&c, s, N, 120.0f, &e)); s[3].bus_v = 100;
    assert(input_limits_half_cycle(&c, s, N, 120.0f, &e));
    tests++;
}
static void test_regeneration_floor(void)
{
    input_limits_cfg_t c = input_limits_native21();
    input_sample_t s[N]; input_estimate_t e;
    half_cycle(s, 170.0f, 20.0f, -0.3f);
    assert(input_limits_half_cycle(&c, s, N, 120.0f, &e));
    assert(e.p_inv_w == 0 && e.i_ps_a == 0 && fabsf(e.inlet_bound_a - c.aux_max_a) < 1e-6f);
    tests++;
}
static void test_aux_allowance(void)
{
    /* Stage 16: PS1 + PS2 static 1.3 A (the pre-stage-16 basis), worst case + PS3 at full blower. */
    input_limits_cfg_t c = input_limits_native21();
    assert(c.aux_min_a == 1.3f && fabsf(c.aux_max_a - 2.569f) < 0.002f);
    assert(input_limits_aux(&c, 2.0f) == 2.0f && input_limits_aux(&c, c.aux_min_a) == c.aux_min_a);
    assert(input_limits_aux(&c, c.aux_max_a) == c.aux_max_a);
    /* Below the static part, above the worst case, or not a number: the worst case. */
    assert(input_limits_aux(&c, 1.0f) == c.aux_max_a && input_limits_aux(&c, 3.0f) == c.aux_max_a);
    assert(input_limits_aux(&c, NAN) == c.aux_max_a && input_limits_aux(&c, -INFINITY) == c.aux_max_a);
    /* Ramp: up by at most the step per half, down at once; an invalid target ramps to the worst. */
    assert(fabsf(input_limits_aux_ramp(&c, 1.35f, 2.4f, 0.05f) - 1.40f) < 1e-6f);
    assert(input_limits_aux_ramp(&c, 2.4f, 1.35f, 0.05f) == 1.35f);
    assert(fabsf(input_limits_aux_ramp(&c, 1.35f, NAN, 0.05f) - 1.40f) < 1e-6f);
    assert(input_limits_aux_ramp(&c, NAN, 1.35f, 0.05f) == 1.35f);
    assert(input_limits_aux_ramp(&c, 1.35f, 2.4f, NAN) == 2.4f);
    input_limits_cfg_t bad = c; bad.aux_max_a = 5.0f; assert(!input_limits_config_ok(&bad));
    bad = c; bad.aux_min_a = -0.1f; assert(!input_limits_config_ok(&bad));
    tests++;
}
static void test_time_weights(void)
{
    /* Weights are the time each reading stands for: two readings, 3 A for 1 unit and 9 A for 3 units
     * (a long gap after the second), eight of them to satisfy n >= 8. */
    input_limits_cfg_t c = input_limits_native21();
    input_sample_t s[8]; input_estimate_t e, u;
    for (int j = 0; j < 8; j++) s[j] = (input_sample_t){ 100.0f, j < 4 ? 3.0f : 9.0f, 1.0f, 0.0f };
    assert(input_limits_half_cycle(&c, s, 8, 120.0f, &u));                       /* all w = 0: equal */
    assert(fabsf(u.tank_rms_a - sqrtf((4 * 9.0f + 4 * 81.0f) / 8)) < 1e-4f);
    for (int j = 0; j < 8; j++) s[j].w = j < 4 ? 1.0f : 3.0f;
    assert(input_limits_half_cycle(&c, s, 8, 120.0f, &e));
    assert(fabsf(e.tank_rms_a - sqrtf((4 * 1.0f * 9.0f + 4 * 3.0f * 81.0f) / 16)) < 1e-4f);
    /* power is weighted the same way */
    assert(fabsf(e.p_inv_w - 0.900316316f * 100.0f * (4 * 1.0f * 3.0f + 4 * 3.0f * 9.0f) / 16) < 0.01f);
    /* scale of the weights does not matter */
    for (int j = 0; j < 8; j++) s[j].w *= 625.0f;
    assert(input_limits_half_cycle(&c, s, 8, 120.0f, &u) && fabsf(u.tank_rms_a - e.tank_rms_a) < 1e-4f);
    /* equal non-zero weights == no weights */
    for (int j = 0; j < 8; j++) s[j].w = 5.0f;
    assert(input_limits_half_cycle(&c, s, 8, 120.0f, &u));
    for (int j = 0; j < 8; j++) s[j].w = 0.0f;
    assert(input_limits_half_cycle(&c, s, 8, 120.0f, &e) && fabsf(u.tank_rms_a - e.tank_rms_a) < 1e-4f);
    /* zero-weight readings drop out; negative, NaN or infinite weights are refused */
    for (int j = 0; j < 8; j++) s[j].w = j < 4 ? 0.0f : 2.0f;
    assert(input_limits_half_cycle(&c, s, 8, 120.0f, &e) && fabsf(e.tank_rms_a - 9.0f) < 1e-4f);
    s[2].w = -1.0f; assert(!input_limits_half_cycle(&c, s, 8, 120.0f, &e));
    s[2].w = NAN; assert(!input_limits_half_cycle(&c, s, 8, 120.0f, &e));
    s[2].w = INFINITY; assert(!input_limits_half_cycle(&c, s, 8, 120.0f, &e));
    tests++;
}
static void test_operating_limit(void)
{
    /* The adapter regulates the reported inlet current at inlet_target_a <= 13.5 A (trip 15 A).
     * The power stage is held to (13.5 - I_aux) / (1 + e_est) and the 15 A trip sits at
     * (15 - I_aux) / (1 + e_est). PS1 + PS2 only (blower allowance released): 11.09 / 12.45 A, the
     * DECISIONS.md boundary; full blower or unknown (static worst case): 9.94 / 11.30 A. */
    input_limits_cfg_t c = input_limits_native21();
    float hold = (13.5f - c.aux_min_a) / (1 + c.est_error), trip = (15.0f - c.aux_min_a) / (1 + c.est_error);
    assert(fabsf(hold - 11.09f) < 0.01f && fabsf(trip - 12.45f) < 0.01f);
    hold = (13.5f - c.aux_max_a) / (1 + c.est_error);
    trip = (15.0f - c.aux_max_a) / (1 + c.est_error);
    assert(fabsf(hold - 9.94f) < 0.01f && fabsf(trip - 11.30f) < 0.01f);
    tests++;
}
int main(void)
{
    test_config();
    test_power_and_bound();
    test_tank_ceiling();
    test_rejects();
    test_regeneration_floor();
    test_aux_allowance();
    test_operating_limit();
    test_time_weights();
    printf("input_limits: %u tests passed\n", tests);
    return 0;
}
