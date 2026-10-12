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
#include "../../control/thermal_mgmt.h"
#include <stdint.h>
#include <stdbool.h>

#ifdef __cplusplus
extern "C" {
#endif

/*
 * Fitted parts (integrated controller, layout L3, DECISIONS C32): heatsink Vishay NTCALUG01A104GA
 * (100 k, B25/85 4190 K) and coil Semitec 104GT-2 class (100 k, B25/85 4267 K, -50..+300 C), both
 * on a 10.0 kOhm pull-up to v3v3. The R-T models are in thermal_mgmt.h (THERMAL_NTC_SINK,
 * THERMAL_NTC_COIL), shared with the fan law and the coil guard, so every consumer converts a
 * reading the same way. ntc_guard_init() defaults to the heatsink part.
 *
 * Raw counts are taken as ratiometric to v3v3 (12 bit, 4095 = v3v3), as before. Open and short
 * thresholds follow the model: a node colder than -20 C reads OPEN, hotter than 200 C reads SHORT
 * (thermal_mgmt.c). A node above the ESP32-S3 ADC's ~3.1 V range (colder than ~15 C) is
 * NTC_GUARD_ERR_RANGE: there an open sensor and a cold one look alike to the ADC, so it is never
 * passed on as "cool". (Open HS / COIL sensors are also latched in hardware by the thermal-sense
 * block's OPEN_REF comparator.)
 */
#define NTC_ADC_FULL_SCALE 4095.0f

// Physical limits (equal to the channel's open / short temperatures)
#define NTC_TEMP_MIN_C -20.0f
#define NTC_TEMP_MAX_C 200.0f
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
    const ntc_channel_t *part;     /* divider + R-T model; THERMAL_NTC_SINK by default */
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
/* As ntc_guard_init(), for a given divider (THERMAL_NTC_COIL, THERMAL_NTC_SINK). */
void ntc_guard_init_part(ntc_guard_t *ctx, hal_adc_channel_t channel, const ntc_channel_t *part);
/* Raw 12-bit counts -> temperature through ctx->part, with the open / short classification. */
ntc_guard_status_t ntc_guard_convert(const ntc_guard_t *ctx, uint16_t raw, float *temp_c);

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
