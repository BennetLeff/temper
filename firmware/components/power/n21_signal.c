#include "n21_signal.h"
#include <math.h>
#include <string.h>

static float trim(float t) { return t == 0.0f ? 1.0f : t; }

n21_sig_t n21_vbus_from_mv(const n21_analog_cal_t *c, float mv, float *v)
{
    if (!c || !v || !isfinite(mv) || !isfinite(c->vbus_offset_mv) || !isfinite(c->vbus_gain_trim))
        return N21_SIG_INVALID;
    /* D-11 thresholds apply to the raw calibrated ADC reading, before any trim. */
    if (mv < N21_VBUS_INVALID_MV) return N21_SIG_INVALID;
    if (mv >= N21_VBUS_OVERRANGE_MV) return N21_SIG_OVERRANGE;
    float bus = ((mv - c->vbus_offset_mv) * 1e-3f - N21_VBUS_BIAS_V) / N21_VBUS_V_PER_V;
    bus *= trim(c->vbus_gain_trim);
    /* D-11 zero accuracy is +/-5 V: tolerate that below zero, reject anything further. */
    if (bus < -10.0f) return N21_SIG_INVALID;
    *v = fmaxf(bus, 0.0f);
    return N21_SIG_OK;
}

n21_sig_t n21_ct_mon_from_mv(const n21_analog_cal_t *c, float mv, float *a)
{
    if (!c || !a || !isfinite(mv) || !isfinite(c->ct_mon_zero_mv)) return N21_SIG_INVALID;
    if (mv < N21_CT_MON_MIN_MV) return N21_SIG_INVALID;
    if (mv > N21_CT_MON_MAX_MV) return N21_SIG_OVERRANGE;
    float zero = c->ct_mon_zero_mv == 0.0f ? N21_CT_MON_BIAS_V * 1e3f : c->ct_mon_zero_mv;
    *a = (mv - zero) * 1e-3f / N21_CT_MON_V_PER_A;
    return N21_SIG_OK;
}

n21_sig_t n21_tank_rms_from_codes(const n21_analog_cal_t *c, uint16_t rms, uint16_t ref,
                                  float *amps, float *v3v3)
{
    /* code_ref = 4096 * 2.5 / v3v3 must sit inside the v3v3 contract. */
    const float ref_lo = N21_LM4040_V * 4096.0f / N21_V3V3_MAX_V;
    const float ref_hi = N21_LM4040_V * 4096.0f / N21_V3V3_MIN_V;
    if (!c || !amps || !isfinite(c->rms_gain_trim) || ref > 4095 || rms > 4095 ||
        (float)ref < ref_lo || (float)ref > ref_hi)
        return N21_SIG_INVALID;
    if (rms >= 4095) return N21_SIG_OVERRANGE; /* clipped: BAT54S clamp territory */
    if (v3v3) *v3v3 = N21_LM4040_V * 4096.0f / ref;
    *amps = N21_LM4040_V * rms / ref / N21_RMS_V_PER_A * trim(c->rms_gain_trim);
    return N21_SIG_OK;
}

float n21_line_rms_from_bus_peak(float peak, float drop)
{
    if (!isfinite(peak) || !isfinite(drop) || drop < 0) return NAN;
    return (peak + drop) * 0.70710678f;
}

void n21_mcp3202_frame(unsigned ch, uint8_t tx[3])
{
    tx[0] = 0x01;                                          /* start bit */
    tx[1] = (uint8_t)(0x80u | ((ch & 1u) << 6) | 0x20u);  /* SGL, ODD/SIGN = ch, MSBF */
    tx[2] = 0x00;
}

bool n21_mcp3202_decode(const uint8_t rx[3], uint16_t *code)
{
    /* rx[1] bit 4 is the null bit, driven low after MSBF; bits 7..5 are high-Z (undefined).
     * A set null bit means the frame was misaligned or nothing drove DOUT. */
    if (!rx || !code || (rx[1] & 0x10u)) return false;
    *code = (uint16_t)(((rx[1] & 0x0Fu) << 8) | rx[2]);
    return true;
}

