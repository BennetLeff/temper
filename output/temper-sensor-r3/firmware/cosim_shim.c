/*
 * Host-only ctypes shim around the firmware's pan_temp_loop (and the
 * estimator / contact check on their own), for the sensor-r3 C-in-the-loop
 * co-simulation. Built with cc by build_lib.sh; not part of the firmware.
 *
 * Parameters are set by name before sim_start(), so Python never mirrors C
 * struct layouts.
 */
#include <stdlib.h>
#include <string.h>

#include "pan_supervisor.h"
#include "pan_temp_loop.h"

typedef struct {
    ptl_params_t p;
    ptl_t loop;
    pte_t est;
    cc_t cc;
    psup_params_t sp;
    psup_t sup;
    ptl_output_t last;
} sim_t;

void *sim_new(void)
{
    sim_t *s = (sim_t *)calloc(1, sizeof(sim_t));
    if (s != NULL) {
        ptl_default_params(&s->p);
        psup_default_params(&s->sp);
    }
    return s;
}

void sim_free(void *h) { free(h); }

#define F(name, field) if (strcmp(key, name) == 0) { field = (float)v; return 0; }
#define U(name, stmt) if (strcmp(key, name) == 0) { stmt; return 0; }

int sim_set(void *h, const char *key, double v)
{
    ptl_params_t *p = &((sim_t *)h)->p;
    F("c_cap", p->est.c_cap_j_per_k)
    F("c_el", p->est.c_el_j_per_k)
    F("g_bond", p->est.g_bond_w_per_k)
    F("g_leak", p->est.g_leak_w_per_k)
    F("area", p->est.contact_area_m2)
    F("h_nom", p->est.h_nom_w_per_m2k)
    F("sigma", p->est.sigma_k)
    F("a0", p->pg.a0_k_per_j)
    F("pg_lag_s", p->pg.lag_s)
    F("pg_k_loss", p->pg.k_loss_w_per_k)
    F("pg_forget_later", p->pg.forget_later)
    F("pg_rise_min", p->pg.rise_min_k)
    U("pg_window", p->pg.window_blocks = (uint16_t)v)
    U("pg_later", p->pg.update_later_ramps = (v != 0.0))
    F("probe_off", p->cc.probe_off_s)
    F("probe_on", p->cc.probe_on_s)
    F("probe_p", p->cc.probe_p_frac)
    F("probe_lag", p->cc.probe_lag_s)
    F("retry_off", p->cc.retry_off_s)
    F("retry_on", p->cc.retry_on_s)
    F("retry_p", p->cc.retry_p_frac)
    F("retry_lag", p->cc.retry_lag_s)
    F("decay_tau", p->cc.decay_tau_s)
    F("trig_hold", p->cc.trig_hold_s)
    F("retry_s", p->cc.retry_s)
    F("decay_min_change", p->cc.decay_min_change_k)
    U("retry_decay_only", p->cc.retry_decay_only = (v != 0.0))
    F("probe_min_sigma", p->cc.probe_min_sigma)
    U("detector", p->detector_enabled = (v != 0.0))
    U("identify", p->identify_gain = (v != 0.0))
    F("fixed_a", p->fixed_gain_k_per_j)
    F("xcheck_hold", p->guard.xcheck_hold_s)
    F("pg_later_rise_min", p->pg.later_rise_min_k)
    U("pg_later_hold_blocks", p->pg.later_hold_blocks = (uint16_t)v)
    F("pg_later_hold_band", p->pg.later_hold_band_k)
    F("pg_later_max_rel_step", p->pg.later_max_rel_step)
    F("pg_later_max_rel_down", p->pg.later_max_rel_down)
    F("pg_later_cov_floor", p->pg.later_cov_floor_rel)
    U("csw", p->csw.enable = (v != 0.0))
    U("csw_up", p->csw.up_enable = (v != 0.0))
    F("csw_dv_trig", p->csw.dv_trig_k_per_s)
    F("csw_h_floor", p->csw.h_floor_w_per_m2k)
    U("lpg", p->pid.lpg_enable = (v != 0.0))
    U("lpg_budget", p->pid.lpg_budget = (v != 0.0))
    {
        psup_params_t *q = &((sim_t *)h)->sp;
        F("sup_margin", q->margin_k)
        F("sup_rise_hold", q->rise_hold_s)
        F("sup_rise_window", q->rise_window_s)
        F("sup_rise_min", q->rise_min_k)
        F("sup_disobey_a", q->disobey_current_a)
        F("sup_disobey_excess_a", q->disobey_excess_a)
        F("sup_cmd_v_min", q->cmd_v_min)
        F("sup_rate_max", q->rate_max_k_per_s)
        U("sup_rate_blocks", q->rate_blocks_required = (uint8_t)v)
    }
    return -1;
}

