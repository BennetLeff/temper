/**
 * @file config.c
 * @brief Implementation of firmware configuration (ADDITIVE, non-breaking)
 * 
 * This file implements the configuration system defined in config.h.
 * All functions are ADDITIVE - existing code using direct
 * constants continues to work.
 * Migration to g_config is optional.
 */

#include "config.h"
#include <string.h>
#include <stdlib.h>

/* ================================
 * Global Configuration Instance
 * ================================
 */

config_t g_config;

/* ================================
 * Implementation
 * ================================
 */

void config_init(void) {
    /* Load temperature limits with defaults */
    g_config.temperatures = (temperature_limits_t)TEMP_LIMITS_DEFAULT;
    
    /* Load timeouts with defaults */
    g_config.timeouts = (timeouts_t)TIMEOUTS_DEFAULT;
    
    /* Load thresholds with defaults */
    g_config.thresholds = (thresholds_t)THRESHOLDS_DEFAULT;
}

void config_load_defaults(void) {
    /* Reset temperature limits to defaults */
    g_config.temperatures = (temperature_limits_t)TEMP_LIMITS_DEFAULT;
    
    /* Reset timeouts to defaults */
    g_config.timeouts = (timeouts_t)TIMEOUTS_DEFAULT;
    
    /* Reset thresholds to defaults */
    g_config.thresholds = (thresholds_t)THRESHOLDS_DEFAULT;
}

void config_set_from_env(void) {
    const char *env_str;
    
    /* Load temperature limits */
    env_str = getenv("TEMP_SAFE_IDLE_C");
    if (env_str) {
        g_config.temperatures.safe_idle_temp = strtof(env_str, NULL, 10);
    }
    
    env_str = getenv("TEMP_MIN_C");
    if (env_str) {
        g_config.temperatures.min_temp = strtof(env_str, NULL, 10);
    }
    
    env_str = getenv("TEMP_MAX_C");
    if (env_str) {
        g_config.temperatures.max_temp = strtof(env_str, NULL, 10);
    }
    
    /* Load timeouts */
    env_str = getenv("PAN_DETECT_TIMEOUT_MS");
    if (env_str) {
        g_config.timeouts.pan_detect = strtoul(env_str, NULL, 10);
    }
    
    env_str = getenv("NO_PAN_GRACE_MS");
    if (env_str) {
        g_config.timeouts.no_pan_grace = strtoul(env_str, NULL, 10);
    }
    
    env_str = getenv("MAX_PREHEAT_MS");
    if (env_str) {
        g_config.timeouts.max_preheat = strtoul(env_str, NULL, 10);
    }
    
    env_str = getenv("WDT_NORMAL_MS");
    if (env_str) {
        g_config.timeouts.wdt_normal = strtoul(env_str, NULL, 10);
    }
    
    env_str = getenv("WDT_IDLE_MS");
    if (env_str) {
        g_config.timeouts.wdt_idle = strtoul(env_str, NULL, 10);
    }
    
    env_str = getenv("WDT_INIT_MS");
    if (env_str) {
        g_config.timeouts.wdt_init = strtoul(env_str, NULL, 10);
    }
    
    env_str = getenv("FAN_CHECK_INTERVAL_MS");
    if (env_str) {
        g_config.timeouts.fan_check_interval = strtoul(env_str, NULL, 10);
    }
    
    env_str = getenv("ADC_CHECK_INTERVAL_MS");
    if (env_str) {
        g_config.timeouts.adc_check_interval = strtoul(env_str, NULL, 10);
    }
    
    /* Load thresholds */
    env_str = getenv("PAN_DEBOUNCE_COUNT");
    if (env_str) {
        g_config.thresholds.pan_debounce_count = (uint16_t)strtoul(env_str, NULL, 10);
    }
    
    env_str = getenv("PAN_CONFIDENCE_REQUIRED");
    if (env_str) {
        g_config.thresholds.pan_confidence_required = (uint8_t)strtoul(env_str, NULL, 10);
    }
    
    env_str = getenv("ADC_MIN_VALID_RAW");
    if (env_str) {
        g_config.thresholds.adc_min_valid_raw = (uint16_t)strtoul(env_str, NULL, 10);
    }
    
    env_str = getenv("ADC_MAX_VALID_RAW");
    if (env_str) {
        g_config.thresholds.adc_max_valid_raw = (uint16_t)strtoul(env_str, NULL, 10);
    }
    
    env_str = getenv("ADC_STUCK_BUFFER_SIZE");
    if (env_str) {
        g_config.thresholds.adc_stuck_buffer_size = (uint8_t)strtoul(env_str, NULL, 10);
    }
    
    env_str = getenv("ADC_STUCK_VARIANCE_THRESHOLD");
    if (env_str) {
        g_config.thresholds.adc_stuck_variance_threshold = (uint32_t)strtoul(env_str, NULL, 10);
    }
    
    env_str = getenv("ADC_WATCHDOG_TIMEOUT_MS");
    if (env_str) {
        g_config.thresholds.adc_watchdog_timeout_ms = strtoul(env_str, NULL, 10);
    }
    
    env_str = getenv("FAN_MAX_TEMP_RISE_RATE_C_PER_S");
    if (env_str) {
        g_config.thresholds.fan_max_temp_rise_rate_c_per_s = strtof(env_str, NULL, 10);
    }
}

