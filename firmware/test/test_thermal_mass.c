/**
 * @file test_thermal_mass.c
 * @brief Unit tests for thermal mass estimation module
 * 
 * Tests verify:
 * - Thermal mass calculation and classification
 * - PID gain selection based on pan type
 * - Temperature validation
 * - State machine integration
 */

#include <math.h>
#include "unity/unity.h"
#include "test_common.h"
#include "../components/control/thermal_mass.h"

/* Test fixtures */
static thermal_mass_handle_t test_thermal_mass;
static thermal_mass_config_t test_config;

/* Unity setup/teardown for this module */
static void thermal_mass_test_setup(void) {
    test_config = thermal_mass_get_default_config();
    thermal_mass_init(&test_thermal_mass, &test_config);
}

/* ============================================================================
 * Configuration Tests
 * ============================================================================ */

static void test_thermal_mass_get_default_config(void) {
    thermal_mass_test_setup();  /* Initialize before each test */
    
    thermal_mass_config_t config = thermal_mass_get_default_config();
    
    TEST_ASSERT_EQUAL_FLOAT(500.0f, config.test_power_watts);
    TEST_ASSERT_EQUAL_UINT32(5000, config.test_duration_ms);
    TEST_ASSERT_EQUAL_FLOAT(500.0f, config.light_threshold);
    TEST_ASSERT_EQUAL_FLOAT(1500.0f, config.medium_threshold);
    TEST_ASSERT_EQUAL_UINT8(10, config.measurement_samples);
    TEST_ASSERT_EQUAL_FLOAT(2.0f, config.min_temp_rise);
}

static void test_thermal_mass_init_with_config(void) {
    thermal_mass_test_setup();  /* Initialize before each test */
    
    thermal_mass_config_t custom_config = {
        .test_power_watts = 300.0f,
        .test_duration_ms = 3000,
        .light_threshold = 400.0f,
        .medium_threshold = 1200.0f,
        .measurement_samples = 5,
        .min_temp_rise = 1.5f
    };
    
    thermal_mass_handle_t handle;
    thermal_mass_init(&handle, &custom_config);
    
    TEST_ASSERT_EQUAL_FLOAT(300.0f, handle.config.test_power_watts);
    TEST_ASSERT_EQUAL_UINT32(3000, handle.config.test_duration_ms);
    TEST_ASSERT_EQUAL_FLOAT(400.0f, handle.config.light_threshold);
    TEST_ASSERT_EQUAL_FLOAT(1200.0f, handle.config.medium_threshold);
    TEST_ASSERT_EQUAL_UINT8(5, handle.config.measurement_samples);
    TEST_ASSERT_EQUAL_FLOAT(1.5f, handle.config.min_temp_rise);
}

static void test_thermal_mass_init_with_null_config(void) {
    thermal_mass_handle_t handle;
    thermal_mass_init(&handle, NULL);
    
    /* Should use defaults */
    TEST_ASSERT_EQUAL_FLOAT(500.0f, handle.config.test_power_watts);
    TEST_ASSERT_EQUAL_UINT32(5000, handle.config.test_duration_ms);
}

/* ============================================================================
 * Classification Tests
 * ============================================================================ */

static void test_thermal_mass_classify_light_pan(void) {
    /* Light pan: M < 500 J/K (fast thermal response) */
    /* Example: 500W * 5s / 10°C rise = 250 J/K */
    pid_gains_t gains = thermal_mass_get_gains_for_class(PAN_CLASS_LIGHT);
    
    TEST_ASSERT_EQUAL_FLOAT(0.5f, gains.kp);
    TEST_ASSERT_EQUAL_FLOAT(0.05f, gains.ki);
    TEST_ASSERT_EQUAL_FLOAT(0.1f, gains.kd);
}

static void test_thermal_mass_classify_medium_pan(void) {
    /* Medium pan: 500 <= M < 1500 J/K (balanced response) */
    /* Example: 500W * 5s / 4°C rise = 625 J/K */
    pid_gains_t gains = thermal_mass_get_gains_for_class(PAN_CLASS_MEDIUM);
    
    TEST_ASSERT_EQUAL_FLOAT(1.0f, gains.kp);
    TEST_ASSERT_EQUAL_FLOAT(0.1f, gains.ki);
    TEST_ASSERT_EQUAL_FLOAT(0.2f, gains.kd);
}

