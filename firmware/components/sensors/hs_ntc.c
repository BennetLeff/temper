/**
 * @file hs_ntc.c
 * @brief Heatsink NTC driver (see header). Structure follows rim_ntc.c.
 */

#include "hs_ntc.h"

#include <math.h>
#include <stddef.h>
#include <string.h>

#include "hs_ntc_table.h"

#define KELVIN 273.15

void hs_ntc_default_params(hs_ntc_params_t *p)
{
    if (p == NULL) {
        return;
    }
    p->dt_s = 0.1f;
    p->r_pullup_ohm = 10000.0f;
    p->adc_gain = HS_NTC_ADC_GAIN;
    p->v3v3_nominal_mv = 3300.0f;
    p->v3v3_min_mv = 3200.0f;
    p->v3v3_max_mv = 3420.0f;
    p->v3v3_contract_max_mv = 3367.0f;
    p->atten0_below_mv = 800.0f;
    p->atten2_below_mv = 1550.0f;
    p->atten_hyst_mv = 30.0f;
    p->fs0_mv = 850.0f;
    p->fs2_mv = 1600.0f;
    p->fs3_mv = 2900.0f;
    p->sat_margin_mv = HS_NTC_SAT_MARGIN_MV;
    p->divider_fault_mv = HS_NTC_DIVIDER_FAULT_MV;
    p->clip_margin_mv = 10.0f;
    p->short_below_mv = 250.0f;
    p->filter_tau_s = 1.0f;
    p->oversample = 8u;
    p->short_persist = 3u;
    p->adc_fail_persist = 10u;
    p->divider_persist = 3u;
}

bool hs_ntc_init(hs_ntc_t *h, const hs_ntc_params_t *p)
{
    if (h == NULL || p == NULL || !(p->dt_s > 0.0f) || !(p->r_pullup_ohm > 0.0f) || !(p->adc_gain > 0.0f) ||
        p->adc_gain > 1.0f || p->oversample < 1u || p->oversample > 16u || !(p->fs0_mv > p->atten0_below_mv) ||
        !(p->fs2_mv > p->atten2_below_mv) || !(p->fs3_mv > p->fs2_mv) ||
        !(p->v3v3_contract_max_mv >= p->v3v3_nominal_mv) || p->short_persist == 0u ||
        p->adc_fail_persist == 0u || !(p->filter_tau_s >= 0.0f) || !(p->sat_margin_mv >= 0.0f) ||
        !(p->sat_margin_mv < p->fs3_mv) || !(p->divider_fault_mv >= 0.0f) ||
        (p->divider_fault_mv > 0.0f && (!(p->divider_fault_mv > p->fs3_mv) || p->divider_persist == 0u))) {
        return false;
    }
    memset(h, 0, sizeof(*h));
    h->p = *p;
    h->atten = RIM_ATTEN_3;
    h->last.state = HS_NTC_NO_DATA;
    h->last.diag = HS_NTC_DIAG_NONE;
    h->last.t_c = NAN;
    h->last.t_raw_c = NAN;
    h->last.node_mv = NAN;
    h->last.v3v3_mv = p->v3v3_nominal_mv;
    h->last.rail_nominal = true;
    h->last.r_ohm = NAN;
    h->last.atten = RIM_ATTEN_3;
    return true;
}

float hs_ntc_r_to_c(float r_ohm)
{
    if (!(r_ohm > 0.0f) || !isfinite(r_ohm)) {
        return NAN;
    }
    for (unsigned i = 0u; i + 1u < HS_NTC_TABLE_N; i++) {
        const double ra = k_hs_ntc_table_ohm[i];
        const double rb = k_hs_ntc_table_ohm[i + 1u];
        if (ra >= r_ohm && r_ohm >= rb) {
            const double ia = 1.0 / ((double)k_hs_ntc_table_c[i] + KELVIN);
            const double ib = 1.0 / ((double)k_hs_ntc_table_c[i + 1u] + KELVIN);
            const double inv = ia + (log((double)r_ohm) - log(ra)) * (ib - ia) / (log(rb) - log(ra));
            return (float)(1.0 / inv - KELVIN);
        }
    }
    return NAN;
}

