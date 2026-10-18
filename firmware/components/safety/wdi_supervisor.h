/**
 * @file wdi_supervisor.h
 * @brief TPS3823 WDI heartbeat, gated on control-loop progress (zapote C42)
 *
 * The controller's TPS3823-33 (U21) watches WDI (GPIO18, 1 k pull-down). With
 * no edge for 0.9-2.5 s (SLVS165O t_tout) it trips the interlock latch and
 * PERMIT drops, whatever the firmware does. zapote/controller DECISIONS C42
 * sets the firmware rule:
 *
 *   WDI is toggled only by the supervisor task, after it has checked the
 *   control loop's progress (sequence counter, RTD read age). Never from an
 *   ISR, a hardware timer, LEDC or RMT. Heartbeat <= 400 ms.
 *
 * Split:
 * - The control task publishes its progress once per iteration with
 *   wdi_progress_publish(): a loop sequence number it increments, and the
 *   sequence number of the newest RTD conversion it has seen.
 * - The supervisor task calls wdi_sup_step() every WDI_SUP_PERIOD_MS with
 *   wdi_progress_read() and drives WDI to the returned level when it returns
 *   true. wdi_sup_step() is pure logic (no HAL, no RTOS), so the host tests
 *   drive it directly.
 *
 * Rule (each step):
 * - loop progress: the loop sequence advanced by >= min_loop_advance since the
 *   previous step;
 * - RTD read age: a conversion has been seen and the newest one is no older
 *   than max_rtd_age_ms (age counted on the supervisor's clock from the step
 *   at which its sequence number was first seen);
 * - the supervisor itself ran within heartbeat_ms of its previous step.
 * Before the first step where all hold (power-up, MAX31865 fault cycle) the
 * supervisor is ARMING and never toggles: the TPS3823 keeps the latch tripped.
 * Once RUNNING, the first failed step stops the heartbeat for good (STOPPED,
 * latched until reset): a stall shorter than the TPS3823 timeout is not
 * forgiven, and the hardware then trips the latch within 0.9-2.5 s.
 */

#ifndef WDI_SUPERVISOR_H
#define WDI_SUPERVISOR_H

#include <stdbool.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

/** C42: the heartbeat is at most 400 ms, inside the TPS3823's 0.9 s minimum
 *  timeout (SLVS165O 6.8). wdi_sup_init() rejects anything longer. */
#define WDI_HEARTBEAT_MAX_MS 400u

/** Supervisor task period. One WDI edge per healthy step: 100 ms. */
#define WDI_SUP_PERIOD_MS 100u

typedef struct {
    uint32_t heartbeat_ms;      /**< max time between steps (and WDI edges), <= 400 */
    uint32_t min_loop_advance;  /**< control-loop iterations required per step */
    uint32_t max_rtd_age_ms;    /**< newest RTD conversion no older than this */
} wdi_sup_params_t;

/** Defaults: the control loop runs every 10 ms, so a 100 ms step expects 10
 *  iterations and requires 5. The MAX31865 converts every 20 ms and
 *  rtd_service declares it stale after 60 ms (D-STALE); 300 ms is five times
 *  that, so a stopped converter stops the heartbeat within 400 ms. */
#define WDI_SUP_DEFAULT_PARAMS() { \
    .heartbeat_ms = WDI_HEARTBEAT_MAX_MS, \
    .min_loop_advance = 5u,               \
    .max_rtd_age_ms = 300u                \
}

typedef enum {
    WDI_SUP_ARMING = 0,  /**< not yet healthy since reset: no heartbeat */
    WDI_SUP_RUNNING,     /**< healthy: one WDI edge per step */
    WDI_SUP_STOPPED      /**< a check failed while running: no heartbeat, latched */
} wdi_sup_state_t;

typedef enum {
    WDI_STOP_NONE = 0,
    WDI_STOP_LOOP_STALLED,     /**< loop sequence advanced < min_loop_advance */
    WDI_STOP_RTD_STALE,        /**< no RTD conversion within max_rtd_age_ms */
    WDI_STOP_SUPERVISOR_LATE   /**< the supervisor's own step came too late */
} wdi_stop_reason_t;

typedef struct {
    wdi_sup_params_t p;
    wdi_sup_state_t state;
    wdi_stop_reason_t reason;
    bool started;            /**< a first step has set the baselines */
    bool level;              /**< WDI level last returned */
    uint32_t last_step_ms;
    uint32_t last_loop_seq;
    bool rtd_seen;
    uint32_t rtd_seq;
    uint32_t rtd_seen_ms;    /**< supervisor time the newest RTD seq was first seen */
    uint32_t edges;          /**< WDI edges returned since init */
} wdi_sup_t;

/** @return false (and the supervisor stays ARMING forever, never toggling)
 *  if the parameters break C42: heartbeat 0 or > 400 ms, or a zero bound. */
bool wdi_sup_init(wdi_sup_t *s, const wdi_sup_params_t *p);

/**
 * One supervisor step.
 *
 * @param now_ms     supervisor clock
 * @param loop_seq   control-loop sequence number (wdi_progress_read)
 * @param rtd_valid  a converted RTD sample exists
 * @param rtd_seq    its conversion sequence number
 * @param level_out  WDI level to drive when the step returns true
 * @return true when WDI must be driven to *level_out (one edge)
 */
bool wdi_sup_step(wdi_sup_t *s, uint32_t now_ms, uint32_t loop_seq, bool rtd_valid,
                  uint32_t rtd_seq, bool *level_out);

wdi_sup_state_t wdi_sup_state(const wdi_sup_t *s);
wdi_stop_reason_t wdi_sup_stop_reason(const wdi_sup_t *s);

/* ---- progress hand-off between the two tasks -------------------------------
 * Single writer (the control task), single reader (the supervisor task). Each
 * field is one aligned 32-bit word, which the ESP32-S3 reads and writes
 * atomically; a torn pair (new loop_seq, old rtd fields) only delays the RTD
 * age by one step. */

/** Control task, once per iteration, after the state machine update. */
void wdi_progress_publish(bool rtd_valid, uint32_t rtd_seq);

/** Supervisor task. */
void wdi_progress_read(uint32_t *loop_seq, bool *rtd_valid, uint32_t *rtd_seq);

#ifdef __cplusplus
}
#endif

#endif /* WDI_SUPERVISOR_H */
