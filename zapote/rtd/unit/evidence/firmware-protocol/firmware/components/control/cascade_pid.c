/**
 * @file cascade_pid.c
 * @brief Cascade PID temperature controller implementation
 * 
 * Dual-loop cascade control system:
 * - Outer loop: Liquid temperature → Pan temperature setpoint
 * - Inner loop: Pan temperature → PWM output
 * 
 * Features:
 * - Automatic mode switching based on probe status
 * - Bumpless transfer between single/dual loop modes
 * - Pan temperature limiting to prevent scorching
 * - Performance monitoring and metrics
 */

#include "cascade_pid.h"
#include <math.h>
#include <stdbool.h>
#include <string.h>

/* Default configuration for induction cooker */
#define CASCADE_OUTER_TAU_DEFAULT    30.0f    /**< Outer loop time constant (s) */
#define CASCADE_INNER_TAU_DEFAULT    2.0f     /**< Inner loop time constant (s) */
#define CASCADE_PAN_TEMP_MIN         25.0f    /**< Minimum pan temp limit (°C) */
#define CASCADE_PAN_TEMP_MAX         200.0f   /**< Maximum pan temp limit (°C) */
#define CASCADE_PROBE_TIMEOUT        5.0f     /**< Probe timeout (s) */

/* Default PID gains (tuned for induction cooker) */
#define CASCADE_OUTER_KP     0.8f    /**< Outer loop proportional gain */
#define CASCADE_OUTER_KI     0.02f   /**< Outer loop integral gain */
#define CASCADE_OUTER_KD     2.0f    /**< Outer loop derivative gain */

#define CASCADE_INNER_KP     2.0f    /**< Inner loop proportional gain */
#define CASCADE_INNER_KI     0.1f    /**< Inner loop integral gain */
#define CASCADE_INNER_KD     0.05f   /**< Inner loop derivative gain */

/* Performance monitoring */
#define CASCADE_METRICS_WINDOW   100   /**< Number of samples for metrics */

/* Platform-specific time function */
#ifdef ESP_PLATFORM
#include "esp_timer.h"
static uint64_t get_time_us(void) {
    return esp_timer_get_time();
}
#else
/* Non-ESP fallback - assume constant dt */
static uint64_t s_simulated_time_us = 0;
static uint64_t get_time_us(void) {
    return s_simulated_time_us;
}
void cascade_pid_test_advance_time_us(uint64_t delta_us) {
    s_simulated_time_us += delta_us;
}
#endif

/* Probe detection constants */
#define PROBE_DETECTION_INTERVAL_MS 1000
#define PROBE_DT_THRESHOLD_FOOD     0.5f    /**< Max degC/sec for food (high mass) */
#define PROBE_DT_THRESHOLD_AIR      2.0f    /**< Min degC/sec for air (low mass) */
#define PROBE_STABLE_TIME_MS        5000    /**< Time to confirm state */

void cascade_pid_init(cascade_pid_handle_t *cascade,
                     float outer_kp, float outer_ki, float outer_kd,
                     float inner_kp, float inner_ki, float inner_kd) {
    /* Initialize structure */
    memset(cascade, 0, sizeof(cascade_pid_handle_t));
    
    /* Set initial mode */
    cascade->mode = CASCADE_MODE_SINGLE;
    cascade->probe_connected = false;
    cascade->probe_in_food = true; // Assume food until proven otherwise
    cascade->probe_detection_enabled = true;
    cascade->probe_state = PROBE_STATE_UNKNOWN;
    
    /* Initialize PID controllers */
    pid_init(&cascade->outer_pid, outer_kp, outer_ki, outer_kd);
    pid_init(&cascade->inner_pid, inner_kp, inner_ki, inner_kd);
    
    /* Configure output limits */
    pid_set_output_limits(&cascade->outer_pid, CASCADE_PAN_TEMP_MIN, CASCADE_PAN_TEMP_MAX);
    pid_set_output_limits(&cascade->inner_pid, 0.0f, 100.0f);
    
    /* Set integrator limits for anti-windup */
    pid_set_integrator_limit(&cascade->outer_pid, 25.0f);  /* Pan temp range */
    pid_set_integrator_limit(&cascade->inner_pid, 50.0f);  /* PWM range */
    
    /* Set default configuration */
    cascade_pid_configure(cascade, CASCADE_OUTER_TAU_DEFAULT, CASCADE_INNER_TAU_DEFAULT,
                         CASCADE_PAN_TEMP_MIN, CASCADE_PAN_TEMP_MAX, CASCADE_PROBE_TIMEOUT);
    
    /* Initialize state */
    cascade->last_pan_setpoint = CASCADE_PAN_TEMP_MIN;
    cascade->bumpless_transfer_pending = false;
    cascade->last_probe_reading_time = 0;
    
    /* Initialize metrics */
    cascade->outer_error_sum = 0.0f;
    cascade->inner_error_sum = 0.0f;
    cascade->mode_switches = 0;
}

