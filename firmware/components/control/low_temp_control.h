/**
 * @file low_temp_control.h
 * @brief Low-temperature (30°C-50°C) control logic
 * 
 * Uses burst-mode PWM and frequency detuning to achieve 
 * stable, low-power heating for delicate culinary tasks.
 */

#ifndef LOW_TEMP_CONTROL_H
#define LOW_TEMP_CONTROL_H

#include <stdint.h>
#include <stdbool.h>

#ifdef __cplusplus
extern "C" {
#endif

/**
 * @brief Low-temperature configuration
 */
typedef struct {
    float burst_duration_ms;    /**< Duration of heating burst */
    float min_period_ms;        /**< Minimum period (highest duty cycle) */
    float max_period_ms;        /**< Maximum period (lowest duty cycle) */
    uint32_t detune_freq_hz;    /**< Operating frequency during burst */
    float kp;                   /**< Low-temp PID proportional gain */
    float ki;                   /**< Low-temp PID integral gain */
    float kd;                   /**< Low-temp PID derivative gain */
} low_temp_config_t;

/**
 * @brief Initialize low-temperature control module
 */
void low_temp_init(void);

/**
 * @brief Start low-temperature control at specific setpoint
 * @param target_temp_c Target temperature (30-50°C)
 */
void low_temp_start(float target_temp_c);

/**
 * @brief Update low-temp control loop
 * 
 * Should be called periodically (e.g. 10Hz) from the heating state update.
 * Manages burst-mode PWM and frequency detuning.
 * 
 * @param current_temp_c Current measured temperature
 * @return True if in burst (heating), false otherwise
 */
bool low_temp_update(float current_temp_c);

/**
 * @brief Stop low-temp control and reset state
 */
void low_temp_stop(void);

/**
 * @brief Check if low-temp control is active
 */
bool low_temp_is_active(void);

/**
 * @brief Get current configuration
 */
const low_temp_config_t* low_temp_get_config(void);

/**
 * @brief Get current operating frequency for ZVS
 * 
 * @return Frequency in Hz
 */
uint32_t low_temp_get_frequency(void);

#ifdef __cplusplus
}
#endif

#endif /* LOW_TEMP_CONTROL_H */