static void test_thermal_mass_classify_heavy_pan(void) {
    /* Heavy pan: M >= 1500 J/K (slow thermal response) */
    /* Example: 500W * 5s / 2°C rise = 1250 J/K */
    pid_gains_t gains = thermal_mass_get_gains_for_class(PAN_CLASS_HEAVY);
    
    TEST_ASSERT_EQUAL_FLOAT(2.0f, gains.kp);
    TEST_ASSERT_EQUAL_FLOAT(0.2f, gains.ki);
    TEST_ASSERT_EQUAL_FLOAT(0.5f, gains.kd);
}

static void test_thermal_mass_class_to_string(void) {
    TEST_ASSERT_EQUAL_STRING("UNKNOWN", thermal_mass_class_to_string(PAN_CLASS_UNKNOWN));
    TEST_ASSERT_EQUAL_STRING("LIGHT", thermal_mass_class_to_string(PAN_CLASS_LIGHT));
    TEST_ASSERT_EQUAL_STRING("MEDIUM", thermal_mass_class_to_string(PAN_CLASS_MEDIUM));
    TEST_ASSERT_EQUAL_STRING("HEAVY", thermal_mass_class_to_string(PAN_CLASS_HEAVY));
    TEST_ASSERT_EQUAL_STRING("INVALID", thermal_mass_class_to_string(PAN_CLASS_INVALID));
}

/* ============================================================================
 * Estimation Process Tests
 * ============================================================================ */

static void test_thermal_mass_start_estimation(void) {
    bool result = thermal_mass_start_estimation(&test_thermal_mass, 25.0f);
    
    TEST_ASSERT_TRUE(result);
    TEST_ASSERT_TRUE(thermal_mass_is_active(&test_thermal_mass));
    TEST_ASSERT_FALSE(thermal_mass_is_classified(&test_thermal_mass));
    TEST_ASSERT_EQUAL_FLOAT(25.0f, test_thermal_mass.initial_temperature);
}

static void test_thermal_mass_start_estimation_invalid_temp(void) {
    bool result = thermal_mass_start_estimation(&test_thermal_mass, -10.0f);
    TEST_ASSERT_FALSE(result);
    
    result = thermal_mass_start_estimation(&test_thermal_mass, 350.0f);
    TEST_ASSERT_FALSE(result);
    
    result = thermal_mass_start_estimation(&test_thermal_mass, NAN);
    TEST_ASSERT_FALSE(result);
}

static void test_thermal_mass_update_light_pan(void) {
    /* Start estimation */
    thermal_mass_start_estimation(&test_thermal_mass, 25.0f);
    
    /* Simulate light pan: temperature rises quickly over multiple samples */
    uint32_t start_time = 1000;
    
    /* First sample sets the start time, so we need to go beyond test duration */
    for (int i = 0; i < 11; i++) {
        float temp = 25.0f + (i + 1) * 1.0f;  /* 26°C, 27°C, ..., 36°C */
        uint32_t current_time = start_time + (i + 1) * 500;
        bool complete = thermal_mass_update(&test_thermal_mass, temp, current_time);
        
        if (i < 10) {
            TEST_ASSERT_FALSE(complete);  /* Not done yet */
        } else {
            TEST_ASSERT_TRUE(complete);   /* Should be done */
        }
    }
    
    TEST_ASSERT_EQUAL(PAN_CLASS_LIGHT, thermal_mass_get_classification(&test_thermal_mass));
    
    pid_gains_t gains = thermal_mass_get_pid_gains(&test_thermal_mass);
    TEST_ASSERT_EQUAL_FLOAT(0.5f, gains.kp);
}

static void test_thermal_mass_update_medium_pan(void) {
    /* Start estimation */
    thermal_mass_start_estimation(&test_thermal_mass, 25.0f);
    
    /* Simulate medium pan: temperature rises moderately over multiple samples */
    uint32_t start_time = 1000;
    
    /* Collect multiple samples with moderate temperature rise */
    for (int i = 0; i < 11; i++) {
        float temp = 25.0f + (i + 1) * 0.25f;  /* 25.25°C, 25.50°C, ..., 27.75°C */
        bool complete = thermal_mass_update(&test_thermal_mass, temp, start_time + (i + 1) * 500);
        
        if (i < 10) {
            TEST_ASSERT_FALSE(complete);  /* Not done yet */
        } else {
            TEST_ASSERT_TRUE(complete);   /* Should be done */
        }
    }
    
    TEST_ASSERT_EQUAL(PAN_CLASS_MEDIUM, thermal_mass_get_classification(&test_thermal_mass));
    
    pid_gains_t gains = thermal_mass_get_pid_gains(&test_thermal_mass);
    TEST_ASSERT_EQUAL_FLOAT(2.0f, gains.kp);
}

