/**
 * @file pan_supervisor.h
 * @brief Firmware runaway supervision for the sensor-r3 C1 pan sensor.
 *
 * Replaces, in TEMPER_PAN_CONTROL_C1 builds, the two legacy firmware checks
 * that C1 trips falsely (output/temper-sensor-r3/firmware/DECISIONS.md D-RUN):
 *
 *   legacy rate latch   15 K/s between two consecutive 10 ms reads. A preheated
 *                       pan placed on the 40 mJ/K disc moves the reading at
 *                       300-460 K/s for about a second, and sensor noise alone
 *                       exceeds 15 K/s over 10 ms. No real pan can be heated
 *                       at 15 K/s by 1.8 kW (lightest modelled pan: 3.2 K/s).
 *   legacy over-target  reading > setpoint + 10 K latches FAULT_THERMAL_RUNAWAY.
 *                       A hot pan placed above the setpoint, or a contact
 *                       change (h_c drop: T_c up to SP + 13 K), trips it.
 *
 * R1, sustained rise (feeds the RUNAWAY latch in check_runaway_boundary):
 *   1 s block means of the raw reading; trip when the block-to-block rise
 *   exceeds rate_max for blocks_required consecutive blocks. A placement
 *   transient decays with the disc's tau63 (<= 1.35 s at the C1 contact
 *   floor) and cannot sustain it; a real runaway that fast still trips within
 *   blocks_required seconds and meets the absolute 300 degC check first.
 *
 * R2, over-target supervision (10 Hz, in PREHEAT/HEATING):
 *   stage 1  max(T_hat, reading) > sp + margin: force the power command to 0
 *            (non-latching; the PID would normally command 0 there anyway);
 *   stage 2a the power stage is not obeying the command -> latch
 *            FAULT_THERMAL_RUNAWAY, when for disobey_hold_s either
 *              - the command has been 0 for settle_s and the bus current still
 *                exceeds disobey_current_a, or
 *              - the bus current exceeds the most the command of the last
 *                settle_s could draw (P_cmd / cmd_v_min) by disobey_excess_a.
 *            This is the failure the legacy over-target latch was a proxy
 *            for, detected directly and usually before the pan reaches the
 *            setpoint;
 *   stage 2b current-independent backup: over target, command 0 for at least
 *            rise_hold_s, and still rising >= rise_min_k over rise_window_s
 *            -> latch FAULT_THERMAL_RUNAWAY. A pan cools with no power; the
 *            hold outlasts a hot-pan placement transient and the pan-centre
 *            lag that keeps the centre rising briefly after the power stops.
 *            Values from the runaway_checks.py sweep (20 s / 5 s / 2 K: no
 *            false trip, and none at half the hold either).
 *
 * Hardware protection is unchanged and independent: the runaway comparator
 * (299-322 degC), the rim-NTC trip (262-288 degC, CR-5), the TCO, and the
 * firmware absolute 300 degC check, which still evaluates every 10 ms read.
 */

#ifndef PAN_SUPERVISOR_H
#define PAN_SUPERVISOR_H

#include <stdbool.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

#define PSUP_MAX_BLOCKS 64u

typedef struct {
    /* R1 */
    uint32_t rate_block_ms;      /**< 1000 */
    float rate_max_k_per_s;      /**< 15 */
    uint8_t rate_blocks_required;/**< 5 */
    /* R2 */
    float dt_s;                  /**< 0.1 */
    float margin_k;              /**< 10: stage 1 and the over-target test */
    float settle_s;              /**< 0.3: command-zero time before 2a looks */
    float disobey_current_a;     /**< 0.5 */
    float disobey_hold_s;        /**< 0.5 */
    float disobey_excess_a;      /**< 2.5 A above the command's current (~250-300 W) */
    float cmd_v_min;             /**< 100 V: lowest bus voltage for the expected
                                      current P_cmd / V (placeholder until the
                                      bus-current sense scaling is fixed)     */
    float rise_hold_s;           /**< stage 2b command-zero hold */
    float rise_window_s;         /**< stage 2b rise window (whole seconds) */
    float rise_min_k;            /**< stage 2b minimum rise */
} psup_params_t;

typedef enum {
    PSUP_OK = 0,
    PSUP_LATCH_DISOBEY = 1,      /**< 2a: current while commanded off */
    PSUP_LATCH_RISING = 2,       /**< 2b: still rising with no command */
} psup_latch_t;

typedef struct {
    /* R1 */
    bool r1_have_block;
    bool r1_have_prev;
    uint32_t r1_block_start_ms;
    double r1_sum;
    uint32_t r1_n;
    float r1_prev_mean;
    uint8_t r1_count;
    float r1_last_rise;
} psup_rate_t;

typedef struct {
    psup_params_t p;
    psup_rate_t rate;
    /* R2 */
    float zero_cmd_s;
    float disobey_s;
    float p_hist[8];             /**< effective command, last periods  */
    uint8_t p_hist_n;
    float blk_acc;
    uint16_t blk_n;
    float blk[PSUP_MAX_BLOCKS];
    uint16_t blk_head;
    uint16_t blk_count;
    psup_latch_t latched;
} psup_t;

typedef struct {
    float t_hat_c;
    float t_raw_c;
    float setpoint_c;
    float p_cmd_w;             /**< power the loop asks for this period */
    float bus_current_a;
    bool current_valid;
} psup_input_t;

typedef struct {
    bool force_zero;           /**< stage 1: command 0 this period      */
    psup_latch_t latch;        /**< latched result (sticky)              */
    float rise_k;              /**< 2b window rise, for logging          */
} psup_output_t;

void psup_default_params(psup_params_t *p);
bool psup_init(psup_t *s, const psup_params_t *p);

/** R1: feed every raw reading (10 ms ticks). Returns true when it trips. */
bool psup_rate_sample(psup_t *s, float t_raw_c, uint32_t now_ms);
/** R1: forget history (state_machine_reset_temp_baseline). */
void psup_rate_reset(psup_t *s);

/** R2: one 10 Hz period. */
void psup_step(psup_t *s, const psup_input_t *in, psup_output_t *out);
/** R2: forget history and the latch at PREHEAT entry (the state machine
 *  holds the latched fault). */
void psup_r2_reset(psup_t *s);

#ifdef __cplusplus
}
#endif

#endif /* PAN_SUPERVISOR_H */