float hs_ntc_c_to_r(float t_c)
{
    if (!isfinite(t_c)) {
        return NAN;
    }
    for (unsigned i = 0u; i + 1u < HS_NTC_TABLE_N; i++) {
        const float ta = k_hs_ntc_table_c[i];
        const float tb = k_hs_ntc_table_c[i + 1u];
        if (ta <= t_c && t_c <= tb) {
            const double ia = 1.0 / ((double)ta + KELVIN);
            const double ib = 1.0 / ((double)tb + KELVIN);
            const double it = 1.0 / ((double)t_c + KELVIN);
            const double la = log((double)k_hs_ntc_table_ohm[i]);
            const double lb = log((double)k_hs_ntc_table_ohm[i + 1u]);
            return (float)exp(la + (lb - la) * (it - ia) / (ib - ia));
        }
    }
    return NAN;
}

static float full_scale(const hs_ntc_params_t *p, rim_atten_t a)
{
    return a == RIM_ATTEN_0 ? p->fs0_mv : (a == RIM_ATTEN_2 ? p->fs2_mv : p->fs3_mv);
}

static rim_atten_t range_up(rim_atten_t a)
{
    return a == RIM_ATTEN_0 ? RIM_ATTEN_2 : RIM_ATTEN_3;
}

/* `n` samples at `a`; trimmed mean (lowest and highest dropped when n >= 3). */
static bool read_set(const hs_ntc_hal_t *hal, rim_atten_t a, uint8_t n, float *mean, float *max_out)
{
    float sum = 0.0f;
    float lo = INFINITY;
    float hi = -INFINITY;
    for (uint8_t i = 0u; i < n; i++) {
        float mv;
        if (!hal->read_pin_mv(hal->ctx, a, &mv) || !isfinite(mv)) {
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

static rim_atten_t choose_atten(const hs_ntc_params_t *p, rim_atten_t cur, float pin_mv)
{
    const rim_atten_t up = pin_mv < p->atten0_below_mv ? RIM_ATTEN_0
                           : (pin_mv < p->atten2_below_mv ? RIM_ATTEN_2 : RIM_ATTEN_3);
    const rim_atten_t down = pin_mv < p->atten0_below_mv - p->atten_hyst_mv ? RIM_ATTEN_0
                             : (pin_mv < p->atten2_below_mv - p->atten_hyst_mv ? RIM_ATTEN_2 : RIM_ATTEN_3);
    if (up > cur) {
        return up;
    }
    if (down < cur) {
        return down;
    }
    return cur;
}

/* Upper bound on the heatsink temperature from a pin reading: the pin less
 * sat_margin_mv (ADC error, divider band, buffer offset), at the rail `vb`.
 * Colder than the table (or the node at or above the rail): the table's
 * -40 degC, which is then also an upper bound. */
static float sat_bound_c(const hs_ntc_params_t *p, float pin_mv, float vb)
{
    const float x = (pin_mv - p->sat_margin_mv) / p->adc_gain / vb;
    const float r = x < 1.0f ? p->r_pullup_ohm * x / (1.0f - x) : INFINITY;
    if (r < k_hs_ntc_table_ohm[HS_NTC_TABLE_N - 1u]) {
        return INFINITY;   /* not reached from the callers (the pin is near the rail); no bound */
    }
    const float t = hs_ntc_r_to_c(r);
    return isfinite(t) ? t : k_hs_ntc_table_c[0];
}

static void latch(hs_ntc_t *h, hs_ntc_diag_t d)
{
    h->last.state = HS_NTC_FAULT;
    h->last.diag = d;
    h->last.t_c = NAN;
    h->have_filter = false;
}

void hs_ntc_step(hs_ntc_t *h, const hs_ntc_hal_t *hal, hs_ntc_reading_t *out)
{
    const hs_ntc_params_t *p = &h->p;
    if (h->last.state == HS_NTC_FAULT) {
        *out = h->last;
        return;
    }

    /* 1. Pin voltage at the CR-7 attenuation, one range up if near its top. */
    rim_atten_t a = h->atten;
    float pin = NAN;
    float hi = NAN;
    bool ok = hal != NULL && hal->read_pin_mv != NULL && read_set(hal, a, p->oversample, &pin, &hi);
    while (ok && a != RIM_ATTEN_3 && hi >= full_scale(p, a) - p->clip_margin_mv) {
        a = range_up(a);
        ok = read_set(hal, a, p->oversample, &pin, &hi);
    }
    if (!ok) {
        if (++h->adc_fail_count >= p->adc_fail_persist) {
            latch(h, HS_NTC_DIAG_ADC);
        }
        *out = h->last;
        return;
    }
    h->adc_fail_count = 0u;
    h->atten = choose_atten(p, a, pin);
    const float node = pin / p->adc_gain;

    /* 1b. Divider fault: a pin level the intact divider cannot produce. */
    if (p->divider_fault_mv > 0.0f && a == RIM_ATTEN_3 && pin >= p->divider_fault_mv) {
        if (++h->divider_count >= p->divider_persist) {
            latch(h, HS_NTC_DIAG_DIVIDER);
        }
        *out = h->last;
        return;
    }
    h->divider_count = 0u;

    /* 2. Rail for the ratio. */
    float vdd = p->v3v3_nominal_mv;
    bool rail_nominal = true;
    float v;
    if (hal->read_v3v3_mv != NULL && hal->read_v3v3_mv(hal->ctx, &v) && isfinite(v) && v >= p->v3v3_min_mv &&
        v <= p->v3v3_max_mv) {
        vdd = v;
        rail_nominal = false;
    }

    hs_ntc_reading_t rd = h->last;
    rd.node_mv = node;
    rd.v3v3_mv = vdd;
    rd.rail_nominal = rail_nominal;
    rd.atten = a;
    rd.diag = HS_NTC_DIAG_NONE;

    /* 3. Short: the node near 0 V. */
    if (node < p->short_below_mv) {
        if (++h->short_count >= p->short_persist) {
            latch(h, HS_NTC_DIAG_SHORT);
        }
        *out = h->last;
        return;
    }
    h->short_count = 0u;

    /* 4. Saturated: above ATTEN3's calibrated range. An upper bound only;
     *    without a rail reading it is taken at the rail's contract maximum,
     *    the coldest temperature the reading can mean. */
    const float vb = rail_nominal ? p->v3v3_contract_max_mv : vdd;
    if (a == RIM_ATTEN_3 && pin >= p->fs3_mv) {
        h->over_count = 0u;
        h->have_filter = false;
        rd.r_ohm = NAN;
        rd.state = HS_NTC_SATURATED;
        rd.t_c = sat_bound_c(p, p->fs3_mv, vb);
        rd.t_raw_c = NAN;
        h->last = rd;
        *out = rd;
        return;
    }

    /* 5. Resistance and temperature. */
    const float x = node / vdd;
    const float res = x < 1.0f ? p->r_pullup_ohm * x / (1.0f - x) : INFINITY;
    const float t = hs_ntc_r_to_c(res);
    if (!isfinite(t)) {
        if (res < k_hs_ntc_table_ohm[HS_NTC_TABLE_N - 1u]) {
            /* Hotter than the table (150 degC, the part's rating). */
            if (++h->over_count >= p->short_persist) {
                latch(h, HS_NTC_DIAG_OVER_RANGE);
            }
            *out = h->last;
            return;
        }
        /* Colder than the table (-40 degC), or the node at the rail (an open
         * sensor, which HS_OPEN latches in hardware): no temperature, an
         * upper bound from this pin reading. */
        h->over_count = 0u;
        h->have_filter = false;
        rd.r_ohm = res;
        rd.state = HS_NTC_SATURATED;
        rd.t_c = sat_bound_c(p, pin, vb);
        rd.t_raw_c = NAN;
        h->last = rd;
        *out = rd;
        return;
    }
    h->over_count = 0u;

    /* 6. Filter. */
    if (!h->have_filter) {
        h->t_filt = t;
        h->have_filter = true;
    } else {
        const float alpha = p->dt_s / (p->filter_tau_s + p->dt_s);
        h->t_filt += alpha * (t - h->t_filt);
    }
    rd.state = HS_NTC_VALID;
    rd.r_ohm = res;
    rd.t_raw_c = t;
    rd.t_c = h->t_filt;
    h->last = rd;
    *out = rd;
}

void hs_ntc_poll(hs_ntc_t *h, const hs_ntc_hal_t *hal, uint32_t now_ms, hs_ntc_reading_t *out)
{
    const uint32_t period_ms = (uint32_t)lroundf(h->p.dt_s * 1000.0f);
    if (h->have_poll && (uint32_t)(now_ms - h->last_poll_ms) < period_ms) {
        *out = h->last;
        return;
    }
    h->have_poll = true;
    h->last_poll_ms = now_ms;
    hs_ntc_step(h, hal, out);
}

float hs_ntc_interlock_c(const hs_ntc_reading_t *rd)
{
    if (rd == NULL) {
        return INFINITY;
    }
    if ((rd->state == HS_NTC_VALID || rd->state == HS_NTC_SATURATED) && isfinite(rd->t_c)) {
        return rd->t_c;
    }
    return INFINITY;
}
