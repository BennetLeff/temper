/**
 * @file contact_check.h
 * @brief sensor-r3 contact-loss detector D1 (thermal trigger + power-step probe).
 *
 * Port of the D1 block, probe_says_contact() and free_decay_rms() in
 * output/temper-sensor-r3/screen.py. All constants live in cc_params_t.
 *
 *  1. Trigger (state NORMAL, outside the hold-off): the slope of T_hat over
 *     the last 2 s is below -0.8 K/s, held for 1 s, while the mean applied
 *     power over those 2 s is >= 40 % of P_MAX. An external request (the
 *     Pt100-vs-rim cross-check) also starts a probe. -> PROBE ("suspect").
 *  2. Probe: coil off / on at 50 % / off for 5 / 8 / 5 s, overriding the PID
 *     (the first probe and the retry probe have separate shapes; defaults in
 *     cc_default_params, rationale in firmware/DECISIONS.md D-B5).
 *  3. Decide at the end of the probe window:
 *       regress the Pt100 reading on [1, t, t^2, E_lag] (E_lag = coil energy,
 *       kJ, through a 3 s first-order lag) -> energy coefficient d (K/kJ);
 *       fit a free decay toward the rim NTC (tau_off = C_cap/G_leak +-40 %,
 *       asymptote within 25 K of the rim reading) -> rms misfit.
 *     LOST iff d < 25 % of a*1000 AND the free decay fits within 0.5 K rms.
 *     Firmware additions (output/temper-sensor-r3/firmware/DECISIONS.md):
 *       D-D1a  a probe from NORMAL concludes LOST only if the fitted decay
 *              moves >= decay_min_change_k over the window;
 *       D-D1b  a retry restores control only if the reading departs from the
 *              free decay;
 *       D-D1c  "responds" also needs d >= probe_min_sigma standard errors.
 *     Each has a parameter that restores the screen.py rule.
 *  4. LOST: power 0, CC_EVT_LOST (state-machine event + UI message), and a
 *     new probe (RETRY) every 20 s; a passing retry restores control
 *     (CC_EVT_RESTORED). A passing probe returns to NORMAL with a 30 s
 *     hold-off (CC_EVT_PROBE_PASSED).
 *
 * Memory is bounded: three fixed ring buffers of CC_RING_LEN samples (just
 * over the 18 s probe window at 10 Hz). No heap. The decision regressions
 * run once per probe, in double precision (about 2k multiply-adds).
 */

#ifndef CONTACT_CHECK_H
#define CONTACT_CHECK_H

#include <stdbool.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

#define CC_RING_LEN 184u   /* >= (2*off + on)/dt + 1 = 181 at 10 Hz */
#define CC_DECAY_STEPS_MAX 33u

typedef enum {
    CC_NORMAL = 0,
    CC_PROBE = 1,
    CC_LOST = 2,
    CC_RETRY = 3,
} cc_state_t;

typedef enum {
    CC_EVT_NONE = 0,
    CC_EVT_SUSPECT = 1,       /**< first probe started from NORMAL           */
    CC_EVT_PROBE_PASSED = 2,  /**< probe found contact; back to NORMAL       */
    CC_EVT_LOST = 3,          /**< contact loss confirmed (raise SM event)   */
    CC_EVT_RESTORED = 4,      /**< a retry probe found contact again         */
} cc_event_t;