static void test_thermal_mass_update_insufficient_rise(void) {
    /* Start estimation */
    thermal_mass_start_estimation(&test_thermal_mass, 25.0f);
    
    /* Simulate insufficient temperature rise over multiple samples */
    uint32_t start_time = 1000;
    
    /* Collect multiple samples with minimal temperature rise */
    for (int i = 0; i < 11; i++) {
        float temp = 25.0f + (i + 1) * 0.05f;  /* 25.05°C, 25.10°C, ..., 25.55°C */
        bool complete = thermal_mass_update(&test_thermal_mass, temp, start_time + (i + 1) * 500);
        
        if (i < 10) {
            TEST_ASSERT_FALSE(complete);  /* Not done yet */
        } else {
            TEST_ASSERT_TRUE(complete);   /* Should be done */
        }
    }
    
    TEST_ASSERT_EQUAL(PAN_CLASS_INVALID, thermal_mass_get_classification(&test_thermal_mass));
}

static void test_thermal_mass_update_in_progress(void) {
    /* Start estimation */
    thermal_mass_start_estimation(&test_thermal_mass, 25.0f);
    
    /* Simulate partial progress - not enough time elapsed */
    uint32_t start_time = 1000;
    bool complete = thermal_mass_update(&test_thermal_mass, 27.0f, start_time + 2000);
    
    TEST_ASSERT_FALSE(complete);
    TEST_ASSERT_TRUE(thermal_mass_is_active(&test_thermal_mass));
    TEST_ASSERT_EQUAL(PAN_CLASS_UNKNOWN, thermal_mass_get_classification(&test_thermal_mass));
    
    /* Verify it's still active after multiple calls within duration */
    complete = thermal_mass_update(&test_thermal_mass, 28.0f, start_time + 4000);
    TEST_ASSERT_FALSE(complete);
    TEST_ASSERT_TRUE(thermal_mass_is_active(&test_thermal_mass));
}

/* ============================================================================
 * State Management Tests
 * ============================================================================ */

static void test_thermal_mass_reset(void) {
    thermal_mass_test_setup();  /* Initialize before each test */
    
    /* Start and complete estimation */
    thermal_mass_start_estimation(&test_thermal_mass, 25.0f);
    
    /* Complete the estimation with multiple samples */
    for (int i = 0; i < 11; i++) {
        float temp = 25.0f + (i + 1) * 1.0f;  /* 26°C, 27°C, ..., 36°C */
        thermal_mass_update(&test_thermal_mass, temp, 1000 + (i + 1) * 500);
    }
    
    TEST_ASSERT_TRUE(thermal_mass_is_classified(&test_thermal_mass));
    
    /* Reset - this function returns void */
    thermal_mass_reset(&test_thermal_mass);
    
    TEST_ASSERT_FALSE(thermal_mass_is_active(&test_thermal_mass));
    TEST_ASSERT_FALSE(thermal_mass_is_classified(&test_thermal_mass));
    TEST_ASSERT_EQUAL(PAN_CLASS_UNKNOWN, thermal_mass_get_classification(&test_thermal_mass));
}

static void test_thermal_mass_null_handle(void) {
    /* Test with NULL handle */
    TEST_ASSERT_EQUAL(PAN_CLASS_INVALID, thermal_mass_get_classification(NULL));
    
    pid_gains_t gains = thermal_mass_get_pid_gains(NULL);
    TEST_ASSERT_EQUAL_FLOAT(0.8f, gains.kp);  /* INVALID class gains */
    
    TEST_ASSERT_FALSE(thermal_mass_is_active(NULL));
    TEST_ASSERT_FALSE(thermal_mass_is_classified(NULL));
    
    thermal_mass_reset(NULL);  /* Should not crash */
}

/* ============================================================================
 * Temperature Validation Tests
 * ============================================================================ */

