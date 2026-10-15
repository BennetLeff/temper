/**
 * @file rim_ntc.c
 * @brief sensor-r3 C1 rim NTC driver (see header).
 */

#include "rim_ntc.h"

#include <math.h>
#include <stddef.h>
#include <string.h>

#include "rim_ntc_table.h"

#define KELVIN 273.15

void rim_ntc_default_params(rim_ntc_params_t *p)
{
    if (p == NULL) {
        return;
    }
    p->dt_s = 0.1f;
    p->r_pullup_ohm = 1000.0f;
    p->v3v3_nominal_mv = 3300.0f;
    p->v3v3_min_mv = 3200.0f;
    p->v3v3_max_mv = 3420.0f;
    p->atten0_below_mv = 800.0f;
    p->atten2_below_mv = 1550.0f;
    p->atten_hyst_mv = 30.0f;
    p->fs0_mv = 850.0f;
    p->fs2_mv = 1600.0f;
    p->fs3_mv = 2900.0f;
    p->clip_margin_mv = 10.0f;
    p->short_below_mv = 250.0f;
    p->t_max_c = 290.0f;
    p->open_pt100_c = 150.0f;
    p->open_hold_s = 600.0f;
    p->filter_tau_s = 1.0f;
    p->oversample = 8u;
    p->short_persist = 3u;
    p->adc_fail_persist = 10u;
}

bool rim_ntc_init(rim_ntc_t *r, const rim_ntc_params_t *p)
{
    if (r == NULL || p == NULL || !(p->dt_s > 0.0f) || !(p->r_pullup_ohm > 0.0f) || p->oversample < 1u ||
        p->oversample > 16u || !(p->fs0_mv > p->atten0_below_mv) || !(p->fs2_mv > p->atten2_below_mv) ||
        !(p->fs3_mv > p->fs2_mv) || !(p->v3v3_nominal_mv > p->fs3_mv) || p->short_persist == 0u ||
        p->adc_fail_persist == 0u || !(p->filter_tau_s >= 0.0f)) {
        return false;
    }
    memset(r, 0, sizeof(*r));
    r->p = *p;
    r->atten = RIM_ATTEN_3;   /* first reading on the full range */
    r->last.state = RIM_NTC_NO_DATA;
    r->last.diag = RIM_NTC_DIAG_NONE;
    r->last.t_c = NAN;
    r->last.t_raw_c = NAN;
    r->last.node_mv = NAN;
    r->last.v3v3_mv = p->v3v3_nominal_mv;
    r->last.rail_nominal = true;
    r->last.r_ohm = NAN;
    r->last.atten = RIM_ATTEN_3;
    return true;
}

float rim_ntc_r_to_c(float r_ohm)
{
    if (!(r_ohm > 0.0f) || !isfinite(r_ohm)) {
        return NAN;
    }
    for (unsigned i = 0u; i + 1u < RIM_NTC_TABLE_N; i++) {
        const double ra = k_rim_ntc_table_ohm[i];
        const double rb = k_rim_ntc_table_ohm[i + 1u];
        if (ra >= r_ohm && r_ohm >= rb) {
            const double ia = 1.0 / ((double)k_rim_ntc_table_c[i] + KELVIN);
            const double ib = 1.0 / ((double)k_rim_ntc_table_c[i + 1u] + KELVIN);
            const double inv = ia + (log((double)r_ohm) - log(ra)) * (ib - ia) / (log(rb) - log(ra));
            return (float)(1.0 / inv - KELVIN);
        }
    }
    return NAN;
}

float rim_ntc_c_to_r(float t_c)
{
    if (!isfinite(t_c)) {
        return NAN;
    }
    for (unsigned i = 0u; i + 1u < RIM_NTC_TABLE_N; i++) {
        const float ta = k_rim_ntc_table_c[i];
        const float tb = k_rim_ntc_table_c[i + 1u];
        if (ta <= t_c && t_c <= tb) {
            const double ia = 1.0 / ((double)ta + KELVIN);
            const double ib = 1.0 / ((double)tb + KELVIN);
            const double it = 1.0 / ((double)t_c + KELVIN);
            const double la = log((double)k_rim_ntc_table_ohm[i]);
            const double lb = log((double)k_rim_ntc_table_ohm[i + 1u]);
            return (float)exp(la + (lb - la) * (it - ia) / (ib - ia));
        }
    }
    return NAN;
}

static float full_scale(const rim_ntc_params_t *p, rim_atten_t a)
{
    return a == RIM_ATTEN_0 ? p->fs0_mv : (a == RIM_ATTEN_2 ? p->fs2_mv : p->fs3_mv);
}

static rim_atten_t range_up(rim_atten_t a)
{
    return a == RIM_ATTEN_0 ? RIM_ATTEN_2 : RIM_ATTEN_3;
}

/* `n` samples at `a`; trimmed mean (lowest and highest dropped when n >= 3). */
static bool read_set(const rim_ntc_hal_t *hal, rim_atten_t a, uint8_t n, float *mean, float *max_out)
{
    float sum = 0.0f;
    float lo = INFINITY;
    float hi = -INFINITY;
    for (uint8_t i = 0u; i < n; i++) {
        float mv;
        if (!hal->read_node_mv(hal->ctx, a, &mv) || !isfinite(mv)) {
            return false;
        }
        sum += mv;
        lo = mv < lo ? mv : lo;
        hi = mv > hi ? mv : hi;
    }
    *mean = n >= 3u ? (sum - lo - hi) / (float)(n - 2u) : sum / (float)n;
    *max_out = hi;
    return true;
}

