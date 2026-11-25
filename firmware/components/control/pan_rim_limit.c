/**
 * @file pan_rim_limit.c
 * @brief Setpoint-relative rim limit (see header; DECISIONS.md D-RIMLIM).
 */

#include "pan_rim_limit.h"

#include <math.h>
#include <stddef.h>
#include <string.h>

void prl_default_params(prl_params_t *p)
{
    if (p == NULL) {
        return;
    }
    p->dt_s = 0.1f;
    p->w_hi = 0.9554f;
    p->w_lo = 0.6457f;
    p->t_eye_hi_c = 139.7f;
    p->tol_table = true;
    p->tol_k = 10.2f + 4.37f + 4.53f;
    p->margin_k = 0.0f;
    p->tau_dec_s = 300.0f;
    p->fall_window_s = 30.0f;
    p->fall_k = 1.0f;
    p->sustain_s = 5.0f;
}

bool prl_init(prl_t *c, const prl_params_t *p)
{
    if (c == NULL || p == NULL || !(p->dt_s > 0.0f) || !(p->w_hi > 0.0f) || !(p->w_hi <= 1.0f) ||
        !(p->w_lo > 0.0f) || !(p->w_lo <= p->w_hi) || !isfinite(p->t_eye_hi_c) || !(p->tol_k >= 0.0f) ||
        !isfinite(p->margin_k) || !(p->tau_dec_s > 0.0f) || !(p->fall_window_s >= 1.0f) ||
        !(p->fall_window_s <= (float)(PRL_HIST_MAX - 1u)) || !(p->fall_k >= 0.0f) || !(p->sustain_s > 0.0f)) {
        return false;
    }
    memset(c, 0, sizeof(*c));
    c->p = *p;
    c->t_ref_c = NAN;
    c->lim_c = NAN;
    return true;
}

static float tol_at(float t_c)
{
    static const float kt[PRL_TOL_N] = PRL_TOL_T_C;
    static const float kk[PRL_TOL_N] = PRL_TOL_K;
    if (!(t_c > kt[0])) {
        return kk[0];
    }
    for (uint32_t i = 1u; i < PRL_TOL_N; i++) {
        if (t_c <= kt[i]) {
            return kk[i - 1u] + (kk[i] - kk[i - 1u]) * (t_c - kt[i - 1u]) / (kt[i] - kt[i - 1u]);
        }
    }
    return kk[PRL_TOL_N - 1u];
}

float prl_limit_c(const prl_params_t *p, float t_ref_c)
{
    const float a = p->w_hi * t_ref_c + (1.0f - p->w_hi) * p->t_eye_hi_c;
    const float b = p->w_lo * t_ref_c + (1.0f - p->w_lo) * p->t_eye_hi_c;
    const float g = a > b ? a : b;
    return g + (p->tol_table ? tol_at(g) : p->tol_k) + p->margin_k;
}

static void restart_rim(prl_t *c)
{
    c->n_valid = 0u;
    c->n_over = 0u;
    c->sub_s = 0.0f;
    c->head = 0u;
    c->filled = 0u;
}

bool prl_step(prl_t *c, float setpoint_c, float t_hat_c, bool rim_valid, float t_rim_c)
{
    if (c == NULL) {
        return false;
    }
    if (c->latched) {
        return true;
    }
    /* Reference: rises at once, decays toward the present value. */
    float u = setpoint_c;
    if (isfinite(t_hat_c) && (!isfinite(u) || t_hat_c > u)) {
        u = t_hat_c;
    }
    if (isfinite(u)) {
        if (!isfinite(c->t_ref_c) || c->t_ref_c <= u) {
            c->t_ref_c = u;
        } else {
            c->t_ref_c = u + (c->t_ref_c - u) * expf(-c->p.dt_s / c->p.tau_dec_s);
        }
    }
    if (!rim_valid || !isfinite(t_rim_c) || !isfinite(c->t_ref_c)) {
        restart_rim(c);
        return false;
    }
    c->lim_c = prl_limit_c(&c->p, c->t_ref_c);

    /* Fall window: one history slot per second of VALID rim. */
    const uint32_t slots = (uint32_t)lroundf(c->p.fall_window_s);
    bool not_falling = false;
    if (c->filled > slots) {
        const uint8_t old = (uint8_t)((c->head + PRL_HIST_MAX - 1u - slots) % PRL_HIST_MAX);
        not_falling = t_rim_c >= c->hist[old] - c->p.fall_k;
    }
    c->n_valid++;
    c->sub_s += c->p.dt_s;
    if (c->n_valid == 1u || c->sub_s >= 1.0f - 1e-4f) {
        c->sub_s = (c->n_valid == 1u) ? 0.0f : c->sub_s - 1.0f;
        c->hist[c->head] = t_rim_c;
        c->head = (uint8_t)((c->head + 1u) % PRL_HIST_MAX);
        if (c->filled < PRL_HIST_MAX) {
            c->filled++;
        }
    }

    if (t_rim_c > c->lim_c && not_falling) {
        c->n_over++;
    } else {
        c->n_over = 0u;
    }
    if ((float)c->n_over * c->p.dt_s >= c->p.sustain_s - 1e-4f) {
        c->latched = true;
    }
    return c->latched;
}
