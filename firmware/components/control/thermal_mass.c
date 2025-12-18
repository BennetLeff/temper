/**
 * @file thermal_mass.c
 * @brief Thermal mass estimation implementation
 * 
 * Estimates pan thermal mass during detection phase to auto-tune PID gains.
 * Uses power pulse method to measure thermal response and classify pan type.
 */

#include "thermal_mass.h"
#include <math.h>
#include <string.h>
#include <stdio.h>

/* Default configuration for thermal mass estimation */
#define THERMAL_MASS_TEST_POWER_DEFAULT    500.0f   /**< 500W test pulse */
#define THERMAL_MASS_TEST_DURATION_DEFAULT 5000     /**< 5 second test */
#define THERMAL_MASS_LIGHT_THRESHOLD       500.0f   /**< J/K threshold for light pans */
#define THERMAL_MASS_MEDIUM_THRESHOLD      1500.0f  /**< J/K threshold for medium pans */
#define THERMAL_MASS_MEASUREMENT_SAMPLES   10       /**< Number of temperature samples */
#define THERMAL_MASS_MIN_TEMP_RISE         2.0f     /**< Minimum temp rise for valid test */

/* PID gain sets for different pan types */
static const pid_gains_t PAN_CLASS_GAINS[] = {
    /* PAN_CLASS_UNKNOWN - use medium as default */
    [PAN_CLASS_UNKNOWN] = { .kp = 1.0f, .ki = 0.1f, .kd = 0.2f },
    
    /* PAN_CLASS_LIGHT - Fast response, low overshoot */
    [PAN_CLASS_LIGHT] = { .kp = 0.5f, .ki = 0.05f, .kd = 0.1f },
    
    /* PAN_CLASS_MEDIUM - Balanced response */
    [PAN_CLASS_MEDIUM] = { .kp = 1.0f, .ki = 0.1f, .kd = 0.2f },
    
    /* PAN_CLASS_HEAVY - Slower, more aggressive */
    [PAN_CLASS_HEAVY] = { .kp = 2.0f, .ki = 0.2f, .kd = 0.5f },
    
    /* PAN_CLASS_INVALID - Safe fallback */
    [PAN_CLASS_INVALID] = { .kp = 0.8f, .ki = 0.08f, .kd = 0.16f }
};

/* Classification names for debugging */
static const char* PAN_CLASS_NAMES[] = {
    [PAN_CLASS_UNKNOWN] = "UNKNOWN",
    [PAN_CLASS_LIGHT] = "LIGHT",
    [PAN_CLASS_MEDIUM] = "MEDIUM", 
    [PAN_CLASS_HEAVY] = "HEAVY",
    [PAN_CLASS_INVALID] = "INVALID"
};

thermal_mass_config_t thermal_mass_get_default_config(void) {
    thermal_mass_config_t config = {
        .test_power_watts = THERMAL_MASS_TEST_POWER_DEFAULT,
        .test_duration_ms = THERMAL_MASS_TEST_DURATION_DEFAULT,
        .light_threshold = THERMAL_MASS_LIGHT_THRESHOLD,
        .medium_threshold = THERMAL_MASS_MEDIUM_THRESHOLD,
        .measurement_samples = THERMAL_MASS_MEASUREMENT_SAMPLES,
        .min_temp_rise = THERMAL_MASS_MIN_TEMP_RISE
    };
    return config;
}

void thermal_mass_init(thermal_mass_handle_t *handle, const thermal_mass_config_t *config) {
    if (handle == NULL) {
        return;
    }
    
    /* Use provided config or defaults */
    if (config != NULL) {
        memcpy(&handle->config, config, sizeof(thermal_mass_config_t));
    } else {
        handle->config = thermal_mass_get_default_config();
    }
    
    /* Initialize state */
    handle->current_class = PAN_CLASS_UNKNOWN;
    handle->current_gains = PAN_CLASS_GAINS[PAN_CLASS_MEDIUM];  /* Default to medium */
    handle->estimation_active = false;
    handle->estimation_start_time = 0;
    handle->initial_temperature = 0.0f;
    handle->test_power_level = 0.0f;
    handle->sample_count = 0;
    handle->temperature_sum = 0.0f;
    handle->classification_valid = false;
}

bool thermal_mass_start_estimation(thermal_mass_handle_t *handle, float initial_temp) {
    if (handle == NULL || !thermal_mass_validate_temperature(initial_temp)) {
        return false;
    }
    
    /* Initialize estimation state */
    handle->estimation_active = true;
    handle->estimation_start_time = 0;  /* Will be set on first update with actual time */
    handle->initial_temperature = initial_temp;
    handle->test_power_level = handle->config.test_power_watts;
    handle->sample_count = 0;
    handle->temperature_sum = 0.0f;
    handle->classification_valid = false;
    handle->current_class = PAN_CLASS_UNKNOWN;
    
    /* Log start of estimation */
    #ifdef ESP_PLATFORM
    ESP_LOGI("thermal_mass", "Starting thermal mass estimation, initial temp: %.1f°C", initial_temp);
    #endif
    
    return true;
}

