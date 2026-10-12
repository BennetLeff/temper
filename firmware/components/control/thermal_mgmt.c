/*
 * Thermal management for the integrated controller: NTC channels (Vishay heatsink, Semitec 104GT-2
 * coil and rim), the C29 input RC, the 250 C pan cap, the R32 fan law and the L3 blower (inverted
 * PWM, tach, stall derate, blower_ctrl_step()). See thermal_mgmt.h.
 */
#include "thermal_mgmt.h"
#include <math.h>
#include <stddef.h>
#include <string.h>

#define T0_K 298.15f
#define C_TO_K 273.15f

const ntc_curve_t NTC_CURVE_VISHAY_MAT_D_4190 = {
    .a = -16.0349, .b = 5459.339, .c = -191141.0, .d = -3.328322E+06,
    .a1 = 3.354016E-03, .b1 = 2.460382E-04, .c1 = 3.405377E-06, .d1 = 1.034240E-07,
};

/* Semitec GT-2 data sheet (2023-08-01) R-T table for 104GT-2, kOhm -> Ohm. 85 C: B25/85 definition. */
static const float GT2_104_T_C[] = {0, 10, 20, 25, 30, 85, 100, 110, 120, 130, 140, 150, 160, 170,
                                    180, 190, 200, 210, 240, 250, 260, 270, 280, 290};
static const float GT2_104_R_OHM[] = {353700, 208600, 126800, 100000, 79360, 9093.7, 5556, 4082,
                                      3043, 2298, 1758, 1360, 1064, 841.4, 671.4, 540.8, 439.3,
                                      359.7, 206.5, 174.0, 147.5, 125.8, 107.9, 93.05};
const ntc_table_t NTC_TABLE_SEMITEC_104GT2 = {
    .n = sizeof GT2_104_T_C / sizeof GT2_104_T_C[0], .t_c = GT2_104_T_C, .r_ohm = GT2_104_R_OHM,
    .r25_ref_ohm = 100000.0f,
};

/* v3v3 nominal 3.304 V (DECISIONS C8). The ADC reads the buffered node in absolute mV, so a v3v3
 * error is a ratio error here; the TPS3703 window bounds it to the 3.146-3.46 V range.
 * Input RC (C29): 10 k (RC0603FR-0710KL, 1 %) into 100 nF (CC0603KRX7R9BB104, X7R) before each
 * buffer; HS / COIL also have the thermal-sense block's 100 nF (C20 / C22) at the node. */
const ntc_channel_t THERMAL_NTC_RIM = {
    .r_pullup_ohm = RIM_NTC_R_PULLUP_OHM, .r25_ohm = RIM_NTC_R25_OHM, .beta_k = RIM_NTC_BETA_K,
    .curve = NULL,
#if RIM_NTC_USE_GT2_TABLE
    .table = &NTC_TABLE_SEMITEC_104GT2,
#else
    .table = NULL,
#endif
    .v_ref_mv = 3304.0f, .t_open_c = -20.0f, .t_short_c = 320.0f,
    .v_meas_max_mv = THERMAL_ADC_MEAS_MAX_MV, .r25_tol = 0.03f, .beta_tol = 0.02f,
    .dissipation_mw_per_k = 0.6f, .filt_r_ohm = 10000.0f, .filt_c_f = 100e-9f, .node_c_f = 0.0f,
};
/* Coil and heatsink: open below -20 C (beyond the ADC's range anyway: see NTC_BELOW_RANGE),
 * short above 200 C (past the 165 C coil trip and the 182 C hardware high corner, so a real
 * over-temperature is never classed as a short first). */
const ntc_channel_t THERMAL_NTC_COIL = {
    .r_pullup_ohm = 10000.0f, .r25_ohm = 100000.0f, .beta_k = 4267.0f,
    .curve = NULL, .table = &NTC_TABLE_SEMITEC_104GT2, .v_ref_mv = 3304.0f, .t_open_c = -20.0f,
    .t_short_c = 200.0f, .v_meas_max_mv = THERMAL_ADC_MEAS_MAX_MV, .r25_tol = 0.03f,
    .beta_tol = 0.02f, .dissipation_mw_per_k = 0.6f, .filt_r_ohm = 10000.0f, .filt_c_f = 100e-9f,
    .node_c_f = 100e-9f,
};
/* Vishay NTCALUG01A104GA: 100 k +/- 2 %, B 4190 K +/- 1.5 % (doc 29092 p. 2); dissipation
 * constant ~1.5 mW/K is not used for a correction (0.1 mW at most on a 10 k pull-up). */