bool n21_cos_phi(const n21_phase_cfg_t *c, uint32_t zc, float *cos_phi, float *phi_out)
{
    if (!c || !cos_phi || c->period_ticks < 4 || zc >= c->period_ticks || !isfinite(c->min_lag_rad))
        return false;
    int64_t p = c->period_ticks;
    int64_t lag = (int64_t)zc - c->ct_zc_delay_ticks - c->vsw_delay_ticks + (c->ct_zc_inverted ? p / 2 : 0);
    lag %= p;
    if (lag < 0) lag += p;
    if (lag > p / 2) lag -= p;               /* (-p/2, p/2]: negative = current leads */
    float phi = 6.28318530718f * (float)lag / (float)p;
    if (phi_out) *phi_out = phi;
    if (phi < c->min_lag_rad) return false;
    *cos_phi = cosf(phi);
    return true;
}

void n21_half_begin(n21_half_t *h, uint64_t zero)
{
    memset(h, 0, sizeof *h);
    h->start_us = zero;
    h->last_us = zero;
    h->open = true;
}

void n21_half_add(n21_half_t *h, uint64_t t, const input_sample_t *s)
{
    if (!h->open || h->broken) return;
    if (!s || t < h->last_us || h->n >= N21_HALF_MAX_SAMPLES) { h->broken = true; return; }
    if (t - h->last_us > h->max_gap_us) h->max_gap_us = t - h->last_us;
    h->last_us = t;
    h->s[h->n++] = *s;
    if (isfinite(s->bus_v) && s->bus_v > h->bus_peak_v) h->bus_peak_v = s->bus_v;
}

void n21_half_note(n21_half_t *h, uint32_t f, bool phi_valid, float phi, float ct)
{
    if (!h->open || h->broken) return;
    if (h->f_lo_hz == 0 || f < h->f_lo_hz) h->f_lo_hz = f;
    if (f > h->f_hi_hz) h->f_hi_hz = f;
    h->f_last_hz = f;
    if (phi_valid && isfinite(phi)) { h->phi_sum += phi; h->phi_n++; }
    if (isfinite(ct) && ct > h->ct_abs_max_a) h->ct_abs_max_a = ct;
}

bool n21_half_close(n21_half_t *h, const input_limits_cfg_t *cfg, uint64_t zero, uint32_t max_gap,
                    float drop, n21_half_result_t *r)
{
    return n21_half_close_aux(h, cfg, cfg ? cfg->aux_max_a : NAN, zero, max_gap, drop, r);
}

bool n21_half_close_aux(n21_half_t *h, const input_limits_cfg_t *cfg, float aux_a, uint64_t zero,
                        uint32_t max_gap, float drop, n21_half_result_t *r)
{
    bool was_open = h->open && !h->broken;
    h->open = false;
    if (!was_open || !r || zero < h->last_us) return false;
    uint64_t half = zero - h->start_us;
    uint64_t tail = zero - h->last_us;
    if (half < 7833 || half > 8834 || h->n < 8 || h->max_gap_us > max_gap || tail > max_gap)
        return false;
    float line = n21_line_rms_from_bus_peak(h->bus_peak_v, drop);
    if (!input_limits_half_cycle_aux(cfg, h->s, h->n, line, aux_a, &r->est)) return false;
    r->end_us = zero;
    r->line_rms_v = line;
    r->f_hz = h->f_last_hz;
    r->f_lo_hz = h->f_lo_hz;
    r->f_hi_hz = h->f_hi_hz;
    r->phi_n = h->phi_n;
    r->phi_mean_rad = h->phi_n ? h->phi_sum / (float)h->phi_n : NAN;
    r->ct_abs_max_a = h->ct_abs_max_a;
    r->rms_sample_max_a = 0;
    for (size_t j = 0; j < h->n; j++)
        if (h->s[j].tank_rms_a > r->rms_sample_max_a) r->rms_sample_max_a = h->s[j].tank_rms_a;
    return true;
}

