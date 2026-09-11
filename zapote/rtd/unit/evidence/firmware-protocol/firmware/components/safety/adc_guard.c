/**
 * @file adc_guard.c
 * @brief Implementation of ADC safety checks
 */

#include "adc_guard.h"
#include <string.h>
#include <stdlib.h>

// Mock time function - replace with actual system time in integration
// For now assuming external tick provider or FreeRTOS xTaskGetTickCount()
extern uint32_t hal_get_tick_ms(void); 

// Helper: Calculate variance of history buffer
static uint32_t calculate_variance(const uint16_t *buffer, size_t size) {
    if (size == 0) return 0;
    
    uint32_t sum = 0;
    for (size_t i = 0; i < size; i++) {
        sum += buffer[i];
    }
    uint32_t mean = sum / size;
    
    uint32_t sq_diff_sum = 0;
    for (size_t i = 0; i < size; i++) {
        int32_t diff = (int32_t)buffer[i] - (int32_t)mean;
        sq_diff_sum += (diff * diff);
    }
    
    return sq_diff_sum / size;
}

void adc_guard_init(adc_guard_channel_t *ctx, hal_adc_channel_t channel) {
    if (!ctx) return;
    memset(ctx, 0, sizeof(adc_guard_channel_t));
    ctx->channel = channel;
    ctx->active = true;
    ctx->last_update_ms = hal_get_tick_ms();
}

adc_guard_status_t adc_guard_read_safe(adc_guard_channel_t *ctx, uint16_t *value) {
    if (!ctx || !value) return ADC_GUARD_ERR_NULL;
    
    uint16_t raw_val;
    hal_status_t status = HAL_ADC_READ_RAW(ctx->channel, &raw_val);
    
    if (status != HAL_OK) {
        return ADC_GUARD_ERR_NULL; // HAL error mapping
    }
    
    // 1. Range Check
    if (raw_val < ADC_MIN_VALID_RAW) {
        return ADC_GUARD_ERR_RANGE_LOW;
    }
    if (raw_val > ADC_MAX_VALID_RAW) {
        return ADC_GUARD_ERR_RANGE_HIGH;
    }
    
    // 2. Update History & Check Stuck
    ctx->history[ctx->history_idx] = raw_val;
    ctx->history_idx = (ctx->history_idx + 1) % ADC_STUCK_BUFFER_SIZE;
    
    // Only check variance once buffer is full (or assume 0 init is fine)
    // Here we check every time, but variance of 0s is 0.
    // Stuck check: if buffer is full of identical values (variance ~ 0)
    // Note: Real signals have noise. Variance < threshold implies stuck.
    
    uint32_t variance = calculate_variance(ctx->history, ADC_STUCK_BUFFER_SIZE);
    if (variance < ADC_STUCK_VARIANCE_THRESHOLD) {
        // Only trigger if we have valid non-zero data
        // (Avoid triggering on startup 0s if valid)
        // But 0 is invalid range (<100), so we are safe.
        // Actually, if signal is perfectly stable DC, this might trigger.
        // For Temper, currents/voltages usually have some ripple/noise.
        // We'll trust the threshold.
        return ADC_GUARD_ERR_STUCK;
    }
    
    // 3. Update Watchdog
    ctx->last_update_ms = hal_get_tick_ms();
    
    *value = raw_val;
    return ADC_GUARD_OK;
}

adc_guard_status_t adc_guard_check_stale(adc_guard_channel_t *ctx) {
    if (!ctx) return ADC_GUARD_ERR_NULL;
    
    uint32_t now = hal_get_tick_ms();
    if ((now - ctx->last_update_ms) > ADC_WATCHDOG_TIMEOUT_MS) {
        return ADC_GUARD_ERR_STALE;
    }
    
    return ADC_GUARD_OK;
}
