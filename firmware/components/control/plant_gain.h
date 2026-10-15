/**
 * @file plant_gain.h
 * @brief Online identification of the pan's heating gain a = eta / C_total.
 *
 * sensor-r3 schedules the rate-domain PID by a (P = rate / a). The r2/r3
 * screens gave the controller the true a; this module identifies it from the
 * pan-temperature estimate and the coil input power.
 *
 * Method (output/temper-sensor-r3/firmware/DECISIONS.md, D-ID):
 *   - average T_hat, cumulative input energy E and the loss integral
 *     S = integral (T_hat - T_amb) dt into 1 s blocks;
 *   - over a sliding window of W blocks regress
 *         dT_hat = a * (dE_lag - k_loss * dS)
 *     with scalar recursive least squares (weak prior a0);
 *   - update only while the caller's gate is true for the whole window
 *     (heat-up phase: setpoint ramp active or power saturated, below the
 *     setpoint, contact check normal, no sensor fault) and after the pan has
 *     risen rise_min_k since the phase began (the pan-centre lag has formed);
 *   - no forgetting in the first heat-up; forgetting factor on later ramps.
 *
 * The power input is explicit about its provenance (pg_power_source_t):
 * measured bus/coil power (temper-coil-driver-r1 RECOMMENDATIONS item 2) or
 * an estimate from the commanded power. A constant scale error in an
 * estimated power is absorbed into a and is harmless to the gain schedule
 * because the same power scale is used to command; the estimate reports which
 * source(s) it was built from so the application can show or log it.
 */

#ifndef PLANT_GAIN_H
#define PLANT_GAIN_H

#include <stdbool.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

#define PG_MAX_BLOCKS 64u

typedef enum {
    PG_POWER_MEASURED = 0,   /**< measured input power (bus current x voltage) */
    PG_POWER_ESTIMATED = 1,  /**< estimated from the power command             */
} pg_power_source_t;

#define PG_SRC_MASK_MEASURED  (1u << PG_POWER_MEASURED)
#define PG_SRC_MASK_ESTIMATED (1u << PG_POWER_ESTIMATED)

typedef struct {
    float dt_s;              /**< sample period (s), 0.1                          */
    uint16_t block_samples;  /**< samples per regression block, 10 (1 s)          */
    uint16_t window_blocks;  /**< regression window, 20 blocks                    */
    float a0_k_per_j;        /**< prior / pre-identification gain (K/J)          */
    float a_min_k_per_j;     /**< clamp, K/J                                     */
    float a_max_k_per_j;     /**< clamp, K/J                                     */
    float prior_rel_sd;      /**< prior sd of a as a multiple of a0              */
    float lag_s;             /**< first-order lag on the energy regressor (0=off) */
    float k_loss_w_per_k;    /**< loss conductance / eta prior (0 = effective gain) */
    float t_amb_c;           /**< ambient for the loss regressor                 */
    float rise_min_k;        /**< rise since phase start before updating         */
    float valid_rise_k;      /**< rise needed before the estimate is used        */
    float valid_energy_j;    /**< regressed energy needed before it is used      */
    float forget_first;      /**< RLS forgetting per block, first heat-up        */
    float forget_later;      /**< RLS forgetting per block, later ramps          */
    bool update_later_ramps; /**< false: freeze after the first heat-up          */
} pg_params_t;

typedef struct {
    float t;        /**< block-mean T_hat */
    float e_lag;    /**< cumulative (lagged) energy at block end, J */
    float s;        /**< cumulative loss integral at block end, K s */
    bool gated;
} pg_block_t;

typedef struct {
    pg_params_t p;
    /* RLS */
    float theta;            /**< current a estimate (K/J)          */
    float pcov;             /**< its covariance                     */
    bool valid;
    float forget;
    /* accumulation */
    double e_j;             /**< cumulative energy, J (double: long runs) */
    double e_lag_j;
    double s_ks;
    float t_acc;
    uint16_t n_acc;
    bool gate_acc;
    pg_power_source_t src_block;
    bool src_block_set;
    pg_power_source_t src_window; /**< provenance of the blocks in the window */
    /* phase */
    bool phase_first;
    bool phase_has_start;
    float phase_t_start;
    float regressed_energy_j;
    float phase_rise_k;
    uint8_t src_mask;       /**< sources that contributed to theta */
    /* window ring */
    pg_block_t ring[PG_MAX_BLOCKS];
    uint16_t head;
    uint16_t count;
    uint32_t updates;
} pg_t;

void pg_default_params(pg_params_t *p);
bool pg_init(pg_t *g, const pg_params_t *p);

/**
 * Start an identification phase: the first heat-up (first = true) or a later
 * setpoint increase. Clears the regression window and the rise reference;
 * keeps the current estimate.
 */
void pg_begin_phase(pg_t *g, bool first);

/**
 * One sample.
 * @param t_hat_c  pan-temperature estimate (degC)
 * @param power_w  input power during the last sample period (W)
 * @param src      whether power_w is measured or estimated
 * @param gate     caller's identification gate for this sample
 */
void pg_update(pg_t *g, float t_hat_c, float power_w, pg_power_source_t src, bool gate);

/** Gain to schedule with: the identified a once valid, else the prior a0. */
float pg_gain(const pg_t *g);
static inline bool pg_valid(const pg_t *g) { return g->valid; }
static inline float pg_raw_estimate(const pg_t *g) { return g->theta; }
/** Bit mask of PG_SRC_MASK_* that contributed to the current estimate. */
static inline uint8_t pg_source_mask(const pg_t *g) { return g->src_mask; }

#ifdef __cplusplus
}
#endif

#endif /* PLANT_GAIN_H */