const ntc_channel_t THERMAL_NTC_SINK = {
    .r_pullup_ohm = 10000.0f, .r25_ohm = 100000.0f, .beta_k = 4190.0f,
    .curve = &NTC_CURVE_VISHAY_MAT_D_4190, .table = NULL, .v_ref_mv = 3304.0f, .t_open_c = -20.0f,
    .t_short_c = 200.0f, .v_meas_max_mv = THERMAL_ADC_MEAS_MAX_MV, .r25_tol = 0.02f,
    .beta_tol = 0.015f, .dissipation_mw_per_k = 1.5f, .filt_r_ohm = 10000.0f, .filt_c_f = 100e-9f,
    .node_c_f = 100e-9f,
};

static double inv_t(double t_c) { return 1.0 / (t_c + C_TO_K); }

/* Segment of the table holding t (or the end segment, for extrapolation). */
static unsigned table_seg_t(const ntc_table_t *tb, double t_c)
{
    unsigned i = 0;
    while (i + 2 < tb->n && t_c > tb->t_c[i + 1]) i++;
    return i;
}

static double table_ln_r(const ntc_table_t *tb, double t_c)
{
    unsigned i = table_seg_t(tb, t_c);
    double x0 = inv_t(tb->t_c[i]), x1 = inv_t(tb->t_c[i + 1]);
    double l0 = log(tb->r_ohm[i]), l1 = log(tb->r_ohm[i + 1]);
    return l0 + (l1 - l0) * (inv_t(t_c) - x0) / (x1 - x0);
}

static double table_t_c(const ntc_table_t *tb, double ln_r)
{
    unsigned i = 0; /* R falls along the table */
    while (i + 2 < tb->n && ln_r < log(tb->r_ohm[i + 1])) i++;
    double x0 = inv_t(tb->t_c[i]), x1 = inv_t(tb->t_c[i + 1]);
    double l0 = log(tb->r_ohm[i]), l1 = log(tb->r_ohm[i + 1]);
    double x = x0 + (ln_r - l0) * (x1 - x0) / (l1 - l0);
    return 1.0 / x - C_TO_K;
}

float ntc_channel_r_at(const ntc_channel_t *ch, float temp_c)
{
    double t = (double)temp_c + C_TO_K;
    if (ch->curve) {
        const ntc_curve_t *k = ch->curve;
        return (float)(ch->r25_ohm * exp(k->a + k->b / t + k->c / (t * t) + k->d / (t * t * t)));
    }
    if (ch->table)
        return (float)(exp(table_ln_r(ch->table, temp_c)) * ch->r25_ohm / ch->table->r25_ref_ohm);
    return ch->r25_ohm * (float)exp(ch->beta_k * (1.0 / t - 1.0 / T0_K));
}

static float temp_from_r(const ntc_channel_t *ch, float r)
{
    double x = log((double)r / ch->r25_ohm), inv;
    if (ch->curve) {
        /* Start from Vishay's inverse formula, then refine on the forward one (the one the R-T
         * tables are printed from): the two differ by up to 0.03 K at 85-120 C and more above
         * 150 C, and the forward form keeps conversion and thresholds on one curve. */
        const ntc_curve_t *k = ch->curve;
        double t = 1.0 / (k->a1 + k->b1 * x + k->c1 * x * x + k->d1 * x * x * x);
        for (int i = 0; i < 4; i++) {
            double f = k->a + k->b / t + k->c / (t * t) + k->d / (t * t * t) - x;
            double df = -k->b / (t * t) - 2.0 * k->c / (t * t * t) - 3.0 * k->d / (t * t * t * t);
            t -= f / df;
        }
        return (float)(t - C_TO_K);
    }
    if (ch->table)
        return (float)table_t_c(ch->table, log((double)r * ch->table->r25_ref_ohm / ch->r25_ohm));
    inv = 1.0 / T0_K + x / ch->beta_k;
    return (float)(1.0 / inv - C_TO_K);
}

