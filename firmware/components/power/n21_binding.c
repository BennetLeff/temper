#include "n21_binding.h"
#include <math.h>
#include <string.h>

#define REPORT_MIN_US 15000u   /* report every second 10 ms tick: 20 ms, inside 14-22 ms */
#define LINE_FRESH_US 12000u   /* newest half cycle must have ended within ~1.4 halves */
#define REF_REFRESH_SAMPLES 8u /* LM4040 reference channel re-read cadence */
#define RESET_MIN_INTERVAL_US 1000000u

n21_config_t n21_config_default(void)
{
    n21_config_t c = {
        .mode = N21_MODE_INHIBITED, .calibrated = false,
        .timer_hz = 80000000u, .freq = tank_freq_default(), .input_deadtime_ns = 200u,
        .max_power_w = 1800.0f, .inlet_target_a = 13.5f, .auxiliary_reserve_w = 156.0f,
        .limits = input_limits_native21(),
        .vsw_delay_ns = 100, .ct_zc_delay_ns = 0, .ct_zc_inverted = false, .min_lag_deg = 5.0f,
        .line_zc = {.min_width_us = 300, .max_width_us = 4000, .min_half_us = 7833,
                    .max_half_us = 8834, .cal_offset_us = 0},
        .rectifier_drop_v = 0.0f, .startup_budget_w = 300.0f,
        .cos_phi_min_current_a = 2.0f,
        .acq_period_us = 625u, .sample_max_age_us = 2000u, .ct_zc_max_age_us = 2000u,
        .capture_age_us = 1000u, .half_max_gap_us = 1500u, .bench_max_ms = 60000u,
        /* 0.05 A per half = 6 A/s: a 0.4 A blower-tick step lands over 8 halves, and the
         * frequency loop (one retreat per half) follows the bound up. 5 blower ticks of age. */
        .aux_slew_a = 0.05f, .aux_max_age_us = 500000u,
    };
    (void)n21_config_set_tank_ceiling(&c, TANK_CEILING_DEFAULT_A);
    return c;
}

bool n21_config_set_tank_ceiling(n21_config_t *c, float a)
{
    if (!c) return false;
    if (!tank_ceiling_ok(a)) {
        c->limits.tank_limit_a = NAN; /* input_limits_config_ok and config_ok refuse it */
        return false;
    }
    c->limits.tank_limit_a = a;
    c->tank_rms_trip_a = tank_rms_trip_for(a);
    c->tank_crest_guard_a = tank_crest_guard_for(a);
    c->tank_peak_trip_a = tank_peak_trip_for(a);
    return true;
}

static void lock(n21_binding_t *b) { if (b->ops.lock) b->ops.lock(b->ops.ctx); }
static void unlock(n21_binding_t *b) { if (b->ops.unlock) b->ops.unlock(b->ops.ctx); }
static uint64_t now_us(n21_binding_t *b) { return b->ops.now_us(b->ops.ctx); }

static void latch(n21_binding_t *b, n21_fault_t f)
{
    if (b->fault == N21_FAULT_NONE) b->fault = f;
}

/* Gate first, then pads (adapter contract: deassert request BEFORE forcing PWM low). Both are
 * attempted whatever the first returns. */
static void pads_off(n21_binding_t *b)
{
    bool ok = true;
    if (b->ops.run_gate && !b->ops.run_gate(b->ops.ctx, false)) ok = false;
    b->gate_on = false;
    if (!b->ops.pwm_outputs(b->ops.ctx, false)) ok = false;
    b->pads_live = false;
    if (!ok) latch(b, N21_FAULT_HW);
}

