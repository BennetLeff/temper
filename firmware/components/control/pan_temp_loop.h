/**
 * @file pan_temp_loop.h
 * @brief sensor-r3 C1 pan-temperature loop: guard -> KF -> a-identification ->
 *        rate PID -> D1 contact check -> power authority.
 *
 * One call per 10 Hz control period. This is the seam the state handlers (and
 * the host co-simulation) drive. Order follows output/temper-sensor-r3/screen.py
 * run(): estimate, PID on the estimate, then D1 may override the PID.
 *
 * Power authority ("never chase a cold reading"): while D1 is probing or has
 * declared contact lost, or while any RTD fault is latched, the output power
 * is the probe/zero value whatever the PID asks.
 */

#ifndef PAN_TEMP_LOOP_H
#define PAN_TEMP_LOOP_H

#include <stdbool.h>
#include <stdint.h>

#include "contact_check.h"
#include "pan_rate_pid.h"
#include "pan_sensor_guard.h"
#include "pan_temp_estimator.h"
#include "plant_gain.h"

#ifdef __cplusplus
extern "C" {
#endif

typedef struct {
    pte_params_t est;
    pg_params_t pg;
    prp_params_t pid;
    cc_params_t cc;
    psg_params_t guard;
    bool detector_enabled;        /**< D1 on (production default true) */
    bool identify_gain;           /**< false: use fixed_gain_k_per_j       */
    float fixed_gain_k_per_j;     /**< used when identify_gain is false    */
    float approach_margin_k;      /**< heat-up phase ends at sp - margin, 2 */
    float new_phase_sp_step_k;    /**< setpoint increase that re-arms ID, 5 */
} ptl_params_t;

typedef struct {
    float t_pt100_c;
    float t_rim_c;
    bool fresh;
    bool spi_ok;
    uint8_t fault_status;
    float setpoint_c;
    float power_applied_w;          /**< input power over the last period */
    pg_power_source_t power_source; /**< measured or estimated            */
} ptl_input_t;

typedef struct {
    float t_hat_c;
    float p_cmd_w;           /**< power to command this period (authority applied) */
    float p_pid_w;
    float a_used_k_per_j;
    bool a_valid;
    uint8_t a_source_mask;
    float sp_eff_c;
    cc_state_t cc_state;
    cc_event_t cc_event;
    psg_verdict_t fault;
    psg_diag_t diag;
    bool ui_pan_must_touch;  /**< show "pan must touch the sensor" */
    bool xcheck_suspect;     /**< the Pt100-vs-rim cross-check fired this period (D-XCHK) */
} ptl_output_t;

typedef struct {
    ptl_params_t p;
    pte_t est;
    pg_t pg;
    prp_t pid;
    cc_t cc;
    psg_t guard;
    bool started;
    bool first_phase_open;
    bool ident_phase_open;   /**< first heat-up identification window open */
    bool later_phase_open;   /**< later setpoint step: open until plant_gain's end hold */
    float last_sp;
    float last_p_cmd;
    bool lost_latched_ui;
    bool settled_prev;       /**< last step held within the margin of the setpoint */
    float pid_p_max_cfg_w;   /**< configured pid.p_max_w (ptl_set_power_limit ceiling) */
} ptl_t;

void ptl_default_params(ptl_params_t *p);
bool ptl_init(ptl_t *l, const ptl_params_t *p, float t0_c);
void ptl_step(ptl_t *l, const ptl_input_t *in, ptl_output_t *out);

/**
 * Runtime power limit (the hob's intensity level), clamped to
 * (0, the configured pid.p_max_w]. The rate PID's output and anti-windup and
 * the plant-gain saturation gate use it; D1 keeps the configured maximum.
 */
void ptl_set_power_limit(ptl_t *l, float p_max_w);

#ifdef __cplusplus
}
#endif

#endif /* PAN_TEMP_LOOP_H */
