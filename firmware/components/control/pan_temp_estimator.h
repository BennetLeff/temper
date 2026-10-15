/**
 * @file pan_temp_estimator.h
 * @brief sensor-r3 C1 pan-temperature Kalman filter (fixed contact model).
 *
 * Port of KFNoPower in output/temper-sensor-r2/estimator_study.py with the
 * C1 cartridge constants of output/temper-sensor-r3 (HANDOFF section C1).
 *
 * State x = [T_pan, v, T_cap, T_el] (degC, K/s, degC, degC):
 *   - T_pan  pan base temperature at the contact point (the estimate),
 *   - v      its rate (constant-velocity model, no coil power input),
 *   - T_cap  Si3N4 contact disc,
 *   - T_el   Pt100 element (the measured node).
 * The disc couples to the pan through a FIXED contact conductance
 * h_nom * A_contact, to the element through G_bond, and leaks to the sink
 * (the rim-NTC reading) through G_leak.
 *
 * The model is linear with constant coefficients, so the 5-substep Euler map
 * and its Jacobian are computed once at init (in double) and the per-sample
 * filter runs in single precision (ESP32-S3 FPU). All cartridge constants
 * live in one struct so the bench can recalibrate C_cap, G_leak and h_nom.
 *
 * No heap, no global state; the caller owns the pte_t.
 */

#ifndef PAN_TEMP_ESTIMATOR_H
#define PAN_TEMP_ESTIMATOR_H

#include <stdbool.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

#define PTE_NX 4

typedef struct {
    float c_cap_j_per_k;       /**< disc + bond heat capacity (J/K), 0.0404   */
    float c_el_j_per_k;        /**< Pt100 chip heat capacity (J/K), 0.008175  */
    float g_bond_w_per_k;      /**< disc-to-element conductance (W/K), 0.0612 */
    float g_leak_w_per_k;      /**< disc-to-sink leak (W/K), 0.0008           */
    float contact_area_m2;     /**< contact face area (m^2), 45.4e-6          */
    float h_nom_w_per_m2k;     /**< fixed contact conductance (W/m^2K), 1300  */
    float dt_s;                /**< filter period (s), 0.1                    */
    uint8_t substeps;          /**< Euler substeps per period, 5              */
    float q_per_s[PTE_NX];     /**< process noise density; Q = diag(q)*dt     */
    float p0[PTE_NX];          /**< initial covariance diagonal               */
    float sigma_k;             /**< Pt100 noise (K rms); R = sigma^2          */
} pte_params_t;

typedef struct {
    pte_params_t p;
    float F[PTE_NX][PTE_NX];   /**< state transition over one period          */
    float g_sink[PTE_NX];      /**< sink-temperature input column             */
    float x[PTE_NX];
    float P[PTE_NX][PTE_NX];
    float r;
    uint32_t steps;
} pte_t;

/** Fill the C1 defaults (HANDOFF section C, item 1). */
void pte_default_params(pte_params_t *p);

/**
 * Initialise the filter with every node at t0_c.
 * @return false if any parameter is non-physical (filter left unusable).
 */
bool pte_init(pte_t *f, const pte_params_t *p, float t0_c);

/**
 * One filter period: predict with the sink reading, update with the Pt100.
 * @param y_pt100_c  Pt100 reading (degC)
 * @param t_sink_c   rim-NTC reading used as the leak sink (degC)
 * @return the pan contact-point estimate T_pan (degC)
 */
float pte_step(pte_t *f, float y_pt100_c, float t_sink_c);

/** Predict only (no measurement this period, e.g. a rejected sample). */
float pte_predict(pte_t *f, float t_sink_c);

static inline float pte_estimate(const pte_t *f) { return f->x[0]; }
static inline float pte_rate(const pte_t *f) { return f->x[1]; }

#ifdef __cplusplus
}
#endif

#endif /* PAN_TEMP_ESTIMATOR_H */