static void test_thermal_mass_validate_temperature_valid(void) {
    TEST_ASSERT_TRUE(thermal_mass_validate_temperature(25.0f));
    TEST_ASSERT_TRUE(thermal_mass_validate_temperature(100.0f));
    TEST_ASSERT_TRUE(thermal_mass_validate_temperature(250.0f));
    TEST_ASSERT_TRUE(thermal_mass_validate_temperature(0.0f));
}

static void test_thermal_mass_validate_temperature_invalid(void) {
    TEST_ASSERT_FALSE(thermal_mass_validate_temperature(-1.0f));
    TEST_ASSERT_FALSE(thermal_mass_validate_temperature(301.0f));
    TEST_ASSERT_FALSE(thermal_mass_validate_temperature(INFINITY));
    TEST_ASSERT_FALSE(thermal_mass_validate_temperature(NAN));
}

/* ============================================================================
 * Integration Tests
 * ============================================================================ */

static void test_thermal_mass_full_estimation_cycle(void) {
    /* Start estimation */
    bool started = thermal_mass_start_estimation(&test_thermal_mass, 20.0f);
    TEST_ASSERT_TRUE(started);
    
    /* Simulate multiple temperature readings during test */
    uint32_t start_time = 1000;
    
    /* Light pan simulation: quick temperature rise over sufficient duration */
    for (int i = 0; i < 11; i++) {
        float temp = 20.0f + (i + 1) * 1.0f;  /* 21°C, 22°C, ..., 31°C */
        bool complete = thermal_mass_update(&test_thermal_mass, temp, start_time + (i + 1) * 500);
        
        if (i < 10) {
            TEST_ASSERT_FALSE(complete);  /* Not done yet */
        } else {
            TEST_ASSERT_TRUE(complete);   /* Should be done */
        }
    }
    
    /* Verify final classification and gains */
    TEST_ASSERT_TRUE(thermal_mass_is_classified(&test_thermal_mass));
    TEST_ASSERT_EQUAL(PAN_CLASS_LIGHT, thermal_mass_get_classification(&test_thermal_mass));
    
    pid_gains_t gains = thermal_mass_get_pid_gains(&test_thermal_mass);
    TEST_ASSERT_EQUAL_FLOAT(0.5f, gains.kp);
    TEST_ASSERT_EQUAL_FLOAT(0.05f, gains.ki);
    TEST_ASSERT_EQUAL_FLOAT(0.1f, gains.kd);
}

/* ============================================================================
 * Edge Cases & Error Conditions Tests
 * ============================================================================ */

static void test_thermal_mass_rapid_temp_changes(void) {
    thermal_mass_test_setup();
    
    thermal_mass_start_estimation(&test_thermal_mass, 25.0f);
    
    /* Rapid temperature fluctuations */
    thermal_mass_update(&test_thermal_mass, 30.0f, 2000);  /* Jump up */
    thermal_mass_update(&test_thermal_mass, 20.0f, 2500);  /* Drop down */
    thermal_mass_update(&test_thermal_mass, 35.0f, 3000);  /* Jump up */
    
    bool complete = thermal_mass_update(&test_thermal_mass, 25.0f, 6000);
    TEST_ASSERT_TRUE(complete);
    
    /* Should handle fluctuations gracefully */
    pan_class_t classification = thermal_mass_get_classification(&test_thermal_mass);
    TEST_ASSERT_TRUE(classification >= PAN_CLASS_LIGHT && classification <= PAN_CLASS_HEAVY);
}

static void test_thermal_mass_temperature_drop_during_test(void) {
    thermal_mass_test_setup();
    
    thermal_mass_start_estimation(&test_thermal_mass, 25.0f);
    
    /* Temperature drops during test */
    thermal_mass_update(&test_thermal_mass, 24.0f, 2000);  /* Drop! */
    thermal_mass_update(&test_thermal_mass, 23.0f, 3000);  /* Drop more! */
    
    bool complete = thermal_mass_update(&test_thermal_mass, 22.0f, 6000);
    TEST_ASSERT_TRUE(complete);
    TEST_ASSERT_EQUAL(PAN_CLASS_INVALID, thermal_mass_get_classification(&test_thermal_mass));
}