void n21_line_agg_add(n21_line_agg_t *a, const n21_half_result_t *r)
{
    if (a->halves == 0) {
        a->line_rms_v = r->line_rms_v;
        a->inlet_bound_a = r->est.inlet_bound_a;
        a->tank_ceiling_w = r->est.tank_ceiling_w;
        a->tank_rms_a = r->est.tank_rms_a;
    } else {
        a->line_rms_v = fminf(a->line_rms_v, r->line_rms_v);
        a->inlet_bound_a = fmaxf(a->inlet_bound_a, r->est.inlet_bound_a);
        a->tank_ceiling_w = fminf(a->tank_ceiling_w, r->est.tank_ceiling_w);
        a->tank_rms_a = fmaxf(a->tank_rms_a, r->est.tank_rms_a);
    }
    a->last_end_us = r->end_us;
    a->halves++;
}

bool n21_line_report(const n21_line_agg_t *a, float pan_w, float startup_w,
                     float *line_v, float *inlet_a, float *budget_w)
{
    if (!a || !line_v || !inlet_a || !budget_w || a->halves == 0 ||
        !isfinite(pan_w) || pan_w < 0 || !isfinite(startup_w) || startup_w < 0)
        return false;
    *line_v = a->line_rms_v;
    *inlet_a = a->inlet_bound_a;
    float ceiling = isfinite(a->tank_ceiling_w) ? a->tank_ceiling_w : startup_w;
    *budget_w = fminf(pan_w, ceiling);
    return true;
}

void n21_feedback_from_capture(const n21_pwm_capture_t *c, const n21_status_rb_t *s,
                               uint32_t serial, bridge_feedback_t *f)
{
    memset(f, 0, sizeof *f);
    if (!c || !s) return;
    f->sampled_us = (uint32_t)c->t_us;
    f->serial = serial;
    f->rails_ok = s->rail_ok;
    f->sup_run_ok = s->sup_run_ok;
    f->interlock_ok = s->permit;
    f->bus_fault = s->bus_fault;
    for (unsigned n = 0; n < 4; n++) {
        const n21_edge_t *e = &c->out[n], *q = &c->out[n ^ 1u]; /* complement in the same leg */
        uint32_t p = e->period;
        if (!e->valid || !q->valid || p == 0 || e->high >= p || e->rise >= p || q->rise >= p ||
            q->high >= p)
            continue;
        uint32_t q_fall = (q->rise + q->high) % p;
        f->period[n] = p;
        f->high_ticks[n] = e->high;
        f->rise_ticks[n] = e->rise;
        f->nonoverlap_ticks[n] = (e->rise + p - q_fall) % p;
        f->valid[n] = true;
    }
}

bool n21_capture_matches(const bridge_cycle_t *c, const bridge_feedback_t *f)
{
    if (!c || !f || c->period < 4) return false;
    for (unsigned n = 0; n < 4; n++) {
        uint32_t tolerance = c->period / 100;
        if (!f->valid[n] || f->period[n] + tolerance < c->period ||
            f->period[n] > c->period + tolerance ||
            f->high_ticks[n] + 2 < c->pulse[n].width || f->high_ticks[n] > c->pulse[n].width + 2 ||
            f->rise_ticks[n] >= c->period)
            return false;
        uint32_t gap = (f->rise_ticks[n] + c->period - c->pulse[n].rise) % c->period;
        if (gap > 2 && gap < c->period - 2) return false;
        if (f->nonoverlap_ticks[n] < c->dead_ticks || f->nonoverlap_ticks[n] > c->dead_ticks + 2)
            return false;
    }
    return true;
}
