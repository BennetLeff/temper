/**
 * @file state_machine.h
 * @brief State machine for induction cooker operation
 * 
 * Coordinates all system operations:
 * - Power-on self-test (POST)
 * - Pan detection
 * - Heating control (preheat + precision)
 * - Safety monitoring
 * - Fault recovery
 */

#ifndef STATE_MACHINE_H
#define STATE_MACHINE_H

#include <stdint.h>
#include <stdbool.h>

#ifdef __cplusplus
extern "C" {
#endif

/**
 * @brief System states — single-source list (X-macro)
 *
 * Add a state: add one X(STATE_NAME, "STRING") line.
 * The enum, STATE_COUNT sentinel, and string-name table
 * all expand from this list automatically.
 */
#define STATE_LIST(X) \
    X(STATE_INIT,     "INIT") \
    X(STATE_IDLE,     "IDLE") \
    X(STATE_PAN_DET,  "PAN_DET") \
    X(STATE_PREHEAT,  "PREHEAT") \
    X(STATE_HEATING,  "HEATING") \
    X(STATE_NO_PAN,   "NO_PAN") \
    X(STATE_COOLDOWN, "COOLDOWN") \
    X(STATE_FAULT,    "FAULT")

#define EXPAND_STATE_ENUM(sym, str)  sym,
typedef enum {
    STATE_LIST(EXPAND_STATE_ENUM)
    STATE_COUNT
} system_state_t;
#undef EXPAND_STATE_ENUM

#define EXPAND_STATE_NAME(sym, str)  { sym, str },
typedef struct { system_state_t value; const char *name; } state_name_entry_t;
static const state_name_entry_t state_name_table[] = {
    STATE_LIST(EXPAND_STATE_NAME)
};
#undef EXPAND_STATE_NAME

/**
 * @brief Fault codes — single-source list (X-macro)
 *
 * Add a fault: add one X(FAULT_NAME, "STRING") line.
 * The enum, FAULT_COUNT sentinel, and string-name table
 * all expand from this list automatically.
 */
#define FAULT_LIST(X) \
    X(FAULT_NONE,             "NO FAULT") \
    X(FAULT_OVER_TEMP,        "OVER TEMP") \
    X(FAULT_OVER_CURRENT,     "OVER CURRENT") \
    X(FAULT_FAN_FAILURE,      "FAN FAILED") \
    X(FAULT_PROBE_OPEN,       "PROBE OPEN") \
    X(FAULT_PROBE_SHORT,      "PROBE SHORT") \
    X(FAULT_THERMAL_RUNAWAY,  "THERMAL RUNAWAY") \
    X(FAULT_SELF_TEST_FAILED, "SELF TEST FAIL") \
    X(FAULT_WATCHDOG_RESET,   "WATCHDOG RESET") \
    X(FAULT_COOLDOWN_OVERHEAT,"COOLDOWN FAULT") \
    X(FAULT_PAN_DETECT_HW,    "PAN DETECT HW")

#define EXPAND_FAULT_ENUM(sym, str)  sym,
typedef enum {
    FAULT_LIST(EXPAND_FAULT_ENUM)
    FAULT_COUNT
} fault_code_t;
#undef EXPAND_FAULT_ENUM

#define EXPAND_FAULT_NAME(sym, str)  { sym, str },
typedef struct { fault_code_t value; const char *name; } fault_name_entry_t;
static const fault_name_entry_t fault_name_table[] = {
    FAULT_LIST(EXPAND_FAULT_NAME)
};
#undef EXPAND_FAULT_NAME

/**
 * @brief Event types — single-source list (X-macro)
 *
 * Add an event: add one X(EVENT_NAME, "STRING") line.
 * The enum, EVENT_COUNT sentinel, and string-name table
 * all expand from this list automatically.
 */
#define EVENT_LIST(X) \
    X(EVENT_SELFTEST_PASS,       "SELFTEST_PASS") \
    X(EVENT_SELFTEST_FAIL,       "SELFTEST_FAIL") \
    X(EVENT_START_BUTTON,        "START_BUTTON") \
    X(EVENT_PAN_DETECTED,        "PAN_DETECTED") \
    X(EVENT_PAN_TIMEOUT,         "PAN_TIMEOUT") \
    X(EVENT_NEAR_TARGET,         "NEAR_TARGET") \
    X(EVENT_PREHEAT_TIMEOUT,     "PREHEAT_TIMEOUT") \
    X(EVENT_OVER_TEMP,           "OVER_TEMP") \
    X(EVENT_OVER_CURRENT,        "OVER_CURRENT") \
    X(EVENT_FAN_FAILURE,         "FAN_FAILURE") \
    X(EVENT_PROBE_OPEN,          "PROBE_OPEN") \
    X(EVENT_PROBE_SHORT,         "PROBE_SHORT") \
    X(EVENT_THERMAL_RUNAWAY,     "THERMAL_RUNAWAY") \
    X(EVENT_PAN_REMOVED,         "PAN_REMOVED") \
    X(EVENT_STOP_BUTTON,         "STOP_BUTTON") \
    X(EVENT_TIMER_EXPIRED,       "TIMER_EXPIRED") \
    X(EVENT_PAN_REPLACED_SAME,   "PAN_REPLACED_SAME") \
    X(EVENT_PAN_REPLACED_DIFFERENT, "PAN_REPLACED_DIFFERENT") \
    X(EVENT_NO_PAN_TIMEOUT,      "NO_PAN_TIMEOUT") \
    X(EVENT_COOLED_DOWN,         "COOLED_DOWN") \
    X(EVENT_COOLDOWN_OVERHEAT,   "COOLDOWN_OVERHEAT") \
    X(EVENT_FAULT_RESET_CLEARED, "FAULT_RESET_CLEARED") \
    X(EVENT_FAULT_RESET_PERSISTS,"FAULT_RESET_PERSISTS")

#define EXPAND_EVENT_ENUM(sym, str)  sym,
typedef enum {
    EVENT_LIST(EXPAND_EVENT_ENUM)
    EVENT_COUNT
} event_t;
#undef EXPAND_EVENT_ENUM

#define EXPAND_EVENT_NAME(sym, str)  { sym, str },
typedef struct { event_t value; const char *name; } event_name_entry_t;
static const event_name_entry_t event_name_table[] = {
    EVENT_LIST(EXPAND_EVENT_NAME)
};
#undef EXPAND_EVENT_NAME

/**
 * @brief Button identifiers
 */
typedef enum {
    BUTTON_START,
    BUTTON_STOP,
    BUTTON_TEMP_UP,
    BUTTON_TEMP_DOWN,
    BUTTON_RESET
} button_id_t;

/**
 * @brief LED patterns
 */
typedef enum {
    LED_OFF,
    LED_STEADY_GREEN,
    LED_STEADY_ORANGE,
    LED_BLINK_SLOW,
    LED_BLINK_FAST,
    LED_FAULT
} led_pattern_t;

/**
 * @brief Fan speed settings
 */
typedef enum {
    FAN_SPEED_OFF,
    FAN_SPEED_MIN,
    FAN_SPEED_MEDIUM,
    FAN_SPEED_MAX
} fan_speed_t;

/* Forward declarations */
struct cooking_profile_t;

/**
 * @brief Initialize the state machine
 */
void state_machine_init(void);

/**
 * @brief Update state machine (call periodically)
 */
void state_machine_update(void);

/**
 * @brief Start a cooking profile
 * 
 * @param profile Pointer to profile definition
 */
void state_machine_start_profile(const struct cooking_profile_t *profile);

/**
 * @brief Set the target temperature
 * 
 * @param temp_celsius Target in °C
 */
void state_machine_set_target_temp(float temp_celsius);

/**
 * @brief Get current state
 * 
 * @return Current system state
 */
system_state_t state_machine_get_state(void);

/**
 * @brief Get current fault code
 * 
 * @return Active fault code (FAULT_NONE if no fault)
 */
fault_code_t state_machine_get_fault(void);

/**
 * @brief Get fault description string
 * 
 * @param code Fault code
 * @return Human-readable fault description
 */
const char* state_machine_get_fault_string(fault_code_t code);

/**
 * @brief Get state name string
 * 
 * @param state System state
 * @return Human-readable state name
 */
const char* state_machine_get_state_string(system_state_t state);

/**
 * @brief Get event name string
 *
 * @param event Event code
 * @return Human-readable event name
 */
const char* state_machine_get_event_string(event_t event);

/**
 * @brief Enable/disable cooking timer
 * 
 * @param enabled Timer enable flag
 * @param time_ms Timer duration in milliseconds
 */
void state_machine_set_timer(bool enabled, uint32_t time_ms);

/**
 * @brief Set intensity level (heat rate limiter)
 * 
 * @param level Intensity level (1-10)
 */
void state_machine_set_intensity(uint8_t level);

/**
 * @brief Get current intensity level
 * 
 * @return Current intensity level (1-10)
 */
uint8_t state_machine_get_intensity(void);

/**
 * @brief Force transition to specific state (for testing)
 * 
 * @param new_state Target state
 */
void state_machine_force_state(system_state_t new_state);

#ifdef __cplusplus
}
#endif

#endif /* STATE_MACHINE_H */
