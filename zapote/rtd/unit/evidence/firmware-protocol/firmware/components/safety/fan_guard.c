/**
 * @file fan_guard.c
 * @brief Implementation of airflow monitoring logic
 */

#include "fan_guard.h"
#include <string.h>
#include <math.h>

// External time provider
extern uint32_t hal_get_tick_ms(void);

void fan_guard_init(fan_guard_t *ctx) {
    if (!ctx) return;
    memset(ctx, 0, sizeof(fan_guard_t));
    ctx->last_check_ms = hal_get_tick_ms();
    ctx->last_temp_c = 25.0f; // Reasonable default
}

float fan_guard_calculate_duty(float heatsink_temp_c) {
    const float T_MIN = 50.0f;   // Start ramping
    const float T_MAX = 80.0f;   // Full speed
    const float DUTY_MIN = 0.3f; // 30% minimum
    const float DUTY_MAX = 1.0f; // 100% maximum
    
    if (heatsink_temp_c <= T_MIN) return DUTY_MIN;
    if (heatsink_temp_c >= T_MAX) return DUTY_MAX;
    
    // Linear interpolation
    float fraction = (heatsink_temp_c - T_MIN) / (T_MAX - T_MIN);
    return DUTY_MIN + fraction * (DUTY_MAX - DUTY_MIN);
}

fan_guard_status_t fan_guard_update(fan_guard_t *ctx, float heatsink_temp_c, float power_w, float ambient_temp_c, uint32_t fan_rpm, float duty_cycle) {
    if (!ctx) return FAN_GUARD_ERR_NULL;
    
    uint32_t now = hal_get_tick_ms();
    uint32_t dt_ms = now - ctx->last_check_ms;
    
    // Update instantaneous state
    ctx->current_power_w = power_w;
    ctx->ambient_temp_c = ambient_temp_c;
    ctx->current_rpm = fan_rpm;
    ctx->duty_cycle = duty_cycle;
    ctx->fan_running = (duty_cycle > 0.05f);
    
    // Logic 0: Tachometer Validation
    // Assume fan reaches ~3000 RPM at 100% duty
    const float MAX_RPM = 3000.0f;
    ctx->expected_rpm = (uint32_t)(duty_cycle * MAX_RPM);
    
    if (ctx->fan_running) {
        // Fault if actual RPM < 50% of expected RPM
        if (fan_rpm < (uint32_t)(ctx->expected_rpm * 0.5f)) {
            return FAN_GUARD_ERR_FAILURE;
        }
    }

    // Only update thermal model at defined interval to avoid noise
    if (dt_ms < FAN_CHECK_INTERVAL_MS) {
        return FAN_GUARD_OK;
    }
    
    float dt = dt_ms / 1000.0f;
    float rate = (heatsink_temp_c - ctx->last_temp_c) / dt;
    
    // Update historic state for next interval
    ctx->last_temp_c = heatsink_temp_c;
    ctx->last_check_ms = now;
    
    // Logic 1: Rate of Rise
    if (ctx->fan_running && rate > FAN_MAX_TEMP_RISE_RATE_C_PER_S) {
        if (rate > (FAN_MAX_TEMP_RISE_RATE_C_PER_S * 2.0f)) {
            return FAN_GUARD_ERR_BLOCKED;
        }
        return FAN_GUARD_WARN_RESTRICTED;
    }
    
    // Logic 2: Thermal Equilibrium Check
    if (ctx->fan_running && dt > 5.0f) { 
        float power_loss = power_w * 0.05f; 
        float expected_rise = power_loss * FAN_RTH_HEATSINK;
        float max_expected_temp = ambient_temp_c + expected_rise + FAN_EQUILIBRIUM_TOLERANCE_C;
        
        if (heatsink_temp_c > max_expected_temp) {
            if (heatsink_temp_c > 50.0f) {
                return FAN_GUARD_WARN_DEGRADED;
            }
        }
    }
    
    return FAN_GUARD_OK;
}