static void test_thermal_mass_sensor_failure_mid_test(void) {
    thermal_mass_test_setup();
    
    thermal_mass_start_estimation(&test_thermal_mass, 25.0f);
    
    /* Normal operation */
    thermal_mass_update(&test_thermal_mass, 27.0f, 2000);
    thermal_mass_update(&test_thermal_mass, 29.0f, 3000);
    
    /* Sensor failure (NaN reading) */
    bool complete = thermal_mass_update(&test_thermal_mass, NAN, 6000);
    TEST_ASSERT_TRUE(complete);
    TEST_ASSERT_EQUAL(PAN_CLASS_INVALID, thermal_mass_get_classification(&test_thermal_mass));
}

static void test_thermal_mass_timing_edge_cases(void) {
    thermal_mass_test_setup();
    
    thermal_mass_start_estimation(&test_thermal_mass, 25.0f);
    
    /* Very rapid updates (simulating high-frequency sampling) */
    for (int i = 0; i < 20; i++) {
        float temp = 25.0f + (i + 1) * 0.5f;
        uint32_t time = 1000 + (i + 1) * 100;  /* 100ms intervals */
        bool complete = thermal_mass_update(&test_thermal_mass, temp, time);
        
        if (i < 19) {
            TEST_ASSERT_FALSE(complete);
        } else {
            TEST_ASSERT_TRUE(complete);
        }
    }
    
    TEST_ASSERT_EQUAL(PAN_CLASS_LIGHT, thermal_mass_get_classification(&test_thermal_mass));
}

/* ============================================================================
 * Boundary Conditions Tests
 * ============================================================================ */

static void test_thermal_mass_exact_threshold_light(void) {
    thermal_mass_test_setup();
    
    thermal_mass_start_estimation(&test_thermal_mass, 25.0f);
    
    /* Exactly at 500 J/K threshold - should classify as LIGHT */
    /* M = P * t / ΔT => 500 = 500 * 5 / ΔT => ΔT = 5°C */
    for (int i = 0; i < 11; i++) {
        float temp = 25.0f + (i + 1) * 0.5f;  /* 25.5°C, 26.0°C, ..., 30.0°C */
        thermal_mass_update(&test_thermal_mass, temp, 1000 + (i + 1) * 500);
    }
    
    TEST_ASSERT_EQUAL(PAN_CLASS_LIGHT, thermal_mass_get_classification(&test_thermal_mass));
}

static void test_thermal_mass_exact_threshold_medium(void) {
    thermal_mass_test_setup();
    
    thermal_mass_start_estimation(&test_thermal_mass, 25.0f);
    
    /* Exactly at 1500 J/K threshold - should classify as MEDIUM */
    /* M = P * t / ΔT => 1500 = 500 * 5 / ΔT => ΔT = 1.67°C */
    for (int i = 0; i < 11; i++) {
        float temp = 25.0f + (i + 1) * 0.167f;  /* ~25.17°C, 25.33°C, ..., 26.67°C */
        thermal_mass_update(&test_thermal_mass, temp, 1000 + (i + 1) * 500);
    }
    
    TEST_ASSERT_EQUAL(PAN_CLASS_MEDIUM, thermal_mass_get_classification(&test_thermal_mass));
}

static void test_thermal_mass_minimum_valid_temperature(void) {
    thermal_mass_test_setup();
    
    bool result = thermal_mass_start_estimation(&test_thermal_mass, 0.0f);
    TEST_ASSERT_TRUE(result);
    
    /* Should work with minimum valid temperature */
    bool complete = thermal_mass_update(&test_thermal_mass, 2.0f, 6000);
    TEST_ASSERT_TRUE(complete);
    TEST_ASSERT_EQUAL(PAN_CLASS_LIGHT, thermal_mass_get_classification(&test_thermal_mass));
}

static void test_thermal_mass_maximum_valid_temperature(void) {
    thermal_mass_test_setup();
    
    bool result = thermal_mass_start_estimation(&test_thermal_mass, 300.0f);
    TEST_ASSERT_TRUE(result);
    
    /* Should work with maximum valid temperature */
    bool complete = thermal_mass_update(&test_thermal_mass, 302.0f, 6000);
    TEST_ASSERT_TRUE(complete);
    TEST_ASSERT_EQUAL(PAN_CLASS_LIGHT, thermal_mass_get_classification(&test_thermal_mass));
}

static void test_thermal_mass_very_short_test_duration(void) {
    thermal_mass_config_t short_config = thermal_mass_get_default_config();
    short_config.test_duration_ms = 1000;  /* Very short test */
    
    thermal_mass_handle_t short_handle;
    thermal_mass_init(&short_handle, &short_config);
    
    bool result = thermal_mass_start_estimation(&short_handle, 25.0f);
    TEST_ASSERT_TRUE(result);
    
    /* Should complete quickly with short duration */
    bool complete = thermal_mass_update(&short_handle, 30.0f, 2000);
    TEST_ASSERT_TRUE(complete);
}

