#include "tank_freq.h"
#include <math.h>

#define TWO_PI 6.28318530718f
#define DEG 0.0174532925f
#define TAN_MAX 1000.0f /* lag within 0.06 deg of 90 (or beyond): treat as 90 */

float tank_peak_trip_for(float c) { return fminf(TANK_PEAK_PER_RMS * c + TANK_PEAK_PICKUP_A, TANK_PEAK_TRIP_CAP_A); }
float tank_rms_trip_for(float c) { return TANK_RMS_TRIP_RATIO * c; }
float tank_crest_guard_for(float c) { return TANK_CREST_GUARD_RATIO * c; }
bool tank_ceiling_ok(float c) { return isfinite(c) && c >= TANK_CEILING_MIN_A && c <= TANK_CEILING_MAX_A; }

tank_freq_cfg_t tank_freq_default(void)
{
    return (tank_freq_cfg_t){
        .f_min_hz = 35000u, .f_max_hz = 60000u,
        .step_down_hz = 250u,  /* 60 -> 35 kHz in 100 halves (~0.83 s) */
        .step_up_hz = 1000u,
        .fit_sep_hz = 2000u,
        .f_res_margin = 1.05f, .zvs_lag_deg = 45.0f, .fit_lag_max_deg = 80.0f,
        .hyst = 0.02f, .peak_margin_a = TANK_PEAK_PICKUP_A,
        .pan_q_max = 10.0f, .pan_r_min_ohm = 0.8f, .pan_min_rms_a = 4.0f,
        .pan_confirm_halves = 6u, .overrun_halves = 12u, /* 50 ms / 100 ms */
        .block_halves = 120u,                             /* 1 s */
    };
}

bool tank_freq_config_ok(const tank_freq_cfg_t *c)
{
    return c && c->f_min_hz >= 35000u && c->f_max_hz <= 60000u && c->f_min_hz < c->f_max_hz &&
           c->step_down_hz >= 50u && c->step_down_hz <= 1000u &&
           c->step_up_hz >= c->step_down_hz && c->step_up_hz <= 2000u &&
           c->fit_sep_hz >= 500u && c->fit_sep_hz <= c->f_max_hz - c->f_min_hz &&
           isfinite(c->f_res_margin) && c->f_res_margin >= 1.05f && c->f_res_margin <= 1.5f &&
           /* (a) must keep proving 1.05 f_res for Q <= 10: never below 44.3 deg */
           isfinite(c->zvs_lag_deg) && c->zvs_lag_deg >= 45.0f && c->zvs_lag_deg <= 80.0f &&
           isfinite(c->fit_lag_max_deg) && c->fit_lag_max_deg >= c->zvs_lag_deg && c->fit_lag_max_deg <= 85.0f &&
           isfinite(c->hyst) && c->hyst >= 0 && c->hyst <= 0.2f &&
           isfinite(c->peak_margin_a) && c->peak_margin_a >= TANK_PEAK_PICKUP_A && c->peak_margin_a <= 10.0f &&
           isfinite(c->pan_q_max) && c->pan_q_max > 1.0f && c->pan_q_max <= 50.0f &&
           isfinite(c->pan_r_min_ohm) && c->pan_r_min_ohm > 0 && c->pan_r_min_ohm <= 10.0f &&
           isfinite(c->pan_min_rms_a) && c->pan_min_rms_a >= 1.0f && c->pan_min_rms_a <= 20.0f &&
           c->pan_confirm_halves >= 1u && c->pan_confirm_halves <= 120u &&
           c->overrun_halves >= 1u && c->overrun_halves <= 60u && c->block_halves <= 1200u;
}

void tank_freq_reset(tank_freq_t *t, const tank_freq_cfg_t *c)
{
    *t = (tank_freq_t){.f_hz = c->f_max_hz, .floor_hz = c->f_min_hz, .ceiling_eff_a = TANK_CEILING_DEFAULT_A,
                       .reason = TF_HOLD_LIMIT};
}

uint32_t tank_freq_slew(uint32_t from, uint32_t to, uint32_t max_step)
{
    if (to > from) return to - from > max_step ? from + max_step : to;
    return from - to > max_step ? from - max_step : to;
}

