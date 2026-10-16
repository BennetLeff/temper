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
 *   inlet_bound = I_ps * (1 + est_error) + I_aux.
 * With the adapter's inlet_target_a (<= 13.5 A regulate, 15 A trip), the power stage is held to
 * (13.5 - I_aux) / (1 + est_error). Bench qualification of est_error (true-RMS line current vs
 * the estimate, 108/120/132 V x pans) replaces the provisional 10 %.
 *
 * Auxiliary allowance I_aux (power-stage DECISIONS 16, stage-16 PLAN section 5). Since s38 the
 * inlet feeds two modules: PS2 (MPM-20-24, gate drive) and PS3 (MPM-65-15ST on the F2 / J11 mains
 * tap, controller logic + blower). Each is counted by its increment to the inlet RMS at the hold
 * point (blower_aux.h): static aux_min_a = 0.26 A with the blower off; aux_max_a is the worst
 * case, PS3 blower at full (0.887 A, hold 11.47 A; temper-aux-load-r1 aux-load.json), and is what
 * input_limits_half_cycle() uses. The binding replaces it, per half, with the allowance scheduled
 * from the commanded blower drive (blower_aux.h, n21_set_aux_allowance()) through
 * input_limits_half_cycle_aux(); a missing, stale or out-of-range allowance falls back to
 * aux_max_a. The regulation target and every trip are unchanged; only the split between the power
 * stage and the auxiliaries moves.
 */
typedef struct {
    float eta_min;      /* inverter + bridge efficiency lower bound, 0.5..1 */
    float est_error;    /* estimator relative error bound, 0..0.5 */
    float aux_max_a;    /* worst-case auxiliary allowance: PS2 + PS3 with the blower at full */
    float aux_min_a;    /* static part, PS2 + PS3 logic (blower off, inlet-RMS increment): the
                         * lowest allowance a schedule may set */
    float tank_limit_a; /* commissioned tank RMS ceiling: 18 A default, <= 28 A (hardware basis) */
} input_limits_cfg_t;
typedef struct {
    float bus_v;      /* VBUS from the isolated AMC1311, V */
    float tank_rms_a; /* tank current RMS over the switching period (CT T1, ct_mon), A */
    float cos_phi;    /* cos of tank current lag behind the bridge voltage (ct_zc vs gate edges) */
    /* Time the reading stands for (any unit, finite, >= 0). All zero (the default) means equal
     * weights; any non-zero weight switches the whole half to time weighting, and then the sum must
     * be positive. n21_half_close() fills it with the sample's share of the half line cycle
     * (mid-point rule, the end samples held to the zero crossings), because the 625 us slot grid
     * does not divide the half cycle: 13 or 14 readings fall in it, and an unweighted mean of them
     * scatters about -3 % .. +2.7 % in RMS with slot phase (build-evidence/rms-estimator). */
    float w;
} input_sample_t;
typedef struct {
    float p_inv_w, p_in_w, i_ps_a, inlet_bound_a, tank_rms_a, tank_ceiling_w;
} input_estimate_t;
input_limits_cfg_t input_limits_native21(void);
bool input_limits_config_ok(const input_limits_cfg_t *);
/* n >= 8 samples spread over one half line cycle. Returns false on any invalid sample. */
bool input_limits_half_cycle(const input_limits_cfg_t *, const input_sample_t *, size_t n,
                             float line_rms_v, input_estimate_t *);
/* The auxiliary allowance a schedule may use: aux_a inside [aux_min_a, aux_max_a]; anything else
 * (NaN, below the static part, above the worst case) is aux_max_a. */
float input_limits_aux(const input_limits_cfg_t *, float aux_a);
/* One half cycle of the allowance in force: towards input_limits_aux(cfg, target_a), up by at most
 * max_up_a (the frequency loop follows the bound up one half at a time), down at once. */
float input_limits_aux_ramp(const input_limits_cfg_t *, float in_force_a, float target_a, float max_up_a);
/* As input_limits_half_cycle() with the scheduled allowance input_limits_aux(cfg, aux_a). */
bool input_limits_half_cycle_aux(const input_limits_cfg_t *, const input_sample_t *, size_t n,
                                 float line_rms_v, float aux_a, input_estimate_t *);
#endif
