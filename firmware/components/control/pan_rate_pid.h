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
 */

#ifndef PAN_RATE_PID_H
#define PAN_RATE_PID_H

#include <stdbool.h>

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
} prp_params_t;

typedef struct {
    prp_params_t p;
    float integ;      /**< integral term, K/s */
    float sp_eff;
    float t_prev;
    float dtf;
    bool started;
    bool ramping;     /**< sp_eff was below the setpoint at the last step */
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

#ifdef __cplusplus
}
#endif

#endif /* PAN_RATE_PID_H */