bool tank_freq_fit(float f1, float t1, float f2, float t2, float *w0sq, float *lr)
{
    if (!isfinite(f1) || !isfinite(f2) || f1 == f2 || !isfinite(t1) || !isfinite(t2) || t1 <= 0 || t2 <= 0)
        return false;
    if (f1 > f2) { float f = f1; f1 = f2; f2 = f; float t = t1; t1 = t2; t2 = t; }
    double w1 = TWO_PI * (double)f1, w2 = TWO_PI * (double)f2;
    /* t w = (L/R)(w^2 - w0^2): two equations in w0^2 and L/R. */
    double den = t2 * w2 - t1 * w1;
    if (!(den > 0)) return false;
    double s = w1 * w2 * (t2 * w1 - t1 * w2) / den;
    if (!(s > 0) || s >= w1 * w1) return false;
    double a = t1 * w1 / (w1 * w1 - s);
    if (!isfinite(a) || !(a > 0)) return false;
    *w0sq = (float)s;
    *lr = (float)a;
    return true;
}

static tank_freq_reason_t up(tank_freq_t *t, const tank_freq_cfg_t *c, uint32_t from, uint32_t step,
                             tank_freq_reason_t why)
{
    uint64_t f = (uint64_t)from + step;
    t->f_hz = f > c->f_max_hz ? c->f_max_hz : (uint32_t)f;
    return t->reason = why;
}

/* A limit exceeded at f: retreat (a full step if the excess is beyond the band) and block f. */
static tank_freq_reason_t over(tank_freq_t *t, const tank_freq_cfg_t *c, uint32_t f, bool marginal,
                               tank_freq_reason_t why)
{
    t->block_hz = f;
    t->block_left = c->block_halves;
    return up(t, c, f, marginal ? c->step_down_hz : c->step_up_hz, why);
}

static void drop_pan(tank_freq_t *t)
{
    t->pan_present = false;
    t->pan_count = 0;
}

/* Fit and f_res update from one half's lag (well-conditioned lags only). */
static void estimate(tank_freq_t *t, const tank_freq_cfg_t *c, float f, float tn)
{
    if (!t->have_anchor) {
        t->have_anchor = true;
        t->anchor_hz = f;
        t->anchor_tan = tn;
    } else if (fabsf(f - t->anchor_hz) >= (float)c->fit_sep_hz) {
        float w0sq, lr;
        /* A failed fit keeps the anchor, so the next half retries against the same point. */
        if (tank_freq_fit(t->anchor_hz, t->anchor_tan, f, tn, &w0sq, &lr)) {
            t->have_fit = true;
            t->l_over_r_s = lr;
            t->anchor_hz = f;
            t->anchor_tan = tn;
        }
    }
    if (!t->have_fit) return;
    /* One-point update with the last L/R: w0^2 = w^2 - t w / (L/R). A lag at or below zero puts
     * f_res at or above f (the floor rises above f: step up). A lag the last L/R cannot explain
     * (w0^2 <= 0) means L/R moved (another load): discard the fit and re-anchor here. */
    float w = TWO_PI * f;
    float w0sq = w * w - tn * w / t->l_over_r_s;
    if (!(w0sq > 0)) {
        t->have_fit = false;
        t->anchor_hz = f;
        t->anchor_tan = tn;
        t->f_res_hz = t->q = 0;
        return;
    }
    t->f_res_hz = sqrtf(w0sq) / TWO_PI;
    t->q = sqrtf(w0sq) * t->l_over_r_s;
}