float ntc_channel_mv_at(const ntc_channel_t *ch, float temp_c)
{
    float r = ntc_channel_r_at(ch, temp_c);
    return ch->v_ref_mv * r / (r + ch->r_pullup_ohm);
}

static float temp_at_mv(const ntc_channel_t *ch, float mv)
{
    return temp_from_r(ch, ch->r_pullup_ohm * mv / (ch->v_ref_mv - mv));
}

float ntc_channel_range_min_c(const ntc_channel_t *ch)
{
    if (!(ch->v_meas_max_mv > 0.0f) || ch->v_meas_max_mv >= ch->v_ref_mv) return ch->t_open_c;
    return temp_at_mv(ch, ch->v_meas_max_mv);
}

ntc_status_t ntc_channel_temp_c(const ntc_channel_t *ch, float mv, float *temp_c)
{
    if (!ch || !temp_c || !isfinite(mv)) return NTC_BAD_ARG;
    /* Thresholds follow the model, so new R / B values need no re-derivation. */
    if (mv >= ntc_channel_mv_at(ch, ch->t_open_c) || mv >= ch->v_ref_mv) return NTC_OPEN;
    if (mv <= ntc_channel_mv_at(ch, ch->t_short_c) || mv <= 0.0f) return NTC_SHORT;
    if (ch->v_meas_max_mv > 0.0f && mv >= ch->v_meas_max_mv) {
        *temp_c = ntc_channel_range_min_c(ch);
        return NTC_BELOW_RANGE;
    }
    *temp_c = temp_at_mv(ch, mv);
    return NTC_OK;
}

float ntc_channel_tol_k(const ntc_channel_t *ch, float temp_c)
{
    double r = ntc_channel_r_at(ch, temp_c);
    double dlnr_dt = (log(ntc_channel_r_at(ch, temp_c + 0.5f)) - log(ntc_channel_r_at(ch, temp_c - 0.5f)));
    double dln = log(1.0 + ch->r25_tol) + ch->beta_tol * fabs(log(r / ch->r25_ohm));
    return (float)(dln / fabs(dlnr_dt));
}

float ntc_channel_self_heat_k(const ntc_channel_t *ch, float temp_c)
{
    double r = ntc_channel_r_at(ch, temp_c), v = ch->v_ref_mv / 1000.0;
    double i = v / (r + ch->r_pullup_ohm);
    double p_mw = i * i * r * 1000.0;
    return ch->dissipation_mw_per_k > 0.0f ? (float)(p_mw / ch->dissipation_mw_per_k) : 0.0f;
}

/* ---------------------------------------------------------------- input RC */
float ntc_input_tau_s(const ntc_channel_t *ch)
{
    double rth = ch->r_pullup_ohm * (1.0 + NTC_RC_R_TOL);           /* pull-up || NTC <= pull-up */
    double rf = ch->filt_r_ohm * (1.0 + NTC_RC_R_TOL);
    double cn = ch->node_c_f * (1.0 + NTC_RC_C_TOL), cf = ch->filt_c_f * (1.0 + NTC_RC_C_TOL);
    return (float)(rth * cn + (rth + rf) * cf);
}

uint32_t ntc_input_settle_ms(const ntc_channel_t *ch)
{
    return (uint32_t)ceil(ntc_input_tau_s(ch) * log(4096.0) * 1000.0);
}

bool ntc_input_settled(const ntc_channel_t *ch, uint32_t ms_since_supply_up)
{
    return ms_since_supply_up >= ntc_input_settle_ms(ch);
}

float ntc_input_lag_k(const ntc_channel_t *ch, float rate_k_per_s)
{
    return ntc_input_tau_s(ch) * fabsf(rate_k_per_s);
}

/* ---------------------------------------------------------------- pan cap */
static uint8_t band_cap(float t_c)
{
    const float start = PAN_CAP_C - PAN_CAP_BAND_C;
    if (t_c <= start) return 100u;
    if (t_c >= PAN_CAP_C) return 0u;
    return (uint8_t)floorf(100.0f * (PAN_CAP_C - t_c) / PAN_CAP_BAND_C);
}