static bool config_ok(const n21_config_t *c)
{
    float ceiling = c->limits.tank_limit_a;
    return c->timer_hz && tank_freq_config_ok(&c->freq) && c->input_deadtime_ns &&
           tank_ceiling_ok(ceiling) &&
           isfinite(c->max_power_w) && c->max_power_w > 0 &&
           isfinite(c->inlet_target_a) && c->inlet_target_a > 0 && c->inlet_target_a <= 13.5f &&
           isfinite(c->auxiliary_reserve_w) && c->auxiliary_reserve_w >= 0 &&
           input_limits_config_ok(&c->limits) &&
           c->line_zc.min_width_us && c->line_zc.max_width_us > c->line_zc.min_width_us &&
           c->line_zc.min_half_us >= 7833 && c->line_zc.max_half_us <= 8834 &&
           isfinite(c->min_lag_deg) && c->min_lag_deg >= 0 && c->min_lag_deg < 90 &&
           isfinite(c->rectifier_drop_v) && c->rectifier_drop_v >= 0 && c->rectifier_drop_v < 5 &&
           isfinite(c->startup_budget_w) && c->startup_budget_w >= 0 &&
           isfinite(c->tank_rms_trip_a) && c->tank_rms_trip_a > 0 &&
           /* Never above the derived 1.05 x trip: the B3 board rating (DECISIONS 55) is computed at it. */
           c->tank_rms_trip_a <= tank_rms_trip_for(ceiling) + 1e-3f &&
           /* The guard sits above the crest of the RMS trip (1.41 x) but never above 1.5 x. */
           isfinite(c->tank_crest_guard_a) && c->tank_crest_guard_a >= c->tank_rms_trip_a &&
           c->tank_crest_guard_a <= tank_crest_guard_for(ceiling) + 1e-3f &&
           /* Peak trip: never above the value derived from the ceiling, never at or above the
            * stage-15 CT band (the hardware trip stays the backstop). */
           isfinite(c->tank_peak_trip_a) && c->tank_peak_trip_a > 0 &&
           c->tank_peak_trip_a <= tank_peak_trip_for(ceiling) + 1e-3f &&
           c->tank_peak_trip_a < TANK_PEAK_TRIP_MAX_A &&
           isfinite(c->cos_phi_min_current_a) && c->cos_phi_min_current_a >= 0 &&
           /* >= 8 samples per half cycle even with one missed period */
           c->acq_period_us >= 100 && c->acq_period_us * 10u <= 7833u &&
           c->half_max_gap_us >= c->acq_period_us && c->half_max_gap_us <= 2000u &&
           c->sample_max_age_us >= c->acq_period_us && c->sample_max_age_us <= 5000u &&
           c->ct_zc_max_age_us && c->ct_zc_max_age_us <= 5000u &&
           c->capture_age_us && c->capture_age_us <= 1000u &&
           c->bench_max_ms && c->bench_max_ms <= 600000u &&
           isfinite(c->aux_slew_a) && c->aux_slew_a > 0 && c->aux_slew_a <= 0.2f &&
           c->aux_max_age_us >= 100000u && c->aux_max_age_us <= 2000000u;
}

static int32_t ns_to_ticks(int32_t ns, uint32_t hz)
{
    return (int32_t)llround((double)ns * hz / 1e9);
}

static bool cycle_equal(const bridge_cycle_t *a, const bridge_cycle_t *b)
{
    if (a->period != b->period || a->dead_ticks != b->dead_ticks) return false;
    for (unsigned n = 0; n < 4; n++)
        if (a->pulse[n].rise != b->pulse[n].rise || a->pulse[n].width != b->pulse[n].width)
            return false;
    return true;
}

static bool status(n21_binding_t *b, n21_status_rb_t *s)
{
    memset(s, 0, sizeof *s);
    if (!b->ops.read_status(b->ops.ctx, s)) {
        /* Unknown is treated as faulted. */
        *s = (n21_status_rb_t){.permit = false, .bus_fault = true, .rail_ok = false, .sup_run_ok = false};
        return false;
    }
    return true;
}

static bool interlock_healthy(const n21_status_rb_t *s)
{
    return s->permit && !s->bus_fault && s->rail_ok && s->sup_run_ok;
}

/* ------------------------------------------------------------------ acquisition context */
static bool loop_active(const n21_binding_t *b)
{
    return b->mode == N21_MODE_COMMISSIONED && b->gate_on && b->pads_live && b->fault == N21_FAULT_NONE;
}

