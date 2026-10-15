/**
 * @file contact_check.c
 * @brief sensor-r3 contact-loss detector D1 (see header).
 */

#include "contact_check.h"

#include <math.h>
#include <stddef.h>
#include <string.h>

void cc_default_params(cc_params_t *p)
{
    if (p == NULL) {
        return;
    }
    p->dt_s = 0.1f;
    p->p_max_w = 1800.0f;
    p->trig_window = 20u;
    p->trig_rate_k_per_s = -0.8f;
    p->trig_hold_s = 1.0f;
    p->trig_pmin_frac = 0.4f;
    p->probe_off_s = 5.0f;
    p->probe_on_s = 8.0f;
    p->probe_p_frac = 0.5f;
    p->probe_lag_s = 3.0f;
    p->retry_off_s = 5.0f;
    p->retry_on_s = 8.0f;
    p->retry_p_frac = 0.5f;
    p->retry_lag_s = 3.0f;
    p->probe_frac = 0.25f;
    p->retry_s = 20.0f;
    p->holdoff_s = 30.0f;
    p->decay_tau_s = 0.0404f / 0.0008f;   /* C_cap / G_leak = 50.5 s */
    p->decay_tau_tol = 0.4f;
    p->decay_steps = 17u;
    p->decay_asym_k = 25.0f;
    p->decay_rms_k = 0.5f;
    p->decay_min_change_k = 1.0f;
    p->retry_decay_only = true;
    p->probe_min_sigma = 3.0f;
}

static uint32_t ticks(float s, float dt)
{
    return (uint32_t)lroundf(s / dt);
}

bool cc_init(cc_t *c, const cc_params_t *p)
{
    if (c == NULL || p == NULL || !(p->dt_s > 0.0f) || p->trig_window < 2u ||
        p->trig_window > CC_RING_LEN || p->decay_steps < 1u || p->decay_steps > CC_DECAY_STEPS_MAX ||
        !(p->decay_tau_s > 0.0f) || !(p->probe_lag_s > 0.0f) || !(p->retry_lag_s > 0.0f)) {
        return false;
    }
    memset(c, 0, sizeof(*c));
    c->p = *p;
    {
        const float off[2] = {p->probe_off_s, p->retry_off_s};
        const float on[2] = {p->probe_on_s, p->retry_on_s};
        for (int i = 0; i < 2; i++) {
            c->off_shape[i] = ticks(off[i], p->dt_s);
            c->on_shape[i] = ticks(on[i], p->dt_s);
            const uint32_t len = 2u * c->off_shape[i] + c->on_shape[i] + 1u;
            if (len > CC_RING_LEN || len < 8u) {
                return false;
            }
            c->len_shape[i] = (uint16_t)len;
        }
        c->probe_len = c->len_shape[0];
    }
    c->hold_ticks = ticks(p->trig_hold_s, p->dt_s);
    c->retry_ticks = ticks(p->retry_s, p->dt_s);
    c->holdoff_ticks = ticks(p->holdoff_s, p->dt_s);
    c->state = CC_NORMAL;
    return true;
}

void cc_request_probe(cc_t *c)
{
    c->probe_requested = true;
}

/* i = 0 is the newest sample, i = count-1 the oldest kept. */
static const cc_sample_t *back(const cc_t *c, uint16_t i)
{
    return &c->ring[(c->head + CC_RING_LEN - 1u - i) % CC_RING_LEN];
}

/* Solve the n x n system A x = b (n <= 4) by Gaussian elimination with
 * partial pivoting. Returns false when singular. */
