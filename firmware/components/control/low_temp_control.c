/**
 * @file low_temp_control.c
 * @brief Low-temperature burst-mode control implementation
 */

#include "low_temp_control.h"
#include "pid_control.h"
#include <math.h>

/* Forward declarations of external dependencies */
extern uint32_t get_time_ms(void);
extern void power_set_level(uint8_t level);
extern void pwm_set_duty_cycle(uint8_t duty);

/* Default configuration for low-temperature range */
static low_temp_config_t g_config = {
    .burst_duration_ms = 300.0f,     /* 300ms heating burst */
    .burst_period_min_ms = 1000.0f,  /* Max 30% duty at 300ms burst */
    .burst_period_max_ms = 30000.0f, /* Min ~1% duty */
    .detune_frequency_hz = 48000.0f, /* Well above 38kHz resonance */
    .pid_kp = 0.5f,                  /* Reduced proportional gain */
    .pid_ki = 0.01f,                 /* Reduced integral gain */
    .pid_kd = 0.1f                   /* Derivative gain */
};

static struct {
    bool active;
    float target_temp;
    uint32_t last_burst_time;
    uint32_t current_period_ms;
    bool in_burst;
    pid_handle_t pid;
} lt_ctx = {0};

void low_temp_init(void) {
    lt_ctx.active = false;
    pid_init(&lt_ctx.pid, g_config.pid_kp, g_config.pid_ki, g_config.pid_kd);
    pid_set_output_limits(&lt_ctx.pid, 1.0f, 30.0f); /* Duty cycle 1% to 30% */
}

void low_temp_start(float target_temp) {
    lt_ctx.target_temp = target_temp;
    lt_ctx.active = true;
    lt_ctx.last_burst_time = get_time_ms();
    lt_ctx.in_burst = false;
    lt_ctx.current_period_ms = (uint32_t)g_config.burst_period_max_ms;
    
    /* Re-initialize PID for low temp gains */
    pid_init(&lt_ctx.pid, g_config.pid_kp, g_config.pid_ki, g_config.pid_kd);
    pid_set_output_limits(&lt_ctx.pid, 1.0f, 30.0f);
    pid_set_integrator_limit(&lt_ctx.pid, 10.0f);
}

void low_temp_stop(void) {
    lt_ctx.active = false;
    lt_ctx.in_burst = false;
    power_set_level(0);
}

bool low_temp_update(float current_temp) {
    if (!lt_ctx.active) return false;

    uint32_t now = get_time_ms();
    uint32_t elapsed = now - lt_ctx.last_burst_time;

    /* 1. Update PID to determine required burst duty cycle */
    /* We use a slower update for the PID itself since the system response is slow */
    static uint32_t last_pid_update = 0;
    if (now - last_pid_update >= 1000) {
        /* PID output is duty cycle in % (1-30) */
        float duty = pid_compute(&lt_ctx.pid, lt_ctx.target_temp, current_temp, 1.0f);
        
        /* Convert duty cycle to period */
        /* duty = duration / period -> period = duration / (duty/100) */
        float period = g_config.burst_duration_ms / (duty / 100.0f);
        
        /* Clamp period */
        if (period > g_config.burst_period_max_ms) period = g_config.burst_period_max_ms;
        if (period < g_config.burst_period_min_ms) period = g_config.burst_period_min_ms;
        
        lt_ctx.current_period_ms = (uint32_t)period;
        last_pid_update = now;
    }

    /* 2. Burst Logic */
    if (lt_ctx.in_burst) {
        if (elapsed >= (uint32_t)g_config.burst_duration_ms) {
            /* Burst finished */
            lt_ctx.in_burst = false;
            power_set_level(0);
        }
    } else {
        if (elapsed >= lt_ctx.current_period_ms) {
            /* Start new burst */
            lt_ctx.in_burst = true;
            lt_ctx.last_burst_time = now;
            
            /* Apply detuned frequency power level */
            /* We assume power_set_level handles the frequency/duty configuration
             * when in low-temp mode, or we'd need to call pll functions here. */
            power_set_level(10); /* Low power setting */
        }
    }

    return lt_ctx.in_burst;
}

bool low_temp_is_active(void) {
    return lt_ctx.active;
}

const low_temp_config_t* low_temp_get_config(void) {
    return &g_config;
}