static rim_atten_t choose_atten(const rim_ntc_params_t *p, rim_atten_t cur, float node_mv)
{
    const rim_atten_t up = node_mv < p->atten0_below_mv ? RIM_ATTEN_0
                           : (node_mv < p->atten2_below_mv ? RIM_ATTEN_2 : RIM_ATTEN_3);
    const rim_atten_t down = node_mv < p->atten0_below_mv - p->atten_hyst_mv ? RIM_ATTEN_0
                             : (node_mv < p->atten2_below_mv - p->atten_hyst_mv ? RIM_ATTEN_2 : RIM_ATTEN_3);
    if (up > cur) {
        return up;
    }
    if (down < cur) {
        return down;
    }
    return cur;
}

static void latch(rim_ntc_t *r, rim_ntc_diag_t d)
{
    r->last.state = RIM_NTC_FAULT;
    r->last.diag = d;
    r->last.t_c = NAN;
    r->have_filter = false;
}

void rim_ntc_step(rim_ntc_t *r, const rim_ntc_hal_t *hal, float t_pt100_c, rim_ntc_reading_t *out)
{
    const rim_ntc_params_t *p = &r->p;
    if (r->last.state == RIM_NTC_FAULT) {
        *out = r->last;
        return;
    }

    /* 1. Node voltage at the CR-7 attenuation, one range up if near clipping. */
    rim_atten_t a = r->atten;
    float node = NAN;
    float hi = NAN;
    bool ok = hal != NULL && hal->read_node_mv != NULL && read_set(hal, a, p->oversample, &node, &hi);
    while (ok && a != RIM_ATTEN_3 && hi >= full_scale(p, a) - p->clip_margin_mv) {
        a = range_up(a);
        ok = read_set(hal, a, p->oversample, &node, &hi);
    }
    if (!ok) {
        if (++r->adc_fail_count >= p->adc_fail_persist) {
            latch(r, RIM_NTC_DIAG_ADC);
        }
        *out = r->last;
        return;
    }
    r->adc_fail_count = 0u;
    r->atten = choose_atten(p, a, node);

    /* 2. Rail for the ratio. */
    float vdd = p->v3v3_nominal_mv;
    bool rail_nominal = true;
    float v;
    if (hal->read_v3v3_mv != NULL && hal->read_v3v3_mv(hal->ctx, &v) && isfinite(v) && v >= p->v3v3_min_mv &&
        v <= p->v3v3_max_mv) {
        vdd = v;
        rail_nominal = false;
    }

    rim_ntc_reading_t rd = r->last;
    rd.node_mv = node;
    rd.v3v3_mv = vdd;
    rd.rail_nominal = rail_nominal;
    rd.atten = a;
    rd.diag = RIM_NTC_DIAG_NONE;

    /* 3. Short: the node near 0 V (also an RTD lead shorted to RIM_SENSE). */
    if (node < p->short_below_mv) {
        r->open_count = 0u;
        if (++r->short_count >= p->short_persist) {
            latch(r, RIM_NTC_DIAG_SHORT);
        }
        *out = r->last;
        return;
    }
    r->short_count = 0u;

    /* 4. Saturated (cold rim, or an open bead): the upper bound only. */
    if (a == RIM_ATTEN_3 && node >= p->fs3_mv) {
        r->over_count = 0u;
        r->have_filter = false;
        if (isfinite(t_pt100_c) && t_pt100_c >= p->open_pt100_c) {
            r->open_count++;
            if ((float)r->open_count * p->dt_s >= p->open_hold_s - 0.5f * p->dt_s) {
                latch(r, RIM_NTC_DIAG_OPEN);
                *out = r->last;
                return;
            }
        } else {
            r->open_count = 0u;
        }
        const float x = p->fs3_mv / vdd;
        rd.r_ohm = p->r_pullup_ohm * x / (1.0f - x);
        rd.state = RIM_NTC_SATURATED;
        rd.t_c = rim_ntc_r_to_c(rd.r_ohm);
        rd.t_raw_c = NAN;
        r->last = rd;
        *out = rd;
        return;
    }
    r->open_count = 0u;

    /* 5. Resistance and temperature. */
    const float x = node / vdd;
    const float res = x < 1.0f ? p->r_pullup_ohm * x / (1.0f - x) : INFINITY;
    const float t = rim_ntc_r_to_c(res);
    if (!isfinite(t) || t > p->t_max_c) {
        /* Below the table's 300 degC resistance, or above t_max_c. */
        if (++r->over_count >= p->short_persist) {
            latch(r, RIM_NTC_DIAG_OVER_RANGE);
        }
        *out = r->last;
        return;
    }
    r->over_count = 0u;

    /* 6. Filter. */
    if (!r->have_filter) {
        r->t_filt = t;
        r->have_filter = true;
    } else {
        const float alpha = p->dt_s / (p->filter_tau_s + p->dt_s);
        r->t_filt += alpha * (t - r->t_filt);
    }
    rd.state = RIM_NTC_VALID;
    rd.r_ohm = res;
    rd.t_raw_c = t;
    rd.t_c = r->t_filt;
    r->last = rd;
    *out = rd;
}

void rim_ntc_report(const rim_ntc_reading_t *rd, rim_ntc_fault_sink_t sink, void *context)
{
    if (rd == NULL || sink == NULL || rd->state != RIM_NTC_FAULT) {
        return;
    }
    const bool short_class = rd->diag == RIM_NTC_DIAG_SHORT || rd->diag == RIM_NTC_DIAG_OVER_RANGE;
    sink(short_class, !short_class, context);
}
