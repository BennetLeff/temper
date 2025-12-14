/**
 * @file pid_control.h
 * @brief PID temperature controller for induction cooker
 * 
 * Implements robust PID with:
 * - Anti-windup (integrator clamping)
 * - Derivative on measurement (avoids setpoint kick)
 * - Output saturation
 */

#ifndef PID_CONTROL_H
#define PID_CONTROL_H

#include <stdint.h>
#include <stdbool.h>

#ifdef __cplusplus
extern "C" {
#endif

/**
 * @brief PID controller handle
 */
typedef struct {
    /* Tuning parameters */
    float kp;               /**< Proportional gain */
    float ki;               /**< Integral gain */
    float kd;               /**< Derivative gain */
    
    /* Output limits */
    float output_min;       /**< Minimum output (typically 0%) */
    float output_max;       /**< Maximum output (typically 100%) */
    float integrator_limit; /**< Anti-windup limit for I-term */
    
    /* Internal state */
    float integrator;       /**< Accumulated integral error */
    float prev_error;       /**< Previous error (for derivative) */
    float prev_measurement; /**< Previous measurement (derivative on measurement) */
} pid_handle_t;

/**
 * @brief Initialize PID controller with gains
 * 
 * @param pid   Pointer to PID handle
 * @param kp    Proportional gain
 * @param ki    Integral gain
 * @param kd    Derivative gain
 */
void pid_init(pid_handle_t *pid, float kp, float ki, float kd);

/**
 * @brief Set PID tuning parameters
 * 
 * @param pid   Pointer to PID handle
 * @param kp    Proportional gain
 * @param ki    Integral gain
 * @param kd    Derivative gain
 */
void pid_set_tuning(float kp, float ki, float kd);

/**
 * @brief Reset integrator to zero
 */
void pid_reset_integral(void);

/**
 * @brief Compute PID output
 * 
 * @param pid         Pointer to PID handle
 * @param setpoint    Target value (temperature in °C)
 * @param measurement Current measured value (temperature in °C)
 * @param dt_sec      Time since last update in seconds
 * @return Output value (duty cycle 0-100%)
 */
float pid_compute(pid_handle_t *pid, float setpoint, float measurement, float dt_sec);

/**
 * @brief Simplified update function using global PID instance
 * 
 * @param setpoint    Target temperature
 * @param measurement Current temperature
 * @return Output duty cycle (0-100%)
 */
float pid_update(float setpoint, float measurement);

/**
 * @brief Set output limits
 * 
 * @param pid Pointer to PID handle
 * @param min Minimum output
 * @param max Maximum output
 */
void pid_set_output_limits(pid_handle_t *pid, float min, float max);

/**
 * @brief Set integrator anti-windup limit
 * 
 * @param pid   Pointer to PID handle
 * @param limit Maximum integrator contribution
 */
void pid_set_integrator_limit(pid_handle_t *pid, float limit);

#ifdef __cplusplus
}
#endif

#endif /* PID_CONTROL_H */
