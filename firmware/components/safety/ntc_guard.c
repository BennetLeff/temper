/**
 * @file ntc_guard.c
 * @brief Implementation of NTC safety checks
 */

#include "ntc_guard.h"
#include "hal_adc.h"
#include <math.h>
#include <stdlib.h>
#include <string.h>

// External dependency
extern uint32_t hal_get_tick_ms(void);

void ntc_guard_init_part(ntc_guard_t *ctx, hal_adc_channel_t channel, const ntc_channel_t *part) {
    if (!ctx) return;
    memset(ctx, 0, sizeof(ntc_guard_t));
    ctx->adc_channel = channel;
    ctx->part = part ? part : &THERMAL_NTC_SINK;
    ctx->valid = false;
}

void ntc_guard_init(ntc_guard_t *ctx, hal_adc_channel_t channel) {
    ntc_guard_init_part(ctx, channel, &THERMAL_NTC_SINK);
}

ntc_guard_status_t ntc_guard_convert(const ntc_guard_t *ctx, uint16_t raw, float *temp_c) {
    if (!ctx || !ctx->part || !temp_c) return NTC_GUARD_ERR_NULL;
    float mv = (float)raw * ctx->part->v_ref_mv / NTC_ADC_FULL_SCALE;
    switch (ntc_channel_temp_c(ctx->part, mv, temp_c)) {
    case NTC_OK: return NTC_GUARD_OK;
    /* Above the ADC's measurable range: colder than ~15 C, or open. The two cannot be told
     * apart, so this guard never reports it as a plausible ("cool") temperature. */
    case NTC_BELOW_RANGE: return NTC_GUARD_ERR_RANGE;
    case NTC_OPEN: return NTC_GUARD_ERR_OPEN;
    case NTC_SHORT: return NTC_GUARD_ERR_SHORT;
    default: return NTC_GUARD_ERR_NULL;
    }
}

ntc_guard_status_t ntc_guard_read_safe(ntc_guard_t *ctx, float *temp_c) {
    if (!ctx || !temp_c) return NTC_GUARD_ERR_NULL;
    
    uint16_t raw_val;
    hal_status_t status = HAL_ADC_READ_RAW(ctx->adc_channel, &raw_val);
    
    if (status != HAL_OK) return NTC_GUARD_ERR_NULL;
    
    // 1-2. Open / short classification and conversion through the fitted part's R-T model
    float t = 0.0f;
    ntc_guard_status_t conv = ntc_guard_convert(ctx, raw_val, &t);
    if (conv != NTC_GUARD_OK) return conv;
    *temp_c = t;
    
    // 3. Physical Range Check
    if (t < NTC_TEMP_MIN_C || t > NTC_TEMP_MAX_C) {
        return NTC_GUARD_ERR_RANGE;
    }
    
    // 4. Rate of Change Check
    uint32_t now = hal_get_tick_ms();
    if (ctx->valid) {
        float dt = (now - ctx->last_read_ms) / 1000.0f;
        if (dt > 0.1f) { // Only check if enough time passed
            float rate = fabsf(t - ctx->last_temp_c) / dt;
            if (rate > NTC_MAX_RATE_C_PER_SEC) {
                return NTC_GUARD_ERR_RATE;
            }
        }
    }
    
    // Update history
    ctx->last_temp_c = t;
    ctx->last_read_ms = now;
    ctx->valid = true;
    
    return NTC_GUARD_OK;
}

ntc_guard_status_t ntc_guard_cross_check(float heatsink_temp, float ambient_temp, bool is_heating) {
    // Basic plausibility
    if (is_heating) {
        // Heatsink significantly cooler than ambient is impossible while heating
        // Allow margin for sensor error (-5C)
        if (heatsink_temp < (ambient_temp - 5.0f)) {
            return NTC_GUARD_ERR_PLAUSIBILITY;
        }
    }
    return NTC_GUARD_OK;
}