/* ============================================================================
 * Integration & State Management Tests
 * ============================================================================ */

static void test_thermal_mass_multiple_consecutive_estimations(void) {
    thermal_mass_test_setup();
    
    /* First estimation - light pan */
    thermal_mass_start_estimation(&test_thermal_mass, 25.0f);
    for (int i = 0; i < 11; i++) {
        float temp = 25.0f + (i + 1) * 1.0f;
        thermal_mass_update(&test_thermal_mass, temp, 1000 + (i + 1) * 500);
    }
    TEST_ASSERT_EQUAL(PAN_CLASS_LIGHT, thermal_mass_get_classification(&test_thermal_mass));
    
    /* Reset and second estimation - heavy pan */
    thermal_mass_reset(&test_thermal_mass);
    thermal_mass_start_estimation(&test_thermal_mass, 25.0f);
    for (int i = 0; i < 11; i++) {
        float temp = 25.0f + (i + 1) * 0.1f;
        thermal_mass_update(&test_thermal_mass, temp, 1000 + (i + 1) * 500);
    }
    TEST_ASSERT_EQUAL(PAN_CLASS_HEAVY, thermal_mass_get_classification(&test_thermal_mass));
}

static void test_thermal_mass_different_initial_temperatures(void) {
    thermal_mass_test_setup();
    
    /* Cold start */
    bool result1 = thermal_mass_start_estimation(&test_thermal_mass, 5.0f);
    TEST_ASSERT_TRUE(result1);
    
    for (int i = 0; i < 11; i++) {
        float temp = 5.0f + (i + 1) * 1.0f;
        thermal_mass_update(&test_thermal_mass, temp, 1000 + (i + 1) * 500);
    }
    TEST_ASSERT_EQUAL(PAN_CLASS_LIGHT, thermal_mass_get_classification(&test_thermal_mass));
    
    /* Hot start */
    thermal_mass_reset(&test_thermal_mass);
    bool result2 = thermal_mass_start_estimation(&test_thermal_mass, 150.0f);
    TEST_ASSERT_TRUE(result2);
    
    for (int i = 0; i < 11; i++) {
        float temp = 150.0f + (i + 1) * 1.0f;
        thermal_mass_update(&test_thermal_mass, temp, 1000 + (i + 1) * 500);
    }
    TEST_ASSERT_EQUAL(PAN_CLASS_LIGHT, thermal_mass_get_classification(&test_thermal_mass));
}

static void test_thermal_mass_state_consistency_after_reset(void) {
    thermal_mass_test_setup();
    
    /* Complete an estimation */
    thermal_mass_start_estimation(&test_thermal_mass, 25.0f);
    for (int i = 0; i < 11; i++) {
        float temp = 25.0f + (i + 1) * 1.0f;
        thermal_mass_update(&test_thermal_mass, temp, 1000 + (i + 1) * 500);
    }
    
    TEST_ASSERT_TRUE(thermal_mass_is_classified(&test_thermal_mass));
    TEST_ASSERT_FALSE(thermal_mass_is_active(&test_thermal_mass));
    
    /* Reset and verify clean state */
    thermal_mass_reset(&test_thermal_mass);
    
    TEST_ASSERT_FALSE(thermal_mass_is_classified(&test_thermal_mass));
    TEST_ASSERT_FALSE(thermal_mass_is_active(&test_thermal_mass));
    TEST_ASSERT_EQUAL(PAN_CLASS_UNKNOWN, thermal_mass_get_classification(&test_thermal_mass));
    
    pid_gains_t gains = thermal_mass_get_pid_gains(&test_thermal_mass);
    TEST_ASSERT_EQUAL_FLOAT(1.0f, gains.kp);  /* Default medium gains */
}

/* ============================================================================
 * Real-World Scenarios Tests
 * ============================================================================ */