typedef struct {
    float dt_s;               /**< 0.1 */
    float p_max_w;            /**< 1800 */
    uint16_t trig_window;     /**< samples in the slope window, 20 (2 s) */
    float trig_rate_k_per_s;  /**< -0.8 */
    float trig_hold_s;        /**< 1.0 */
    float trig_pmin_frac;     /**< 0.4 */
    /* First probe (from NORMAL): off / on / off, power fraction, regressor lag. */
    float probe_off_s;        /**< 5 (screen.py) */
    float probe_on_s;         /**< 8 */
    float probe_p_frac;       /**< 0.5 */
    float probe_lag_s;        /**< 3 (energy regressor lag) */
    /* Retry probe (from LOST): no time pressure, power is already off. */
    float retry_off_s;        /**< 5 */
    float retry_on_s;         /**< 8 */
    float retry_p_frac;       /**< 0.5 */
    float retry_lag_s;        /**< 3 */
    float probe_frac;         /**< 0.25 of a*1000 */
    float retry_s;            /**< 20 */
    float holdoff_s;          /**< 30 */
    float decay_tau_s;        /**< C_cap / G_leak */
    float decay_tau_tol;      /**< 0.4 -> tau x [0.6, 1.4] */
    uint16_t decay_steps;     /**< 17 grid points */
    float decay_asym_k;       /**< 25 */
    float decay_rms_k;        /**< 0.5 */
    float probe_min_sigma;    /**< 3.0: "responds" also needs d >= this many
                                   standard errors (low-gain pans such as a water
                                   pot give d noise ~0.4 d_exp); 0 = screen.py
                                   (DECISIONS D-D1c) */
    bool retry_decay_only;    /**< true: a retry restores control only when the
                                   reading departs from the free decay (rms >
                                   decay_rms_k); the energy coefficient is not
                                   used to leave LOST (DECISIONS D-D1b) */
    float decay_min_change_k; /**< 1.0: a probe started from NORMAL may only
                                   conclude LOST if the fitted free decay moves
                                   at least this much over the window (a flat
                                   reading is no evidence of loss); 0 = screen.py */
} cc_params_t;

typedef struct {
    float y;   /**< Pt100 reading */
    float th;  /**< T_hat */
    float p;   /**< power applied during the preceding period */
} cc_sample_t;

typedef struct {
    cc_params_t p;
    cc_sample_t ring[CC_RING_LEN];
    uint16_t head;
    uint16_t count;
    uint32_t tick;
    cc_state_t state;
    uint32_t state_tick;
    bool trig_active;
    uint32_t trig_since;
    uint32_t holdoff_until;
    bool probe_requested;
    /* bookkeeping for tests and logs */
    uint32_t probes;
    bool has_suspect;
    uint32_t suspect_tick;
    bool has_lost;
    uint32_t lost_tick;
    float last_d;
    float last_d_exp;
    float last_decay_rms;
    float last_decay_change;
    uint16_t probe_len;       /**< samples in the first-probe window (incl. start) */
    uint16_t len_shape[2];    /**< [0] first probe, [1] retry */
    uint32_t off_shape[2];
    uint32_t on_shape[2];
    uint8_t shape;            /**< shape of the probe in progress */
    uint32_t hold_ticks;
    uint32_t retry_ticks;
    uint32_t holdoff_ticks;
} cc_t;

typedef struct {
    bool override;        /**< true: use p_override_w instead of the PID */
    float p_override_w;
    cc_state_t state;
    cc_event_t event;
    bool reset_integrator;
} cc_output_t;

void cc_default_params(cc_params_t *p);
bool cc_init(cc_t *c, const cc_params_t *p);

/** Ask for a probe at the next NORMAL step outside the hold-off. */
void cc_request_probe(cc_t *c);

/**
 * One 10 Hz step, called after the estimator and the PID.
 * @param t_hat_c      estimate this step
 * @param y_c          Pt100 reading this step
 * @param p_applied_w  power applied during the period that just ended
 * @param a_k_per_j    current plant gain (sets the expected probe response)
 * @param t_rim_c      rim-NTC reading (free-decay asymptote)
 */
void cc_step(cc_t *c, float t_hat_c, float y_c, float p_applied_w, float a_k_per_j,
             float t_rim_c, cc_output_t *out);

/**
 * The probe decision on a window of n samples taken dt apart, starting at the
 * probe start. Exposed for unit tests. Returns true if contact is present.
 */
bool cc_probe_says_contact(const cc_params_t *p, const float *y, const float *pw, uint16_t n,
                           float a_k_per_j, float t_rim_c, float lag_s, bool require_change, float *d_out,
                           float *d_exp_out, float *decay_rms_out, float *decay_change_out);

/** Free-decay hypothesis misfit (K rms); 1e9 if no admissible fit. If
 *  change_out is given it receives |fitted change| over the window of the
 *  best-fitting decay. */
float cc_free_decay_rms(const cc_params_t *p, const float *y, uint16_t n, float t_rim_c, float *change_out);

#ifdef __cplusplus
}
#endif

#endif /* CONTACT_CHECK_H */