/* Once per half line cycle: the auxiliary allowance in force for the closing half. A fresh schedule
 * is followed up by at most aux_slew_a and down at once; no schedule, a stale one or an invalid
 * value ramps towards the worst case. */
static float aux_for_half(n21_binding_t *b, uint64_t now)
{
    const input_limits_cfg_t *l = &b->cfg.limits;
    bool fresh = b->have_aux && now >= b->aux_set_us && now - b->aux_set_us <= b->cfg.aux_max_age_us;
    float target = fresh ? input_limits_aux(l, b->aux_set_a) : l->aux_max_a;
    b->aux_now_a = input_limits_aux_ramp(l, b->aux_now_a, target, b->cfg.aux_slew_a);
    b->tm.aux_a = b->aux_now_a;
    return b->aux_now_a;
}

/* Once per half line cycle, r == NULL when the half failed to close (stale or broken samples). */
static void half_closed(n21_binding_t *b, const n21_half_result_t *r)
{
    /* Stuck-low plausibility (tank_freq.h): the AD8436 chain reading far below what the raw CT_MON
     * peak allows, with the bridge running through the whole half, for several halves in a row.
     * The fault is the RMS-channel one: the same latch that a failed MCP3202 or reference read
     * takes, which inhibits the bridge. A half that failed to close is no evidence either way. */
    if (r) {
        if (b->half_live && tank_rms_implausible(r->est.tank_rms_a, r->ct_abs_max_a)) {
            if (++b->rms_implaus_n >= TANK_RMS_PLAUS_HALVES) latch(b, N21_FAULT_RMS_CHANNEL);
        } else {
            b->rms_implaus_n = 0;
        }
    }
    /* The envelope trip, on the half-cycle RMS (round 6: per-sample readings are the envelope
     * crest, ~1.41 x the line-cycle RMS). */
    if (r && r->est.tank_rms_a > b->cfg.tank_rms_trip_a) latch(b, N21_FAULT_TANK_RMS);
    if (!loop_active(b)) {
        tank_freq_reset(&b->tf, &b->cfg.freq);
        return;
    }
    tank_freq_obs_t o = {.valid = false};
    if (r) {
        float peak = fmaxf(TANK_PEAK_PER_RMS * r->est.tank_rms_a,
                           fmaxf(TANK_PEAK_PER_CREST_RMS * r->rms_sample_max_a, r->ct_abs_max_a));
        o = (tank_freq_obs_t){
            .valid = true, .phase_valid = r->phi_n >= 4u, .f_hz = r->f_hz,
            /* Frequency moved by at most one approach step within the half: its lag may feed the
             * f_res fit, at the mean frequency. */
            .fit_ok = r->f_lo_hz > 0 && r->f_hi_hz - r->f_lo_hz <= b->cfg.freq.step_down_hz,
            .f_fit_hz = 0.5f * ((float)r->f_lo_hz + (float)r->f_hi_hz),
            .phi_rad = r->phi_mean_rad, .tank_rms_a = r->est.tank_rms_a,
            .inlet_a = r->est.inlet_bound_a, .peak_a = peak, .p_inv_w = r->est.p_inv_w,
            .p_in_w = r->est.p_in_w,
        };
    }
    float ceiling = b->cfg.limits.tank_limit_a;
    if (b->thermal_limited && b->thermal_limit_a < ceiling) ceiling = b->thermal_limit_a;
    tank_freq_limits_t lim = {.ceiling_a = ceiling,
                              .inlet_max_a = b->cfg.inlet_target_a,
                              .peak_trip_a = b->cfg.tank_peak_trip_a, .request_w = b->request_w};
    if (tank_freq_step(&b->tf, &b->cfg.freq, &lim, &o) == TF_FAULT_OVERRUN)
        latch(b, N21_FAULT_TANK_RMS); /* no-pan clamp (or ceiling) not held: latch */
}

