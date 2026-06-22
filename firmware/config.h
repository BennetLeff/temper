/**
 * @file config.h
 * @brief Centralized firmware configuration — GENERATED FILE
 *
 * DO NOT EDIT. This file is generated from firmware/config.yaml
 * by firmware/tools/gen_config.py.
 *
 * Usage:
 *     #include "config.h"
 *
 *     config_init();  // Load defaults
 *     float temp = g_config.thresholds.pan_confidence_required;
 *     uint32_t timeout = g_config.timeouts.pan_detect;
 *
 * All configuration values are single-sourced from firmware/config.yaml.
 * The bare #define block at the bottom allows state_machine.c call sites
 * to compile without changes. Every #define value matches the corresponding
 * field in the *_DEFAULT initializer.
 */

#ifndef CONFIG_H
#define CONFIG_H

#include <stdint.h>
#include <stdbool.h>

/* ================================
 * Version Information
 * ================================
 */

#define CONFIG_VERSION_MAJOR 0
#define CONFIG_VERSION_MINOR 1
#define CONFIG_VERSION_PATCH 0

#define CONFIG_VERSION_STRING "0.1.0"
#define CONFIG_BUILD_DATE __DATE__
#define CONFIG_BUILD_TIME __TIME__
/* ================================
 * Temperature Limits (°C)
 * ================================
 */

typedef struct {
    float safe_idle_temp; /**< Safe temperature to return to IDLE (°C) */
    float min_temp; /**< Minimum setpoint temperature (°C) */
    float max_temp; /**< Maximum setpoint temperature (°C) */
} temperature_limits_t;

/* Default temperatures */
#define TEMP_LIMITS_DEFAULT { \
    .safe_idle_temp = 50.0f, \
    .min_temp = 30.0f, \
    .max_temp = 250.0f, \
}


/* ================================
 * Timeouts (ms)
 * ================================
 */

typedef struct {
    uint32_t pan_detect; /**< Pan detection timeout (ms) */
    uint32_t no_pan_grace; /**< Pan removal grace period (ms) */
    uint32_t max_preheat; /**< Maximum preheat time (ms) */
    uint32_t wdt_normal; /**< Watchdog timeout in normal operation (ms) */
    uint32_t wdt_idle; /**< Watchdog timeout in IDLE state (ms) */
    uint32_t wdt_init; /**< Watchdog timeout during INIT (ms) */
    uint32_t fan_check_interval; /**< Fan guard check interval (ms) */
    uint32_t adc_check_interval; /**< ADC guard check interval (ms) */
} timeouts_t;

/* Default timeouts */
#define TIMEOUTS_DEFAULT { \
    .pan_detect = 5000, \
    .no_pan_grace = 3000, \
    .max_preheat = 600000, \
    .wdt_normal = 1000, \
    .wdt_idle = 10000, \
    .wdt_init = 5000, \
    .fan_check_interval = 1000, \
    .adc_check_interval = 500, \
}


/* ================================
 * Thresholds
 * ================================
 */

typedef struct {
    uint16_t pan_debounce_count; /**< Pan detection debounce samples */
    uint8_t pan_confidence_required; /**< Pan detection confirmations needed */
    uint16_t adc_min_valid_raw; /**< ADC minimum valid raw value */
    uint16_t adc_max_valid_raw; /**< ADC maximum valid raw value */
    uint8_t adc_stuck_buffer_size; /**< ADC stuck check buffer size */
    uint32_t adc_stuck_variance_threshold; /**< ADC stuck variance threshold */
    uint32_t adc_watchdog_timeout_ms; /**< ADC watchdog timeout (ms) */
    float fan_max_temp_rise_rate_c_per_s; /**< Maximum fan temp rise rate (°C/s) */
} thresholds_t;

/* Default thresholds */
#define THRESHOLDS_DEFAULT { \
    .pan_debounce_count = 10, \
    .pan_confidence_required = 3, \
    .adc_min_valid_raw = 100, \
    .adc_max_valid_raw = 3950, \
    .adc_stuck_buffer_size = 8, \
    .adc_stuck_variance_threshold = 5, \
    .adc_watchdog_timeout_ms = 500, \
    .fan_max_temp_rise_rate_c_per_s = 5.0f, \
}


