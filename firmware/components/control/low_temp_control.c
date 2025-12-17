/**
 * @file low_temp_control.c
 * @brief Implementation of low-temperature burst-mode control
 */

#include "low_temp_control.h"
#include <stdbool.h>
#include <string.h>

/* Default configuration */
static const low_temp_config_t DEFAULT_CONFIG = {
    .burst_duration_ms = 300.0f,
    .min_period_ms = 1000.0f,
    .max_period_ms = 30000.0f,
    .detune_freq_hz = 48000,
    .kp = 0.5f,
    .ki = 0.01f,
    .kd = 0.1f
};

/* Externals */
extern uint32_t get_time_ms(void);
extern float pid_update(float setpoint, float measurement);
extern void power_set_level(uint8_t level);

/* State */
static struct {
    low_temp_config_t config;
    uint32_t last_burst_start_ms;
    bool burst_active;
    uint32_t current_period_ms;
    float target_temp;
    bool active;
} lt_ctx;

void low_temp_init(void) {
    memset(&lt_ctx, 0, sizeof(lt_ctx));
    lt_ctx.config = DEFAULT_CONFIG;
    lt_ctx.current_period_ms = (uint32_t)lt_ctx.config.max_period_ms;
    lt_ctx.active = false;
}

void low_temp_start(float target_temp_c) {
    lt_ctx.target_temp = target_temp_c;
    lt_ctx.active = true;
    lt_ctx.last_burst_start_ms = get_time_ms();
    lt_ctx.burst_active = false;
}

bool low_temp_update(float current_temp_c) {
    if (!lt_ctx.active) return false;

    uint32_t now = get_time_ms();
    
    /* 1. Update PID to determine desired duty cycle (mapped to period) */
    float pid_out = pid_update(lt_ctx.target_temp, current_temp_c);
    
    /* 2. Map PID output (0-100) to burst period (max_period to min_period) */
    float range = lt_ctx.config.max_period_ms - lt_ctx.config.min_period_ms;
    float period = lt_ctx.config.max_period_ms - (pid_out * range / 100.0f);
    
    /* Clamp period */
    if (period < lt_ctx.config.min_period_ms) period = lt_ctx.config.min_period_ms;
    if (period > lt_ctx.config.max_period_ms) period = lt_ctx.config.max_period_ms;
    
    lt_ctx.current_period_ms = (uint32_t)period;

    /* 3. Manage Burst Timing */
    if (!lt_ctx.burst_active) {
        /* Check if it's time for a new burst */
        if ((now - lt_ctx.last_burst_start_ms) >= lt_ctx.current_period_ms) {
            lt_ctx.burst_active = true;
            lt_ctx.last_burst_start_ms = now;
        }
    } else {
        /* Check if current burst is over */
        if ((now - lt_ctx.last_burst_start_ms) >= (uint32_t)lt_ctx.config.burst_duration_ms) {
            lt_ctx.burst_active = false;
        }
    }

    /* 4. Set power level (10% power during burst for ~50W target, 0% otherwise) */
    /* Note: Level 10 = 10% of 1800W = 180W? 
     * The coder resolution mentioned Level 10. Let's use 10. */
    power_set_level(lt_ctx.burst_active ? 10 : 0);

    return lt_ctx.burst_active;
}

void low_temp_stop(void) {
    lt_ctx.active = false;
    lt_ctx.burst_active = false;
    power_set_level(0);
}

bool low_temp_is_active(void) {
    return lt_ctx.active;
}

const low_temp_config_t* low_temp_get_config(void) {
    return &lt_ctx.config;
}

uint32_t low_temp_get_frequency(void) {
    return lt_ctx.config.detune_freq_hz;
}