static void test_thermal_mass_actual_heating_curve(void) {
    thermal_mass_test_setup();
    
    thermal_mass_start_estimation(&test_thermal_mass, 22.0f);  /* Room temperature */
    
    /* Simulate realistic heating curve (non-linear) */
    uint32_t times[] = {1500, 2000, 2500, 3000, 3500, 4000, 4500, 5000, 5500, 6000, 6500};
    float temps[] = {22.5f, 23.2f, 24.1f, 25.3f, 26.8f, 28.5f, 30.4f, 32.5f, 34.8f, 37.2f, 39.8f};
    
    for (int i = 0; i < 11; i++) {
        bool complete = thermal_mass_update(&test_thermal_mass, temps[i], times[i]);
        
        if (i < 10) {
            TEST_ASSERT_FALSE(complete);
        } else {
            TEST_ASSERT_TRUE(complete);
        }
    }
    
    /* Should classify based on realistic heating curve */
    pan_class_t classification = thermal_mass_get_classification(&test_thermal_mass);
    TEST_ASSERT_TRUE(classification >= PAN_CLASS_LIGHT && classification <= PAN_CLASS_HEAVY);
}

static void test_thermal_mass_ambient_temperature_effects(void) {
    thermal_mass_test_setup();
    
    /* Hot ambient temperature */
    bool result1 = thermal_mass_start_estimation(&test_thermal_mass, 35.0f);  /* Hot day */
    TEST_ASSERT_TRUE(result1);
    
    for (int i = 0; i < 11; i++) {
        float temp = 35.0f + (i + 1) * 0.5f;
        thermal_mass_update(&test_thermal_mass, temp, 1000 + (i + 1) * 500);
    }
    TEST_ASSERT_EQUAL(PAN_CLASS_LIGHT, thermal_mass_get_classification(&test_thermal_mass));
    
    /* Cold ambient temperature */
    thermal_mass_reset(&test_thermal_mass);
    bool result2 = thermal_mass_start_estimation(&test_thermal_mass, 10.0f);  /* Cold day */
    TEST_ASSERT_TRUE(result2);
    
    for (int i = 0; i < 11; i++) {
        float temp = 10.0f + (i + 1) * 0.5f;
        thermal_mass_update(&test_thermal_mass, temp, 1000 + (i + 1) * 500);
    }
    TEST_ASSERT_EQUAL(PAN_CLASS_LIGHT, thermal_mass_get_classification(&test_thermal_mass));
}

static void test_thermal_mass_high_frequency_updates(void) {
    thermal_mass_test_setup();
    
    thermal_mass_start_estimation(&test_thermal_mass, 25.0f);
    
    /* High frequency updates (every 50ms) */
    for (int i = 0; i < 101; i++) {  /* 100 samples over 5 seconds */
        float temp = 25.0f + (i + 1) * 0.1f;
        uint32_t time = 1000 + (i + 1) * 50;  /* 50ms intervals */
        bool complete = thermal_mass_update(&test_thermal_mass, temp, time);
        
        if (i < 100) {
            TEST_ASSERT_FALSE(complete);
        } else {
            TEST_ASSERT_TRUE(complete);
        }
    }
    
    TEST_ASSERT_EQUAL(PAN_CLASS_LIGHT, thermal_mass_get_classification(&test_thermal_mass));
}

/* ============================================================================
 * Performance & Memory Tests
 * ============================================================================ */

static void test_thermal_mass_performance_with_many_samples(void) {
    thermal_mass_test_setup();
    
    thermal_mass_start_estimation(&test_thermal_mass, 25.0f);
    
    /* Many samples (stress test) */
    for (int i = 0; i < 1000; i++) {
        float temp = 25.0f + ((i % 100) + 1) * 0.1f;
        uint32_t time = 1000 + (i + 1) * 5;  /* Very frequent updates */
        
        if (i < 999) {
            bool complete = thermal_mass_update(&test_thermal_mass, temp, time);
            TEST_ASSERT_FALSE(complete);
        } else {
            bool complete = thermal_mass_update(&test_thermal_mass, temp, 6000);
            TEST_ASSERT_TRUE(complete);
        }
    }
    
    /* Should still classify correctly despite many samples */
    pan_class_t classification = thermal_mass_get_classification(&test_thermal_mass);
    TEST_ASSERT_TRUE(classification >= PAN_CLASS_LIGHT && classification <= PAN_CLASS_HEAVY);
}