void cascade_pid_configure(cascade_pid_handle_t *cascade,
                          float outer_tau, float inner_tau,
                          float pan_min, float pan_max,
                          float probe_timeout_sec) {
    cascade->outer_time_constant = outer_tau;
    cascade->inner_time_constant = inner_tau;
    cascade->pan_temp_limit_min = pan_min;
    cascade->pan_temp_limit_max = pan_max;
    cascade->probe_timeout_sec = probe_timeout_sec;
    
    /* Update PID output limits */
    pid_set_output_limits(&cascade->outer_pid, pan_min, pan_max);
}

static void update_probe_detection(cascade_pid_handle_t *cascade, float liquid_actual, float pwm_output, float dt_sec) {
    if (!cascade->probe_detection_enabled || !cascade->probe_connected) {
        cascade->probe_in_food = true;
        cascade->probe_state = PROBE_STATE_UNKNOWN;
        return;
    }

    // Only run detection if heater is significantly ON (>20%)
    if (pwm_output < 20.0f) {
        // If power is low, we can't reliably detect thermal mass via dT/dt
        // but we keep the last known state.
        return;
    }

    float rate = (liquid_actual - cascade->last_stable_temp) / dt_sec;
    cascade->last_stable_temp = liquid_actual;

    // Filtered state detection
    if (rate > PROBE_DT_THRESHOLD_AIR) {
        // Temp rising very fast -> likely in air
        if (cascade->probe_state != PROBE_STATE_AIR) {
            cascade->probe_state = PROBE_STATE_AIR;
            cascade->probe_state_timer_ms = 0;
        }
    } else if (rate < PROBE_DT_THRESHOLD_FOOD && rate > -0.1f) {
        // Temp stable or rising slowly -> likely in food
        if (cascade->probe_state != PROBE_STATE_FOOD) {
            cascade->probe_state = PROBE_STATE_FOOD;
            cascade->probe_state_timer_ms = 0;
        }
    }

    // Update transition timer
    cascade->probe_state_timer_ms += (uint32_t)(dt_sec * 1000.0f);

    // Confirm state after stability period
    if (cascade->probe_state_timer_ms >= PROBE_STABLE_TIME_MS) {
        if (cascade->probe_state == PROBE_STATE_AIR) {
            cascade->probe_in_food = false;
        } else if (cascade->probe_state == PROBE_STATE_FOOD) {
            cascade->probe_in_food = true;
        }
    }
}

float cascade_pid_update(cascade_pid_handle_t *cascade,
                        float liquid_target, float liquid_actual,
                        float pan_actual, float dt_sec) {
    
    /* Validate inputs */
    if (dt_sec <= 0.0f || !isfinite(dt_sec)) {
        dt_sec = 0.1f;  /* Fallback to 100ms */
    }
    
    /* Check for NaN/Inf in temperature inputs */
    if (!isfinite(liquid_target) || !isfinite(pan_actual)) {
        return 0.0f;  /* Safe output on invalid input */
    }
    
    /* Update probe connection status */
    uint64_t now_us = get_time_us();
    bool probe_valid = isfinite(liquid_actual) && liquid_actual > 5.0f && liquid_actual < 300.0f;
    
    if (probe_valid) {
        if (!cascade->probe_connected) {
            cascade->last_stable_temp = liquid_actual;
            cascade->probe_state_timer_ms = 0;
            cascade->probe_state = PROBE_STATE_UNKNOWN;
        }
        cascade->probe_connected = true;
        cascade->last_probe_reading_time = (uint32_t)(now_us / 1000000);  /* Convert to seconds */
    } else {
        cascade->probe_connected = false;
        cascade->probe_in_food = true; // Reset to safe default
    }
    
    /* Determine control mode */
    // Fallback to single-loop if probe is not in food
    bool use_dual = cascade->probe_connected && cascade->probe_in_food;
    cascade_mode_t new_mode = use_dual ? CASCADE_MODE_DUAL : CASCADE_MODE_SINGLE;
    
    /* Handle mode transitions */
    if (new_mode != cascade->mode) {
        cascade->mode_switches++;
        
        if (cascade->mode == CASCADE_MODE_SINGLE && new_mode == CASCADE_MODE_DUAL) {
            /* Switching to dual loop - prepare for bumpless transfer */
            cascade->bumpless_transfer_pending = true;
            cascade->last_pan_setpoint = pan_actual;  /* Start from current pan temp */
        } else if (cascade->mode == CASCADE_MODE_DUAL && new_mode == CASCADE_MODE_SINGLE) {
            /* Switching to single loop - reset outer loop integrator */
            cascade->outer_pid.integrator = 0.0f;
        }
        
        cascade->mode = new_mode;
    }
    
    float pan_setpoint;
    float pwm_output;
    
    if (cascade->mode == CASCADE_MODE_DUAL) {
        /* Dual-loop cascade control */
        
        /* Outer loop: Liquid temperature → Pan temperature setpoint */
        float outer_output = pid_compute(&cascade->outer_pid, liquid_target, liquid_actual, dt_sec);
        
        /* Apply pan temperature limits */
        if (outer_output < cascade->pan_temp_limit_min) {
            outer_output = cascade->pan_temp_limit_min;
        }
        if (outer_output > cascade->pan_temp_limit_max) {
            outer_output = cascade->pan_temp_limit_max;
        }
        
        pan_setpoint = outer_output;
        
        /* Bumpless transfer on mode entry */
        if (cascade->bumpless_transfer_pending) {
            /* Initialize inner loop to avoid setpoint kick */
            if (cascade->inner_pid.ki > 0.0f) {
                cascade->inner_pid.integrator = (pan_setpoint - pan_actual) / cascade->inner_pid.ki;
            }
            cascade->bumpless_transfer_pending = false;
        }
        
    } else {
        /* Single-loop control: Direct pan temperature control */
        pan_setpoint = liquid_target;  /* User target becomes pan target */
    }
    
    /* Inner loop: Pan temperature → PWM output */
    pwm_output = pid_compute(&cascade->inner_pid, pan_setpoint, pan_actual, dt_sec);
    
    /* Update probe detection (using current PWM output for mass inference) */
    update_probe_detection(cascade, liquid_actual, pwm_output, dt_sec);

    /* Update performance metrics */
    float outer_error = liquid_target - liquid_actual;
    float inner_error = pan_setpoint - pan_actual;
    
    cascade->outer_error_sum += outer_error * outer_error;
    cascade->inner_error_sum += inner_error * inner_error;
    
    return pwm_output;
}

