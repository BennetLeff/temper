#ifndef TEMPER_ENERGY_SUPERVISOR_H
#define TEMPER_ENERGY_SUPERVISOR_H
#include <stdbool.h>
#include <stdint.h>
/* Portable supervisor logic. Execute on the independently AUX-powered owner,
 * not on the downstream controller which is unpowered during precharge. */
typedef enum { ENERGY_OFF, ENERGY_PRECHARGE, ENERGY_BYPASS_CLOSE,
    ENERGY_BYPASS_PROVE, ENERGY_RAIL_QUALIFY, ENERGY_READY, ENERGY_RUN,
    ENERGY_DISCHARGE, ENERGY_FAULT } energy_state_t;
typedef enum { ENERGY_OK, ENERGY_BAD_SAMPLE, ENERGY_STOP, ENERGY_TIMEOUT,
    ENERGY_CONTACT, ENERGY_RAIL, ENERGY_LIMIT, ENERGY_PWM, ENERGY_CONFIG } energy_fault_t;
typedef struct {
    bool commissioned; /* No default authorization to energize proposed hardware. */
    uint32_t precharge_ms, bypass_close_ms, proof_ms, attempt_ms, rail_ms;
    uint32_t retry_ms, discharge_stable_ms, sample_max_age_ms;
    float bus_max_v, catch_max_v, tank_max_v, inlet_max_a;
} energy_config_t;
typedef struct {
    uint32_t now_ms, sampled_ms;
    uint32_t manual_post_serial; /* Nonzero, new record for every attempt. */
    bool start, reset, off_request, stop_ok, aux_ok, sensors_valid, hardware_ok;
    bool hardware_latch_ok, catch_charge_proven;
    bool k1_released, k2_released, kb_released;
    bool manual_post_ok, resistor_cool, receiver_ok;
    /* These are qualified electrical tests, not open mirror contacts. */
    bool precharge_complete, bypass_closed_electrically, proof_current_valid;
    bool rails_ok, bus_fault, interlock_ok, controller_alive;
    bool pwm_qualified, heat_request;
    uint8_t valid_line_cycles;
    float bus_v, catch_v, tank_abs_v, line_rms_v, inlet_rms_a;
} energy_inputs_t;
typedef struct { bool k1, k2, kb, kt, sup_run_ok, reset_ok; } energy_outputs_t;
typedef struct {
    energy_state_t state;
    energy_fault_t fault;
    energy_config_t cfg;
    energy_outputs_t out;
    uint32_t entered_ms, attempt_ms, lockout_ms, safe_since_ms, previous_ms;
    uint32_t used_post_serial, proof_since_ms;
    bool proof_timing;
    bool reset_armed;
    bool start_released, reset_released, safe_timing, configured;
} energy_supervisor_t;
energy_config_t energy_study_config(void);
void energy_supervisor_init(energy_supervisor_t *, const energy_config_t *, uint32_t now_ms);
void energy_supervisor_step(energy_supervisor_t *, const energy_inputs_t *);
#endif
