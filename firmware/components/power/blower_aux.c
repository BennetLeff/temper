#include "blower_aux.h"
#include <math.h>
#include <string.h>

blower_aux_cfg_t blower_aux_native21(void)
{
    return (blower_aux_cfg_t){
        /* IRM-20-SPEC 2025-11-21: 0.6 A typ. at 115 Vac each, at 108 V, rounded up (input_limits). */
        .base_a = 1.3f,
        /* C28: 140 k / 11.5 k FB, 56.2 k + 12.1 k injection, VFB 0.788-0.812 V, v3v3 high
         * 3.242-3.367 V, 0.1 % / 1 % resistors. Envelope: 12.3999 V at duty 0 and a slope of at
         * least 6.573 V per unit duty (test_blower_aux.c recomputes both over the 32 corners). */
        .vout_max_v = 12.40f, .vout_slope_min_v = 6.57f,
        /* Delta BFB1012VH-F00 spec p.1 (enclosure R33 study 10): 12 V, 2.70 A / 32.40 W maximum. */
        .v_rated_v = 12.0f, .p_rated_max_w = 32.4f, .fan_law_exp = 3.0f,
        .eta_buck = 0.90f,
        /* IRM-60-SPEC 2025-11-21 p.2, IRM-60-15: efficiency 89 % typ.; AC current 1.8 A typ. at
         * 115 Vac -> PF = 60 / 0.89 / (115 * 1.8). Low-line corner 108 V (DECISIONS 2026-10-08). */
        .ps3_eta = 0.89f, .ps3_pf = (60.0f / 0.89f) / (115.0f * 1.8f), .v_line_low_v = 108.0f,
        .idle_a = 0.05f, .margin = 0.15f,
        /* Schedule. rise: 0.4 A per 100 ms blower tick, which the binding spreads over halves at
         * aux_slew_a; lead 300 ms > one tick plus the binding's ramp of one tick's step (8 halves). */
        .rise_a_per_s = 4.0f, .urgent_a_per_s = 20.0f, .fall_a_per_s = 1.0f,
        .lead_ms = 300u, .release_ms = 1000u,
        .off_rpm = 300.0f, /* = thermal_mgmt.h BLOWER_STALL_RPM */
    };
}

static bool pos(float x) { return isfinite(x) && x > 0; }

bool blower_aux_config_ok(const blower_aux_cfg_t *c)
{
    return c && isfinite(c->base_a) && c->base_a >= 0 && pos(c->vout_max_v) &&
           pos(c->vout_slope_min_v) && c->vout_slope_min_v < c->vout_max_v &&
           pos(c->v_rated_v) && pos(c->p_rated_max_w) && isfinite(c->fan_law_exp) &&
           c->fan_law_exp >= 1.0f && c->fan_law_exp <= 3.0f &&
           pos(c->eta_buck) && c->eta_buck <= 1 && pos(c->ps3_eta) && c->ps3_eta <= 1 &&
           pos(c->ps3_pf) && c->ps3_pf <= 1 && pos(c->v_line_low_v) &&
           isfinite(c->idle_a) && c->idle_a >= 0 && isfinite(c->margin) && c->margin >= 0 &&
           pos(c->rise_a_per_s) && c->urgent_a_per_s >= c->rise_a_per_s && pos(c->fall_a_per_s) &&
           c->lead_ms >= 100u && c->lead_ms <= 5000u && c->release_ms <= 60000u &&
           pos(c->off_rpm) &&
           blower_aux_worst_a(c) < 5.0f; /* input_limits_config_ok's cap */
}

float blower_aux_vout_max_v(const blower_aux_cfg_t *c, float duty)
{
    if (!isfinite(duty) || duty < 0) duty = 0; /* unknown: full speed */
    if (duty > 1) duty = 1;
    return c->vout_max_v - c->vout_slope_min_v * duty;
}

