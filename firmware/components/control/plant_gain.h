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
 *   - no forgetting in the first heat-up;
 *   - later setpoint increases: one hold-to-hold energy-balance update per
 *     step (see the later_* parameters).
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
    float forget_later;      /**< RLS forgetting at a later-phase update         */
    bool update_later_ramps; /**< false: freeze after the first heat-up          */
    /* Later ramps (DECISIONS.md D-ID2). A later setpoint step (10-30 K) is
     * too short for the first-heat-up window, and a sliding window over it is
     * corrupted by the pan-centre lag: the reading lags the pan mean by up to
     * 30 K while the ramp power is on and catches up afterwards, so 8 s
     * windows read a at 0.5x-1.8x of the truth. Later phases therefore use a
     * hold-to-hold energy balance, which the lag cannot bias because the
     * centre-to-mean offset is the same steady value at both holds:
     *
     *   a = (T_end - T_0) / (E_in - E_loss)
     *
     * T_0, P_0: hold mean temperature and input power over the
     *           later_hold_blocks before the setpoint step (the hold power is
     *           the loss at T_0, measured; with k_loss = 0 it would otherwise
     *           bias a low by P_0 / P_ramp, ~25 % at 200 degC: unsafe side);
     * T_end, P_end: the same over the first later_hold_blocks that form a hold
     *           after the step;
     * E_loss:   integral of a loss linear in T between (T_0, P_0) and
     *           (T_end, P_end).
     *
     * The caller's gate must stay true from the step to the end hold (no D1
     * event, no fault, contact normal); one update per phase. */
    float later_rise_min_k;      /**< minimum T_end - T_0, 5 K                    */
    uint16_t later_hold_blocks;  /**< blocks that define a hold, 10 (10 s)        */
    float later_hold_band_k;     /**< hold: block means within this band, 1 K     */
    uint16_t later_timeout_blocks; /**< no end hold within this: no update, 300   */
    float later_max_rel_step;    /**< plausibility: the phase estimate must lie in
                                      [theta/(1+r), theta*(1+r)], r = 0.5; a boil
                                      plateau (the end-hold power is the boil
                                      power), a lifted pan or a stuck reading
                                      fall outside and are rejected; also the
                                      most a phase may raise theta             */
    float later_max_rel_down;    /**< the most a phase may lower theta: to
                                      theta/(1+r), r = 0.25. Too low an a
                                      over-powers (sensitivity.json: 0.5x a
                                      overshoots 7.6 K), too high is sluggish;
                                      a real decrease (food) moves a by at most
                                      this per phase, and one beyond 1/(1+
                                      later_max_rel_step) is rejected        */
    float later_cov_floor_rel;   /**< RLS covariance floor at the update,
                                      (r * theta)^2, r = 0.2: the first ramp's
                                      100+ updates otherwise freeze theta       */
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
    float theta_phase0;     /**< theta when the current phase began  */
    uint32_t later_updates; /**< later phases that updated theta      */
    uint32_t rejected;      /**< later phases rejected as implausible */
    float last_window_a;    /**< estimate of the last evaluated later phase */
    bool later_open;        /**< later phase waiting for its end hold */
    bool later_clean;       /**< gate held since the step             */
    uint16_t later_blocks;  /**< blocks since the step                */
    pg_power_source_t later_src;
    float p_base_w;         /**< P_0, W                               */
    float t_base_c;         /**< T_0                                  */
    double later_e0_j;      /**< cumulative energy at the step        */
    double later_s0_ks;     /**< loss integral at the step           */
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
