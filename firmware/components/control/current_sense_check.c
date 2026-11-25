/**
 * @file current_sense_check.c
 * @brief Bus-current sense plausibility (see header).
 */

#include "current_sense_check.h"

#include <math.h>
#include <stddef.h>
#include <string.h>

void csc_default_params(csc_params_t *p)
{
    if (p == NULL) {
        return;
    }
    p->dt_s = 0.1f;
    p->near_zero_a = 0.5f;
    p->settle_s = 0.3f;
    p->run_p_min_w = 300.0f;
    p->run_hold_s = 0.5f;
    p->pulse_w = 360.0f;
    p->pulse_s = 1.0f;
    p->xc_floor_a = 1.0f;
    p->xc_abs_tol_a = 1.0f;
    p->xc_rel_tol = 0.25f;
    p->xc_hold_s = 0.5f;
}

bool csc_init(csc_t *c, const csc_params_t *p)
{
    if (c == NULL || p == NULL || !(p->dt_s > 0.0f) || !(p->near_zero_a >= 0.0f) ||
        !(p->run_p_min_w > 0.0f) || !(p->pulse_w > 0.0f) || !(p->pulse_s > p->settle_s)) {
        return false;
    }
    memset(c, 0, sizeof(*c));
    c->p = *p;
    return true;
}

static void latch(csc_t *c, csc_latch_t l)
{
    if (c->latched == CSC_OK) {
        c->latched = l;
    }
}

/* A reading that cannot be a current is as implausible as no current. */
static bool no_current(const csc_t *c, float i_a)
{
    return !isfinite(i_a) || i_a <= c->p.near_zero_a;
}

bool csc_run_step(csc_t *c, float p_applied_w, float i_bus_a)
{
    const csc_params_t *p = &c->p;
    const float eps = 1e-3f;
    if (csc_pulse_active(c)) {
        /* The start-up pulse is (b)'s own test; (a) starts after it. */
        c->run_cmd_s = 0.0f;
        c->run_bad_s = 0.0f;
        return c->latched != CSC_OK;
    }
    if (p_applied_w >= p->run_p_min_w) {
        c->run_cmd_s += p->dt_s;
    } else {
        c->run_cmd_s = 0.0f;
    }
    if (c->run_cmd_s > p->settle_s + eps && no_current(c, i_bus_a)) {
        c->run_bad_s += p->dt_s;
    } else {
        c->run_bad_s = 0.0f;
    }
    if (c->run_bad_s >= p->run_hold_s - eps) {
        latch(c, CSC_LATCH_RUN);
    }
    return c->latched != CSC_OK;
}

void csc_pulse_begin(csc_t *c)
{
    c->pulse = CSC_PULSE_PENDING;
    c->pulse_cmd_w = 0.0f;
    c->pulse_on_s = 0.0f;
    c->pulse_i_sum = 0.0f;
    c->pulse_i_n = 0u;
    c->pulse_i_bad = false;
}

bool csc_pulse_active(const csc_t *c)
{
    return c->pulse == CSC_PULSE_PENDING || c->pulse == CSC_PULSE_RUNNING;
}

csc_pulse_state_t csc_pulse_step(csc_t *c, float p_applied_w, float i_bus_a, float p_limit_w,
                                 float *p_cmd_w)
{
    const csc_params_t *p = &c->p;
    const float eps = 1e-3f;
    if (!csc_pulse_active(c)) {
        return c->pulse;
    }
    /* Was the pulse actually applied over the period that just ended? The
     * runtime quantises the command to 1 % of 1.8 kW (18 W). */
    const bool applied = c->pulse_cmd_w > 0.0f && p_applied_w >= c->pulse_cmd_w - 9.0f;
    if (applied) {
        c->pulse = CSC_PULSE_RUNNING;
        c->pulse_on_s += p->dt_s;
        if (c->pulse_on_s > p->settle_s + eps) {
            if (isfinite(i_bus_a)) {
                c->pulse_i_sum += i_bus_a;
                c->pulse_i_n++;
            } else {
                c->pulse_i_bad = true;
            }
        }
        if (c->pulse_on_s >= p->pulse_s - eps) {
            c->pulse_mean_a = c->pulse_i_n > 0u ? c->pulse_i_sum / (float)c->pulse_i_n : 0.0f;
            if (c->pulse_i_bad || c->pulse_i_n == 0u || c->pulse_mean_a <= p->near_zero_a) {
                c->pulse = CSC_PULSE_FAILED;
                latch(c, CSC_LATCH_PULSE);
            } else {
                c->pulse = CSC_PULSE_PASSED;
            }
            c->pulse_cmd_w = 0.0f;
            if (p_cmd_w != NULL) {
                *p_cmd_w = 0.0f;
            }
            return c->pulse;
        }
    } else if (c->pulse == CSC_PULSE_RUNNING) {
        /* Something zeroed the pulse mid-way: start it again. */
        c->pulse = CSC_PULSE_PENDING;
        c->pulse_on_s = 0.0f;
        c->pulse_i_sum = 0.0f;
        c->pulse_i_n = 0u;
        c->pulse_i_bad = false;
    }
    float w = p->pulse_w;
    if (isfinite(p_limit_w) && p_limit_w > 0.0f && p_limit_w < w) {
        w = p_limit_w;
    }
    c->pulse_cmd_w = w;
    if (p_cmd_w != NULL) {
        *p_cmd_w = w;
    }
    return c->pulse;
}

bool csc_xcheck_step(csc_t *c, float i_in_a, float i_bus_a)
{
    const csc_params_t *p = &c->p;
    const float eps = 1e-3f;
    bool bad;
    if (!isfinite(i_in_a) || !isfinite(i_bus_a)) {
        bad = true;
    } else {
        const float big = fmaxf(fabsf(i_in_a), fabsf(i_bus_a));
        const float tol = fmaxf(p->xc_abs_tol_a, p->xc_rel_tol * big);
        bad = big >= p->xc_floor_a && fabsf(i_in_a - i_bus_a) > tol;
    }
    c->xc_bad_s = bad ? c->xc_bad_s + p->dt_s : 0.0f;
    if (c->xc_bad_s >= p->xc_hold_s - eps) {
        latch(c, CSC_LATCH_XCHECK);
    }
    return c->latched != CSC_OK;
}