static bool solve(double A[4][4], double b[4], int n, double x[4])
{
    for (int col = 0; col < n; col++) {
        int piv = col;
        double best = fabs(A[col][col]);
        for (int r = col + 1; r < n; r++) {
            if (fabs(A[r][col]) > best) {
                best = fabs(A[r][col]);
                piv = r;
            }
        }
        if (!(best > 1e-12)) {
            return false;
        }
        if (piv != col) {
            for (int k = 0; k < n; k++) {
                const double t = A[col][k];
                A[col][k] = A[piv][k];
                A[piv][k] = t;
            }
            const double t = b[col];
            b[col] = b[piv];
            b[piv] = t;
        }
        for (int r = col + 1; r < n; r++) {
            const double f = A[r][col] / A[col][col];
            for (int k = col; k < n; k++) {
                A[r][k] -= f * A[col][k];
            }
            b[r] -= f * b[col];
        }
    }
    for (int r = n - 1; r >= 0; r--) {
        double acc = b[r];
        for (int k = r + 1; k < n; k++) {
            acc -= A[r][k] * x[k];
        }
        x[r] = acc / A[r][r];
    }
    return true;
}

float cc_free_decay_rms(const cc_params_t *p, const float *y, uint16_t n, float t_rim_c, float *change_out)
{
    double best = 1e9;
    double best_change = 0.0;
    const double span = (n > 1u) ? (double)(n - 1u) * (double)p->dt_s : 0.0;
    const uint16_t steps = p->decay_steps;
    for (uint16_t k = 0u; k < steps; k++) {
        const double f = (steps == 1u) ? 1.0
                         : (1.0 - p->decay_tau_tol) + 2.0 * p->decay_tau_tol * (double)k / (double)(steps - 1u);
        const double tau = f * (double)p->decay_tau_s;
        double s1 = 0.0, sz = 0.0, szz = 0.0, sy = 0.0, szy = 0.0;
        for (uint16_t i = 0u; i < n; i++) {
            const double z = exp(-(double)i * (double)p->dt_s / tau);
            s1 += 1.0;
            sz += z;
            szz += z * z;
            sy += y[i];
            szy += z * y[i];
        }
        const double det = s1 * szz - sz * sz;
        if (!(fabs(det) > 1e-12)) {
            continue;
        }
        const double c0 = (szz * sy - sz * szy) / det;
        const double c1 = (s1 * szy - sz * sy) / det;
        if (fabs(c0 - (double)t_rim_c) > (double)p->decay_asym_k) {
            continue;
        }
        double ss = 0.0;
        for (uint16_t i = 0u; i < n; i++) {
            const double z = exp(-(double)i * (double)p->dt_s / tau);
            const double r = (double)y[i] - (c0 + c1 * z);
            ss += r * r;
        }
        const double rms = sqrt(ss / (double)n);
        if (rms < best) {
            best = rms;
            best_change = fabs(c1) * (1.0 - exp(-span / tau));
        }
    }
    if (change_out != NULL) {
        *change_out = (float)best_change;
    }
    return (float)best;
}