bool config_validate(void) {
    bool valid = true;
    
    /* Validate temperature limits */
    if (g_config.temperatures.min_temp < 0 || g_config.temperatures.min_temp > 300) {
        valid = false;
    }
    if (g_config.temperatures.max_temp < 0 || g_config.temperatures.max_temp > 300) {
        valid = false;
    }
    if (g_config.temperatures.safe_idle_temp < 0 || g_config.temperatures.safe_idle_temp > 300) {
        valid = false;
    }
    
    /* Validate temperatures are in range */
    if (g_config.temperatures.min_temp >= g_config.temperatures.max_temp) {
        valid = false;
    }
    if (g_config.temperatures.safe_idle_temp > g_config.temperatures.max_temp) {
        valid = false;
    }
    
    /* Validate timeouts are positive */
    if (g_config.timeouts.pan_detect == 0 || g_config.timeouts.pan_detect > 60000) {
        valid = false;
    }
    if (g_config.timeouts.no_pan_grace == 0 || g_config.timeouts.no_pan_grace > 60000) {
        valid = false;
    }
    if (g_config.timeouts.max_preheat == 0 || g_config.timeouts.max_preheat > 600000) {
        valid = false;
    }
    if (g_config.timeouts.wdt_normal == 0 || g_config.timeouts.wdt_normal > 60000) {
        valid = false;
    }
    if (g_config.timeouts.wdt_idle == 0 || g_config.timeouts.wdt_idle > 60000) {
        valid = false;
    }
    if (g_config.timeouts.wdt_init == 0 || g_config.timeouts.wdt_init > 30000) {
        valid = false;
    }
    if (g_config.timeouts.fan_check_interval == 0 || g_config.timeouts.fan_check_interval > 10000) {
        valid = false;
    }
    if (g_config.timeouts.adc_check_interval == 0 || g_config.timeouts.adc_check_interval > 10000) {
        valid = false;
    }
    
    /* Validate thresholds are reasonable */
    if (g_config.thresholds.pan_debounce_count == 0 || g_config.thresholds.pan_debounce_count > 100) {
        valid = false;
    }
    if (g_config.thresholds.pan_confidence_required == 0 || g_config.thresholds.pan_confidence_required > 10) {
        valid = false;
    }
    if (g_config.thresholds.adc_min_valid_raw == 0 || g_config.thresholds.adc_min_valid_raw >= 4096) {
        valid = false;
    }
    if (g_config.thresholds.adc_max_valid_raw <= g_config.thresholds.adc_min_valid_raw) {
        valid = false;
    }
    if (g_config.thresholds.adc_stuck_buffer_size == 0 || g_config.thresholds.adc_stuck_buffer_size > 32) {
        valid = false;
    }
    if (g_config.thresholds.adc_stuck_variance_threshold == 0) {
        valid = false;
    }
    if (g_config.thresholds.adc_watchdog_timeout_ms == 0 || g_config.thresholds.adc_watchdog_timeout_ms > 10000) {
        valid = false;
    }
    if (g_config.thresholds.fan_max_temp_rise_rate_c_per_s < 0 || g_config.thresholds.fan_max_temp_rise_rate_c_per_s > 100) {
        valid = false;
    }
    
    return valid;
}

void config_print(void) {
    /* Print version info */
    printf("========================================\n");
    printf("Firmware Configuration\n");
    printf("========================================\n");
    printf("Version: %s\n", CONFIG_VERSION_STRING);
    printf("Build: %s %s\n", CONFIG_BUILD_DATE, CONFIG_BUILD_TIME);
    printf("\n");
    
    /* Print temperature limits */
    printf("Temperature Limits (°C):\n");
    printf("  Safe Idle: %.1f\n", g_config.temperatures.safe_idle_temp);
    printf("  Minimum:   %.1f\n", g_config.temperatures.min_temp);
    printf("  Maximum:   %.1f\n", g_config.temperatures.max_temp);
    printf("\n");
    
    /* Print timeouts (ms) */
    printf("Timeouts (ms):\n");
    printf("  Pan Detect:     %lu\n", g_config.timeouts.pan_detect);
    printf("  No Pan Grace:   %lu\n", g_config.timeouts.no_pan_grace);
    printf("  Max Preheat:    %lu\n", g_config.timeouts.max_preheat);
    printf("  WDT Normal:      %lu\n", g_config.timeouts.wdt_normal);
    printf("  WDT Idle:        %lu\n", g_config.timeouts.wdt_idle);
    printf("  WDT Init:         %lu\n", g_config.timeouts.wdt_init);
    printf("  Fan Check:       %lu\n", g_config.timeouts.fan_check_interval);
    printf("  ADC Check:       %lu\n", g_config.timeouts.adc_check_interval);
    printf("\n");
    
    /* Print thresholds */
    printf("Thresholds:\n");
    printf("  Pan Debounce Count:   %u\n", g_config.thresholds.pan_debounce_count);
    printf("  Pan Confidence Required: %u\n", g_config.thresholds.pan_confidence_required);
    printf("  ADC Min Valid:      %u\n", g_config.thresholds.adc_min_valid_raw);
    printf("  ADC Max Valid:      %u\n", g_config.thresholds.adc_max_valid_raw);
    printf("  ADC Stuck Buffer:   %u\n", g_config.thresholds.adc_stuck_buffer_size);
    printf("  ADC Stuck Variance: %u\n", g_config.thresholds.adc_stuck_variance_threshold);
    printf("  ADC Watchdog:      %lu ms\n", g_config.thresholds.adc_watchdog_timeout_ms);
    printf("  Fan Max Temp Rise: %.2f °C/s\n", g_config.thresholds.fan_max_temp_rise_rate_c_per_s);
    printf("\n");
    printf("========================================\n");
}