void n21_acquire_step(n21_binding_t *b)
{
    if (!b || !b->initialized) return;
    uint64_t now = now_us(b);
    lock(b);
    uint64_t t[8];
    bool lv[8];
    size_t edges = b->ops.line_zc_edges ? b->ops.line_zc_edges(b->ops.ctx, t, lv, 8) : 0;
    for (size_t i = 0; i < edges && i < 8; i++) line_zc_edge(&b->zc, t[i], lv[i]);

    /* Half-cycle boundaries come from LINE_ZC only (DECISIONS 2026-10-06). */
    uint64_t zero;
    while (line_zc_poll(&b->zc, now, &zero)) {
        if (b->half.open) {
            n21_half_result_t r;
            float aux = aux_for_half(b, now);
            if (n21_half_close_aux(&b->half, &b->cfg.limits, aux, zero, b->cfg.half_max_gap_us,
                                   b->cfg.rectifier_drop_v, &r)) {
                n21_line_agg_add(&b->agg, &r);
                b->tm.last_half = r;
                b->tm.have_half = true;
                b->tm.halves_ok++;
                half_closed(b, &r);
            } else {
                b->tm.halves_bad++;
                half_closed(b, NULL);
            }
        }
        if (b->ops.shadow_half) {
            /* Bench shadow RMS (telemetry only: nothing below reads tm.shadow_*). */
            float v = NAN;
            uint32_t fs = 0;
            b->tm.shadow_valid = b->ops.shadow_half(b->ops.ctx, b->cycle_hz, &v, &fs);
            b->tm.shadow_rms_a = b->tm.shadow_valid ? v : NAN;
            b->tm.shadow_fs_hz = fs;
        }
        n21_half_begin(&b->half, zero);
        b->half_live = b->pads_live;
    }
    b->tm.zc_locked = b->zc.locked;

    bool invalid = false;
    float vbus_mv = NAN, ct_mv = NAN, bus = NAN, ct_a = NAN, rms = NAN, v3 = NAN;
    if (!b->ops.read_adc1(b->ops.ctx, &vbus_mv, &ct_mv)) {
        invalid = true;
    } else {
        n21_sig_t s = n21_vbus_from_mv(&b->cfg.analog, vbus_mv, &bus);
        if (s == N21_SIG_OVERRANGE) latch(b, N21_FAULT_VBUS_OVERRANGE); /* D-11 latch */
        else if (s != N21_SIG_OK) invalid = true;                      /* D-20 O13: re-arms */
        s = n21_ct_mon_from_mv(&b->cfg.analog, ct_mv, &ct_a);
        if (s == N21_SIG_OVERRANGE) latch(b, N21_FAULT_TANK_PEAK);
        else if (s != N21_SIG_OK) latch(b, N21_FAULT_CT_MON);
        else if (fabsf(ct_a) > b->cfg.tank_peak_trip_a) latch(b, N21_FAULT_TANK_PEAK);
    }
    /* MCP3202: the reference channel is re-read every few samples; v3v3 moves slowly. */
    uint16_t code = 0;
    if (b->ref_code == 0 || b->samples % REF_REFRESH_SAMPLES == 0) {
        if (!b->ops.read_ext_adc(b->ops.ctx, N21_MCP3202_CH_REF, &code)) latch(b, N21_FAULT_RMS_CHANNEL);
        else b->ref_code = code;
    }
    if (!b->ops.read_ext_adc(b->ops.ctx, N21_MCP3202_CH_RMS, &code)) {
        latch(b, N21_FAULT_RMS_CHANNEL);
    } else if (n21_tank_rms_from_codes(&b->cfg.analog, code, b->ref_code, &rms, &v3) != N21_SIG_OK) {
        latch(b, N21_FAULT_RMS_CHANNEL);
    } else if (rms > b->cfg.tank_crest_guard_a) {
        latch(b, N21_FAULT_TANK_RMS);  /* per-sample crest guard; the trip is on the half RMS */
    }

    /* cos(phi): CT_ZC is undefined without tank current; cos = 1 is the conservative bound. */
    float cos_phi = 1.0f, phi = 0.0f;
    bool phi_valid = false;
    if (isfinite(rms) && rms >= b->cfg.cos_phi_min_current_a && b->pads_live) {
        uint32_t zc = 0;
        uint64_t zt = 0;
        if (!b->ops.read_ct_zc(b->ops.ctx, &zc, &zt) || zt > now || now - zt > b->cfg.ct_zc_max_age_us)
            latch(b, N21_FAULT_CT_ZC_STALE);
        else if (!n21_cos_phi(&b->phase, zc, &cos_phi, &phi))
            latch(b, N21_FAULT_PHASE);
        else
            phi_valid = true;
    }

    b->half_live = b->half_live && b->pads_live;
    bool good = !invalid && b->fault == N21_FAULT_NONE && isfinite(bus) && isfinite(rms);
    if (good) {
        input_sample_t s = {.bus_v = bus, .tank_rms_a = rms, .cos_phi = cos_phi};
        n21_half_add(&b->half, now, &s);
        n21_half_note(&b->half, b->cycle_hz, phi_valid, phi, fabsf(ct_a));
    } else {
        b->half.broken = true;  /* a half with a bad sample never closes */
    }
    b->invalid = invalid;
    b->samples++;
    b->last_sample_us = now;
    b->have_sample = true;
    b->tm.bus_v = bus;
    b->tm.ct_mon_a = ct_a;
    b->tm.tank_rms_a = rms;
    b->tm.cos_phi = cos_phi;
    b->tm.phi_rad = phi;
    b->tm.v3v3 = v3;
    b->tm.sample_invalid = invalid;
    unlock(b);
}