bool cc_probe_says_contact(const cc_params_t *p, const float *y, const float *pw, uint16_t n,
                           float a_k_per_j, float t_rim_c, float lag_s, bool require_change, float *d_out,
                           float *d_exp_out, float *decay_rms_out, float *decay_change_out)
{
    const double dt = (double)p->dt_s;
    const double span = (n > 1u) ? (double)(n - 1u) * dt : 1.0;
    double A[4][4] = {{0.0}};
    double b[4] = {0.0};
    double coef[4] = {0.0};
    double e = 0.0, e_prev = 0.0, e_lag = 0.0;

    for (uint16_t i = 0u; i < n; i++) {
        /* E = cumulative coil energy (kJ) including this sample's period;
         * E_lag[i] advances from E[i-1] (as the reference does). */
        if (i > 0u) {
            e_lag += dt / (double)lag_s * (e_prev - e_lag);
        }
        e += (double)pw[i] * dt / 1000.0;
        e_prev = e;
        const double tau = (double)i * dt / span;   /* scaled time: same fit */
        const double xr[4] = {1.0, tau, tau * tau, e_lag};
        for (int r = 0; r < 4; r++) {
            for (int k = 0; k < 4; k++) {
                A[r][k] += xr[r] * xr[k];
            }
            b[r] += xr[r] * (double)y[i];
        }
    }
    double Acopy[4][4];
    double bcopy[4];
    memcpy(Acopy, A, sizeof(A));
    memcpy(bcopy, b, sizeof(b));
    const bool solved = solve(A, b, 4, coef);
    const double d = solved ? coef[3] : 0.0;
    const double d_exp = (double)a_k_per_j * 1000.0;
    bool responds = d >= (double)p->probe_frac * d_exp;
    if (solved && responds && p->probe_min_sigma > 0.0f && n > 4u) {
        /* Significance of d: sd = sqrt(s^2 (X'X)^-1[3][3]), with the residual
         * variance from the normal equations. (X'X)^-1[3][3] is the last entry
         * of the solution of (X'X) u = e3. */
        double sse = 0.0;
        {
            /* sum (y - X coef)^2 = y'y - 2 coef'X'y + coef'X'X coef; y'y is
             * accumulated separately below. */
            double yy = 0.0;
            for (uint16_t i = 0u; i < n; i++) {
                yy += (double)y[i] * (double)y[i];
            }
            double cxy = 0.0, cxxc = 0.0;
            for (int r = 0; r < 4; r++) {
                cxy += coef[r] * bcopy[r];
                for (int k = 0; k < 4; k++) {
                    cxxc += coef[r] * Acopy[r][k] * coef[k];
                }
            }
            sse = yy - 2.0 * cxy + cxxc;
            if (sse < 0.0) {
                sse = 0.0;
            }
        }
        double e3[4] = {0.0, 0.0, 0.0, 1.0};
        double u[4] = {0.0};
        if (solve(Acopy, e3, 4, u) && u[3] > 0.0) {
            const double sd = sqrt(sse / (double)(n - 4u) * u[3]);
            responds = d >= (double)p->probe_min_sigma * sd;
        }
    }
    float change = 0.0f;
    const float rms = cc_free_decay_rms(p, y, n, t_rim_c, &change);
    const bool decays = rms <= p->decay_rms_k && (!require_change || change >= p->decay_min_change_k);
    if (d_out != NULL) {
        *d_out = (float)d;
    }
    if (d_exp_out != NULL) {
        *d_exp_out = (float)d_exp;
    }
    if (decay_rms_out != NULL) {
        *decay_rms_out = rms;
    }
    if (decay_change_out != NULL) {
        *decay_change_out = change;
    }
    return responds || !decays;
}

/* Least-squares slope (K/s) of T_hat and the mean applied power over the last
 * n samples. */
static bool window_stats(const cc_t *c, uint16_t n, double *slope, double *pmean)
{
    double tm = 0.0, ym = 0.0, pm = 0.0;
    for (uint16_t i = 0u; i < n; i++) {
        const cc_sample_t *h = back(c, i);
        tm += (double)(n - 1u - i);
        ym += h->th;
        pm += h->p;
    }
    tm /= n;
    ym /= n;
    pm /= n;
    double sxy = 0.0, sxx = 0.0;
    for (uint16_t i = 0u; i < n; i++) {
        const cc_sample_t *h = back(c, i);
        const double dx = (double)(n - 1u - i) - tm;
        sxy += dx * ((double)h->th - ym);
        sxx += dx * dx;
    }
    if (!(sxx > 0.0)) {
        return false;
    }
    *slope = sxy / sxx / (double)c->p.dt_s;
    *pmean = pm;
    return true;
}

