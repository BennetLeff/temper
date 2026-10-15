/**
 * @file pan_rate_pid.c
 * @brief Rate-domain gain-scheduled PID (see header).
 */

#include "pan_rate_pid.h"

#include <math.h>
#include <stddef.h>

void prp_default_params(prp_params_t *p)
{
    if (p == NULL) {
        return;
    }
    p->kp_per_s = 0.1f;
    p->ki_per_s2 = 0.002f;
    p->kd = 1.0f;
    p->i_band_k = 10.0f;
    p->sp_rate_k_per_s = 1.0f;
    p->p_max_w = 1800.0f;
    p->dt_s = 0.1f;
    p->d_filter_s = 2.0f;
}

bool prp_init(prp_t *c, const prp_params_t *p)
{
    if (c == NULL || p == NULL || !(p->dt_s > 0.0f) || !(p->p_max_w > 0.0f) || !(p->d_filter_s > 0.0f)) {
        return false;
    }
    c->p = *p;
    c->integ = 0.0f;
    c->sp_eff = 0.0f;
    c->t_prev = 0.0f;
    c->dtf = 0.0f;
    c->started = false;
    c->ramping = false;
    return true;
}

void prp_start(prp_t *c, float t_hat_c)
{
    c->integ = 0.0f;
    c->sp_eff = t_hat_c;
    c->t_prev = t_hat_c;
    c->dtf = 0.0f;
    c->started = true;
    c->ramping = false;
}

static float clampf(float v, float lo, float hi)
{
    return v < lo ? lo : (v > hi ? hi : v);
}

float prp_step(prp_t *c, float sp_c, float t_hat_c, float a_k_per_j)
{
    const prp_params_t *p = &c->p;
    if (!c->started) {
        prp_start(c, t_hat_c);
    }
    if (!(a_k_per_j > 0.0f) || !isfinite(t_hat_c) || !isfinite(sp_c)) {
        return 0.0f;
    }
    c->ramping = sp_c > c->sp_eff;
    if (c->ramping) {
        const float next = c->sp_eff + p->sp_rate_k_per_s * p->dt_s;
        c->sp_eff = next < sp_c ? next : sp_c;
    } else {
        c->sp_eff = sp_c;
    }
    c->dtf += (p->dt_s / p->d_filter_s) * ((t_hat_c - c->t_prev) / p->dt_s - c->dtf);
    c->t_prev = t_hat_c;
    const float e = c->sp_eff - t_hat_c;
    if (fabsf(e) < p->i_band_k) {
        c->integ = clampf(c->integ + p->ki_per_s2 * e * p->dt_s, 0.0f, p->p_max_w * a_k_per_j);
    }
    return clampf((p->kp_per_s * e + c->integ - p->kd * c->dtf) / a_k_per_j, 0.0f, p->p_max_w);
}
