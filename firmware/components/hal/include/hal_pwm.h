/**
 * @file hal_pwm.h
 * @brief PWM Hardware Abstraction Layer
 * 
 * Provides platform-independent PWM operations for:
 * - Single-channel PWM
 * - Complementary PWM with dead-time (for half-bridge)
 * - Frequency adjustment (for PLL tracking)
 * 
 * Used by:
 * - Gate driver (UCC21550) control
 * - PLL frequency tracking for ZVS
 * - Fan speed control
 */

#ifndef HAL_PWM_H
#define HAL_PWM_H

#include "hal_types.h"

#ifdef __cplusplus
extern "C" {
#endif

/**
 * @brief PWM channel state (for verification/testing)
 */
typedef struct {
    uint32_t frequency_hz;      /**< Current frequency */
    float duty_percent;         /**< Current duty cycle */
    uint16_t dead_time_ns;      /**< Current dead-time */
    bool running;               /**< PWM is active */
    bool complementary;         /**< Complementary mode enabled */
} hal_pwm_state_t;

/**
 * @brief PWM operations interface
 */
typedef struct {
    /**
     * @brief Initialize PWM channel
     * 
     * @param channel PWM channel identifier
     * @param config PWM configuration
     * @return HAL_OK on success
     */
    hal_status_t (*init)(hal_pwm_channel_t channel, const hal_pwm_config_t *config);
    
    /**
     * @brief Set PWM frequency
     * 
     * For PLL tracking, this must update without glitches.
     * 
     * @param channel PWM channel
     * @param freq_hz Frequency in Hz
     * @return HAL_OK on success
     */
    hal_status_t (*set_frequency)(hal_pwm_channel_t channel, uint32_t freq_hz);
    
    /**
     * @brief Set PWM duty cycle
     * 
     * @param channel PWM channel
     * @param duty_percent Duty cycle (0-100%)
     * @return HAL_OK on success
     */
    hal_status_t (*set_duty)(hal_pwm_channel_t channel, float duty_percent);
    
    /**
     * @brief Set dead-time for complementary PWM
     * 
     * @param channel PWM channel
     * @param dead_time_ns Dead-time in nanoseconds
     * @return HAL_OK on success
     */
    hal_status_t (*set_dead_time)(hal_pwm_channel_t channel, uint16_t dead_time_ns);
    
    /**
     * @brief Start PWM output
     * 
     * @param channel PWM channel
     * @return HAL_OK on success
     */
    hal_status_t (*start)(hal_pwm_channel_t channel);
    
    /**
     * @brief Stop PWM output (outputs go low)
     * 
     * @param channel PWM channel
     * @return HAL_OK on success
     */
    hal_status_t (*stop)(hal_pwm_channel_t channel);
    
    /**
     * @brief Emergency stop all PWM channels
     * 
     * Forces all outputs low immediately.
     * Called by safety interlock on fault.
     * 
     * @return HAL_OK on success
     */
    hal_status_t (*emergency_stop)(void);
    
    /**
     * @brief Get current PWM state
     * 
     * Used for verification and testing.
     * 
     * @param channel PWM channel
     * @param state Pointer to store state
     * @return HAL_OK on success
     */
    hal_status_t (*get_state)(hal_pwm_channel_t channel, hal_pwm_state_t *state);
    
    /**
     * @brief Deinitialize PWM channel
     * 
     * @param channel PWM channel
     * @return HAL_OK on success
     */
    hal_status_t (*deinit)(hal_pwm_channel_t channel);
} hal_pwm_ops_t;

/**
 * @brief Global PWM operations pointer
 */
extern const hal_pwm_ops_t *hal_pwm;

/**
 * @brief Set PWM operations implementation
 */
void hal_pwm_set_ops(const hal_pwm_ops_t *ops);

/* ============================================================================
 * Convenience Macros
 * ============================================================================ */

/**
 * @brief Set PWM duty cycle (convenience wrapper)
 */
#define HAL_PWM_SET_DUTY(channel, duty) \
    (hal_pwm ? hal_pwm->set_duty((channel), (duty)) : HAL_ERROR_NOT_READY)

/**
 * @brief Set PWM frequency (convenience wrapper)
 */
#define HAL_PWM_SET_FREQ(channel, freq) \
    (hal_pwm ? hal_pwm->set_frequency((channel), (freq)) : HAL_ERROR_NOT_READY)

/**
 * @brief Emergency stop all PWM (convenience wrapper)
 */
#define HAL_PWM_EMERGENCY_STOP() \
    (hal_pwm ? hal_pwm->emergency_stop() : HAL_ERROR_NOT_READY)

#ifdef __cplusplus
}
#endif

#endif /* HAL_PWM_H */
