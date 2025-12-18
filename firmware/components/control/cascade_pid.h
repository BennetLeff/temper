/**
 * @file cascade_pid.h
 * @brief Cascade PID temperature controller for induction cooker
 * 
 * Implements dual-loop cascade control:
 * - Outer loop: Liquid temperature (slow, ~30s time constant)
 * - Inner loop: Pan temperature (fast, ~2s time constant)
 * 
 * Prevents pan scorching while heating liquids to target temperature.
 */

#ifndef CASCADE_PID_H
#define CASCADE_PID_H

#include <stdint.h>
#include <stdbool.h>
#include "pid_control.h"

#ifdef __cplusplus
extern "C" {
#endif

/**
 * @brief Cascade controller modes
 */
typedef enum {
    CASCADE_MODE_SINGLE,    /**< Single-loop: pan temp only */
    CASCADE_MODE_DUAL,      /**< Dual-loop: liquid + pan temp */
    CASCADE_MODE_ERROR      /**< Error state */
} cascade_mode_t;

/**
 * @brief Probe insertion state
 */
typedef enum {
    PROBE_STATE_UNKNOWN,
    PROBE_STATE_AIR,
    PROBE_STATE_FOOD
} probe_insertion_state_t;

/**
 * @brief Cascade PID controller handle
 */
typedef struct {
    /* Control mode */
    cascade_mode_t mode;           /**< Current control mode */
    bool probe_connected;          /**< Liquid probe status */
    bool probe_in_food;            /**< Liquid probe in food status */
    bool probe_detection_enabled;  /**< Enable probe insertion detection */
    
    /* PID controllers */
    pid_handle_t outer_pid;        /**< Outer loop: liquid temp → pan setpoint */
    pid_handle_t inner_pid;        /**< Inner loop: pan temp → PWM output */
    
    /* Configuration */
    float outer_time_constant;     /**< Outer loop time constant (seconds) */
    float inner_time_constant;     /**< Inner loop time constant (seconds) */
    float pan_temp_limit_min;      /**< Minimum pan temp limit (°C) */
    float pan_temp_limit_max;      /**< Maximum pan temp limit (°C) */
    float probe_timeout_sec;       /**< Probe disconnection timeout */
    
    /* State tracking */
    uint32_t last_probe_reading_time; /**< Timestamp of last valid probe reading */
    float last_pan_setpoint;       /**< Last pan setpoint for bumpless transfer */
    bool bumpless_transfer_pending; /**< Pending bumpless transfer */
    float last_stable_temp;        /**< Temperature for delta-T check */
    uint32_t probe_state_timer_ms;  /**< Timer for state transitions */
    probe_insertion_state_t probe_state; /**< Current filtered state */
    
    /* Performance monitoring */
    float outer_error_sum;         /**< Accumulated outer loop error */
    float inner_error_sum;         /**< Accumulated inner loop error */
    uint32_t mode_switches;        /**< Number of mode switches */
} cascade_pid_handle_t;

/**
 * @brief Initialize cascade PID controller
 * 
 * @param cascade Pointer to cascade handle
 * @param outer_kp Outer loop proportional gain
 * @param outer_ki Outer loop integral gain  
 * @param outer_kd Outer loop derivative gain
 * @param inner_kp Inner loop proportional gain
 * @param inner_ki Inner loop integral gain
 * @param inner_kd Inner loop derivative gain
 */
void cascade_pid_init(cascade_pid_handle_t *cascade,
                     float outer_kp, float outer_ki, float outer_kd,
                     float inner_kp, float inner_ki, float inner_kd);

/**
 * @brief Set cascade controller configuration
 * 
 * @param cascade Pointer to cascade handle
 * @param outer_tau Outer loop time constant (seconds)
 * @param inner_tau Inner loop time constant (seconds)
 * @param pan_min Minimum pan temperature limit (°C)
 * @param pan_max Maximum pan temperature limit (°C)
 * @param probe_timeout Probe disconnection timeout (seconds)
 */
void cascade_pid_configure(cascade_pid_handle_t *cascade,
                          float outer_tau, float inner_tau,
                          float pan_min, float pan_max,
                          float probe_timeout_sec);

/**
 * @brief Update cascade controller
 * 
 * @param cascade Pointer to cascade handle
 * @param liquid_target Target liquid temperature (°C)
 * @param liquid_actual Actual liquid temperature (°C, 0 if probe disconnected)
 * @param pan_actual Actual pan temperature (°C)
 * @param dt_sec Time step in seconds
 * @return PWM duty cycle output (0-100%)
 */
float cascade_pid_update(cascade_pid_handle_t *cascade,
                        float liquid_target, float liquid_actual,
                        float pan_actual, float dt_sec);

/**
 * @brief Get current control mode
 * 
 * @param cascade Pointer to cascade handle
 * @return Current cascade mode
 */
cascade_mode_t cascade_pid_get_mode(cascade_pid_handle_t *cascade);

/**
 * @brief Check if probe is connected and valid
 * 
 * @param cascade Pointer to cascade handle
 * @return true if probe is connected and providing valid readings
 */
bool cascade_pid_probe_connected(cascade_pid_handle_t *cascade);

/**
 * @brief Check if probe is detected to be in food (high thermal mass)
 * 
 * @param cascade Pointer to cascade handle
 * @return true if probe is in food
 */
bool cascade_pid_is_probe_in_food(cascade_pid_handle_t *cascade);

/**
 * @brief Enable or disable automatic probe insertion detection
 * 
 * @param cascade Pointer to cascade handle
 * @param enabled true to enable
 */
void cascade_pid_set_probe_detection(cascade_pid_handle_t *cascade, bool enabled);

/**
 * @brief Force single-loop mode (for testing or fallback)
 * 
 * @param cascade Pointer to cascade handle
 */
void cascade_pid_force_single_loop(cascade_pid_handle_t *cascade);

/**
 * @brief Reset cascade controller state
 * 
 * @param cascade Pointer to cascade handle
 */
void cascade_pid_reset(cascade_pid_handle_t *cascade);

/**
 * @brief Get controller performance metrics
 * 
 * @param cascade Pointer to cascade handle
 * @param outer_error Pointer to store outer loop RMS error
 * @param inner_error Pointer to store inner loop RMS error
 * @param switches Pointer to store mode switch count
 */
void cascade_pid_get_metrics(cascade_pid_handle_t *cascade,
                           float *outer_error, float *inner_error,
                           uint32_t *switches);

/**
 * @brief Set pan temperature limits
 * 
 * @param cascade Pointer to cascade handle
 * @param min Minimum pan temperature (°C)
 * @param max Maximum pan temperature (°C)
 */
void cascade_pid_set_pan_limits(cascade_pid_handle_t *cascade, float min, float max);

/**
 * @brief Default cascade controller initialization
 * 
 * Uses tuned gains for induction cooker application:
 * - Outer loop: Slow response for liquid heating
 * - Inner loop: Fast response for pan temperature limiting
 */
void cascade_pid_init_default(cascade_pid_handle_t *cascade);

#ifdef __cplusplus
}
#endif

#endif /* CASCADE_PID_H */