tank_freq_reason_t tank_freq_step(tank_freq_t *t, const tank_freq_cfg_t *c, const tank_freq_limits_t *lim,
                                  const tank_freq_obs_t *o)
{
    if (!t || !c) return TF_UP_INVALID;
    bool ok = lim && o && o->valid && o->f_hz >= c->f_min_hz && o->f_hz <= c->f_max_hz &&
              isfinite(o->tank_rms_a) && o->tank_rms_a >= 0 && isfinite(o->inlet_a) &&
              isfinite(o->peak_a) && isfinite(o->p_inv_w) &&
              isfinite(lim->ceiling_a) && lim->ceiling_a > 0 && isfinite(lim->inlet_max_a) &&
              isfinite(lim->peak_trip_a) && (!o->phase_valid || isfinite(o->phi_rad)) &&
              (!o->fit_ok || (isfinite(o->f_fit_hz) && o->f_fit_hz > 0));
    if (!ok) {
        drop_pan(t);
        t->ceiling_eff_a = lim && isfinite(lim->ceiling_a) ? fminf(lim->ceiling_a, TANK_CEILING_DEFAULT_A)
                                                            : TANK_CEILING_DEFAULT_A;
        return up(t, c, t->f_hz, c->step_up_hz, TF_UP_INVALID);
    }
    uint32_t f = o->f_hz;
    float tn = NAN;
    bool well_cond = false;
    if (o->phase_valid) {
        tn = o->phi_rad >= 1.5707963f ? TAN_MAX : fminf(tanf(o->phi_rad), TAN_MAX);
        well_cond = o->phi_rad <= c->fit_lag_max_deg * DEG;
        if (o->fit_ok && well_cond) estimate(t, c, o->f_fit_hz, tn);
    }

    /* Pan evidence, then the no-pan clamp. */
    bool evidence = well_cond && t->have_fit && t->q <= c->pan_q_max && o->tank_rms_a >= c->pan_min_rms_a &&
                    o->p_inv_w >= c->pan_r_min_ohm * o->tank_rms_a * o->tank_rms_a;
    if (!evidence) drop_pan(t);
    else if (++t->pan_count >= c->pan_confirm_halves) { t->pan_present = true; t->pan_count = c->pan_confirm_halves; }
    float ceiling = t->pan_present ? lim->ceiling_a : fminf(lim->ceiling_a, TANK_CEILING_DEFAULT_A);
    t->ceiling_eff_a = ceiling;
    t->overrun = o->tank_rms_a > TANK_RMS_TRIP_RATIO * ceiling ? t->overrun + 1u : 0u;

    /* Floor (b): 1.05 f_res once estimated, never below f_min. */
    uint32_t floor = c->f_min_hz;
    if (t->have_fit) {
        float fl = ceilf(c->f_res_margin * t->f_res_hz);
        if (fl > (float)floor) floor = fl > (float)c->f_max_hz ? c->f_max_hz + 1u : (uint32_t)fl;
    }
    t->floor_hz = floor;

    if (t->overrun > c->overrun_halves) return up(t, c, f, c->step_up_hz, TF_FAULT_OVERRUN);
    if (!o->phase_valid) return up(t, c, f, c->step_up_hz, TF_UP_NO_PHASE);
    if (f < floor) return up(t, c, f, c->step_up_hz, TF_UP_BELOW_FLOOR);
    float k = 1.0f - c->hyst, kx = 1.0f + c->hyst;
    float lag_min = c->zvs_lag_deg * DEG, peak_max = lim->peak_trip_a - c->peak_margin_a;
    if (o->phi_rad < lag_min) return over(t, c, f, o->phi_rad >= k * lag_min, TF_UP_LAG);
    if (o->tank_rms_a > ceiling) return over(t, c, f, o->tank_rms_a <= kx * ceiling, TF_UP_RMS);
    if (o->inlet_a > lim->inlet_max_a) return over(t, c, f, o->inlet_a <= kx * lim->inlet_max_a, TF_UP_INLET);
    if (o->peak_a > peak_max) return over(t, c, f, o->peak_a <= kx * peak_max, TF_UP_PEAK);

    t->f_hz = f;
    if (t->block_left) t->block_left--;
    uint32_t next = f - c->step_down_hz < floor ? floor : f - c->step_down_hz;
    if (o->tank_rms_a > k * ceiling || o->inlet_a > k * lim->inlet_max_a || o->peak_a > k * peak_max ||
        o->phi_rad < kx * lag_min || (t->block_left && next <= t->block_hz && next < f))
        return t->reason = TF_HOLD_LIMIT;
    if (next >= f) return t->reason = floor <= c->f_min_hz ? TF_HOLD_FLOOR_MIN : TF_HOLD_FLOOR_ZVS;
    t->f_hz = next;
    return t->reason = TF_DOWN;
}