static void evaluate_probe(cc_t *c, uint32_t k, cc_output_t *out, float a, float t_rim)
{
    float ybuf[CC_RING_LEN];
    float pbuf[CC_RING_LEN];
    uint32_t n32 = k - c->state_tick + 1u;
    if (n32 > c->count) {
        n32 = c->count;
    }
    const uint16_t n = (uint16_t)n32;
    for (uint16_t i = 0u; i < n; i++) {
        const cc_sample_t *s = back(c, (uint16_t)(n - 1u - i));
        ybuf[i] = s->y;
        pbuf[i] = s->p;
    }
    const cc_state_t was = c->state;
    /* Entering LOST from NORMAL needs evidence of a free decay; leaving LOST
     * (a retry) keeps the reference rule. */
    const float lag = (c->shape == 0u) ? c->p.probe_lag_s : c->p.retry_lag_s;
    bool ok = cc_probe_says_contact(&c->p, ybuf, pbuf, n, a, t_rim, lag, was == CC_PROBE, &c->last_d,
                                    &c->last_d_exp, &c->last_decay_rms, &c->last_decay_change);
    if (was == CC_RETRY && c->p.retry_decay_only) {
        /* Leaving LOST needs the reading to depart from the free decay: the
         * energy coefficient alone is noise-limited on low-gain pans. */
        ok = c->last_decay_rms > c->p.decay_rms_k;
    }
    if (!ok) {
        c->state = CC_LOST;
        c->state_tick = k;
        if (!c->has_lost) {
            c->has_lost = true;
            c->lost_tick = k;
        }
        if (was == CC_PROBE) {
            out->event = CC_EVT_LOST;
        }
    } else {
        c->state = CC_NORMAL;
        c->trig_active = false;
        c->holdoff_until = k + c->holdoff_ticks;
        out->reset_integrator = true;
        out->event = (was == CC_RETRY) ? CC_EVT_RESTORED : CC_EVT_PROBE_PASSED;
    }
}

void cc_step(cc_t *c, float t_hat_c, float y_c, float p_applied_w, float a_k_per_j,
             float t_rim_c, cc_output_t *out)
{
    const cc_params_t *p = &c->p;
    const uint32_t k = c->tick++;

    out->override = false;
    out->p_override_w = 0.0f;
    out->event = CC_EVT_NONE;
    out->reset_integrator = false;

    /* History first (the reference appends before the detector runs). */
    cc_sample_t *s = &c->ring[c->head];
    s->y = y_c;
    s->th = t_hat_c;
    s->p = p_applied_w;
    c->head = (uint16_t)((c->head + 1u) % CC_RING_LEN);
    if (c->count < CC_RING_LEN) {
        c->count++;
    }

    if (c->state == CC_NORMAL && k >= c->holdoff_until) {
        bool start = false;
        if (c->probe_requested) {
            start = true;
        } else {
            double slope = 0.0, pm = 0.0;
            if (c->count > p->trig_window && window_stats(c, p->trig_window, &slope, &pm) &&
                slope < (double)p->trig_rate_k_per_s && pm >= (double)p->trig_pmin_frac * p->p_max_w) {
                if (!c->trig_active) {
                    c->trig_active = true;
                    c->trig_since = k;
                }
                if (k - c->trig_since >= c->hold_ticks) {
                    start = true;
                }
            } else {
                c->trig_active = false;
            }
        }
        if (start) {
            c->probe_requested = false;
            c->state = CC_PROBE;
            c->shape = 0u;
            c->state_tick = k;
            c->probes++;
            if (!c->has_suspect) {
                c->has_suspect = true;
                c->suspect_tick = k;
            }
            out->event = CC_EVT_SUSPECT;
        }
    } else if (c->state != CC_NORMAL) {
        /* A request while probing or lost is already being served. */
        c->probe_requested = false;
    }

    if (c->state == CC_PROBE || c->state == CC_RETRY) {
        const uint32_t d = k - c->state_tick;
        const uint8_t sh = c->shape;
        if (d < (uint32_t)c->len_shape[sh] - 1u) {
            const float frac = (sh == 0u) ? p->probe_p_frac : p->retry_p_frac;
            out->override = true;
            out->p_override_w = (d >= c->off_shape[sh] && d < c->off_shape[sh] + c->on_shape[sh])
                                    ? frac * p->p_max_w : 0.0f;
        } else {
            evaluate_probe(c, k, out, a_k_per_j, t_rim_c);
        }
    }
    if (c->state == CC_LOST) {
        out->override = true;
        out->p_override_w = 0.0f;
        if (k - c->state_tick >= c->retry_ticks) {
            c->state = CC_RETRY;
            c->shape = 1u;
            c->state_tick = k;
        }
    }
    if (c->state != CC_NORMAL) {
        out->reset_integrator = true;
    }
    out->state = c->state;
}
