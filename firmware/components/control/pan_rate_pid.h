/**
 * @file pan_rate_pid.h
 * @brief sensor-r2/r3 frozen rate-domain PID, gain-scheduled by a = eta/C.
 *
 *   rate_cmd [K/s] = KP e + I - KD dT_f,   e = sp_eff - T_hat
 *   I += KI e dt only while |e| < I_BAND, clamped to [0, P_MAX * a]
 *   P = clamp(rate_cmd / a, 0, P_MAX)
 *   sp_eff ramps toward an increased setpoint at SP_RATE; drops at once.
 *   dT_f is the estimate's derivative through a 2 s first-order filter.
 *
 * Constants are those frozen in output/temper-sensor-r2/DECISIONS.md section 5
 * (KP 0.1/s, KI 0.002/s^2, KD 1.0, band 10 K, 1 K/s, 1800 W).
 *
 * Latent-plateau guard (LPG, output/temper-sensor-r3/firmware/DECISIONS.md
 * D-LPG; evidence in output/temper-sensor-r3/robustness/): water trapped in the
 * glass bore around the post boils under the pan centre and pins the centre,
 * and the Pt100 with it, near 100 C while the coil heats the annulus. The PID
 * would hold full power on the flat reading. When the estimate sits in
 * [lpg_band_lo, lpg_band_hi], its least-squares slope over the previous
 * lpg_n samples is within +-lpg_slope, and the setpoint is more than
 * lpg_margin above it, the power is limited to lpg_rate / a: a heating rate
 * the lumped pan cannot exceed.
 *
 * Energy budget (lpg_budget): the limit applies only once the PID has
 * delivered, since the estimate entered the band from below, the energy that
 * would take the whole pan from the estimate to the setpoint (a * E >= sp -
 * T_hat; losses make the true rise smaller). That heats the pan around a wet
 * pocket so the pocket boils off, instead of holding the pan at 100 C with the
 * pocket intact, and keeps the pan mean at or below the setpoint. Entering the
 * band from above (the reading fell into it, so the pan was hotter than the
 * estimate) gives no budget. E is the PID's output (the loop only ever
 * reduces it), so it over-counts: the safe side.
 */

#ifndef PAN_RATE_PID_H
#define PAN_RATE_PID_H

#include <stdbool.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

typedef struct {
    float kp_per_s;
    float ki_per_s2;
    float kd;
    float i_band_k;
    float sp_rate_k_per_s;
    float p_max_w;
    float dt_s;
    float d_filter_s;
    /* latent-plateau guard */
    bool lpg_enable;          /**< true */
    uint16_t lpg_n;           /**< 100 samples (10 s) */
    float lpg_slope_k_per_s;  /**< 0.15 */
    float lpg_band_lo_c;      /**< 95 */
    float lpg_band_hi_c;      /**< 118 */
    float lpg_margin_k;       /**< 5 */
    float lpg_rate_k_per_s;   /**< 0.2 */
    bool lpg_budget;          /**< true: the energy budget above */
} prp_params_t;

#define PRP_LPG_MAX 128u

typedef struct {
    prp_params_t p;
    float integ;      /**< integral term, K/s */
    float sp_eff;
    float t_prev;
    float dtf;
    bool started;
    bool ramping;     /**< sp_eff was below the setpoint at the last step */
    float hist[PRP_LPG_MAX];  /**< previous estimates, oldest first (LPG) */
    uint16_t hist_n;
    bool lpg_active;          /**< the guard limited the last output */
    double lpg_e_j;           /**< PID energy since the estimate entered the band */
    bool lpg_no_budget;       /**< entered the band from above */
    uint32_t lpg_steps;       /**< periods the guard has limited */
} prp_t;

void prp_default_params(prp_params_t *p);
bool prp_init(prp_t *c, const prp_params_t *p);

/**
 * Start from a known state. sensor-r2/r3 start with sp_eff = T_hat = T_amb;
 * the firmware starts bumplessly from the first estimate.
 */
void prp_start(prp_t *c, float t_hat_c);

/** One control period. Returns the PID's power request (W). */
float prp_step(prp_t *c, float sp_c, float t_hat_c, float a_k_per_j);

static inline void prp_reset_integrator(prp_t *c) { c->integ = 0.0f; }
static inline float prp_sp_eff(const prp_t *c) { return c->sp_eff; }
static inline bool prp_ramping(const prp_t *c) { return c->ramping; }
static inline bool prp_lpg_active(const prp_t *c) { return c->lpg_active; }

#ifdef __cplusplus
}
#endif

#endif /* PAN_RATE_PID_H */
