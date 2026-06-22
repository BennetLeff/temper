/**
 * @file state_handlers.h
 * @brief Per-state entry and update handler declarations
 *
 * Extracted from state_machine.c so the state machine orchestration shell
 * stays under the 1000-line cap. All 16 handlers (entry + update for each
 * of the 8 states) are declared here and implemented in state_handlers.c.
 */

#ifndef STATE_HANDLERS_H
#define STATE_HANDLERS_H

#include "state_machine.h"
#include <stdint.h>
#include <stdbool.h>
#include "../components/control/thermal_mass.h"
#include "../components/control/profiles.h"

#ifdef __cplusplus
extern "C" {
#endif

/** @brief State machine runtime context (defined in state_machine.c). */
typedef struct {
    system_state_t current_state;
    system_state_t previous_state;
    fault_code_t fault_code;
    uint32_t state_entry_time;
    uint32_t state_duration;

    uint8_t pan_detect_confidence;
    uint8_t pan_absent_count;
    float initial_pan_impedance;
    float cooldown_start_temp;
    uint16_t countdown_timer_ms;

    float target_temperature;
    uint32_t cooking_time_ms;
    bool cooking_timer_enabled;
    uint8_t intensity_level;

    profile_status_t profile;

    bool message_pending;
    system_state_t message_next_state;
    uint32_t message_start_time;

    uint32_t last_update_time_ms;

    thermal_mass_handle_t thermal_mass;
    bool thermal_mass_estimation_done;

    float last_pan_temp;
    uint8_t pan_temp_stuck_count;
    float last_heatsink_temp;
    uint8_t heatsink_temp_stuck_count;
} sm_context_t;

extern sm_context_t sm_ctx;

/* ---- State handler functions (16 total) ---- */
void state_init_entry(void);
void state_init_update(void);
void state_idle_entry(void);
void state_idle_update(void);
void state_pan_det_entry(void);
void state_pan_det_update(void);
void state_preheat_entry(void);
void state_preheat_update(void);
void state_heating_entry(void);
void state_heating_update(void);
void state_no_pan_entry(void);
void state_no_pan_update(void);
void state_cooldown_entry(void);
void state_cooldown_update(void);
void state_fault_entry(void);
void state_fault_update(void);

/* ---- Helpers shared with handlers (defined in state_machine.c) ---- */
void transition_to(system_state_t new_state);
bool run_self_test(void);
void check_safety_interlocks(void);
bool fault_cleared(void);
void show_message_then_transition(const char *msg, system_state_t next_state);

#ifdef __cplusplus
}
#endif

#endif /* STATE_HANDLERS_H */