/* ------------------------------------------------------------------ control context */
static void capture(n21_binding_t *b, uint64_t now, const n21_status_rb_t *s, bridge_feedback_t *f)
{
    n21_pwm_capture_t cap;
    memset(&cap, 0, sizeof cap);
    cap.t_us = now;
    if (b->pads_live && !b->ops.pwm_capture(b->ops.ctx, &cap)) memset(cap.out, 0, sizeof cap.out);
    n21_feedback_from_capture(&cap, s, ++b->serial, f);
}

static bool line_ready(const n21_binding_t *b, uint64_t now)
{
    return b->agg.halves > 0 && now >= b->agg.last_end_us && now - b->agg.last_end_us <= LINE_FRESH_US;
}

static bool sample_fresh(const n21_binding_t *b, uint64_t now)
{
    return b->have_sample && now >= b->last_sample_us && now - b->last_sample_us <= b->cfg.sample_max_age_us;
}

static bool report(n21_binding_t *b, uint64_t now, bool *line, float *v, float *a, float *w)
{
    if (!n21_line_report(&b->agg, b->pan_model_w, b->cfg.startup_budget_w, v, a, w)) return false;
    memset(&b->agg, 0, sizeof b->agg);
    b->last_report_us = now;
    *line = true;
    return true;
}

static bool sample(void *ctx, uint32_t *now32, bridge_feedback_t *f, bool *line,
                   float *v, float *a, float *w)
{
    n21_binding_t *b = ctx;
    *line = false;
    uint64_t now = now_us(b);
    *now32 = (uint32_t)now;
    n21_status_rb_t s;
    if (!status(b, &s)) latch(b, N21_FAULT_HW);
    lock(b);
    bool ok = true;
    if (b->fault != N21_FAULT_NONE) {
        ok = false;
    } else if (!b->armed_line) {
        /* Pre-arm: the adapter has no line record, so power_service never reaches apply and the
         * pads stay low. Readback and invalid-sample conditions only delay arming here. */
        if (!b->invalid && sample_fresh(b, now) && interlock_healthy(&s) && line_ready(b, now)) {
            if (!b->pads_live) {
                /* With the run gate low the drivers stay disabled (hardware gap H1 otherwise,
                 * where init has already refused to bind). */
                if (b->ops.run_gate == NULL || b->gate_on || !b->ops.pwm_outputs(b->ops.ctx, true)) {
                    latch(b, N21_FAULT_HW);
                    ok = false;
                } else {
                    b->pads_live = true;
                }
            }
            if (ok && report(b, now, line, v, a, w)) b->armed_line = true;
        }
    } else if (b->invalid || !sample_fresh(b, now) || !interlock_healthy(&s)) {
        ok = false;
    } else if (now - b->last_report_us >= REPORT_MIN_US) {
        if (!line_ready(b, now) || !report(b, now, line, v, a, w)) ok = false; /* LINE_ZC lost */
    }
    unlock(b);
    capture(b, now, &s, f);
    b->tm.fault = b->fault;
    return ok;
}

