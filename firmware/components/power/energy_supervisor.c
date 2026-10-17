#include "energy_supervisor.h"
#include <math.h>
#include <string.h>
static void enter(energy_supervisor_t *s, energy_state_t state, uint32_t now)
{
    s->state = state;
    s->entered_ms = now;
}
static void trip(energy_supervisor_t *s, energy_fault_t fault, uint32_t now)
{
    if (s->state != ENERGY_FAULT) {
        s->fault = fault;
        s->lockout_ms = now;
    }
    enter(s, ENERGY_FAULT, now);
    s->out = (energy_outputs_t){
        0
    };
    s->start_released = false;
}
energy_config_t energy_study_config(void)
{
    return (energy_config_t){
        .precharge_ms = 298,.bypass_close_ms = 50,
            .proof_ms = 96,.attempt_ms = 446,.rail_ms = 2000,.retry_ms = 60000,
            .discharge_stable_ms = 1000,.sample_max_age_ms = 20,
            .bus_max_v = 250,.catch_max_v = 250,.tank_max_v = 2000,.inlet_max_a = 15
    };
}
void energy_supervisor_init(energy_supervisor_t *s, const energy_config_t *c, uint32_t now)
{
    if (!s)
        return;
    memset(s, 0, sizeof(*s));
    if (c)
        s->cfg = *c;
    s->entered_ms = s->lockout_ms = s->previous_ms = now;
    s->configured = c && c->commissioned && c->precharge_ms && c->precharge_ms <= 298 &&
        c->bypass_close_ms && c->bypass_close_ms <= 50 && c->proof_ms >= 50 && c->proof_ms <= 96 &&
        c->attempt_ms && c->attempt_ms <= 446 && c->rail_ms && c->rail_ms <= 2000 && c->retry_ms >= 60000 &&
        c->discharge_stable_ms >= 1000 && c->sample_max_age_ms && c->sample_max_age_ms <= 20 &&
        isfinite(c->bus_max_v) && c->bus_max_v > 30 &&
        isfinite(c->catch_max_v) && c->catch_max_v > 30 &&
        isfinite(c->tank_max_v) && c->tank_max_v > 30 &&
        isfinite(c->inlet_max_a) && c->inlet_max_a > 0 && c->inlet_max_a <= 15;
    if (!s->configured)
        trip(s, ENERGY_CONFIG, now);
}
void energy_supervisor_step(energy_supervisor_t *s, const energy_inputs_t *i)
{
    if (!s)
        return;
    if (!i) {
        trip(s, ENERGY_BAD_SAMPLE, s->previous_ms);
        return;
    }
    s->out = (energy_outputs_t){
        0
    };
    bool start_edge = i->start && s->start_released;
    bool reset_edge = i->reset && s->reset_released;
    s->start_released = !i->start;
    s->reset_released = !i->reset;
    bool values = isfinite(i->bus_v) && i->bus_v >= 0 &&
    isfinite(i->catch_v) && i->catch_v >= 0 &&
    isfinite(i->tank_abs_v) && i->tank_abs_v >= 0 &&
    isfinite(i->line_rms_v) && i->line_rms_v >= 0 &&
    isfinite(i->inlet_rms_a) && i->inlet_rms_a >= 0;
    bool fresh = (uint32_t)(i->now_ms - i->sampled_ms) <= s->cfg.sample_max_age_ms;
    bool clock_ok = (uint32_t)(i->now_ms - s->previous_ms) < UINT32_C(0x80000000);
    s->previous_ms = i->now_ms;
    bool healthy = s->configured && values && fresh && clock_ok && i->sensors_valid &&
    i->aux_ok && i->hardware_ok && i->stop_ok;
    bool released = i->k1_released && i->k2_released && i->kb_released;
    bool discharged = healthy && released && i->bus_v < 30 &&
    i->catch_v < 30 && i->tank_abs_v < 30;
    if (!discharged)
        s->safe_timing = false;
    else if (!s->safe_timing) {
        s->safe_timing = true;
        s->safe_since_ms = i->now_ms;
    }
    bool cold = discharged && i->resistor_cool && i->receiver_ok &&
    (uint32_t)(i->now_ms - s->safe_since_ms) >= s->cfg.discharge_stable_ms &&
    (uint32_t)(i->now_ms - s->lockout_ms) >= s->cfg.retry_ms;
    bool reset_state = s->state == ENERGY_OFF || s->state == ENERGY_FAULT;
    if (!cold || !reset_state || i->start)
        s->reset_armed = false;
    else if (!i->reset)
        s->reset_armed = true;
    /* Arm before a physical RESET edge. A held switch must not generate the
     * hardware latch clock when eligibility eventually becomes true. */
    s->out.reset_ok = cold && reset_state && s->reset_armed && !i->start;
    if (s->state == ENERGY_FAULT) {
        if (reset_edge && cold) {
            s->fault = ENERGY_OK;
            enter(s, ENERGY_OFF, i->now_ms);
        }
        return;                 /* RESET never processes START or energizes in this call. */
    }
    if (!healthy) {
        trip(s, !i->stop_ok ? ENERGY_STOP : ENERGY_BAD_SAMPLE, i->now_ms);
        return;
    }
    if (i->bus_v >= s->cfg.bus_max_v || i->catch_v >= s->cfg.catch_max_v ||
        i->tank_abs_v >= s->cfg.tank_max_v || i->inlet_rms_a > s->cfg.inlet_max_a) {
        trip(s, ENERGY_LIMIT, i->now_ms);
        return;
    }
    bool line_ok = i->line_rms_v >= 100 && i->line_rms_v <= 140;
    if (s->state >= ENERGY_PRECHARGE && s->state <= ENERGY_RUN && !i->hardware_latch_ok) {
        trip(s, ENERGY_CONTACT, i->now_ms);
        return;
    }
    if (s->state >= ENERGY_PRECHARGE && s->state <= ENERGY_RUN &&
        (!line_ok || !i->resistor_cool || !i->receiver_ok)) {
        trip(s, ENERGY_LIMIT, i->now_ms);
        return;
    }
    uint32_t elapsed = i->now_ms - s->entered_ms;
    if (s->state >= ENERGY_PRECHARGE && s->state <= ENERGY_BYPASS_PROVE &&
        (uint32_t)(i->now_ms - s->attempt_ms) >= s->cfg.attempt_ms) {
        trip(s, ENERGY_TIMEOUT, i->now_ms);
        return;
    }
    if (s->state >= ENERGY_RAIL_QUALIFY && s->state <= ENERGY_RUN &&
        !i->bypass_closed_electrically) {
        trip(s, ENERGY_CONTACT, i->now_ms);
        return;
    }
    if (s->state >= ENERGY_READY && s->state <= ENERGY_RUN &&
        (!i->rails_ok || i->bus_fault || !i->interlock_ok || !i->controller_alive)) {
        trip(s, ENERGY_RAIL, i->now_ms);
        return;
    }
    if (s->state >= ENERGY_READY && s->state <= ENERGY_RUN && !i->catch_charge_proven) {
        trip(s, ENERGY_LIMIT, i->now_ms);
        return;
    }
    if (i->off_request && s->state >= ENERGY_PRECHARGE && s->state <= ENERGY_RUN) {
        s->lockout_ms = i->now_ms;
        s->start_released = false;
        enter(s, ENERGY_DISCHARGE, i->now_ms);
        return;
    }
    switch (s->state) {
    case ENERGY_OFF:
        if (start_edge && !i->reset && i->hardware_latch_ok && cold && line_ok &&
            i->valid_line_cycles >= 2 && i->manual_post_ok &&
            i->manual_post_serial && i->manual_post_serial != s->used_post_serial) {
            s->used_post_serial = i->manual_post_serial;
            s->attempt_ms = i->now_ms;
            enter(s, ENERGY_PRECHARGE, i->now_ms);
        }
        break;
    case ENERGY_PRECHARGE:
        if (elapsed >= s->cfg.precharge_ms)
            trip(s, ENERGY_TIMEOUT, i->now_ms);
        else if (elapsed >= 50 && (i->k1_released || i->k2_released))
            trip(s, ENERGY_CONTACT, i->now_ms);
        else if (!i->kb_released)
            trip(s, ENERGY_CONTACT, i->now_ms);
        else if (i->precharge_complete)
            enter(s, ENERGY_BYPASS_CLOSE, i->now_ms);
        break;
    case ENERGY_BYPASS_CLOSE:
        if (elapsed >= s->cfg.bypass_close_ms)
            trip(s, ENERGY_TIMEOUT, i->now_ms);
        else if (i->bypass_closed_electrically) {
            s->proof_timing = false;
            enter(s, ENERGY_BYPASS_PROVE, i->now_ms);
        }
        break;
    case ENERGY_BYPASS_PROVE:
        if (i->proof_current_valid && !s->proof_timing) {
            s->proof_timing = true;
            s->proof_since_ms = i->now_ms;
        }
        if (!i->bypass_closed_electrically)
            trip(s, ENERGY_CONTACT, i->now_ms);
        else if (s->proof_timing && !i->proof_current_valid)
            trip(s, ENERGY_CONTACT, i->now_ms);
        else if (elapsed >= s->cfg.proof_ms)
            trip(s, ENERGY_TIMEOUT, i->now_ms);
        else if (i->proof_current_valid && s->proof_timing &&
                 (uint32_t)(i->now_ms - s->proof_since_ms) >= 50)
            enter(s, ENERGY_RAIL_QUALIFY, i->now_ms);
        break;
    case ENERGY_RAIL_QUALIFY:
        if (elapsed >= s->cfg.rail_ms)
            trip(s, ENERGY_TIMEOUT, i->now_ms);
        else if (i->rails_ok && !i->bus_fault && i->interlock_ok && i->controller_alive &&
                 i->catch_charge_proven)
            enter(s, ENERGY_READY, i->now_ms);
        break;
    case ENERGY_READY:
        if (i->heat_request && i->pwm_qualified)
            enter(s, ENERGY_RUN, i->now_ms);
        break;
    case ENERGY_RUN:
        if (!i->pwm_qualified)
            trip(s, ENERGY_PWM, i->now_ms);
        else if (!i->heat_request)
            enter(s, ENERGY_READY, i->now_ms);
        break;
    case ENERGY_DISCHARGE:
        if (cold)
            enter(s, ENERGY_OFF, i->now_ms);
        break;
    case ENERGY_FAULT:
        break;
    }
    if (s->state >= ENERGY_PRECHARGE && s->state <= ENERGY_RUN)
        s->out.k1 = s->out.k2 = true;
    if (s->state >= ENERGY_BYPASS_CLOSE && s->state <= ENERGY_RUN)
        s->out.kb = true;
    s->out.kt = s->state == ENERGY_BYPASS_PROVE;
    s->out.sup_run_ok = s->state == ENERGY_RUN && i->pwm_qualified;
}
