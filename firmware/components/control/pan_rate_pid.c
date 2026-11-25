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
    p->lpg_enable = true;
    p->lpg_n = 100u;
    p->lpg_slope_k_per_s = 0.15f;
    p->lpg_band_lo_c = 95.0f;
    p->lpg_band_hi_c = 118.0f;
    p->lpg_margin_k = 5.0f;
    p->lpg_rate_k_per_s = 0.2f;
    p->lpg_budget = true;
}

bool prp_init(prp_t *c, const prp_params_t *p)
{
    if (c == NULL || p == NULL || !(p->dt_s > 0.0f) || !(p->p_max_w > 0.0f) || !(p->d_filter_s > 0.0f) ||
        p->lpg_n < 2u || p->lpg_n > PRP_LPG_MAX) {
        return false;
    }
    c->p = *p;
    c->integ = 0.0f;
    c->sp_eff = 0.0f;
    c->t_prev = 0.0f;
    c->dtf = 0.0f;
    c->started = false;
    c->ramping = false;
    c->hist_n = 0u;
    c->lpg_active = false;
    c->lpg_steps = 0u;
    c->lpg_e_j = 0.0;
    c->lpg_no_budget = false;
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

/* Least-squares slope (K/s) of the stored estimates. */
static double hist_slope(const prp_t *c, uint16_t n)
{
    const uint16_t i0 = (uint16_t)(c->hist_n - n);
    double tm = 0.0, ym = 0.0;
    for (uint16_t i = 0; i < n; i++) {
        tm += (double)i;
        ym += (double)c->hist[i0 + i];
    }
    tm /= (double)n;
    ym /= (double)n;
    double sxy = 0.0, sxx = 0.0;
    for (uint16_t i = 0; i < n; i++) {
        sxy += ((double)i - tm) * ((double)c->hist[i0 + i] - ym);
        sxx += ((double)i - tm) * ((double)i - tm);
    }
    return sxy / sxx / (double)c->p.dt_s;
}

static void hist_push(prp_t *c, float v)
{
    if (c->hist_n < c->p.lpg_n) {
        c->hist[c->hist_n++] = v;
    } else {
        for (uint16_t i = 1; i < c->hist_n; i++) {
            c->hist[i - 1u] = c->hist[i];
        }
        c->hist[c->hist_n - 1u] = v;
    }
}

static float pid_core(prp_t *c, float sp_c, float t_hat_c, float a_k_per_j);

float prp_step(prp_t *c, float sp_c, float t_hat_c, float a_k_per_j)
{
    const prp_params_t *p = &c->p;
    float out = pid_core(c, sp_c, t_hat_c, a_k_per_j);
    c->lpg_active = false;
    if (p->lpg_enable && a_k_per_j > 0.0f && isfinite(t_hat_c) && c->hist_n >= p->lpg_n) {
        const bool in_band = t_hat_c >= p->lpg_band_lo_c && t_hat_c <= p->lpg_band_hi_c;
        if (in_band && c->hist[c->hist_n - 1u] > p->lpg_band_hi_c) {
            c->lpg_no_budget = true;   /* fell into the band: the pan was hotter */
        }
        if (in_band && sp_c - t_hat_c > p->lpg_margin_k &&
            fabs(hist_slope(c, p->lpg_n)) < (double)p->lpg_slope_k_per_s &&
            (!p->lpg_budget || c->lpg_no_budget ||
             (double)a_k_per_j * c->lpg_e_j >= (double)sp_c - (double)t_hat_c)) {
            const float cap = p->lpg_rate_k_per_s / a_k_per_j;
            if (out > cap) {
                out = cap;
            }
            c->lpg_active = true;
            c->lpg_steps++;
        }
        if (in_band) {
            c->lpg_e_j += (double)out * (double)p->dt_s;
        } else {
            c->lpg_e_j = 0.0;
            c->lpg_no_budget = false;
        }
    }
    if (isfinite(t_hat_c)) {
        hist_push(c, t_hat_c);
    }
    return out;
}

static float pid_core(prp_t *c, float sp_c, float t_hat_c, float a_k_per_j)
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