/* Control context, once per tick before fullbridge_apply: the loop target (f_max while the gate is
 * off), approached from the programmed frequency by at most step_up_hz. */
static uint32_t frequency(void *ctx, float requested_w)
{
    n21_binding_t *b = ctx;
    lock(b);
    b->request_w = isfinite(requested_w) && requested_w > 0 ? requested_w : 0.0f;
    uint32_t target = loop_active(b) ? b->tf.f_hz : b->cfg.freq.f_max_hz;
    b->freq_cmd_hz = tank_freq_slew(b->cycle_hz, target, b->cfg.freq.step_up_hz);
    uint32_t f = b->freq_cmd_hz;
    unlock(b);
    return f;
}

static bool apply_cycle(void *ctx, const bridge_cycle_t *c)
{
    n21_binding_t *b = ctx;
    const tank_freq_cfg_t *fc = &b->cfg.freq;
    /* Only the 180-degree plan of the frequency last handed out by frequency(), inside
     * [f_min, f_max] and at most one bounded step from the programmed cycle. */
    uint32_t f = b->freq_cmd_hz;
    bridge_cycle_t want;
    if (!c || f < fc->f_min_hz || f > fc->f_max_hz ||
        !bridge_plan_cycle(b->cfg.timer_hz, f, b->cfg.input_deadtime_ns, 1.0f, &want) || !cycle_equal(c, &want))
        return false;
    if (b->programmed && cycle_equal(c, &b->cycle)) return true;
    uint32_t step = f > b->cycle_hz ? f - b->cycle_hz : b->cycle_hz - f;
    if (b->programmed && step > fc->step_up_hz) return false;
    lock(b); /* the period and the CT_ZC phase reference change together */
    bool ok = b->pads_live ? (b->ops.pwm_update && b->ops.pwm_update(b->ops.ctx, c))
                           : b->ops.pwm_program(b->ops.ctx, c);
    if (ok) {
        b->cycle = *c;
        b->cycle_hz = f;
        b->phase.period_ticks = c->period;
        b->programmed = true;
    }
    unlock(b);
    return ok;
}

static bool set_request(void *ctx, bool on)
{
    n21_binding_t *b = ctx;
    if (!on) {
        bool ok = !b->ops.run_gate || b->ops.run_gate(b->ops.ctx, false);
        b->gate_on = false;
        return ok;
    }
    n21_status_rb_t s;
    if (b->mode != N21_MODE_COMMISSIONED || !b->ops.run_gate || !b->pads_live || !b->armed_line ||
        b->fault != N21_FAULT_NONE || !status(b, &s) || !interlock_healthy(&s))
        return false;
    if (!b->ops.run_gate(b->ops.ctx, true)) return false;
    b->gate_on = true;
    return true;
}

static void inhibit(void *ctx)
{
    pads_off((n21_binding_t *)ctx);
}

