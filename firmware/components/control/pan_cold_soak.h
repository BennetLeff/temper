/**
 * @file pan_cold_soak.h
 * @brief Cold-soak Pt100 leakage check: before the coil starts, a soaked
 *        Pt100 must not read far below the heatsink NTC.
 *
 * A leak in parallel with the Pt100 element reads low (DECISIONS.md D-LEAK).
 * A temperature-independent leak (moisture, a conductive film) reads low at
 * room temperature too, where every part of an idle unit sits at ambient.
 * The only on-board ambient reference is the heatsink NTC (hs_ntc.c).
 * DECISIONS.md D-SOAK; numbers from output/temper-sensor-r3/firmware/
 * hs_ntc.py (hs-ntc.json, which gates the constants below) and cold_soak.py.
 *
 * When: at PREHEAT entry, before the first control period commands power
 * (main/pan_control.c). Power-up alone cannot prove a soak: without a stored
 * token, uptime counts as coil-on time. A token in NVS (pan_soak_store.h,
 * D-SOAKNV) credits a lower bound on the coil-off time from before the power
 * cycle (pcs_credit_off); the window's history still starts at boot.
 *
 * History (pcs_note, from every state-machine tick, at most once a second):
 * the time the coil was last active (from pcs_init, i.e. power-up, while the
 * C1 loop runs or commands power), and per-minute min/max of the Pt100
 * reading and of the heatsink reading while it is VALID, kept only while the
 * coil is off.
 *
 * Rule (pcs_evaluate), in order; any failed condition skips the check and
 * says why:
 *   soaked   the coil off >= soak_n_s (30 min: >= 2x the largest estimated
 *            time constant, glass ~820 s; D-SOAK);
 *   history  the last window_s (15 min) of per-minute history complete;
 *   ref      the heatsink VALID now and through the window, <= hs_max_c
 *            (45 degC). With the CR-8 divider (zapote C45) the channel is
 *            VALID from -40 degC, so the check runs at room temperature
 *            (DECISIONS D-HSNTC); the threshold is budgeted for rooms down
 *            to 5 degC (5 K under the rated 10 degC);
 *   flat     the heatsink within hs_flat_k (1.0 K) and the Pt100 within
 *            pt_flat_k (0.25 K) over the window: a single exponential with
 *            tau <= 1800 s that moved that little is then within 1.54 K /
 *            0.39 K of where it is going (the residual allowance in the
 *            threshold);
 *   rim      the rim NTC SATURATED (the glass below ~87 degC);
 * then LEAK when the heatsink exceeds the Pt100 by more than threshold_k
 * through the whole window (the heatsink's window minimum against the
 * Pt100's window maximum) and now; PASS otherwise.
 *
 * threshold_k is the false-latch stack at its worst over the band where the
 * check runs (hs-ntc.json cold_soak_budget, heatsink 5..45 degC, worst at
 * 5 degC): heatsink reads high (sensor, pull-up, divider gain band, ADC
 * +/-50 mV, SAR sampling, buffer, the rail read as 3300 mV when it is 3242,
 * all at once through the driver's arithmetic), Pt100 reads low (class,
 * Rref, converter offset), the soak residuals and a 1 K standby offset of
 * the heatsink over the room.
 *
 * threshold_measured_k is the same stack with the rail measured (DECISIONS
 * D-RAIL: MCP3202 CH1 against the LM4040A25, rail_adc.c) instead of assumed:
 * the rail term is then the reading's own error over a 5..50 degC board
 * (rail_adc.py: LM4040 tolerance, tempco, current, drift and hysteresis
 * allowances, MCP3202 offset/gain/INL, the half LSB, ripple), not the
 * contract's 3242 mV read as 3300 (hs-ntc.json cold_soak_budget_rail_measured).
 * The evaluation uses it only when the heatsink reading used a measured rail
 * at every history note through the window and now (pcs_note_rail /
 * pcs_evaluate_rail); one note with the rail unknown and the check uses
 * threshold_k. The 3.300 V fallback is the board's validated state, so an
 * unknown rail is not a fault: it only widens the threshold.
 */

#ifndef PAN_COLD_SOAK_H
#define PAN_COLD_SOAK_H

#include <stdbool.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

/* Gated against output/temper-sensor-r3/firmware/hs-ntc.json by hs_ntc.py. */
#define PCS_THRESHOLD_K 19.4f
#define PCS_THRESHOLD_MEASURED_K 16.9f
#define PCS_SOAK_N_S 1800.0f
#define PCS_WINDOW_S 900.0f
#define PCS_HS_FLAT_K 1.0f
#define PCS_PT_FLAT_K 0.25f
#define PCS_HS_MAX_C 45.0f

#define PCS_BUCKET_MAX 32u   /**< per-minute history slots (window / bucket + 1 <= this) */

