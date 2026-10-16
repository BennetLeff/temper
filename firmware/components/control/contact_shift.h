/**
 * @file contact_shift.h
 * @brief sensor-r3 C1 contact-shift window (CSW): bounded, event-gated update of
 *        the estimator's contact model after an abrupt contact change.
 *
 * Port of output/temper-sensor-r3/robustness/shift_kf.py (the Python
 * reference; the co-simulation checks the two against each other).
 * Rationale and evidence: output/temper-sensor-r3/robustness/DECISIONS.md and
 * output/temper-sensor-r3/firmware/DECISIONS.md D-CSW.
 *
 * The fixed-contact KF (pan_temp_estimator) reads low when the contact
 * conductance h_c drops mid-cook (pan nudged or tilted, the post sticking),
 * and the loop then overheats the pan by the change in the static offset.
 * sensor-r2 showed that h_c cannot be identified from coil power over a run,
 * because the contact lag and the pan-centre lag commute. A step in h_c is
 * different: the cartridge settles in 0.2-3.5 s while the pan cannot change
 * its rate without a power change. With the pan pinned to its trajectory just
 * before the step, the only explanation of the reading's fall is a lower G.
 *
 *  1. Trigger (no window open, D1 normal, no sensor fault, >= start_holdoff_s
 *     after start and > holdoff_s after the last window): the slope of the
 *     reading over the last n_recent samples minus its slope over the
 *     n_before samples before that is below -dv_trig (DOWN), or above
 *     +dv_trig with G below 0.95 G_nom (UP); and no 1 s block of the applied
 *     power over the last p_recent_s is lower (DOWN) / higher (UP) than the
 *     mean of the p_recent_s before by more than dp_frac * P_max.
 *  2. The estimator state from trig_lag_s ago is replayed as a 5-state EKF
 *     [T_pan, v, T_cap, T_el, ln G] in double. T_pan (sd p0_t) and v (the
 *     reading's slope over v_ref_s before the snapshot, sd p0_v) are pinned
 *     (process noise q_t, q_v); ln G starts at the current value (sd p0_lng,
 *     noise q_lng), clamped to [ln G_floor, ln G] (DOWN) or [ln G, ln G_nom]
 *     (UP): the assumed contact can only go down, or back up to nominal.
 *     While the window is open its estimate is the loop's T_hat.
 *  3. Close:
 *       ESCALATE (DOWN) ln G reaches the floor: a fall faster than any partial
 *                contact gives (contact loss, or real pan cooling such as
 *                food). The model is kept; the caller requests a D1 probe.
 *       ACCEPT   >= win_min_s (win_min_hold_s when the loop was steady at its
 *                setpoint) after the trigger, ln G moved < settle_dlng over
 *                settle_s, the change is >= min_drop and the sd of ln G is
 *                <= max_sd_lng (or the UP estimate sits at nominal): the
 *                estimator takes the window's state and the contact
 *                exp(ln G - accept_bias_sd * sd), the lower side of the
 *                estimate, since a contact assumed too good over-heats.
 *       REVERT   at win_max_s, or when the caller's gate drops. The estimator
 *                ran on with the old contact throughout, so nothing changes.
 *
 * The estimator (pte_t) keeps running in parallel during a window. No heap;
 * about 5 kB of state. All tuning in csw_params_t.
 */

#ifndef CONTACT_SHIFT_H
#define CONTACT_SHIFT_H

#include <stdbool.h>
#include <stdint.h>

#include "pan_temp_estimator.h"

