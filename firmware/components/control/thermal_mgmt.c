/*
 * Thermal management for the integrated controller: NTC channels (incl. the R36 rim NTC), the
 * 250 C pan cap, the R32 fan law and the L3 blower stall hook. See thermal_mgmt.h.
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

/* v3v3 nominal 3.304 V (DECISIONS C8). The ADC reads the buffered node in absolute mV, so a v3v3
 * error is a ratio error here; the TPS3703 window bounds it to the 3.146-3.46 V range. */
const ntc_channel_t THERMAL_NTC_RIM = {
    .r_pullup_ohm = RIM_NTC_R_PULLUP_OHM, .r25_ohm = RIM_NTC_R25_OHM, .beta_k = RIM_NTC_BETA_K,
    .curve = NULL, .v_ref_mv = 3304.0f, .t_open_c = -20.0f, .t_short_c = 320.0f,
};
/* Coil and heatsink: open below -20 C (the node is within ~31 mV of v3v3 there; colder is not a
 * credible kitchen and must not read as "cool"), short above 200 C (past the 165 C coil trip and
 * the part's 150 C rating, so a real over-temperature is never classed as a short first). */
const ntc_channel_t THERMAL_NTC_COIL = {
    .r_pullup_ohm = 10000.0f, .r25_ohm = 100000.0f, .beta_k = 4190.0f,
    .curve = &NTC_CURVE_VISHAY_MAT_D_4190, .v_ref_mv = 3304.0f, .t_open_c = -20.0f, .t_short_c = 200.0f,
};
const ntc_channel_t THERMAL_NTC_SINK = {
    .r_pullup_ohm = 10000.0f, .r25_ohm = 100000.0f, .beta_k = 4190.0f,
    .curve = &NTC_CURVE_VISHAY_MAT_D_4190, .v_ref_mv = 3304.0f, .t_open_c = -20.0f, .t_short_c = 200.0f,
};

float ntc_channel_r_at(const ntc_channel_t *ch, float temp_c)
{
    double t = (double)temp_c + C_TO_K;
    if (ch->curve) {
        const ntc_curve_t *k = ch->curve;
        return (float)(ch->r25_ohm * exp(k->a + k->b / t + k->c / (t * t) + k->d / (t * t * t)));
    }
    return ch->r25_ohm * (float)exp(ch->beta_k * (1.0 / t - 1.0 / T0_K));
}

static float temp_from_r(const ntc_channel_t *ch, float r)
{
    double x = log((double)r / ch->r25_ohm), inv_t;
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
    } else {
        inv_t = 1.0 / T0_K + x / ch->beta_k;
    }
    return (float)(1.0 / inv_t - C_TO_K);
}

float ntc_channel_mv_at(const ntc_channel_t *ch, float temp_c)
{
    float r = ntc_channel_r_at(ch, temp_c);
    return ch->v_ref_mv * r / (r + ch->r_pullup_ohm);
}

ntc_status_t ntc_channel_temp_c(const ntc_channel_t *ch, float mv, float *temp_c)
{
    if (!ch || !temp_c || !isfinite(mv)) return NTC_BAD_ARG;
    /* Thresholds follow the model, so new R / B values need no re-derivation. */
    if (mv >= ntc_channel_mv_at(ch, ch->t_open_c) || mv >= ch->v_ref_mv) return NTC_OPEN;
    if (mv <= ntc_channel_mv_at(ch, ch->t_short_c) || mv <= 0.0f) return NTC_SHORT;
    float r = ch->r_pullup_ohm * mv / (ch->v_ref_mv - mv);
    *temp_c = temp_from_r(ch, r);
    return NTC_OK;
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

/* ---------------------------------------------------------------- blower stall */
void blower_stall_init(blower_stall_t *s) { memset(s, 0, sizeof *s); }

uint8_t blower_stall_update(blower_stall_t *s, bool driven, float tach_hz, uint32_t now_ms,
                            float sink_c, float coil_c)
{
    bool low = driven && !(tach_hz >= BLOWER_STALL_TACH_HZ); /* NaN tach counts as low */
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

float blower_pwm_duty_from_drive(float drive)
{
    if (!isfinite(drive)) return 0.0f; /* duty 0 = full speed, the fail-safe */
    return 1.0f - clamp01(drive);
}
