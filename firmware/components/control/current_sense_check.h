/**
 * @file current_sense_check.h
 * @brief Bus-current sense plausibility for the C1 runtime: catch a dead
 *        current sense before it can hide a stuck-on power stage.
 *
 * Supervisor stage 2a (pan_supervisor.c) detects a power stage that does not
 * obey its command from the bus current. If the sense reads 0 A, 2a is blind,
 * and the only firmware defence left against a stuck-on stage is stage 2b
 * (over target, command 0 for 20 s, still rising: <= 35.0 s, T_c <= 245.7
 * degC). A stuck stage and a dead sense need not fail together: a sense that
 * dies first is a latent fault. These checks catch it on its own
 * (output/temper-sensor-r3/firmware/DECISIONS.md D-ISENSE):
 *
 * (a) run      every control period: the command has been >= run_p_min_w for
 *              settle_s, and the bus current reads <= near_zero_a (or is not
 *              finite) for run_hold_s -> latch. run_p_min_w sits well above
 *              the stage's ~160 W burst floor, so the stage runs continuously
 *              whenever the check looks (below the floor it bursts at the
 *              floor with a 20 s period and reads 0 A between bursts). At
 *              run_p_min_w an obeying stage draws at least
 *              0.9 * P / 120 V = 2.25 A (the supervisor's P_cmd / 100-120 V
 *              stage model, with the coil delivering down to 0.9 of the
 *              command), 4.5x the near-zero bound.
 * (b) pulse    at the start of a heating session (PREHEAT entry, so a pan is
 *              present), before the loop heats: pulse_w (clamped to the power
 *              limit) for pulse_s; after settle_s the mean bus current must
 *              exceed near_zero_a, or latch. The pulse waits while anything
 *              holds the command at 0 (supervisor stage 1, a sensor fault).
 *              (a) does not look while the pulse is armed: the pulse is its
 *              own test, and nothing else is commanded meanwhile.
 * (c) xcheck   input (line) current against bus current, for the AMC1301
 *              input-current sense (nameplate-r1 DECISIONS D3). On the
 *              unfiltered full-bridge bus |i_in(t)| = i_bus(t), so the two
 *              readings of the same statistic agree within the senses'
 *              tolerances: when either exceeds xc_floor_a, a difference above
 *              max(xc_abs_tol_a, xc_rel_tol * the larger) for xc_hold_s
 *              latches. Compiled into the runtime only with
 *              TEMPER_INPUT_CURRENT_SENSE (default 0: the sense is not on the
 *              board yet).
 *
 * Stage 2b is unchanged and stays the last resort for a stage and a sense
 * that fail at the same moment.
 */

#ifndef CURRENT_SENSE_CHECK_H
#define CURRENT_SENSE_CHECK_H

#include <stdbool.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

typedef struct {
    float dt_s;           /**< 0.1 (control period)                          */
    float near_zero_a;    /**< 0.5: sense offset + noise allowance, the same
                               "no current" bound as supervisor 2a           */
    float settle_s;       /**< 0.3: the stage follows a command step within
                               this (supervisor settle_s)                    */
    /* (a) */
    float run_p_min_w;    /**< 300 */
    float run_hold_s;     /**< 0.5 */
    /* (b) */
    float pulse_w;        /**< 360 (20 % of 1.8 kW) */
    float pulse_s;        /**< 1.0 */
    /* (c) */
    float xc_floor_a;     /**< 1.0 */
    float xc_abs_tol_a;   /**< 1.0 */
    float xc_rel_tol;     /**< 0.25 */
    float xc_hold_s;      /**< 0.5 */
} csc_params_t;

typedef enum {
    CSC_PULSE_IDLE = 0,     /**< not armed                                  */
    CSC_PULSE_PENDING = 1,  /**< armed; waiting for the command to be applied */
    CSC_PULSE_RUNNING = 2,
    CSC_PULSE_PASSED = 3,
    CSC_PULSE_FAILED = 4,
} csc_pulse_state_t;

typedef enum {
    CSC_OK = 0,
    CSC_LATCH_RUN = 1,      /**< (a) commanded power, no current            */
    CSC_LATCH_PULSE = 2,    /**< (b) start-up pulse showed no current       */
    CSC_LATCH_XCHECK = 3,   /**< (c) input and bus current disagree         */
} csc_latch_t;

typedef struct {
    csc_params_t p;
    /* (a) */
    float run_cmd_s;
    float run_bad_s;
    /* (b) */
    csc_pulse_state_t pulse;
    float pulse_cmd_w;      /**< command the pulse asked for this period */
    float pulse_on_s;
    float pulse_i_sum;
    uint16_t pulse_i_n;
    bool pulse_i_bad;
    float pulse_mean_a;     /**< mean current of the last evaluated pulse */
    /* (c) */
    float xc_bad_s;
    csc_latch_t latched;
} csc_t;

void csc_default_params(csc_params_t *p);
bool csc_init(csc_t *c, const csc_params_t *p);

/**
 * (a) One control period. p_applied_w is the command that was in force over
 * the period that just ended, i_bus_a the bus current read at its end.
 * Returns true once latched (sticky until csc_init).
 */
bool csc_run_step(csc_t *c, float p_applied_w, float i_bus_a);

/** (b) Arm the start-up pulse (a new heating session). */
void csc_pulse_begin(csc_t *c);

/**
 * (b) One control period while armed. p_applied_w / i_bus_a as for
 * csc_run_step. Returns the pulse state; while it is PENDING or RUNNING,
 * *p_cmd_w is the power to command next (pulse_w, at most p_limit_w), which
 * replaces the loop's command. Any limit that then zeroes the command (stage
 * 1, a fault) restarts the pulse. FAILED also latches CSC_LATCH_PULSE.
 */
csc_pulse_state_t csc_pulse_step(csc_t *c, float p_applied_w, float i_bus_a, float p_limit_w,
                                 float *p_cmd_w);

/** True while the pulse is armed and not yet passed or failed. */
bool csc_pulse_active(const csc_t *c);

/** (c) One control period: input current against bus current. */
bool csc_xcheck_step(csc_t *c, float i_in_a, float i_bus_a);

#ifdef __cplusplus
}
#endif

#endif /* CURRENT_SENSE_CHECK_H */
