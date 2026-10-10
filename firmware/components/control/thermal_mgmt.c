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

/* v3v3 nominal 3.304 V (DECISIONS C8). The ADC reads the buffered node in absolute mV, so a v3v3
 * error is a ratio error here; the TPS3703 window bounds it to the 3.146-3.46 V range. */
const ntc_channel_t THERMAL_NTC_RIM = {
    .r_pullup_ohm = 10000.0f, .r25_ohm = 10000.0f, .beta_k = 3950.0f, /* B PROVISIONAL */
    .v_ref_mv = 3304.0f, .v_open_mv = 3200.0f, .v_short_mv = 3.0f,
};
/* Coil and heatsink: Vishay NTCALUG01A104GA (100 k) on a 10 k pull-up (thermal-sense block).
 * B25/85 = 4190 K from the Vishay datasheet, to be confirmed against the part on the bench. */
const ntc_channel_t THERMAL_NTC_COIL = {
    .r_pullup_ohm = 10000.0f, .r25_ohm = 100000.0f, .beta_k = 4190.0f,
    .v_ref_mv = 3304.0f, .v_open_mv = 3250.0f, .v_short_mv = 20.0f,
};
const ntc_channel_t THERMAL_NTC_SINK = {
    .r_pullup_ohm = 10000.0f, .r25_ohm = 100000.0f, .beta_k = 4190.0f,
    .v_ref_mv = 3304.0f, .v_open_mv = 3250.0f, .v_short_mv = 20.0f,
};

ntc_status_t ntc_channel_temp_c(const ntc_channel_t *ch, float mv, float *temp_c)
{
    if (!ch || !temp_c || !isfinite(mv)) return NTC_BAD_ARG;
    if (mv >= ch->v_open_mv || mv >= ch->v_ref_mv) return NTC_OPEN;
    if (mv <= ch->v_short_mv || mv <= 0.0f) return NTC_SHORT;
    float r = ch->r_pullup_ohm * mv / (ch->v_ref_mv - mv);
    float inv_t = 1.0f / T0_K + logf(r / ch->r25_ohm) / ch->beta_k;
    *temp_c = 1.0f / inv_t - C_TO_K;
    return NTC_OK;
}

float ntc_channel_mv_at(const ntc_channel_t *ch, float temp_c)
{
    float r = ch->r25_ohm * expf(ch->beta_k * (1.0f / (temp_c + C_TO_K) - 1.0f / T0_K));
    return ch->v_ref_mv * r / (r + ch->r_pullup_ohm);
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
    f->tank_cap_pct = 100u;
    if (fault || !valid) {
        f->on = true;
        f->drive = 1.0f;
        if (isfinite(coil_c) && coil_c > FAN_COIL_LIMIT_C) {
            f->coil_limit = true;
        }
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
        /* "Coil above 150 C at full fan": full fan is the 0.8 cap outside a fault. */
        f->coil_limit = coil_c > FAN_COIL_LIMIT_C && f->drive >= FAN_DRIVE_CAP - 1e-6f;
    }
    if (f->coil_limit) {
        float over = coil_c - FAN_COIL_LIMIT_C;
        float cap = 100.0f * (1.0f - over / FAN_COIL_LIMIT_BAND_K);
        f->tank_cap_pct = cap <= 0.0f ? 0u : (uint8_t)floorf(cap);
    }
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