typedef enum {
    PCS_NONE = 0,              /**< not evaluated                                  */
    PCS_PASS = 1,              /**< soaked and the readings agree                  */
    PCS_LEAK = 2,              /**< soaked and the Pt100 reads low: latch          */
    PCS_SKIP_NOT_SOAKED = 3,   /**< the coil was on (or power-up) < soak_n_s ago   */
    PCS_SKIP_HISTORY = 4,      /**< the window's history is incomplete            */
    PCS_SKIP_HS_INVALID = 5,   /**< heatsink not VALID (saturated cold, or fault)  */
    PCS_SKIP_HS_WARM = 6,      /**< heatsink above hs_max_c                        */
    PCS_SKIP_HS_DRIFT = 7,     /**< heatsink moved more than hs_flat_k             */
    PCS_SKIP_PT_INVALID = 8,   /**< no Pt100 reading through the window            */
    PCS_SKIP_PT_DRIFT = 9,     /**< Pt100 moved more than pt_flat_k                */
    PCS_SKIP_RIM_WARM = 10,    /**< rim NTC not saturated: the glass is warm       */
} pcs_verdict_t;

typedef struct {
    float threshold_k;   /**< PCS_THRESHOLD_K: the rail not measured (3.300 V assumed) */
    float threshold_measured_k;   /**< PCS_THRESHOLD_MEASURED_K: the rail measured through the window */
    float soak_n_s;      /**< PCS_SOAK_N_S    */
    float window_s;      /**< PCS_WINDOW_S    */
    float bucket_s;      /**< 60              */
    float hs_flat_k;     /**< PCS_HS_FLAT_K   */
    float pt_flat_k;     /**< PCS_PT_FLAT_K   */
    float hs_max_c;      /**< PCS_HS_MAX_C    */
} pcs_params_t;

typedef struct {
    uint32_t t0_ms;
    float pt_min, pt_max;
    float hs_min, hs_max;
    bool pt_ok;          /**< every note in the bucket had a Pt100 reading */
    bool hs_ok;          /**< every note in the bucket had a VALID heatsink */
    bool rail_ok;        /**< every note in the bucket had a measured rail */
} pcs_bucket_t;

typedef struct {
    pcs_params_t p;
    uint32_t bucket_ms;
    uint32_t last_active_ms;   /**< power-up counts as coil activity */
    pcs_bucket_t b[PCS_BUCKET_MAX];
    unsigned head;             /**< index of the newest bucket */
    unsigned count;            /**< buckets since the coil was last active */
} pcs_t;

/** Diagnostics of one evaluation. */
typedef struct {
    pcs_verdict_t verdict;
    float off_s;         /**< coil-off time at the evaluation */
    float gap_k;         /**< heatsink window min - Pt100 window max (NAN if not reached) */
    float hs_c;
    float pt_c;
    bool rail_measured;  /**< the rail was measured through the window and now */
    float threshold_k;   /**< the threshold the verdict used (NAN if not reached) */
} pcs_result_t;

void pcs_default_params(pcs_params_t *p);
bool pcs_init(pcs_t *s, const pcs_params_t *p, uint32_t now_ms);

/**
 * Credit coil-off time from before this boot (pan_soak_store.h, D-SOAKNV): the
 * coil was last active at least off_s ago. Only moves the last activity
 * earlier; the history (and so the 15 min window) still starts now.
 */
void pcs_credit_off(pcs_t *s, uint32_t now_ms, uint32_t off_s);

/** Coil-off seconds at now_ms (0 after a backwards clock). */
float pcs_off_s(const pcs_t *s, uint32_t now_ms);

/**
 * One history sample. coil_active restarts the soak and clears the history.
 * pt_c: the Pt100 reading (NAN if none); hs_valid / hs_c: the heatsink driver
 * VALID and its reading.
 */
void pcs_note(pcs_t *s, uint32_t now_ms, bool coil_active, float pt_c, bool hs_valid, float hs_c);
/** pcs_note with whether the heatsink reading used a measured rail (hs_ntc rail_nominal false). */
void pcs_note_rail(pcs_t *s, uint32_t now_ms, bool coil_active, float pt_c, bool hs_valid, float hs_c,
                   bool rail_measured);

/**
 * Evaluate at now_ms with the present readings (the same meaning as
 * pcs_note's) and whether the rim NTC is SATURATED. Does not change s.
 */
pcs_result_t pcs_evaluate(const pcs_t *s, uint32_t now_ms, float pt_c, bool hs_valid, float hs_c,
                          bool rim_saturated);
/** pcs_evaluate with the present reading's rail state: threshold_measured_k when the rail was
 *  measured now and at every note through the window, threshold_k otherwise. pcs_evaluate()
 *  is this with rail_measured false. */
pcs_result_t pcs_evaluate_rail(const pcs_t *s, uint32_t now_ms, float pt_c, bool hs_valid, float hs_c,
                               bool rim_saturated, bool rail_measured);

/** True when a cold-soak latch may be reset: the Pt100 within threshold_k of a VALID heatsink. */
bool pcs_agrees(const pcs_t *s, float pt_c, bool hs_valid, float hs_c);
/** pcs_agrees against threshold_measured_k when this reading's rail is measured. */
bool pcs_agrees_rail(const pcs_t *s, float pt_c, bool hs_valid, float hs_c, bool rail_measured);

const char *pcs_verdict_name(pcs_verdict_t v);

#ifdef __cplusplus
}
#endif

#endif /* PAN_COLD_SOAK_H */
