#include "input_limits.h"
#include "blower_aux.h"
#include <math.h>
input_limits_cfg_t input_limits_native21(void)
{
    /* est_error provisional until bench qualification; PS1 + PS2 from IRM-20-SPEC 2025-11-21
     * (0.6 A typ. at 115 Vac each) scaled to 108 V and rounded up (1.28 -> 1.3 A, the existing
     * basis); worst case adds PS3 at full blower (blower_aux.h, DECISIONS 16); tank ceiling: the
     * 22 A shipping default (2026-10-08 envelope; DECISIONS 10). The commissioned value replaces
     * it (Kconfig TEMPER_POWER_TANK_CEILING_DA via n21_config_set_tank_ceiling). */
    blower_aux_cfg_t b = blower_aux_native21();
    return (input_limits_cfg_t){ .eta_min = 0.93f, .est_error = 0.10f, .aux_min_a = b.base_a,
                                 .aux_max_a = blower_aux_worst_a(&b), .tank_limit_a = 22.0f };
}
bool input_limits_config_ok(const input_limits_cfg_t *c)
{
    return c && isfinite(c->eta_min) && c->eta_min >= 0.5f && c->eta_min <= 1.0f &&
           isfinite(c->est_error) && c->est_error >= 0 && c->est_error <= 0.5f &&
           isfinite(c->aux_min_a) && c->aux_min_a >= 0 &&
           isfinite(c->aux_max_a) && c->aux_max_a >= c->aux_min_a && c->aux_max_a < 5.0f &&
           isfinite(c->tank_limit_a) && c->tank_limit_a > 0 &&
           c->tank_limit_a <= 28.0f; /* stage-15 hardware sizing basis (DECISIONS 10) */
}
float input_limits_aux(const input_limits_cfg_t *c, float aux_a)
{
    return isfinite(aux_a) && aux_a >= c->aux_min_a && aux_a <= c->aux_max_a ? aux_a : c->aux_max_a;
}
float input_limits_aux_ramp(const input_limits_cfg_t *c, float now_a, float target_a, float max_up_a)
{
    float t = input_limits_aux(c, target_a), a = input_limits_aux(c, now_a);
    if (!(isfinite(max_up_a) && max_up_a > 0)) return t;
    return t > a ? fminf(t, a + max_up_a) : t;
}
bool input_limits_half_cycle(const input_limits_cfg_t *c, const input_sample_t *s, size_t n,
                             float line_rms_v, input_estimate_t *out)
{
    return input_limits_half_cycle_aux(c, s, n, line_rms_v, c ? c->aux_max_a : NAN, out);
}
bool input_limits_half_cycle_aux(const input_limits_cfg_t *c, const input_sample_t *s, size_t n,
                                 float line_rms_v, float aux_a, input_estimate_t *out)
{
    if (!input_limits_config_ok(c) || !s || !out || n < 8 ||
        !isfinite(line_rms_v) || line_rms_v < 100 || line_rms_v > 140)
        return false;
    const float k = 0.900316316f; /* 2*sqrt(2)/pi: RMS fundamental of a full-bridge square wave */
    bool weighted = false;
    for (size_t j = 0; j < n; j++)
        if (s[j].w != 0.0f) weighted = true;
    double p = 0, i2 = 0, wsum = 0;
    for (size_t j = 0; j < n; j++) {
        if (!isfinite(s[j].bus_v) || s[j].bus_v < 0 || s[j].bus_v > 220 ||
            !isfinite(s[j].tank_rms_a) || s[j].tank_rms_a < 0 || s[j].tank_rms_a > 100 ||
            !isfinite(s[j].cos_phi) || s[j].cos_phi < -1 || s[j].cos_phi > 1 ||
            !isfinite(s[j].w) || s[j].w < 0)
            return false;
        double w = weighted ? (double)s[j].w : 1.0;
        p += w * k * s[j].bus_v * s[j].tank_rms_a * s[j].cos_phi;
        i2 += w * s[j].tank_rms_a * s[j].tank_rms_a;
        wsum += w;
    }
    if (!(wsum > 0)) return false;
    /* Net regeneration does not reduce the inlet current bound below zero. */
    float p_inv = (float)fmax(0, p / wsum);
    out->p_inv_w = p_inv;
    out->p_in_w = p_inv / c->eta_min;
    out->i_ps_a = out->p_in_w / line_rms_v;
    out->inlet_bound_a = out->i_ps_a * (1 + c->est_error) + input_limits_aux(c, aux_a);
    out->tank_rms_a = (float)sqrt(i2 / wsum);
    /* For a given pan, power scales with tank current squared: the power that would put the
     * tank at its ceiling. With no tank current there is no evidence, so no ceiling (INFINITY). */
    out->tank_ceiling_w = out->tank_rms_a > 0.5f
        ? p_inv * (c->tank_limit_a / out->tank_rms_a) * (c->tank_limit_a / out->tank_rms_a)
        : INFINITY;
    return true;
}
