#ifndef TEMPER_INPUT_LIMITS_H
#define TEMPER_INPUT_LIMITS_H
#include <stdbool.h>
#include <stddef.h>
/*
 * Native-21 input-current estimate and tank-current ceiling (power-stage DECISIONS.md 2026-10-08,
 * "input current <= 15 A RMS" and "operating envelope: tank current ceiling"). Pure functions,
 * no HAL: the power binding samples, calls input_limits_half_cycle once per half line cycle, and
 * feeds the adapter (fullbridge_line_cycle):
 *   inlet_rms_a   <- est.inlet_bound_a         conservative total inlet current, AUX included
 *   pan_budget_w  <- min(pan model, est.tank_ceiling_w)
 * The board has no line-current sensor. The estimate is the inverter's fundamental power
 *   P_inv = mean((2*sqrt2/pi) * V_bus * I_tank,rms * cos(phi))  over the half cycle (unsmoothed bus),
 *   I_ps  = P_inv / eta_min / V_line,rms                         (PF ~ 1 on the unsmoothed bus),
 *   inlet_bound = I_ps * (1 + est_error) + aux_max_a.
 * With the adapter's inlet_target_a (<= 13.5 A regulate, 15 A trip), the power stage is held to
 * (13.5 - aux_max_a) / (1 + est_error): 11.1 A at the provisional 10 % / 1.3 A. Bench
 * qualification of est_error (true-RMS line current vs the estimate, 108/120/132 V x pans)
 * replaces the 10 %.
 */
typedef struct {
    float eta_min;      /* inverter + bridge efficiency lower bound, 0.5..1 */
    float est_error;    /* estimator relative error bound, 0..0.5 */
    float aux_max_a;    /* auxiliary inlet current allowance (both IRM-20 at full load) */
    float tank_limit_a; /* commissioned tank RMS ceiling: 22 A default, <= 28 A (hardware basis) */
} input_limits_cfg_t;
typedef struct {
    float bus_v;      /* VBUS from the isolated AMC1311, V */
    float tank_rms_a; /* tank current RMS over the switching period (CT T1, ct_mon), A */
    float cos_phi;    /* cos of tank current lag behind the bridge voltage (ct_zc vs gate edges) */
} input_sample_t;
typedef struct {
    float p_inv_w, p_in_w, i_ps_a, inlet_bound_a, tank_rms_a, tank_ceiling_w;
} input_estimate_t;
input_limits_cfg_t input_limits_native21(void);
bool input_limits_config_ok(const input_limits_cfg_t *);
/* n >= 8 samples spread over one half line cycle. Returns false on any invalid sample. */
bool input_limits_half_cycle(const input_limits_cfg_t *, const input_sample_t *, size_t n,
                             float line_rms_v, input_estimate_t *);
#endif
