/**
 * @file coil_guard.c
 * @brief Implementation of coil fault detection
 */

#include "coil_guard.h"
#include <string.h>
#include <stdlib.h>

void coil_guard_init(coil_guard_t *ctx) {
    if (!ctx) return;
    memset(ctx, 0, sizeof(coil_guard_t));
    ctx->baseline_valid = false;
}

void coil_guard_set_baseline(coil_guard_t *ctx, float freq_hz) {
    if (!ctx) return;
    ctx->baseline_freq_hz = freq_hz;
    ctx->baseline_valid = true;
}

coil_guard_status_t coil_guard_update(coil_guard_t *ctx, float current_freq_hz, float coil_temp_c) {
    if (!ctx) return COIL_GUARD_ERR_NULL;
    
    // 1. Check Temperature (if available)
    if (coil_temp_c > -100.0f) { // Valid temp provided
        if (coil_temp_c > COIL_MAX_TEMP_C) {
            return COIL_GUARD_ERR_OVERTEMP;
        }
    }
    
    // 2. Check Inductance Drop via Frequency Shift
    // f = 1 / (2*pi*sqrt(L*C))
    // If L drops, f increases.
    // L_ratio = L_new / L_base = (f_base / f_new)^2
    
    if (ctx->baseline_valid && current_freq_hz > 0) {
        float freq_ratio = ctx->baseline_freq_hz / current_freq_hz;
        float inductance_ratio = freq_ratio * freq_ratio;
        
        // Example: 10% drop -> ratio 0.90
        float drop_percent = (1.0f - inductance_ratio) * 100.0f;
        
        if (drop_percent > COIL_INDUCTANCE_DROP_FAULT_PERCENT) {
            return COIL_GUARD_ERR_SHORTED;
        }
        
        if (drop_percent > COIL_INDUCTANCE_DROP_WARN_PERCENT) {
            return COIL_GUARD_WARN_INDUCTANCE_LOW;
        }
    }
    
    return COIL_GUARD_OK;
}
