/**
 * @file ntc_guard.h
 * @brief NTC Thermistor Failure Detection and Protection
 * 
 * Provides safety wrappers for NTC temperature readings:
 * - Open/Short circuit detection
 * - Rate-of-change validation
 * - Plausibility checks (cooling while heating)
 * - Sensor cross-checks
 */

#ifndef NTC_GUARD_H
#define NTC_GUARD_H

#include "hal_types.h"
#include <stdint.h>
#include <stdbool.h>

#ifdef __cplusplus
extern "C" {
#endif

// Safety limits (ADC raw counts, 12-bit)
#define NTC_ADC_MIN 100     // Below this = Short to GND
#define NTC_ADC_MAX 3900    // Above this = Open/Short to VCC

// Physical limits
#define NTC_TEMP_MIN_C -20.0f
#define NTC_TEMP_MAX_C 150.0f
#define NTC_MAX_RATE_C_PER_SEC 10.0f

/**
 * @brief NTC Guard Failure Codes
 */
typedef enum {
    NTC_GUARD_OK = 0,
    NTC_GUARD_ERR_OPEN = 1,        // Open circuit (ADC high)
    NTC_GUARD_ERR_SHORT = 2,       // Short circuit (ADC low)
    NTC_GUARD_ERR_RANGE = 3,       // Temp value out of physical bounds
    NTC_GUARD_ERR_RATE = 4,        // Rate of change too high
    NTC_GUARD_ERR_PLAUSIBILITY = 5,// Physics violation (cooling while heating)
    NTC_GUARD_ERR_NULL = 6         // Invalid pointer
} ntc_guard_status_t;

/**
 * @brief NTC Sensor Context
 */
typedef struct {
    hal_adc_channel_t adc_channel;
    float last_temp_c;
    uint32_t last_read_ms;
    bool valid;
} ntc_guard_t;

/**
 * @brief Initialize NTC guard
 * @param ctx Sensor context
 * @param channel ADC channel
 */
void ntc_guard_init(ntc_guard_t *ctx, hal_adc_channel_t channel);

/**
 * @brief Read temperature with safety checks
 * 
 * Converts ADC reading to temperature and validates against
 * physical constraints and historical trends.
 * 
 * @param ctx Sensor context
 * @param temp_c Pointer to store temperature
 * @return NTC_GUARD_OK or error code
 */
ntc_guard_status_t ntc_guard_read_safe(ntc_guard_t *ctx, float *temp_c);

/**
 * @brief Perform cross-check between sensors
 * 
 * E.g. Heatsink should be >= Ambient when system is active.
 * 
 * @param heatsink_temp Heatsink temperature
 * @param ambient_temp Ambient temperature
 * @param is_heating True if system is actively heating
 * @return NTC_GUARD_OK if plausible, error otherwise
 */
ntc_guard_status_t ntc_guard_cross_check(float heatsink_temp, float ambient_temp, bool is_heating);

#ifdef __cplusplus
}
#endif

#endif /* NTC_GUARD_H */
