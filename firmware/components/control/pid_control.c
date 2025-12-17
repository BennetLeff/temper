/**
 * @file pid_control.c
 * @brief PID temperature controller implementation
 * 
 * Features:
 * - Anti-windup via integrator clamping
 * - Derivative on measurement (prevents setpoint kick)
 * - Output saturation
 * - Auto-initialization with sensible defaults
 * 
 * Tuning Guidelines (Ziegler-Nichols Modified for No Overshoot):
 * 1. Set Ki=0, Kd=0
 * 2. Increase Kp until system oscillates (Ultimate Gain Ku)
 * 3. Measure oscillation period Tu
 * 4. Calculate: Kp=0.3*Ku, Ki=2*Kp/Tu, Kd=Kp*Tu/3
 */

#include "pid_control.h"
#include <math.h>
#include <stdbool.h>

/* Default PID gains for induction cooker temperature control */
#define PID_DEFAULT_KP      1.0f
#define PID_DEFAULT_KI      0.05f
#define PID_DEFAULT_KD      0.2f

/* Global PID instance for simplified API */
static pid_handle_t g_pid = {
    .kp = PID_DEFAULT_KP,
    .ki = PID_DEFAULT_KI,
    .kd = PID_DEFAULT_KD,
    .output_min = 0.0f,
    .output_max = 100.0f,
    .integrator_limit = 50.0f,
    .integrator = 0.0f,
    .prev_error = 0.0f,
    .prev_measurement = 0.0f
};

static float g_last_dt = 0.01f;     /* Default 10ms update rate */
static bool g_pid_initialized = false;
static uint64_t g_last_update_time_us = 0;

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
/* For testing: advance simulated time */
void pid_test_advance_time_us(uint64_t delta_us) {
    s_simulated_time_us += delta_us;
}
#endif

void pid_init(pid_handle_t *pid, float kp, float ki, float kd) {
    pid->kp = kp;
    pid->ki = ki;
    pid->kd = kd;
    pid->integrator = 0.0f;
    pid->prev_error = 0.0f;
    pid->prev_measurement = 0.0f;
    pid->output_min = 0.0f;
    pid->output_max = 100.0f;      /* Duty cycle % */
    pid->integrator_limit = 50.0f; /* Limit I-term contribution */
}

/**
 * @brief Initialize global PID with custom gains
 * 
 * Call this before using pid_update() to set custom tuning.
 * If not called, pid_update() will use default gains.
 */
void pid_global_init(float kp, float ki, float kd) {
    pid_init(&g_pid, kp, ki, kd);
    g_pid_initialized = true;
    g_last_update_time_us = get_time_us();
}

void pid_set_tuning(float kp, float ki, float kd) {
    g_pid.kp = kp;
    g_pid.ki = ki;
    g_pid.kd = kd;
    
    /* Mark as initialized if tuning is set */
    if (!g_pid_initialized) {
        g_pid_initialized = true;
        g_last_update_time_us = get_time_us();
    }
}

void pid_reset_integral(void) {
    g_pid.integrator = 0.0f;
    g_pid.prev_error = 0.0f;
    g_pid.prev_measurement = 0.0f;
}

/**
 * @brief Set the expected loop period for pid_update()
 * 
 * Use this if you know the fixed loop rate and want to override
 * the automatic dt calculation.
 * 
 * @param dt_sec Loop period in seconds
 */
void pid_set_dt(float dt_sec) {
    if (dt_sec > 0.0f && dt_sec < 10.0f) {
        g_last_dt = dt_sec;
    }
}

float pid_compute(pid_handle_t *pid, float setpoint, float measurement, float dt_sec) {
    /* Validate dt to prevent division issues */
    if (dt_sec <= 0.0f || !isfinite(dt_sec)) {
        dt_sec = 0.01f;  /* Fallback to 10ms */
    }
    
    /* Check for NaN/Inf in inputs */
    if (!isfinite(setpoint) || !isfinite(measurement)) {
        return pid->output_min;  /* Safe output on invalid input */
    }
    
    float error = setpoint - measurement;
    
    /* 1. Proportional term */
    float p_term = pid->kp * error;
    
    /* 2. Integral term (Trapezoidal rule for better accuracy) */
    /* I_new = I_old + Ki * (error_old + error_new) / 2 * dt */
    /* Simplified to Euler for now, but preserving the structure */
    pid->integrator += (error * dt_sec);
    
    /* Anti-windup: Clamping */
    if (pid->integrator > pid->integrator_limit) {
        pid->integrator = pid->integrator_limit;
    }
    if (pid->integrator < -pid->integrator_limit) {
        pid->integrator = -pid->integrator_limit;
    }
    
    float i_term = pid->ki * pid->integrator;
    
    /* 3. Derivative term (Derivative on Measurement to avoid "Kick") */
    /* dMeasured/dt = (Current - Prev) / dt */
    float d_term = 0.0f;
    if (dt_sec > 0.0f) {
        float dmeas = measurement - pid->prev_measurement;
        /* Guard against derivative spike on first call */
        if (isfinite(dmeas) && pid->prev_measurement != 0.0f) {
            d_term = -pid->kd * (dmeas / dt_sec);
        }
    }
    
    /* Output calculation */
    float output = p_term + i_term + d_term;
    
    /* Output saturation */
    if (output > pid->output_max) {
        output = pid->output_max;
    }
    if (output < pid->output_min) {
        output = pid->output_min;
    }
    
    /* Update state for next iteration */
    pid->prev_error = error;
    pid->prev_measurement = measurement;
    
    return output;
}

float pid_update(float setpoint, float measurement) {
    /* Auto-initialize if never initialized */
    if (!g_pid_initialized) {
        g_pid_initialized = true;
        g_last_update_time_us = get_time_us();
        /* First call: use default dt, can't compute real dt yet */
        return pid_compute(&g_pid, setpoint, measurement, g_last_dt);
    }
    
    /* Calculate actual dt from timestamps */
    uint64_t now_us = get_time_us();
    uint64_t elapsed_us = now_us - g_last_update_time_us;
    
    /* Sanity check elapsed time (0.1ms to 1s) */
    if (elapsed_us > 0 && elapsed_us < 1000000) {
        g_last_dt = (float)elapsed_us / 1000000.0f;
    }
    /* else keep previous g_last_dt */
    
    g_last_update_time_us = now_us;
    
    return pid_compute(&g_pid, setpoint, measurement, g_last_dt);
}

void pid_set_output_limits(pid_handle_t *pid, float min, float max) {
    if (min < max) {
        pid->output_min = min;
        pid->output_max = max;
    }
}

void pid_set_integrator_limit(pid_handle_t *pid, float limit) {
    if (limit > 0.0f) {
        pid->integrator_limit = limit;
    }
}

/**
 * @brief Get current dt value (for debugging/monitoring)
 */
float pid_get_dt(void) {
    return g_last_dt;
}
