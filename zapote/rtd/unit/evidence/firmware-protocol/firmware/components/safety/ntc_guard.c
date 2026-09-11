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

// NTC Parameters (Match BOM: NCU18XH103F6SRB)
#define NTC_R25 10000.0f
#define NTC_B 3950.0f
#define NTC_R_PULLUP 10000.0f
#define ADC_MAX_COUNTS 4095.0f

static float convert_adc_to_temp(uint16_t adc_val) {
    if (adc_val == 0) return 999.0f; // Prevent div by zero
    
    // Voltage divider: V_out = Vcc * R_ntc / (R_ntc + R_pullup)
    // ADC = 4095 * R_ntc / (R_ntc + R_pullup)
    // R_ntc = R_pullup * ADC / (4095 - ADC)
    // Assumes NTC is bottom resistor (to GND)
    
    float r_ntc = NTC_R_PULLUP * (float)adc_val / (ADC_MAX_COUNTS - (float)adc_val);
    
    // Beta equation: 1/T = 1/T0 + 1/B * ln(R/R0)
    float t_kelvin = 1.0f / (1.0f / 298.15f + 1.0f / NTC_B * logf(r_ntc / NTC_R25));
    return t_kelvin - 273.15f;
}

void ntc_guard_init(ntc_guard_t *ctx, hal_adc_channel_t channel) {
    if (!ctx) return;
    memset(ctx, 0, sizeof(ntc_guard_t));
    ctx->adc_channel = channel;
    ctx->valid = false;
}

ntc_guard_status_t ntc_guard_read_safe(ntc_guard_t *ctx, float *temp_c) {
    if (!ctx || !temp_c) return NTC_GUARD_ERR_NULL;
    
    uint16_t raw_val;
    hal_status_t status = HAL_ADC_READ_RAW(ctx->adc_channel, &raw_val);
    
    if (status != HAL_OK) return NTC_GUARD_ERR_NULL;
    
    // 1. Raw Range Check (Open/Short)
    if (raw_val < NTC_ADC_MIN) return NTC_GUARD_ERR_SHORT; // Short to GND
    if (raw_val > NTC_ADC_MAX) return NTC_GUARD_ERR_OPEN;  // Open / Short to VCC
    
    // 2. Convert to Temperature
    float t = convert_adc_to_temp(raw_val);
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