/* ------------------------------------------------------------------ init / API */
n21_init_t n21_binding_init(n21_binding_t *b, const n21_config_t *c, const n21_hw_ops_t *ops,
                            power_binding_t *out)
{
    if (out) memset(out, 0, sizeof *out);
    if (!b) return N21_INIT_ERROR;
    memset(b, 0, sizeof *b);
    if (!ops || !ops->pwm_outputs) return N21_INIT_ERROR;
    b->ops = *ops;
    /* Safe state first, unconditionally. */
    if (ops->run_gate) (void)ops->run_gate(ops->ctx, false);
    if (!ops->pwm_outputs(ops->ctx, false)) return N21_INIT_ERROR;
    if (!c || !ops->now_us || !ops->pwm_program || !ops->pwm_capture || !ops->read_status ||
        !ops->interlock_reset_pulse || !ops->read_adc1 || !ops->read_ext_adc || !ops->read_ct_zc ||
        !ops->line_zc_edges)
        return N21_INIT_ERROR;
    b->cfg = *c;
    b->mode = c->mode;
    b->pan_model_w = c->max_power_w;
    b->aux_now_a = c->limits.aux_max_a; /* worst case until the blower schedule reports */
    b->tm.aux_a = b->aux_now_a;
    line_zc_init(&b->zc, &c->line_zc);
    if (c->mode == N21_MODE_INHIBITED) {
        /* Telemetry only. Phase/limits still need a sane config to evaluate. */
        b->initialized = input_limits_config_ok(&c->limits) && c->acq_period_us > 0;
        return b->initialized ? N21_INIT_INHIBITED : N21_INIT_ERROR;
    }
    if (c->mode != N21_MODE_BENCH && c->mode != N21_MODE_COMMISSIONED) return N21_INIT_ERROR;
    if (!config_ok(c) || !bridge_plan_cycle(c->timer_hz, c->freq.f_max_hz, c->input_deadtime_ns, 1.0f, &b->cycle))
        return N21_INIT_ERROR;
    b->cycle_hz = b->freq_cmd_hz = c->freq.f_max_hz;
    tank_freq_reset(&b->tf, &c->freq);
    b->phase = (n21_phase_cfg_t){
        .period_ticks = b->cycle.period,
        .vsw_delay_ticks = ns_to_ticks(c->vsw_delay_ns, c->timer_hz),
        .ct_zc_delay_ticks = ns_to_ticks(c->ct_zc_delay_ns, c->timer_hz),
        .ct_zc_inverted = c->ct_zc_inverted,
        .min_lag_rad = c->min_lag_deg * 0.0174532925f,
    };
    if (c->mode == N21_MODE_COMMISSIONED) {
        if (!ops->run_gate) return N21_INIT_NO_RUN_GATE;
        if (!c->calibrated) return N21_INIT_NOT_CALIBRATED;
        if (!ops->pwm_update) return N21_INIT_ERROR; /* the frequency loop needs live retiming */
    }
    if (!ops->pwm_program(ops->ctx, &b->cycle)) return N21_INIT_ERROR;
    b->programmed = true;
    b->initialized = true;
    if (c->mode == N21_MODE_BENCH) return N21_INIT_BENCH;
    if (!out) return N21_INIT_ERROR;
    out->config = (bridge_config_t){
        .timer_hz = c->timer_hz, .frequency_hz = c->freq.f_max_hz, .frequency_min_hz = c->freq.f_min_hz,
        .input_deadtime_ns = c->input_deadtime_ns, .capture_age_us = c->capture_age_us,
        .max_power_w = c->max_power_w, .inlet_target_a = c->inlet_target_a,
        .auxiliary_reserve_w = c->auxiliary_reserve_w,
        .commissioned = true, /* reached only via MODE_COMMISSIONED + calibrated + run gate */
    };
    out->backend = (bridge_backend_t){apply_cycle, set_request, inhibit, b};
    out->sample = sample;
    out->frequency = frequency;
    out->context = b;
    /* burst stays zero-initialised: burst_enabled = false */
    return N21_INIT_BIND;
}

bool n21_set_pan_model(n21_binding_t *b, float w)
{
    if (!b || !isfinite(w) || w < 0) return false;
    lock(b);
    b->pan_model_w = fminf(w, b->cfg.max_power_w);
    unlock(b);
    return true;
}