bool thermal_mass_update(thermal_mass_handle_t *handle, float current_temp, uint32_t current_time_ms) {
    if (handle == NULL || !handle->estimation_active) {
        return false;
    }
    
    /* Validate temperature reading */
    if (!thermal_mass_validate_temperature(current_temp)) {
        #ifdef ESP_PLATFORM
        ESP_LOGW("thermal_mass", "Invalid temperature reading: %.1f°C", current_temp);
        #endif
        handle->estimation_active = false;
        handle->current_class = PAN_CLASS_INVALID;
        return true;  /* Estimation failed */
    }
    
    /* Initialize start time on first call */
    if (handle->estimation_start_time == 0) {
        handle->estimation_start_time = current_time_ms;
    }
    
    /* Check if test duration has elapsed */
    uint32_t elapsed_ms = current_time_ms - handle->estimation_start_time;
    
    if (elapsed_ms < handle->config.test_duration_ms) {
        /* Test not complete yet, just collect sample */
        handle->sample_count++;
        handle->temperature_sum += current_temp;
        return false;
    }
    
    /* Test duration elapsed, collect final sample and complete */
    handle->sample_count++;
    handle->temperature_sum += current_temp;
    
    /* Calculate average temperature rise */
    float avg_temp = handle->temperature_sum / handle->sample_count;
    float temp_rise = avg_temp - handle->initial_temperature;
    
    /* Debug logging */
    #ifdef ESP_PLATFORM
    ESP_LOGI("thermal_mass", "Avg temp: %.1f°C, Initial: %.1f°C, Rise: %.1f°C", 
            avg_temp, handle->initial_temperature, temp_rise);
    #endif
    
    /* Validate measurement */
    if (temp_rise < handle->config.min_temp_rise) {
        #ifdef ESP_PLATFORM
        ESP_LOGW("thermal_mass", "Temperature rise too small: %.1f°C (min: %.1f°C)", 
                temp_rise, handle->config.min_temp_rise);
        #endif
        handle->current_class = PAN_CLASS_INVALID;
    } else {
        /* Calculate thermal mass indicator: M = P * t / ΔT */
        float test_time_sec = (float)elapsed_ms / 1000.0f;
        float thermal_mass = (handle->config.test_power_watts * test_time_sec) / temp_rise;
        
        /* Classify pan based on thermal mass */
        if (thermal_mass < handle->config.light_threshold) {
            handle->current_class = PAN_CLASS_LIGHT;
        } else if (thermal_mass < handle->config.medium_threshold) {
            handle->current_class = PAN_CLASS_MEDIUM;
        } else {
            handle->current_class = PAN_CLASS_HEAVY;
        }
        
        /* Log classification result */
        #ifdef ESP_PLATFORM
        ESP_LOGI("thermal_mass", "Thermal mass: %.0f J/K, classified as: %s", 
                thermal_mass, PAN_CLASS_NAMES[handle->current_class]);
        #endif
    }
    
    /* Set final gains based on classification */
    handle->current_gains = PAN_CLASS_GAINS[handle->current_class];
    handle->classification_valid = true;
    handle->estimation_active = false;
    
    return true;  /* Estimation complete */
    
    return false;  /* Estimation still in progress */
}

pan_class_t thermal_mass_get_classification(thermal_mass_handle_t *handle) {
    if (handle == NULL) {
        return PAN_CLASS_INVALID;
    }
    return handle->current_class;
}

pid_gains_t thermal_mass_get_pid_gains(thermal_mass_handle_t *handle) {
    if (handle == NULL) {
        return PAN_CLASS_GAINS[PAN_CLASS_INVALID];
    }
    return handle->current_gains;
}

bool thermal_mass_is_active(thermal_mass_handle_t *handle) {
    if (handle == NULL) {
        return false;
    }
    return handle->estimation_active;
}

bool thermal_mass_is_classified(thermal_mass_handle_t *handle) {
    if (handle == NULL) {
        return false;
    }
    return handle->classification_valid;
}

void thermal_mass_reset(thermal_mass_handle_t *handle) {
    if (handle == NULL) {
        return;
    }
    
    handle->current_class = PAN_CLASS_UNKNOWN;
    handle->current_gains = PAN_CLASS_GAINS[PAN_CLASS_MEDIUM];
    handle->estimation_active = false;
    handle->classification_valid = false;
    handle->sample_count = 0;
    handle->temperature_sum = 0.0f;
}

pid_gains_t thermal_mass_get_gains_for_class(pan_class_t pan_class) {
    if (pan_class >= PAN_CLASS_INVALID) {
        return PAN_CLASS_GAINS[PAN_CLASS_INVALID];
    }
    return PAN_CLASS_GAINS[pan_class];
}

const char* thermal_mass_class_to_string(pan_class_t pan_class) {
    if (pan_class >= PAN_CLASS_INVALID) {
        return "INVALID";
    }
    return PAN_CLASS_NAMES[pan_class];
}

bool thermal_mass_validate_temperature(float temp) {
    /* Check for reasonable temperature range for cooktop operation */
    return (temp >= 0.0f && temp <= 300.0f && isfinite(temp));
}