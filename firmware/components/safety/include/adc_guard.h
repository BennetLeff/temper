/**
 * @file adc_guard.h
 * @brief ADC Sanity Checking and Protection
 * 
 * Provides safety wrappers for ADC readings to detect:
 * - Out-of-range values (open/short circuit)
 * - Stuck values (frozen ADC)
 * - Stale readings (watchdog)
 */

#ifndef ADC_GUARD_H
#define ADC_GUARD_H

#include "hal_types.h"
#include "hal_adc.h"
#include <stdint.h>
#include <stdbool.h>

#ifdef __cplusplus
extern "C" {
#endif

// Safety limits
#define ADC_MIN_VALID_RAW 100
#define ADC_MAX_VALID_RAW 3950
#define ADC_STUCK_BUFFER_SIZE 8
#define ADC_STUCK_VARIANCE_THRESHOLD 5
#define ADC_WATCHDOG_TIMEOUT_MS 500

/**
 * @brief ADC Guard Failure Codes
 */
typedef enum {
    ADC_GUARD_OK = 0,
    ADC_GUARD_ERR_RANGE_LOW = 1,   // Possible short to GND
    ADC_GUARD_ERR_RANGE_HIGH = 2,  // Possible open/short to VCC
    ADC_GUARD_ERR_STUCK = 3,       // Value not changing (frozen ADC)
    ADC_GUARD_ERR_STALE = 4,       // Watchdog timeout (no updates)
    ADC_GUARD_ERR_NULL = 5         // Invalid pointer
} adc_guard_status_t;

/**
 * @brief Channel state for stuck/stale detection
 */
typedef struct {
    hal_adc_channel_t channel;
    uint16_t history[ADC_STUCK_BUFFER_SIZE];
    uint8_t history_idx;
    uint32_t last_update_ms;
    bool active;
} adc_guard_channel_t;

/**
 * @brief Initialize ADC guard for a channel
 * @param ctx Channel context to initialize
 * @param channel ADC channel to monitor
 */
void adc_guard_init(adc_guard_channel_t *ctx, hal_adc_channel_t channel);

/**
 * @brief Read ADC value with full safety checks
 * 
 * Performs:
 * 1. HAL read
 * 2. Range check
 * 3. Stuck value check
 * 4. Watchdog update
 * 
 * @param ctx Channel context
 * @param value Pointer to store result
 * @return ADC_GUARD_OK or error code
 */
adc_guard_status_t adc_guard_read_safe(adc_guard_channel_t *ctx, uint16_t *value);

/**
 * @brief Check if channel is stale (watchdog check)
 * @param ctx Channel context
 * @return ADC_GUARD_ERR_STALE if timed out, OK otherwise
 */
adc_guard_status_t adc_guard_check_stale(adc_guard_channel_t *ctx);

#ifdef __cplusplus
}
#endif

#endif /* ADC_GUARD_H */