bool n21_set_thermal_tank_limit(n21_binding_t *b, bool limited, float a)
{
    if (!b || (limited && !(isfinite(a) && a >= TANK_CEILING_MIN_A))) return false;
    lock(b);
    b->thermal_limited = limited;
    b->thermal_limit_a = limited ? a : 0.0f;
    unlock(b);
    return true;
}

bool n21_set_aux_allowance(n21_binding_t *b, float a)
{
    if (!b) return false;
    uint64_t now = b->ops.now_us ? now_us(b) : 0;
    lock(b);
    b->aux_set_a = a;
    b->aux_set_us = now;
    b->have_aux = b->ops.now_us != NULL;
    unlock(b);
    return true;
}

bool n21_request_interlock_reset(n21_binding_t *b, bool confirmed)
{
    if (!b || !b->initialized || !confirmed || b->pads_live || b->gate_on || b->bench_active ||
        b->fault != N21_FAULT_NONE)
        return false;
    n21_status_rb_t s;
    if (!status(b, &s) || s.permit || s.bus_fault || !s.rail_ok || !s.sup_run_ok) return false;
    uint64_t now = now_us(b);
    if (b->have_reset && now - b->last_reset_us < RESET_MIN_INTERVAL_US) return false;
    b->have_reset = true;
    b->last_reset_us = now;
    return b->ops.interlock_reset_pulse(b->ops.ctx);
}

void n21_telemetry(n21_binding_t *b, n21_telemetry_t *t)
{
    if (!b || !t) return;
    lock(b);
    *t = b->tm;
    t->fault = b->fault;
    t->pads_live = b->pads_live;
    t->gate_on = b->gate_on;
    t->armed_line = b->armed_line;
    t->bench_active = b->bench_active;
    t->freq_hz = b->cycle_hz;
    t->freq_target_hz = b->tf.f_hz;
    t->floor_hz = b->tf.floor_hz;
    t->f_res_hz = b->tf.f_res_hz;
    t->q = b->tf.q;
    t->ceiling_eff_a = b->tf.ceiling_eff_a;
    t->pan_present = b->tf.pan_present;
    t->freq_reason = b->tf.reason;
    unlock(b);
}

bool n21_bench_start(n21_binding_t *b, uint32_t ms, bool confirmed)
{
    if (!b || !b->initialized || b->mode != N21_MODE_BENCH || !confirmed || b->bench_active ||
        b->fault != N21_FAULT_NONE || !b->programmed || ms == 0 || ms > b->cfg.bench_max_ms)
        return false;
    n21_status_rb_t s;
    if (!status(b, &s)) return false;
    /* PERMIT high with a faulted source means the interlock itself is suspect. */
    if (s.permit && (s.bus_fault || !s.rail_ok || !s.sup_run_ok)) return false;
    if (!b->ops.pwm_outputs(b->ops.ctx, true)) { pads_off(b); latch(b, N21_FAULT_HW); return false; }
    b->pads_live = true;
    if (b->ops.run_gate) {
        if (!b->ops.run_gate(b->ops.ctx, true)) { pads_off(b); latch(b, N21_FAULT_HW); return false; }
        b->gate_on = true;
    }
    b->bench_until_us = now_us(b) + (uint64_t)ms * 1000u;
    b->bench_active = true;
    return true;
}

void n21_bench_stop(n21_binding_t *b)
{
    if (!b) return;
    pads_off(b);
    b->bench_active = false;
}

bool n21_bench_poll(n21_binding_t *b)
{
    if (!b || !b->bench_active) return false;
    uint64_t now = now_us(b);
    n21_status_rb_t s;
    bool ok = status(b, &s);
    bridge_feedback_t f;
    capture(b, now, &s, &f);
    if (!ok) latch(b, N21_FAULT_HW);
    else if (!n21_capture_matches(&b->cycle, &f)) latch(b, N21_FAULT_PWM);
    bool fault = b->fault != N21_FAULT_NONE || (s.permit && s.bus_fault) || !sample_fresh(b, now);
    if (fault || now >= b->bench_until_us) {
        n21_bench_stop(b);
        return false;
    }
    return true;
}
