#include "fullbridge_adapter.h"
#include <math.h>
#include <string.h>
bool bridge_plan_cycle(uint32_t hz, uint32_t freq, uint32_t ns, float phase, bridge_cycle_t *c)
{
    if (!c || hz == 0 || freq < 35000 || freq > 60000 || !isfinite(phase) || phase < 0 || phase > 1 || ns == 0)
        return false;
    uint32_t period = hz / freq;
    /* Even periods keep both polarities exactly balanced. */
    period &= ~UINT32_C(1);
    if ((uint64_t)hz > UINT64_C(60000) * period)
        period += 2;
    if ((uint64_t)hz < UINT64_C(35000) * period ||
        (uint64_t)hz > UINT64_C(60000) * period)
        return false;
    uint64_t dead = ((uint64_t)hz * ns + 999999999) / 1000000000;
    if (period < 4 || dead == 0 || dead >= period / 4)
        return false;
    uint32_t half = period / 2, shift = (uint32_t)lroundf(phase * half);
    *c = (bridge_cycle_t){
        .period = period,.dead_ticks = (uint32_t)dead
    };
    c->pulse[0] = (bridge_pulse_t){
        (uint32_t)dead, half - (uint32_t)dead
    };
    c->pulse[1] = (bridge_pulse_t){
        half + (uint32_t)dead, half - (uint32_t)dead
    };
    c->pulse[2] = (bridge_pulse_t){
        (shift + (uint32_t)dead) % period, half - (uint32_t)dead
    };
    c->pulse[3] = (bridge_pulse_t){
        (shift + half + (uint32_t)dead) % period, half - (uint32_t)dead
    };
    return true;
}
bool bridge_output_at(const bridge_cycle_t *c, unsigned pin, uint32_t tick)
{
    if (!c || !c->period || pin >= 4)
        return false;
    return (tick % c->period + c->period - c->pulse[pin].rise) % c->period < c->pulse[pin].width;
}
void fullbridge_stop(fullbridge_adapter_t *b)
{
    if (!b)
        return;
    if (b->backend.inhibit)
        b->backend.inhibit(b->backend.context);
    b->armed = false;
    b->conductance_s = 0;
    b->requested_w = 0;
}
static bool fail(fullbridge_adapter_t *b){
    fullbridge_stop(b);
    b->tripped = true;
    return false;
}
bool fullbridge_init(fullbridge_adapter_t *b, const bridge_config_t *c, const bridge_backend_t *ops)
{
    if (!b)
        return false;
    memset(b, 0, sizeof(*b));
    if (ops)
        b->backend = *ops;
    fullbridge_stop(b);
    if (!c || !ops || !ops->inhibit || !ops->set_request || !ops->apply_cycle ||
        !c->commissioned || !c->scope_record_id ||
        (c->feedback_kind!=BRIDGE_FEEDBACK_ONCHIP_REGISTER && c->feedback_kind!=BRIDGE_FEEDBACK_BENCH_CAPTURE) || !c->capture_age_us || c->capture_age_us > 1000 ||
        !isfinite(c->max_power_w) || c->max_power_w <= 0 ||
        !isfinite(c->inlet_target_a) || c->inlet_target_a <= 0 || c->inlet_target_a > 13.5f ||
        !isfinite(c->auxiliary_reserve_w) || c->auxiliary_reserve_w < 0 ||
        !bridge_plan_cycle(c->timer_hz, c->frequency_hz, c->input_deadtime_ns, 0, &b->cycle))
        return fail(b);
    b->cfg = *c;
    /* Zero differential phase, PERMIT inhibited: qualify the selected feedback kind before RUN. */
    if (!ops->set_request(ops->context, false) || !ops->apply_cycle(ops->context, &b->cycle))
        return fail(b);
    b->initialized = true;
    return true;
}
bool fullbridge_request(fullbridge_adapter_t *b, float w)
{
    if (!b || !b->initialized || b->tripped)
        return false;
    if (!isfinite(w) || w < 0 || w > b->cfg.max_power_w)
        return fail(b);
    b->requested_w = w;
    if (w == 0) {
        b->conductance_s = 0;
        b->armed = false;
        if (!b->backend.set_request(b->backend.context, false))
            return fail(b);
    }
    return true;
}
bool fullbridge_line_cycle(fullbridge_adapter_t *b, uint32_t now, float v, float current, float pan_w)
{
    if (!b || !b->initialized || b->tripped)
        return false;
    if (!isfinite(v) || v < 100 || v > 140 || !isfinite(current) || current < 0 ||
        !isfinite(pan_w) || pan_w < 0)
        return fail(b);
    uint32_t elapsed = now - b->last_line_us;
    if (!b->have_line) {
        b->have_line = true;
        b->last_line_us = now;
        b->conductance_s = 0;
        return true;
    }
    if (elapsed < 14000 || elapsed > 22000)
        return fail(b);
    b->last_line_us = now;
    float dt = elapsed * 1e-6f;
    float budget = fmaxf(0, fminf(b->requested_w, fminf(pan_w, v * b->cfg.inlet_target_a - b->cfg.auxiliary_reserve_w)));
    float target = budget / (v * v);
    if (current > b->cfg.inlet_target_a) {
        /* Measured current already includes AUX; never subtract it twice. */
        target = fminf(target, b->conductance_s * b->cfg.inlet_target_a / current);
    }
    if (current > 15)
        return fail(b);
    if (target <= b->conductance_s)
        b->conductance_s = target;
    else {
        float alpha = -expm1f(-6.28318530718f * 2 * dt);
        b->conductance_s += fminf(alpha * (target - b->conductance_s), 2000 * dt / (v * v));
    }
    return true;
}
bool fullbridge_apply(fullbridge_adapter_t *b, uint32_t now, const bridge_feedback_t *f, float phase)
{
    if (!b || !b->initialized || b->tripped)
        return false;
    if (!f || f->kind!=b->cfg.feedback_kind || !f->rails_ok || !f->interlock_ok || f->bus_fault ||
        (uint32_t)(now - f->sampled_us) > b->cfg.capture_age_us ||
        !b->have_line || (uint32_t)(now - b->last_line_us) > 22000 ||
        !isfinite(phase) || phase < 0 || phase > 1)
        return fail(b);
    if (b->have_capture && (uint32_t)(f->serial - b->last_capture_serial) >= UINT32_C(0x80000000))
        return fail(b);
    /* Same capture may be consumed within its age, but cannot refresh age. */
    b->have_capture = true;
    b->last_capture_serial = f->serial;
    if(f->kind==BRIDGE_FEEDBACK_ONCHIP_REGISTER) {
        if(!f->onchip.coherent || !f->onchip.timer_advancing || !f->onchip.outputs_connected ||
           f->onchip.timer_hz!=b->cfg.timer_hz ||
           memcmp(&f->onchip.programmed_cycle,&b->cycle,sizeof b->cycle)) return fail(b);
    } else for (unsigned n = 0; n < 4; n++) {
        uint32_t tolerance = b->cycle.period / 100;
        if (!f->valid[n] || f->period[n] + tolerance < b->cycle.period ||
            f->period[n] > b->cycle.period + tolerance ||
            f->high_ticks[n] + 2 < b->cycle.pulse[n].width ||
            f->high_ticks[n] > b->cycle.pulse[n].width + 2)
            return fail(b);
        if (f->rise_ticks[n] >= b->cycle.period)
            return fail(b);
        uint32_t gap = (f->rise_ticks[n] + b->cycle.period - b->cycle.pulse[n].rise) % b->cycle.period;
        if (gap > 2 && gap < b->cycle.period - 2)
            return fail(b);
        if (f->nonoverlap_ticks[n] < b->cycle.dead_ticks ||
            f->nonoverlap_ticks[n] > b->cycle.dead_ticks + 2)
            return fail(b);
    }
    bool run = b->requested_w > 0 && b->conductance_s > 0;
    if (!run)
        phase = 0;
    /*
     * A dropped supervisor permission after running is a latched fault. During arming, request is
     * asserted with zero phase; supervisor may then grant it.
     */
    if (b->armed && !f->sup_run_ok)
        return fail(b);
    if (!f->sup_run_ok)
        phase = 0;
    if (!bridge_plan_cycle(b->cfg.timer_hz, b->cfg.frequency_hz, b->cfg.input_deadtime_ns, phase, &b->cycle) ||
        !b->backend.apply_cycle(b->backend.context, &b->cycle) ||
        !b->backend.set_request(b->backend.context, run))
        return fail(b);
    b->armed = run && f->sup_run_ok;
    return true;
}