float blower_aux_ps3_model_a(const blower_aux_cfg_t *c, float v)
{
    if (!isfinite(v) || v < 0) v = c->vout_max_v;
    float p_blower = c->p_rated_max_w * powf(v / c->v_rated_v, c->fan_law_exp);
    return p_blower / c->eta_buck / (c->ps3_eta * c->ps3_pf * c->v_line_low_v);
}

float blower_aux_worst_a(const blower_aux_cfg_t *c)
{
    return c->base_a + blower_aux_ps3_model_a(c, c->vout_max_v);
}

float blower_aux_level_a(const blower_aux_cfg_t *c, bool on, float duty)
{
    float worst = blower_aux_worst_a(c);
    if (!on) return fminf(worst, c->base_a + c->idle_a);
    if (!isfinite(duty) || duty <= 0 || duty > 1) return worst;
    float ps3 = (1 + c->margin) * blower_aux_ps3_model_a(c, blower_aux_vout_max_v(c, duty)) + c->idle_a;
    return fminf(worst, c->base_a + ps3);
}

void blower_aux_init(blower_aux_t *s, const blower_aux_cfg_t *c)
{
    memset(s, 0, sizeof *s);
    s->allowance_a = blower_aux_worst_a(c);
    s->on = true; /* reset: GPIO46 on its strap pull-down, 11.0-11.4 V */
    s->duty = 0;
}

blower_aux_out_t blower_aux_step(blower_aux_t *s, const blower_aux_cfg_t *c, const blower_aux_in_t *in,
                                 uint32_t now)
{
    float worst = blower_aux_worst_a(c);
    if (!s->primed) {
        s->primed = true;
        s->last_ms = now;
        s->rise_ms = now; /* the initial (worst-case) allowance counts from the first tick */
    }
    float dt = (float)(uint32_t)(now - s->last_ms) * 1e-3f;
    if (dt > 1.0f) dt = 1.0f;
    s->last_ms = now;

    bool duty_ok = isfinite(in->duty) && in->duty >= 0 && in->duty <= 1;
    bool unknown = !in->known || (in->on && !duty_ok);
    bool fast = in->urgent || unknown;
    /* Level of the commanded state, and the target: an off command counts only once the tach
     * shows the blower stopped (FAN_OFF took effect); until then the blower may be at full. */
    float cmd_level = unknown ? worst : blower_aux_level_a(c, in->on, in->duty);
    float target = cmd_level;
    if (!unknown && !in->on && !(isfinite(in->tach_rpm) && in->tach_rpm < c->off_rpm)) target = worst;

    if (target > s->allowance_a) {
        s->allowance_a = fminf(target, s->allowance_a + (fast ? c->urgent_a_per_s : c->rise_a_per_s) * dt);
        s->rise_ms = now;
        s->lower = false;
    } else if (target < s->allowance_a) {
        if (!s->lower) {
            s->lower = true;
            s->lower_since_ms = now;
        }
        if ((uint32_t)(now - s->lower_since_ms) >= c->release_ms)
            s->allowance_a = fmaxf(target, s->allowance_a - c->fall_a_per_s * dt);
    } else {
        s->lower = false;
    }

    /* The blower: a fault or an unknown state goes at once; a slow-down goes at once; a speed-up
     * waits until its level has been in force for lead_ms. */
    bool holding = false;
    float applied_level = blower_aux_level_a(c, s->on, s->duty);
    if (fast || cmd_level <= applied_level ||
        (cmd_level <= s->allowance_a && (uint32_t)(now - s->rise_ms) >= c->lead_ms)) {
        s->on = in->on;
        s->duty = in->on ? (duty_ok ? in->duty : 0.0f) : 0.0f; /* off: duty 0 (blower_ctrl) */
    } else {
        holding = true;
    }
    return (blower_aux_out_t){.on = s->on, .duty = s->duty, .allowance_a = s->allowance_a,
                              .target_a = target, .holding = holding};
}