pan_cap_t pan_cap_evaluate(float pan_rtd_c, bool rtd_valid, float rim_c, bool rim_valid)
{
    pan_cap_t r = {.cap_pct = 100u};
    if (!rtd_valid || !isfinite(pan_rtd_c)) {
        r.cap_pct = 0u;
    } else {
        uint8_t c = band_cap(pan_rtd_c);
        r.rtd_limiting = c < 100u;
        if (c < r.cap_pct) r.cap_pct = c;
    }
    if (!rim_valid || !isfinite(rim_c)) {
        r.rim_invalid = true;
    } else {
        uint8_t c = band_cap(rim_c);
        r.rim_limiting = c < 100u;
        if (c < r.cap_pct) r.cap_pct = c;
    }
    return r;
}

/* ---------------------------------------------------------------- fan law */
void fan_law_init(fan_law_t *f)
{
    memset(f, 0, sizeof *f);
    f->sink.setpoint_c = FAN_SINK_SETPOINT_C;
    f->coil.setpoint_c = FAN_COIL_SETPOINT_C;
    f->tank_cap_pct = 100u;
}

static float clamp01(float x) { return x < 0.0f ? 0.0f : (x > 1.0f ? 1.0f : x); }

/* PI with conditional integration: the integrator only moves while the output is not pinned in
 * the direction of the error, so it cannot wind up during long cool or hot spells. */
static float pi_step(fan_pi_t *p, float t_c, float dt_s, float out_max)
{
    float e = t_c - p->setpoint_c;
    float out = FAN_KP_PER_K * e + p->integ;
    bool pinned_hi = out >= out_max && e > 0.0f;
    bool pinned_lo = out <= 0.0f && e < 0.0f;
    if (!pinned_hi && !pinned_lo) {
        p->integ += FAN_KI_PER_K_S * e * dt_s;
        if (p->integ < 0.0f) p->integ = 0.0f;
        if (p->integ > out_max) p->integ = out_max;
        out = FAN_KP_PER_K * e + p->integ;
    }
    out = clamp01(out);
    return out > out_max ? out_max : out;
}

void fan_law_step(fan_law_t *f, float sink_c, float coil_c, float dt_s, bool fault)
{
    bool valid = isfinite(sink_c) && isfinite(coil_c);
    f->coil_limit = false;
    if (fault || !valid) {
        f->on = true;
        f->drive = 1.0f;
        f->coil_limit = isfinite(coil_c) && coil_c > FAN_COIL_LIMIT_C;
    } else {
        float hottest = sink_c > coil_c ? sink_c : coil_c;
        if (f->on && hottest < FAN_OFF_BELOW_C) f->on = false;
        else if (!f->on && hottest >= FAN_OFF_BELOW_C + FAN_HYSTERESIS_K) f->on = true;
        if (!f->on) {
            f->sink.integ = f->coil.integ = 0.0f;
            f->drive = 0.0f;
        } else {
            float a = pi_step(&f->sink, sink_c, dt_s, FAN_DRIVE_CAP);
            float b = pi_step(&f->coil, coil_c, dt_s, FAN_DRIVE_CAP);
            f->drive = a > b ? a : b;
        }
        /* R32 says "coil above 150 C at full fan". The derate is applied above 150 C whatever the
         * fan does: 150 C is also the mean winding limit, and the coil loop is far into its range
         * there anyway (10 K above its 140 C setpoint). */
        f->coil_limit = coil_c > FAN_COIL_LIMIT_C;
    }
    f->tank_cap_pct = coil_tank_cap_pct(coil_c);
}

uint8_t coil_tank_cap_pct(float coil_c)
{
    if (!isfinite(coil_c)) return 0u;
    if (coil_c <= FAN_COIL_LIMIT_C) return 100u;
    float cap = 100.0f * (1.0f - (coil_c - FAN_COIL_LIMIT_C) / FAN_COIL_LIMIT_BAND_K);
    return cap <= 0.0f ? 0u : (uint8_t)floorf(cap);
}

/* ---------------------------------------------------------------- blower tach */
void blower_tach_init(blower_tach_t *t)
{
    memset(t, 0, sizeof *t);
    t->rpm = NAN;
}