#ifdef __cplusplus
extern "C" {
#endif

#define CSW_HIST 160u   /* >= max(n_recent + n_before, 2 p_recent/dt, lag + 1 + v_ref/dt) */
#define CSW_SNAP 32u    /* >= trig_lag/dt + 1 */
#define CSW_WIN  200u   /* >= trig_lag/dt + 1 + win_max/dt */

typedef struct {
    bool enable;               /**< true */
    bool up_enable;            /**< true: allow the return toward nominal */
    float dt_s;                /**< 0.1 */
    float p_max_w;             /**< 1800 */
    uint16_t n_recent;         /**< 15 samples */
    uint16_t n_before;         /**< 30 samples */
    float dv_trig_k_per_s;     /**< 0.6 */
    float p_recent_s;          /**< 8 (whole seconds) */
    float dp_frac;             /**< 0.10 */
    float start_holdoff_s;     /**< 30 */
    float holdoff_s;           /**< 20 */
    float trig_lag_s;          /**< 2.5 */
    float v_ref_s;             /**< 5 */
    float p0_t_k;              /**< 0.1 */
    float p0_v_k_per_s;        /**< 0.03 */
    float q_t;                 /**< 1e-4 per s */
    float q_v;                 /**< 1e-4 per s */
    float p0_lng;              /**< 1.0 */
    float q_lng;               /**< 0.002 per s */
    float h_floor_w_per_m2k;   /**< 150 */
    float win_min_s;           /**< 4 */
    float win_min_hold_s;      /**< 8 */
    float win_max_s;           /**< 12 */
    float settle_s;            /**< 2 */
    float settle_dlng;         /**< 0.04 */
    float min_drop;            /**< 0.25 */
    float max_sd_lng;          /**< 0.2 */
    float accept_bias_sd;      /**< 1.0: accept ln G - this x its sd (the safe side) */
} csw_params_t;

typedef enum {
    CSW_EVT_NONE = 0,
    CSW_EVT_OPEN_DOWN = 1,
    CSW_EVT_OPEN_UP = 2,
    CSW_EVT_ACCEPT = 3,
    CSW_EVT_REVERT = 4,
    CSW_EVT_ESCALATE = 5,   /**< request a D1 probe */
} csw_event_t;

typedef struct {
    csw_params_t p;
    pte_params_t k;            /**< cartridge model (from the estimator) */
    double g_nom;              /**< W/K */
    double g;                  /**< current model contact, W/K */
    /* histories (index 0 = oldest kept) */
    float y[CSW_HIST];
    float ts[CSW_HIST];
    float pw[CSW_HIST];
    uint16_t count;
    float snap_x[CSW_SNAP][PTE_NX];
    float snap_P[CSW_SNAP][PTE_NX][PTE_NX];
    uint16_t snap_count;
    uint32_t t;                /**< steps */
    uint32_t holdoff_until;
    uint16_t nlag, npw, nref, nkeep, nblk;
    /* window */
    bool win;
    int8_t dir;                /**< +1 down, -1 up */
    bool steady;
    double z[5];
    double Pz[5][5];
    double lo, hi, g_before;
    float p_ref;
    uint16_t n, n_replay;
    double lng_log[CSW_WIN];
    /* bookkeeping */
    uint32_t windows, accepts, escalations;
} csw_t;

typedef struct {
    float t_hat_c;             /**< estimate for the loop this step */
    csw_event_t event;
    bool window_open;
    float h_model_w_per_m2k;
} csw_output_t;

void csw_default_params(csw_params_t *p);

/** Initialise against the estimator's cartridge model. False on bad params. */
bool csw_init(csw_t *c, const csw_params_t *p, const pte_params_t *k);

/**
 * One 10 Hz step. Runs the estimator (pte_step) itself, then the window.
 * @param est         the loop's estimator (its contact may be changed on ACCEPT)
 * @param y_c         Pt100 reading
 * @param t_sink_c    rim-NTC reading (the model's sink)
 * @param p_applied_w input power over the period that just ended
 * @param allow       caller's gate: D1 NORMAL and no sensor fault
 * @param steady      the loop has held its setpoint (no ramp) for a while
 */
void csw_step(csw_t *c, pte_t *est, float y_c, float t_sink_c, float p_applied_w, bool allow, bool steady,
              csw_output_t *out);

/** Close an open window without changing the model (a sample was rejected). */
void csw_reset_window(csw_t *c);

/** D1 restored contact after a loss (a new seating): back to the nominal model. */
void csw_reset_contact(csw_t *c, pte_t *est);

static inline float csw_h_model(const csw_t *c) { return (float)(c->g / (double)c->k.contact_area_m2); }

#ifdef __cplusplus
}
#endif

#endif /* CONTACT_SHIFT_H */
