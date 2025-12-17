/**
 * @file low_temp_control.h
 * @brief Low-temperature control for chocolate tempering and delicate sauces (30-50°C)
 * 
 * Implements Burst-Mode PWM with frequency detuning to achieve stable low-power
 * heating (~50W) without thermal runaway.
 */

#ifndef LOW_TEMP_CONTROL_H
#define LOW_TEMP_CONTROL_H

#include <stdint.h>
#include <stdbool.h>

#ifdef __cplusplus
extern "C" {
#endif

/**
 * @brief Configuration for low-temperature operation
 */
typedef struct {
    float burst_duration_ms;    /**< Duration of heating pulse (100-500ms) */
    float burst_period_min_ms;  /**< Minimum period between bursts (1000ms) */
    float burst_period_max_ms;  /**< Maximum period between bursts (10000ms) */
    float detune_frequency_hz;  /**< Frequency further from resonance (45000-50000 Hz) */
    float pid_kp;               /**< Proportional gain for low-temp range */
    float pid_ki;               /**< Integral gain for low-temp range */
    float pid_kd;               /**< Derivative gain for low-temp range */
} low_temp_config_t;

/**
 * @brief Initialize low-temp control module
 */
void low_temp_init(void);

/**
 * @brief Start low-temp control session
 * 
 * @param target_temp Target temperature in °C (30-50°C)
 */
void low_temp_start(float target_temp);

/**
 * @brief Stop low-temp control session
 */
void low_temp_stop(void);

/**
 * @brief Update low-temp control loop
 * 
 * Should be called at a regular interval (e.g. 10ms).
 * 
 * @param current_temp Current measured pan temperature
 * @return true if currently in the "ON" part of the burst
 */
bool low_temp_update(float current_temp);

/**
 * @brief Check if low-temp control is currently active
 * 
 * @return true if active
 */
bool low_temp_is_active(void);

/**
 * @brief Get current configuration
 */
const low_temp_config_t* low_temp_get_config(void);

#ifdef __cplusplus
}
#endif

#endif /* LOW_TEMP_CONTROL_H */