cascade_mode_t cascade_pid_get_mode(cascade_pid_handle_t *cascade) {
    return cascade->mode;
}

bool cascade_pid_probe_connected(cascade_pid_handle_t *cascade) {
    return cascade->probe_connected;
}

bool cascade_pid_is_probe_in_food(cascade_pid_handle_t *cascade) {
    return cascade->probe_in_food;
}

void cascade_pid_set_probe_detection(cascade_pid_handle_t *cascade, bool enabled) {
    cascade->probe_detection_enabled = enabled;
    if (!enabled) {
        cascade->probe_in_food = true;
    }
}

void cascade_pid_force_single_loop(cascade_pid_handle_t *cascade) {
    cascade->mode = CASCADE_MODE_SINGLE;
    cascade->probe_connected = false;
    cascade->bumpless_transfer_pending = false;
    cascade->outer_pid.integrator = 0.0f;
}

void cascade_pid_reset(cascade_pid_handle_t *cascade) {
    /* Reset PID controllers */
    cascade->outer_pid.integrator = 0.0f;
    cascade->outer_pid.prev_error = 0.0f;
    cascade->outer_pid.prev_measurement = 0.0f;
    cascade->inner_pid.integrator = 0.0f;
    cascade->inner_pid.prev_error = 0.0f;
    cascade->inner_pid.prev_measurement = 0.0f;
    
    /* Reset state */
    cascade->mode = CASCADE_MODE_SINGLE;
    cascade->probe_connected = false;
    cascade->last_pan_setpoint = CASCADE_PAN_TEMP_MIN;
    cascade->bumpless_transfer_pending = false;
    cascade->last_probe_reading_time = 0;
    
    /* Reset metrics */
    cascade->outer_error_sum = 0.0f;
    cascade->inner_error_sum = 0.0f;
    cascade->mode_switches = 0;
}

void cascade_pid_get_metrics(cascade_pid_handle_t *cascade,
                           float *outer_error, float *inner_error,
                           uint32_t *switches) {
    if (outer_error != NULL) {
        *outer_error = sqrtf(cascade->outer_error_sum / CASCADE_METRICS_WINDOW);
    }
    if (inner_error != NULL) {
        *inner_error = sqrtf(cascade->inner_error_sum / CASCADE_METRICS_WINDOW);
    }
    if (switches != NULL) {
        *switches = cascade->mode_switches;
    }
}

void cascade_pid_set_pan_limits(cascade_pid_handle_t *cascade, float min, float max) {
    if (min < max && min > 0.0f && max < 300.0f) {
        cascade->pan_temp_limit_min = min;
        cascade->pan_temp_limit_max = max;
        pid_set_output_limits(&cascade->outer_pid, min, max);
    }
}

void cascade_pid_init_default(cascade_pid_handle_t *cascade) {
    cascade_pid_init(cascade,
                    CASCADE_OUTER_KP, CASCADE_OUTER_KI, CASCADE_OUTER_KD,
                    CASCADE_INNER_KP, CASCADE_INNER_KI, CASCADE_INNER_KD);
}