int sim_start(void *h, double t0)
{
    sim_t *s = (sim_t *)h;
    return ptl_init(&s->loop, &s->p, (float)t0) ? 0 : -1;
}

/* out: t_hat, p_cmd, p_pid, a, a_valid, sp_eff, cc_state, cc_event, fault, diag, ui, src_mask,
 *      last probe d (K/kJ), d_exp (K/kJ), free-decay rms (K), fitted decay change (K) */
void sim_step(void *h, double y, double rim, double sp, double p_applied, int src, int fresh, int spi_ok,
              int fault_status, double *out)
{
    sim_t *s = (sim_t *)h;
    const ptl_input_t in = {
        .t_pt100_c = (float)y,
        .t_rim_c = (float)rim,
        .fresh = fresh != 0,
        .spi_ok = spi_ok != 0,
        .fault_status = (uint8_t)fault_status,
        .setpoint_c = (float)sp,
        .power_applied_w = (float)p_applied,
        .power_source = src ? PG_POWER_ESTIMATED : PG_POWER_MEASURED,
    };
    ptl_output_t o;
    ptl_step(&s->loop, &in, &o);
    s->last = o;
    out[0] = o.t_hat_c;
    out[1] = o.p_cmd_w;
    out[2] = o.p_pid_w;
    out[3] = o.a_used_k_per_j;
    out[4] = o.a_valid;
    out[5] = o.sp_eff_c;
    out[6] = o.cc_state;
    out[7] = o.cc_event;
    out[8] = o.fault;
    out[9] = o.diag;
    out[10] = o.ui_pan_must_touch;
    out[11] = o.a_source_mask;
    out[12] = s->loop.cc.last_d;
    out[13] = s->loop.cc.last_d_exp;
    out[14] = s->loop.cc.last_decay_rms;
    out[15] = s->loop.cc.last_decay_change;
}

/* Contact-shift window / latent-plateau guard after the last sim_step:
 * out = event, window open, h_model (W/m2K), lpg active, allow, steady,
 * windows, accepts, escalations. */
void sim_cs_stats(void *h, double *out)
{
    const sim_t *s = (const sim_t *)h;
    out[0] = (double)s->last.cs_event;
    out[1] = s->last.cs_window;
    out[2] = s->last.h_model_w_per_m2k;
    out[3] = s->last.lpg_active;
    out[4] = s->loop.cs_allow_last;
    out[5] = s->loop.cs_steady_last;
    out[6] = (double)s->loop.csw.windows;
    out[7] = (double)s->loop.csw.accepts;
    out[8] = (double)s->loop.csw.escalations;
}

/* Ask D1 for a probe now (co-sim "probe on intact contact" cases). */
void sim_request_probe(void *h)
{
    cc_request_probe(&((sim_t *)h)->loop.cc);
}

/* Estimator alone, with the params set by sim_set. */
int est_start(void *h, double t0)
{
    sim_t *s = (sim_t *)h;
    return pte_init(&s->est, &s->p.est, (float)t0) ? 0 : -1;
}

double est_step(void *h, double y, double rim)
{
    return pte_step(&((sim_t *)h)->est, (float)y, (float)rim);
}

/* ---- runaway supervisor (components/control/pan_supervisor.c) ---------- */
int sup_start(void *h)
{
    sim_t *s = (sim_t *)h;
    return psup_init(&s->sup, &s->sp) ? 0 : -1;
}

int sup_rate(void *h, double t_raw, unsigned int now_ms)
{
    return psup_rate_sample(&((sim_t *)h)->sup, (float)t_raw, (uint32_t)now_ms) ? 1 : 0;
}

/* out: force_zero, latch, rise_k */
void sup_step(void *h, double t_hat, double t_raw, double sp, double p_cmd, double i_bus, int valid, double *out)
{
    const psup_input_t in = {
        .t_hat_c = (float)t_hat,
        .t_raw_c = (float)t_raw,
        .setpoint_c = (float)sp,
        .p_cmd_w = (float)p_cmd,
        .bus_current_a = (float)i_bus,
        .current_valid = valid != 0,
    };
    psup_output_t o;
    psup_step(&((sim_t *)h)->sup, &in, &o);
    out[0] = o.force_zero;
    out[1] = o.latch;
    out[2] = o.rise_k;
}

/* Plant-gain diagnostics: out = later_updates, rejected, updates, theta,
 * last later-phase estimate, later phase open, hold power P_0 (W). */
void sim_pg_stats(void *h, double *out)
{
    const pg_t *g = &((sim_t *)h)->loop.pg;
    out[0] = (double)g->later_updates;
    out[1] = (double)g->rejected;
    out[2] = (double)g->updates;
    out[3] = (double)g->theta;
    out[4] = (double)g->last_window_a;
    out[5] = (double)g->later_open;
    out[6] = (double)g->p_base_w;
}
