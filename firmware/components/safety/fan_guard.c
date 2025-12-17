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

fan_guard_status_t fan_guard_update(fan_guard_t *ctx, float heatsink_temp_c, float power_w, float ambient_temp_c, bool fan_on) {
    if (!ctx) return FAN_GUARD_ERR_NULL;
    
    uint32_t now = hal_get_tick_ms();
    uint32_t dt_ms = now - ctx->last_check_ms;
    
    // Only update at defined interval to avoid noise
    if (dt_ms < FAN_CHECK_INTERVAL_MS) {
        return FAN_GUARD_OK; // Or cache last status
    }
    
    float dt = dt_ms / 1000.0f;
    float rate = (heatsink_temp_c - ctx->last_temp_c) / dt;
    
    // Update state
    ctx->last_temp_c = heatsink_temp_c;
    ctx->last_check_ms = now;
    ctx->current_power_w = power_w;
    ctx->ambient_temp_c = ambient_temp_c;
    ctx->fan_running = fan_on;
    
    // Logic 1: Rate of Rise
    // If fan is ON, temperature shouldn't rise too fast unless power is massive
    // Expected passive rise ~ Power * mass_factor?
    // Simplified check: If rate > Limit, warn
    if (fan_on && rate > FAN_MAX_TEMP_RISE_RATE_C_PER_S) {
        // Threshold might need to scale with power. 
            // 0.5C/s at 1800W is plausible? 
            // At 1800W into 500g Aluminum (cp=0.9 J/gK):
            // 50W loss (97.5% eff) -> 50 J/s
            // dT = 50 / (500 * 0.9) = 0.11 C/s
            // So > 0.5 C/s implies >> 200W loss or very small mass -> Blockage        
        if (rate > (FAN_MAX_TEMP_RISE_RATE_C_PER_S * 2.0f)) {
            return FAN_GUARD_ERR_BLOCKED;
        }
        return FAN_GUARD_WARN_RESTRICTED;
    }
    
    // Logic 2: Thermal Equilibrium Check
    // T_expected = T_ambient + Power * Rth
    // If T_actual >> T_expected, cooling is degraded
    if (fan_on && dt > 5.0f) { // Only check after some settling? Or continuous.
        // Assume fan reduces Rth to 1.0 C/W
        // Loss power is ~2-5% of input power
        float power_loss = power_w * 0.05f; // Conservative 5% loss estimate
        float expected_rise = power_loss * FAN_RTH_HEATSINK;
        float max_expected_temp = ambient_temp_c + expected_rise + FAN_EQUILIBRIUM_TOLERANCE_C;
        
        if (heatsink_temp_c > max_expected_temp) {
            // Also ensure we are actually hot enough to care (>50C)
            if (heatsink_temp_c > 50.0f) {
                return FAN_GUARD_WARN_DEGRADED;
            }
        }
    }
    
    return FAN_GUARD_OK;
}
