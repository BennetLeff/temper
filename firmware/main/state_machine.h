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
 * @brief System states
 */
typedef enum {
    STATE_INIT,         /**< Power-on self-test */
    STATE_IDLE,         /**< Standby (no heating) */
    STATE_PAN_DET,      /**< Pan detection */
    STATE_PREHEAT,      /**< Aggressive heating to target */
    STATE_HEATING,      /**< Precision PID control */
    STATE_NO_PAN,       /**< Pan removed (brief pause) */
    STATE_COOLDOWN,     /**< Active cooling after stop */
    STATE_FAULT         /**< Lockout (requires user reset) */
} system_state_t;

/**
 * @brief Fault codes
 */
typedef enum {
    FAULT_NONE = 0,
    FAULT_OVER_TEMP,            /**< Heatsink >100°C */
    FAULT_OVER_CURRENT,         /**< DC bus current >35A */
    FAULT_FAN_FAILURE,          /**< Fan tachometer = 0 */
    FAULT_PROBE_OPEN,           /**< RTD resistance >10kΩ */
    FAULT_PROBE_SHORT,          /**< RTD resistance <10Ω */
    FAULT_THERMAL_RUNAWAY,      /**< Temp rising with power off */
    FAULT_SELF_TEST_FAILED,     /**< POST failed */
    FAULT_WATCHDOG_RESET,       /**< Software crash */
    FAULT_COOLDOWN_OVERHEAT,    /**< Temp rising in cooldown */
    FAULT_PAN_DETECT_HW         /**< Pan detection hardware issue */
} fault_code_t;

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