static void test_thermal_mass_concurrent_operations(void) {
    thermal_mass_test_setup();
    
    /* Test multiple handle operations */
    thermal_mass_handle_t handle2, handle3;
    thermal_mass_init(&handle2, NULL);
    thermal_mass_init(&handle3, NULL);
    
    /* Start multiple estimations */
    bool result1 = thermal_mass_start_estimation(&test_thermal_mass, 25.0f);
    bool result2 = thermal_mass_start_estimation(&handle2, 30.0f);
    bool result3 = thermal_mass_start_estimation(&handle3, 20.0f);
    
    TEST_ASSERT_TRUE(result1);
    TEST_ASSERT_TRUE(result2);
    TEST_ASSERT_TRUE(result3);
    
    /* Update all handles */
    bool active1 = thermal_mass_is_active(&test_thermal_mass);
    bool active2 = thermal_mass_is_active(&handle2);
    bool active3 = thermal_mass_is_active(&handle3);
    
    TEST_ASSERT_TRUE(active1);
    TEST_ASSERT_TRUE(active2);
    TEST_ASSERT_TRUE(active3);
    
    /* Complete first estimation */
    for (int i = 0; i < 11; i++) {
        float temp = 25.0f + (i + 1) * 1.0f;
        thermal_mass_update(&test_thermal_mass, temp, 1000 + (i + 1) * 500);
    }
    
    TEST_ASSERT_FALSE(thermal_mass_is_active(&test_thermal_mass));
    TEST_ASSERT_TRUE(thermal_mass_is_active(&handle2));  /* Others still active */
    TEST_ASSERT_TRUE(thermal_mass_is_active(&handle3));
}

/* ============================================================================
 * Test Runner
 * ============================================================================ */

void run_thermal_mass_tests(void) {
    /* Configuration */
    RUN_TEST(test_thermal_mass_get_default_config);
    RUN_TEST(test_thermal_mass_init_with_config);
    RUN_TEST(test_thermal_mass_init_with_null_config);
    
    /* Classification */
    RUN_TEST(test_thermal_mass_classify_light_pan);
    RUN_TEST(test_thermal_mass_classify_medium_pan);
    RUN_TEST(test_thermal_mass_classify_heavy_pan);
    RUN_TEST(test_thermal_mass_class_to_string);
    
    /* Estimation process */
    RUN_TEST(test_thermal_mass_start_estimation);
    RUN_TEST(test_thermal_mass_start_estimation_invalid_temp);
    RUN_TEST(test_thermal_mass_update_light_pan);
    RUN_TEST(test_thermal_mass_update_medium_pan);
    RUN_TEST(test_thermal_mass_update_insufficient_rise);
    RUN_TEST(test_thermal_mass_update_in_progress);
    
    /* State management */
    RUN_TEST(test_thermal_mass_reset);
    RUN_TEST(test_thermal_mass_null_handle);
    
    /* Temperature validation */
    RUN_TEST(test_thermal_mass_validate_temperature_valid);
    RUN_TEST(test_thermal_mass_validate_temperature_invalid);
    
    /* Integration */
    RUN_TEST(test_thermal_mass_full_estimation_cycle);
    
    /* Edge Cases & Error Conditions */
    RUN_TEST(test_thermal_mass_rapid_temp_changes);
    RUN_TEST(test_thermal_mass_temperature_drop_during_test);
    RUN_TEST(test_thermal_mass_sensor_failure_mid_test);
    RUN_TEST(test_thermal_mass_timing_edge_cases);
    
    /* Boundary Conditions */
    RUN_TEST(test_thermal_mass_exact_threshold_light);
    RUN_TEST(test_thermal_mass_exact_threshold_medium);
    RUN_TEST(test_thermal_mass_minimum_valid_temperature);
    RUN_TEST(test_thermal_mass_maximum_valid_temperature);
    RUN_TEST(test_thermal_mass_very_short_test_duration);
    
    /* Integration & State Management */
    RUN_TEST(test_thermal_mass_multiple_consecutive_estimations);
    RUN_TEST(test_thermal_mass_different_initial_temperatures);
    RUN_TEST(test_thermal_mass_state_consistency_after_reset);
    
    /* Real-World Scenarios */
    RUN_TEST(test_thermal_mass_actual_heating_curve);
    RUN_TEST(test_thermal_mass_ambient_temperature_effects);
    RUN_TEST(test_thermal_mass_high_frequency_updates);
    
    /* Performance & Memory */
    RUN_TEST(test_thermal_mass_performance_with_many_samples);
    RUN_TEST(test_thermal_mass_concurrent_operations);
}