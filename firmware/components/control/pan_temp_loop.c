/**
 * @file pan_temp_loop.c
 * @brief sensor-r3 C1 pan-temperature loop composition (see header).
 */

#include "pan_temp_loop.h"

#include <stddef.h>
#include <string.h>

void ptl_default_params(ptl_params_t *p)
{
    if (p == NULL) {
        return;
    }
    pte_default_params(&p->est);
    pg_default_params(&p->pg);
    prp_default_params(&p->pid);
    cc_default_params(&p->cc);
    psg_default_params(&p->guard);
    p->cc.decay_tau_s = p->est.c_cap_j_per_k / p->est.g_leak_w_per_k;
    p->detector_enabled = true;
    p->identify_gain = true;
    p->fixed_gain_k_per_j = 1.0e-3f;
    p->approach_margin_k = 2.0f;
    p->new_phase_sp_step_k = 5.0f;
}

bool ptl_init(ptl_t *l, const ptl_params_t *p, float t0_c)
{
    if (l == NULL || p == NULL) {
        return false;
    }
    memset(l, 0, sizeof(*l));
    l->p = *p;
    return pte_init(&l->est, &p->est, t0_c) && pg_init(&l->pg, &p->pg) && prp_init(&l->pid, &p->pid) &&
           cc_init(&l->cc, &p->cc) && psg_init(&l->guard, &p->guard);
}

void ptl_step(ptl_t *l, const ptl_input_t *in, ptl_output_t *out)
{
    const ptl_params_t *p = &l->p;
    psg_output_t g;
    const psg_input_t gi = {
        .t_pt100_c = in->t_pt100_c,
        .t_rim_c = in->t_rim_c,
        .fresh = in->fresh,
        .spi_ok = in->spi_ok,
        .fault_status = in->fault_status,
        .heating = l->last_p_cmd > 0.0f,
    };

    memset(out, 0, sizeof(*out));
    psg_step(&l->guard, &gi, &g);

    const float t_hat = g.sample_valid ? pte_step(&l->est, in->t_pt100_c, in->t_rim_c)
                                       : pte_predict(&l->est, in->t_rim_c);
    const float sp = in->setpoint_c;

    if (!l->started) {
        l->started = true;
        l->first_phase_open = true;
        l->ident_phase_open = true;
        l->last_sp = sp;
        pg_begin_phase(&l->pg, true);
    }
    if (!l->first_phase_open && sp >= l->last_sp + p->new_phase_sp_step_k && l->settled_prev) {
        /* A later ramp is identified only if it starts from a settled hold:
         * a pan still recovering from a load (food) is not a clean ramp. */
        pg_begin_phase(&l->pg, false);
        l->ident_phase_open = true;
    }
    if (sp < l->last_sp || sp >= l->last_sp + p->new_phase_sp_step_k) {
        l->last_sp = sp;
    }

    const bool faulted = g.verdict != PSG_OK;
    const bool approaching = t_hat < sp - p->approach_margin_k;
    if (!approaching) {
        l->first_phase_open = false;
        l->ident_phase_open = false;
    }
    const bool ramping = sp > l->pid.sp_eff || !l->pid.started;
    const bool saturated = l->last_p_cmd >= 0.999f * p->pid.p_max_w;
    const bool cc_normal = !p->detector_enabled || l->cc.state == CC_NORMAL;
    const bool gate = l->ident_phase_open && approaching && (ramping || saturated) && cc_normal && !faulted;

    pg_update(&l->pg, t_hat, in->power_applied_w, in->power_source, gate);
    const float a = p->identify_gain ? pg_gain(&l->pg) : p->fixed_gain_k_per_j;

    float p_cmd = prp_step(&l->pid, sp, t_hat, a);
    out->p_pid_w = p_cmd;

    if (g.suspect) {
        cc_request_probe(&l->cc);
    }
    if (p->detector_enabled) {
        cc_output_t co;
        cc_step(&l->cc, t_hat, in->t_pt100_c, in->power_applied_w, a, in->t_rim_c, &co);
        if (co.reset_integrator) {
            prp_reset_integrator(&l->pid);
        }
        if (co.override) {
            p_cmd = co.p_override_w;
        }
        if (co.event != CC_EVT_NONE) {
            /* Any D1 activity ends the identification phase: a disturbance
             * (food, lifted pan) must not be regressed as plant gain. */
            l->ident_phase_open = false;
        }
        if (co.event == CC_EVT_LOST) {
            l->lost_latched_ui = true;
        } else if (co.event == CC_EVT_RESTORED) {
            l->lost_latched_ui = false;
        }
        out->cc_state = co.state;
        out->cc_event = co.event;
    } else {
        out->cc_state = CC_NORMAL;
        out->cc_event = CC_EVT_NONE;
    }

    /* Power authority: never chase a cold reading. */
    if (faulted) {
        p_cmd = 0.0f;
        prp_reset_integrator(&l->pid);
    }
    l->last_p_cmd = p_cmd;
    l->settled_prev = !faulted && out->cc_state == CC_NORMAL && t_hat >= sp - p->approach_margin_k &&
                      t_hat <= sp + p->approach_margin_k;

    out->t_hat_c = t_hat;
    out->p_cmd_w = p_cmd;
    out->a_used_k_per_j = a;
    out->a_valid = pg_valid(&l->pg);
    out->a_source_mask = pg_source_mask(&l->pg);
    out->sp_eff_c = prp_sp_eff(&l->pid);
    out->fault = g.verdict;
    out->diag = g.diag;
    out->ui_pan_must_touch = l->lost_latched_ui;
}
