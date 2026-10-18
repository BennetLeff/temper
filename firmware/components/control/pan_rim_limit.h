/**
 * @file pan_rim_limit.h
 * @brief Setpoint-relative rim limit: latch when the glass under the rim NTC
 *        is hotter than any pan at the loop's own temperature could make it.
 *
 * A leak in parallel with the Pt100 element reads low, and the loop holds the
 * *reading* at the setpoint while the pan runs hot (DECISIONS.md D-LEAK). The
 * glass under the rim NTC follows the *pan*. So the rim reading has a ceiling
 * set by the temperature the loop believes the pan is at, and a rim above it
 * means a pan hotter than the loop believes.
 *
 * Glass envelope (output/temper-sensor-r3/firmware/rim_limit.py, D-RIMLIM):
 * the glass under the bead is a weighted mean of the pan and the coil-eye
 * air, Tg = w T_pan + (1 - w) T_eye, with w 0.646-0.955 (cad/thermal-axisym
 * and study 08) and the eye air at most 139.7 degC (study 02 via 08). The
 * hottest benign glass for a pan at T is
 *     Tg_max(T) = max(w_hi T + (1 - w_hi) T_eye, w_lo T + (1 - w_lo) T_eye).
 *
 * Rule, each control period:
 *   T_ref = a decaying maximum of max(setpoint, t_hat): it rises at once and
 *           falls toward the present value with tau_dec_s, slower than the
 *           glass can cool (study 08: t63 18-106 s), so a lowered setpoint
 *           or a food quench does not lower the limit under a hot glass;
 *   lim   = Tg_max(T_ref) + tol(Tg_max(T_ref)) + margin_k, tol the rim
 *           channel's hot stack at that temperature: the bead's hot corner
 *           (10.2 K at 250 degC, pcb D5), the rail read as 3300 mV when it is
 *           3242 mV, and 4.53 K of still-air self-heating (D-RIM), tabulated
 *           by rim_limit.py (PRL_TOL_*, gated there). D-RIM's constant
 *           19.1 K adds the rail's worst, near the saturation end, to the
 *           bead's worst at 250 degC; tol_table = false uses it (tol_k);
 *   the rim VALID, reading above lim and not falling (now >= the reading
 *   fall_window_s ago - fall_k) for sustain_s latches. A rim that is not
 *   VALID restarts the count and the fall window. "Not falling" keeps a
 *   cooling glass (a cold pan on hot glass, a setpoint lowered after a long
 *   hold) from tripping whatever its level; a leak heats the glass.
 *
 * Limits (rim-limit.json): at a 250 degC setpoint lim is 264 degC, the CR-5
 * band's low edge, so the rule adds little there; it is strongest at the
 * setpoints a leak passes through first. It needs the rim VALID (above about
 * 92 degC) and cannot see a pan that a leak holds only a few tens of kelvin
 * over the setpoint.
 */

#ifndef PAN_RIM_LIMIT_H
#define PAN_RIM_LIMIT_H

#include <stdbool.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

#define PRL_HIST_MAX 64u   /**< fall-window history, 1 s slots */

/* The rim hot stack against the rim temperature (rim_limit.py tol_hot_table,
 * gated against rim-limit.json): knots in degC, stack in K, linear between,
 * held beyond the ends. */
#define PRL_TOL_N 7u
#define PRL_TOL_T_C {90.0f, 100.0f, 150.0f, 200.0f, 250.0f, 300.0f, 350.0f}
#define PRL_TOL_K {11.39f, 10.95f, 11.20f, 13.21f, 15.98f, 19.34f, 23.18f}

typedef struct {
    float dt_s;            /**< 0.1 (control period)                                */
    float w_hi;            /**< 0.9554: flat pan, glass at the NTC (thermal-axisym)  */
    float w_lo;            /**< 0.6457: study 08 B, 0.5 mm gap, 100 degC hold         */
    float t_eye_hi_c;      /**< 139.7: hottest coil-eye air (fry_hold_12.7A)         */
    bool tol_table;        /**< true: the stack from PRL_TOL_* at the envelope       */
    float tol_k;           /**< 19.1: the constant stack when tol_table is false     */
    float margin_k;        /**< 0                                                   */
    float tau_dec_s;       /**< 300: decay of the reference toward the present value */
    float fall_window_s;   /**< 30                                                  */
    float fall_k;          /**< 1.0                                                 */
    float sustain_s;       /**< 5                                                   */
} prl_params_t;

typedef struct {
    prl_params_t p;
    float t_ref_c;         /**< decaying max of max(setpoint, t_hat); NAN at start  */
    float lim_c;           /**< the limit of the last period (diagnostic)           */
    float hist[PRL_HIST_MAX];
    uint32_t n_valid;      /**< consecutive VALID periods                           */
    uint32_t n_over;       /**< consecutive periods over the limit, not falling     */
    float sub_s;           /**< time since the last history slot                    */
    uint8_t head;          /**< next history slot                                   */
    uint8_t filled;        /**< history slots in use                                */
    bool latched;
} prl_t;

void prl_default_params(prl_params_t *p);
bool prl_init(prl_t *c, const prl_params_t *p);

/** Tg_max(t) + tol + margin_k: the rim limit for a reference temperature. */
float prl_limit_c(const prl_params_t *p, float t_ref_c);

/**
 * One control period. setpoint_c and t_hat_c (NAN allowed: then the setpoint
 * alone) are the loop's; rim_valid / t_rim_c the rim NTC driver's state and
 * filtered reading. Returns true once latched (sticky until prl_init).
 */
bool prl_step(prl_t *c, float setpoint_c, float t_hat_c, bool rim_valid, float t_rim_c);

#ifdef __cplusplus
}
#endif

#endif /* PAN_RIM_LIMIT_H */
