#include "input_limits.h"
#include <math.h>
input_limits_cfg_t input_limits_native21(void)
{
    /* est_error provisional until bench qualification; aux from IRM-20-SPEC 2025-11-21
     * (0.6 A typ. at 115 Vac each) scaled to 108 V; tank ceiling: the 22 A shipping default
     * (2026-10-08 envelope; DECISIONS 10). The commissioned value replaces it (Kconfig
     * TEMPER_POWER_TANK_CEILING_DA via n21_config_set_tank_ceiling). */
    return (input_limits_cfg_t){ .eta_min = 0.93f, .est_error = 0.10f, .aux_max_a = 1.3f, .tank_limit_a = 22.0f };
}
bool input_limits_config_ok(const input_limits_cfg_t *c)
{
    return c && isfinite(c->eta_min) && c->eta_min >= 0.5f && c->eta_min <= 1.0f &&
           isfinite(c->est_error) && c->est_error >= 0 && c->est_error <= 0.5f &&
           isfinite(c->aux_max_a) && c->aux_max_a >= 0 && c->aux_max_a < 5.0f &&
           isfinite(c->tank_limit_a) && c->tank_limit_a > 0 &&
           c->tank_limit_a <= 28.0f; /* stage-15 hardware sizing basis (DECISIONS 10) */
}
bool input_limits_half_cycle(const input_limits_cfg_t *c, const input_sample_t *s, size_t n,
                             float line_rms_v, input_estimate_t *out)
{
    if (!input_limits_config_ok(c) || !s || !out || n < 8 ||
        !isfinite(line_rms_v) || line_rms_v < 100 || line_rms_v > 140)
        return false;
    const float k = 0.900316316f; /* 2*sqrt(2)/pi: RMS fundamental of a full-bridge square wave */
    double p = 0, i2 = 0;
    for (size_t j = 0; j < n; j++) {
        if (!isfinite(s[j].bus_v) || s[j].bus_v < 0 || s[j].bus_v > 220 ||
            !isfinite(s[j].tank_rms_a) || s[j].tank_rms_a < 0 || s[j].tank_rms_a > 100 ||
            !isfinite(s[j].cos_phi) || s[j].cos_phi < -1 || s[j].cos_phi > 1)
            return false;
        p += (double)k * s[j].bus_v * s[j].tank_rms_a * s[j].cos_phi;
        i2 += (double)s[j].tank_rms_a * s[j].tank_rms_a;
    }
    /* Net regeneration does not reduce the inlet current bound below zero. */
    float p_inv = (float)fmax(0, p / n);
    out->p_inv_w = p_inv;
    out->p_in_w = p_inv / c->eta_min;
    out->i_ps_a = out->p_in_w / line_rms_v;
    out->inlet_bound_a = out->i_ps_a * (1 + c->est_error) + c->aux_max_a;
    out->tank_rms_a = (float)sqrt(i2 / n);
    /* For a given pan, power scales with tank current squared: the power that would put the
     * tank at its ceiling. With no tank current there is no evidence, so no ceiling (INFINITY). */
    out->tank_ceiling_w = out->tank_rms_a > 0.5f
        ? p_inv * (c->tank_limit_a / out->tank_rms_a) * (c->tank_limit_a / out->tank_rms_a)
        : INFINITY;
    return true;
}
