/**
 * @file pwm_guard.h
 * @brief PWM Frequency and Configuration Validation
 * 
 * Provides safety mechanisms for the PWM generation:
 * - Startup self-test (verify frequency/deadtime)
 * - Runtime frequency monitoring via timer capture
 * - Configuration integrity checks (register CRC)
 * - Frequency boundary enforcement
 */

#ifndef PWM_GUARD_H
#define PWM_GUARD_H

#include "hal_types.h"
#include <stdint.h>
#include <stdbool.h>

#ifdef __cplusplus
extern "C" {
#endif

// Safety limits
#define PWM_GUARD_MIN_FREQ_HZ 25000
#define PWM_GUARD_MAX_FREQ_HZ 60000
#define PWM_GUARD_TARGET_FREQ_HZ 38000
#define PWM_GUARD_FREQ_TOLERANCE_PERCENT 5
#define PWM_GUARD_MIN_DEADTIME_NS 300
#define PWM_GUARD_MAX_DEADTIME_NS 1000

/**
 * @brief PWM Guard Failure Codes
 */
typedef enum {
    PWM_GUARD_OK = 0,
    PWM_GUARD_ERR_FREQ_LOW = 1,    // Frequency below minimum
    PWM_GUARD_ERR_FREQ_HIGH = 2,   // Frequency above maximum
    PWM_GUARD_ERR_DEADTIME = 3,    // Deadtime out of range
    PWM_GUARD_ERR_MISMATCH = 4,    // Measured freq != Configured freq
    PWM_GUARD_ERR_CORRUPTION = 5,  // Register CRC mismatch
    PWM_GUARD_ERR_NULL = 6         // Invalid pointer
} pwm_guard_status_t;

/**
 * @brief Initialize PWM guard
 * @param pwm_channel PWM channel to monitor
 * @param timer_channel Timer channel used for frequency capture
 */
void pwm_guard_init(hal_pwm_channel_t pwm_channel, hal_timer_t timer_channel);

/**
 * @brief Perform startup self-test
 * 
 * Verifies:
 * 1. Configured frequency is within bounds
 * 2. Read-back frequency matches target
 * 3. Dead-time is within safe limits
 * 
 * @return PWM_GUARD_OK or error code
 */
pwm_guard_status_t pwm_guard_self_test(void);

/**
 * @brief Runtime frequency integrity check
 * 
 * Measures actual output frequency using timer capture and compares
 * to expected target. Should be called periodically (e.g. 100ms).
 * 
 * @return PWM_GUARD_OK or error code
 */
pwm_guard_status_t pwm_guard_check_integrity(void);

/**
 * @brief Validate frequency setpoint before applying
 * 
 * @param freq_hz Target frequency
 * @return PWM_GUARD_OK if safe, error otherwise
 */
pwm_guard_status_t pwm_guard_validate_frequency(uint32_t freq_hz);

#ifdef __cplusplus
}
#endif

#endif /* PWM_GUARD_H */