float blower_tach_update(blower_tach_t *t, bool count_ok, uint16_t count, uint32_t now_ms,
                         unsigned pulses_per_rev)
{
    if (!count_ok || pulses_per_rev == 0u) {
        blower_tach_init(t); /* no trustworthy count: no speed until a fresh window closes */
        return t->rpm;
    }
    if (!t->primed) {
        t->primed = true;
        t->last_count = count;
        t->window_start_ms = now_ms;
        t->pulses = 0;
        return t->rpm;
    }
    t->pulses += (uint16_t)(count - t->last_count); /* modulo 2^16 */
    t->last_count = count;
    uint32_t elapsed = now_ms - t->window_start_ms;
    if (elapsed >= BLOWER_TACH_WINDOW_MS) {
        t->rpm = (float)t->pulses * 60000.0f / ((float)elapsed * (float)pulses_per_rev);
        t->pulses = 0;
        t->window_start_ms = now_ms;
    }
    return t->rpm;
}

/* ---------------------------------------------------------------- blower stall */
void blower_stall_init(blower_stall_t *s) { memset(s, 0, sizeof *s); }

uint8_t blower_stall_update(blower_stall_t *s, bool driven, float tach_rpm, uint32_t now_ms,
                            float sink_c, float coil_c)
{
    bool low = driven && !(tach_rpm >= BLOWER_STALL_RPM); /* NaN tach counts as low */
    if (!low) {
        s->below = false;
        s->stalled = false; /* the blower recovered: the derate and the stop lift */
        s->stopped = false;
        return 100u;
    }
    if (!s->below) {
        s->below = true;
        s->below_since_ms = now_ms;
    }
    if (!s->stalled && now_ms - s->below_since_ms > BLOWER_STALL_TIME_MS) {
        s->stalled = true;
        s->sink_at_stall = sink_c;
        s->coil_at_stall = coil_c;
    }
    if (!s->stalled) return 100u;
    bool rising = !isfinite(sink_c) || !isfinite(coil_c) ||
                  sink_c > s->sink_at_stall + BLOWER_STALL_RISE_K ||
                  coil_c > s->coil_at_stall + BLOWER_STALL_RISE_K;
    /* The stop holds until the tach recovers, so cooling does not cycle the tank on and off. */
    if (rising) s->stopped = true;
    return s->stopped ? 0u : (uint8_t)BLOWER_STALL_POWER_CAP_PCT;
}

/* ---------------------------------------------------------------- blower speed */
float blower_pwm_duty_from_drive(float drive)
{
    if (!isfinite(drive)) return 0.0f; /* duty 0 = full speed, the fail-safe */
    return (1.0f - clamp01(drive)) * BLOWER_PWM_DUTY_MAX;
}

uint32_t blower_ledc_counts(float duty, unsigned res_bits)
{
    if (res_bits == 0u || res_bits > 20u || !isfinite(duty)) return 0u;
    float full = (float)(1u << res_bits);
    return (uint32_t)lroundf(clamp01(duty) * full);
}

/* ---------------------------------------------------------------- blower controller */
void blower_ctrl_init(blower_ctrl_t *c)
{
    fan_law_init(&c->law);
    blower_tach_init(&c->tach);
    blower_stall_init(&c->stall);
}

blower_cmd_t blower_ctrl_step(blower_ctrl_t *c, float sink_c, float coil_c, bool fault,
                              bool tach_ok, uint16_t tach_count, uint32_t now_ms, float dt_s,
                              unsigned pulses_per_rev)
{
    blower_cmd_t o;
    fan_law_step(&c->law, sink_c, coil_c, dt_s, fault);
    o.on = c->law.on;
    /* Off: duty 0 anyway, so if FAN_OFF fails to switch the buck off the blower runs full. */
    o.duty = o.on ? blower_pwm_duty_from_drive(c->law.drive) : 0.0f;
    o.rpm = blower_tach_update(&c->tach, tach_ok, tach_count, now_ms, pulses_per_rev);
    uint8_t stall_cap = blower_stall_update(&c->stall, o.on, o.rpm, now_ms, sink_c, coil_c);
    o.power_cap_pct = c->law.tank_cap_pct < stall_cap ? c->law.tank_cap_pct : stall_cap;
    o.blower_failed = c->stall.stopped;
    return o;
}
