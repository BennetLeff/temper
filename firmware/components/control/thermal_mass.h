/**
 * @file thermal_mass.h
 * @brief Thermal mass estimation for pan classification
 * 
 * Estimates pan thermal mass during detection phase to auto-tune PID gains.
 * Classifies pans as light, medium, or heavy based on thermal response.
 */

#ifndef THERMAL_MASS_H
#define THERMAL_MASS_H

#include <stdint.h>
#include <stdbool.h>

#ifdef __cplusplus
extern "C" {
#endif

/**
 * @brief Pan thermal mass classifications
 */
typedef enum {
    PAN_CLASS_UNKNOWN,    /**< Not yet classified */
    PAN_CLASS_LIGHT,      /**< Thin stainless, aluminum (fast response) */
    PAN_CLASS_MEDIUM,     /**< Standard cookware (balanced response) */
    PAN_CLASS_HEAVY,      /**< Cast iron, enameled (slow response) */
    PAN_CLASS_INVALID     /**< Measurement failed or invalid */
} pan_class_t;

/**
 * @brief Thermal mass estimation configuration
 */
typedef struct {
    float test_power_watts;        /**< Power level for test pulse (W) */
    uint32_t test_duration_ms;     /**< Duration of test pulse (ms) */
    float light_threshold;         /**< Threshold for light pan (J/K) */
    float medium_threshold;        /**< Threshold for medium pan (J/K) */
    uint8_t measurement_samples;   /**< Number of temperature samples */
    float min_temp_rise;           /**< Minimum temperature rise for valid test (°C) */
} thermal_mass_config_t;

/**
 * @brief PID gain sets for different pan types
 */
typedef struct {
    float kp;  /**< Proportional gain */
    float ki;  /**< Integral gain */
    float kd;  /**< Derivative gain */
} pid_gains_t;

/**
 * @brief Thermal mass estimation state
 */
typedef struct {
    thermal_mass_config_t config;      /**< Configuration parameters */
    pan_class_t current_class;         /**< Current pan classification */
    pid_gains_t current_gains;         /**< Current PID gains */
    bool estimation_active;            /**< Currently performing estimation */
    uint32_t estimation_start_time;    /**< Start time of estimation */
    float initial_temperature;         /**< Initial pan temperature */
    float test_power_level;            /**< Power level during test */
    uint8_t sample_count;              /**< Number of samples collected */
    float temperature_sum;             /**< Sum of temperature readings */
    bool classification_valid;         /**< Classification result is valid */
} thermal_mass_handle_t;

/**
 * @brief Initialize thermal mass estimation module
 * 
 * @param handle Pointer to thermal mass handle
 * @param config Configuration parameters (use NULL for defaults)
 */
void thermal_mass_init(thermal_mass_handle_t *handle, const thermal_mass_config_t *config);

/**
 * @brief Start thermal mass estimation
 * 
 * Begins a test sequence to measure pan thermal mass.
 * Should be called when entering PAN_DET state.
 * 
 * @param handle Pointer to thermal mass handle
 * @param initial_temp Initial pan temperature (°C)
 * @return true if estimation started successfully
 */
bool thermal_mass_start_estimation(thermal_mass_handle_t *handle, float initial_temp);

/**
 * @brief Update thermal mass estimation
 * 
 * Call this periodically during PAN_DET state.
 * Applies test power pulse and collects temperature samples.
 * 
 * @param handle Pointer to thermal mass handle
 * @param current_temp Current pan temperature (°C)
 * @param current_time_ms Current time in milliseconds
 * @return true if estimation is complete
 */
bool thermal_mass_update(thermal_mass_handle_t *handle, float current_temp, uint32_t current_time_ms);

/**
 * @brief Get pan classification
 * 
 * @param handle Pointer to thermal mass handle
 * @return Pan classification (UNKNOWN if not yet classified)
 */
pan_class_t thermal_mass_get_classification(thermal_mass_handle_t *handle);

/**
 * @brief Get PID gains for current pan classification
 * 
 * @param handle Pointer to thermal mass handle
 * @return PID gains structure
 */
pid_gains_t thermal_mass_get_pid_gains(thermal_mass_handle_t *handle);

/**
 * @brief Check if estimation is active
 * 
 * @param handle Pointer to thermal mass handle
 * @return true if estimation is currently in progress
 */
bool thermal_mass_is_active(thermal_mass_handle_t *handle);

/**
 * @brief Check if classification is valid
 * 
 * @param handle Pointer to thermal mass handle
 * @return true if classification has been completed successfully
 */
bool thermal_mass_is_classified(thermal_mass_handle_t *handle);

/**
 * @brief Reset thermal mass estimation
 * 
 * Clears current classification and gains.
 * Call this when pan is removed or system resets.
 * 
 * @param handle Pointer to thermal mass handle
 */
void thermal_mass_reset(thermal_mass_handle_t *handle);

/**
 * @brief Get default configuration
 * 
 * @return Default thermal mass configuration
 */
thermal_mass_config_t thermal_mass_get_default_config(void);

/**
 * @brief Get PID gains for specific pan class
 * 
 * @param pan_class Pan classification
 * @return PID gains for the specified class
 */
pid_gains_t thermal_mass_get_gains_for_class(pan_class_t pan_class);

/**
 * @brief Get classification name as string
 * 
 * @param pan_class Pan classification
 * @return String representation of classification
 */
const char* thermal_mass_class_to_string(pan_class_t pan_class);

/**
 * @brief Validate temperature reading for estimation
 * 
 * Checks if temperature reading is valid for thermal mass estimation.
 * 
 * @param temp Temperature to validate (°C)
 * @return true if temperature is valid
 */
bool thermal_mass_validate_temperature(float temp);

#ifdef __cplusplus
}
#endif

#endif /* THERMAL_MASS_H */