/* ================================
 * Combined Runtime Configuration
 * ================================
 */

typedef struct {
    temperature_limits_t temperatures;
    timeouts_t timeouts;
    thresholds_t thresholds;
} config_t;

/* Global configuration instance */
extern config_t g_config;

/* ================================
 * Public API
 * ================================
 */

/**
 * @brief Initialize configuration with default values
 *
 * This function loads all default values into g_config.
 * Call this during system initialization before using any
 * configuration values.
 */
void config_init(void);

/**
 * @brief Load configuration from environment variables
 *
 * Allows runtime configuration via environment variables:

 * - TEMP_SAFE_IDLE_C
 * - TEMP_MIN_C
 * - TEMP_MAX_C
 * - PAN_DETECT_TIMEOUT_MS
 * - NO_PAN_GRACE_MS
 * - MAX_PREHEAT_MS
 * - WDT_NORMAL_MS
 * - WDT_IDLE_MS
 * - WDT_INIT_MS
 * - FAN_CHECK_INTERVAL_MS
 * - ADC_CHECK_INTERVAL_MS
 * - PAN_DEBOUNCE_COUNT
 * - PAN_CONFIDENCE_REQUIRED
 * - ADC_MIN_VALID_RAW
 * - ADC_MAX_VALID_RAW
 * - ADC_STUCK_BUFFER_SIZE
 * - ADC_STUCK_VARIANCE_THRESHOLD
 * - ADC_WATCHDOG_TIMEOUT_MS
 * - FAN_MAX_TEMP_RISE_RATE_C_PER_S
 *
 * Useful for testing or calibration without recompiling.
 */
void config_set_from_env(void);

/**
 * @brief Validate configuration values
 *
 * @return true if all values are valid, false otherwise
 *
 * Checks for:
 * - Temperature ranges (0-300°C)
 * - Timeouts are positive
 * - Thresholds are valid
 */
bool config_validate(void);

/**
 * @brief Print current configuration (for debugging)
 *
 * Dumps all configuration values to stdout in a readable format.
 * Useful for debugging configuration issues.
 */
void config_print(void);

/* ================================
 * Access Macros (Convenience)
 * ================================
 */

/**
 * @brief Check if temperature is in valid operating range
 */
#define CONFIG_IS_VALID_TEMP(t) \
    ((t) >= g_config.temperatures.min_temp && (t) <= g_config.temperatures.max_temp)

/**
 * @brief Check if temperature is safe for IDLE state
 */
#define CONFIG_IS_SAFE_IDLE_TEMP(t) \
    ((t) <= g_config.temperatures.safe_idle_temp)

/**
 * @brief Check if pan detection timeout has elapsed
 */
#define CONFIG_PAN_DETECT_TIMEOUT(now_ms, start_ms) \
    ((now_ms) - (start_ms) >= g_config.timeouts.pan_detect)

/**
 * @brief Calculate remaining pan detection time (ms)
 */
#define CONFIG_PAN_DETECT_REMAINING(now_ms, start_ms) \
    (g_config.timeouts.pan_detect - ((now_ms) - (start_ms)))

#endif /* CONFIG_H */

/* ================================
 * Legacy #define block
 * ================================
 *
 * These are emitted for backward compatibility with state_machine.c.
 * Every value matches the corresponding field in the *_DEFAULT block above.
 * New parameters should use `legacy_define: false` and access g_config directly.
 */

#define SAFE_IDLE_TEMP 50.0f
#define MIN_TEMP 30.0f
#define MAX_TEMP 250.0f
#define PAN_DETECT_TIMEOUT_MS 5000
#define NO_PAN_TIMEOUT_MS 3000
#define MAX_PREHEAT_TIME_MS 600000
#define PAN_DEBOUNCE_COUNT 10
#define PAN_CONFIDENCE_REQUIRED 3
#define MESSAGE_DISPLAY_TIME_MS 2000
