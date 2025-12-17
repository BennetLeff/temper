/**
 * @file test_safety.c
 * @brief Unit tests for safety module
 * 
 * Tests verify:
 * - Over-temperature detection
 * - Over-current detection  
 * - Fan failure detection
 * - RTD sensor validation
 * - Watchdog functionality
 * - Safe mode entry
 */

#include <math.h>
#include "unity/unity.h"
#include "test_common.h"
#include "../components/safety/safety.h"

/* ============================================================================
 * Safety Check Tests
 * ============================================================================ */

static void test_safety_ok_normal_conditions(void) {
    /* Reset to safe state */
    safety_sim_reset();
    
    safety_status_t status = run_safety_check();
    TEST_ASSERT_EQUAL_INT(SAFETY_OK, status);
}

static void test_safety_over_temp_detection(void) {
    safety_sim_reset();
    safety_sim_set_temp(101.0f);  /* Over 100°C threshold */
    
    safety_status_t status = run_safety_check();
    TEST_ASSERT_EQUAL_INT(SAFETY_OVER_TEMP, status);
}

static void test_safety_temp_at_threshold(void) {
    safety_sim_reset();
    safety_sim_set_temp(100.0f);  /* Exactly at threshold */
    
    /* At threshold should still be OK (> not >=) */
    safety_status_t status = run_safety_check();
    TEST_ASSERT_EQUAL_INT(SAFETY_OK, status);
}

static void test_safety_over_current_detection(void) {
    safety_sim_reset();
    safety_sim_set_current(36.0f);  /* Over 35A threshold */
    
    safety_status_t status = run_safety_check();
    TEST_ASSERT_EQUAL_INT(SAFETY_OVER_CURRENT, status);
}

static void test_safety_current_at_threshold(void) {
    safety_sim_reset();
    safety_sim_set_current(35.0f);  /* Exactly at threshold */
    
    safety_status_t status = run_safety_check();
    TEST_ASSERT_EQUAL_INT(SAFETY_OK, status);
}

static void test_safety_fan_failure_detection(void) {
    safety_sim_reset();
    safety_sim_set_fan(false);  /* Fan stopped */
    
    safety_status_t status = run_safety_check();
    TEST_ASSERT_EQUAL_INT(SAFETY_FAN_FAILURE, status);
}

static void test_safety_rtd_open_circuit(void) {
    safety_sim_reset();
    safety_sim_set_rtd(11000.0f);  /* Over 10kΩ = open */
    
    safety_status_t status = run_safety_check();
    TEST_ASSERT_EQUAL_INT(SAFETY_SENSOR_FAULT, status);
}

static void test_safety_rtd_short_circuit(void) {
    safety_sim_reset();
    safety_sim_set_rtd(5.0f);  /* Under 10Ω = short */
    
    safety_status_t status = run_safety_check();
    TEST_ASSERT_EQUAL_INT(SAFETY_SENSOR_FAULT, status);
}

static void test_safety_rtd_normal_range(void) {
    safety_sim_reset();
    safety_sim_set_rtd(110.0f);  /* Normal ~25°C for PT100 */
    
    safety_status_t status = run_safety_check();
    TEST_ASSERT_EQUAL_INT(SAFETY_OK, status);
}

/* ============================================================================
 * NaN/Inf Input Tests
 * ============================================================================ */

static void test_safety_nan_temp_detection(void) {
    safety_sim_reset();
    safety_sim_set_temp(NAN);
    
    safety_status_t status = run_safety_check();
    TEST_ASSERT_EQUAL_INT(SAFETY_OVER_TEMP, status);
}

static void test_safety_inf_temp_detection(void) {
    safety_sim_reset();
    safety_sim_set_temp(INFINITY);
    
    safety_status_t status = run_safety_check();
    TEST_ASSERT_EQUAL_INT(SAFETY_OVER_TEMP, status);
}

static void test_safety_nan_current_detection(void) {
    safety_sim_reset();
    safety_sim_set_current(NAN);
    
    safety_status_t status = run_safety_check();
    TEST_ASSERT_EQUAL_INT(SAFETY_OVER_CURRENT, status);
}

static void test_safety_nan_rtd_detection(void) {
    safety_sim_reset();
    safety_sim_set_rtd(NAN);
    
    safety_status_t status = run_safety_check();
    TEST_ASSERT_EQUAL_INT(SAFETY_SENSOR_FAULT, status);
}

/* ============================================================================
 * Fault Injection Tests
 * ============================================================================ */

static void test_safety_fault_injection(void) {
    safety_sim_reset();
    safety_sim_inject_fault(SAFETY_INTERLOCK_TRIP);
    
    safety_status_t status = run_safety_check();
    TEST_ASSERT_EQUAL_INT(SAFETY_INTERLOCK_TRIP, status);
}

static void test_safety_strict_mode(void) {
    safety_sim_reset();
    safety_sim_set_strict_mode(true);
    
    safety_status_t status = run_safety_check();
    TEST_ASSERT_EQUAL_INT(SAFETY_INTERLOCK_TRIP, status);
    
    /* Reset strict mode */
    safety_sim_set_strict_mode(false);
}

/* ============================================================================
 * Hardware Interlock Tests
 * ============================================================================ */

static void test_interlocks_ok_normal(void) {
    safety_sim_reset();
    
    bool ok = check_hardware_interlocks();
    TEST_ASSERT_TRUE(ok);
}

static void test_interlocks_fail_over_temp(void) {
    safety_sim_reset();
    safety_sim_set_temp(150.0f);
    
    bool ok = check_hardware_interlocks();
    TEST_ASSERT_FALSE(ok);
}

static void test_interlocks_fail_over_current(void) {
    safety_sim_reset();
    safety_sim_set_current(50.0f);
    
    bool ok = check_hardware_interlocks();
    TEST_ASSERT_FALSE(ok);
}

static void test_interlocks_fail_fan(void) {
    safety_sim_reset();
    safety_sim_set_fan(false);
    
    bool ok = check_hardware_interlocks();
    TEST_ASSERT_FALSE(ok);
}

/* ============================================================================
 * Sensor Validation Tests
 * ============================================================================ */

static void test_sensors_valid_normal(void) {
    safety_sim_reset();
    
    bool valid = check_sensors_valid();
    TEST_ASSERT_TRUE(valid);
}

static void test_sensors_invalid_rtd_open(void) {
    safety_sim_reset();
    safety_sim_set_rtd(15000.0f);
    
    bool valid = check_sensors_valid();
    TEST_ASSERT_FALSE(valid);
}

static void test_sensors_invalid_rtd_short(void) {
    safety_sim_reset();
    safety_sim_set_rtd(1.0f);
    
    bool valid = check_sensors_valid();
    TEST_ASSERT_FALSE(valid);
}

static void test_sensors_invalid_rtd_nan(void) {
    safety_sim_reset();
    safety_sim_set_rtd(NAN);
    
    bool valid = check_sensors_valid();
    TEST_ASSERT_FALSE(valid);
}

/* ============================================================================
 * Watchdog Tests
 * ============================================================================ */

static void test_watchdog_feed_increments_count(void) {
    safety_sim_reset();
    uint32_t initial = safety_sim_get_wdt_feeds();
    
    watchdog_feed();
    watchdog_feed();
    watchdog_feed();
    
    uint32_t final = safety_sim_get_wdt_feeds();
    TEST_ASSERT_EQUAL_UINT32(initial + 3, final);
}

static void test_secure_wdt_reset_ok_conditions(void) {
    safety_sim_reset();
    uint32_t initial = safety_sim_get_wdt_feeds();
    
    secure_wdt_reset();
    
    /* Should have fed watchdog */
    uint32_t final = safety_sim_get_wdt_feeds();
    TEST_ASSERT_EQUAL_UINT32(initial + 1, final);
}

static void test_secure_wdt_reset_unsafe_no_feed(void) {
    safety_sim_reset();
    safety_sim_set_temp(150.0f);  /* Unsafe condition */
    uint32_t initial = safety_sim_get_wdt_feeds();
    
    secure_wdt_reset();
    
    /* Should NOT have fed watchdog (unsafe) */
    uint32_t final = safety_sim_get_wdt_feeds();
    TEST_ASSERT_EQUAL_UINT32(initial, final);
}

/* ============================================================================
 * Safe Mode Tests
 * ============================================================================ */

static void test_safe_mode_initially_inactive(void) {
    safety_sim_reset();
    
    bool active = is_safe_mode_active();
    TEST_ASSERT_FALSE(active);
}

static void test_enter_safe_mode_activates(void) {
    safety_sim_reset();
    
    enter_safe_mode();
    
    bool active = is_safe_mode_active();
    TEST_ASSERT_TRUE(active);
}

static void test_hardware_shutdown_activates_safe_mode(void) {
    safety_sim_reset();
    
    trigger_hardware_shutdown();
    
    bool active = is_safe_mode_active();
    TEST_ASSERT_TRUE(active);
}

/* ============================================================================
 * Multiple Fault Priority Tests
 * ============================================================================ */

static void test_over_temp_priority_over_current(void) {
    safety_sim_reset();
    safety_sim_set_temp(150.0f);
    safety_sim_set_current(50.0f);
    
    /* Temperature check comes first in run_safety_check */
    safety_status_t status = run_safety_check();
    TEST_ASSERT_EQUAL_INT(SAFETY_OVER_TEMP, status);
}

static void test_current_priority_over_fan(void) {
    safety_sim_reset();
    safety_sim_set_current(50.0f);
    safety_sim_set_fan(false);
    
    safety_status_t status = run_safety_check();
    TEST_ASSERT_EQUAL_INT(SAFETY_OVER_CURRENT, status);
}

/* ============================================================================
 * Test Runner
 * ============================================================================ */

void run_safety_tests(void) {
    /* Basic safety checks */
    RUN_TEST(test_safety_ok_normal_conditions);
    RUN_TEST(test_safety_over_temp_detection);
    RUN_TEST(test_safety_temp_at_threshold);
    RUN_TEST(test_safety_over_current_detection);
    RUN_TEST(test_safety_current_at_threshold);
    RUN_TEST(test_safety_fan_failure_detection);
    RUN_TEST(test_safety_rtd_open_circuit);
    RUN_TEST(test_safety_rtd_short_circuit);
    RUN_TEST(test_safety_rtd_normal_range);
    
    /* NaN/Inf handling */
    RUN_TEST(test_safety_nan_temp_detection);
    RUN_TEST(test_safety_inf_temp_detection);
    RUN_TEST(test_safety_nan_current_detection);
    RUN_TEST(test_safety_nan_rtd_detection);
    
    /* Fault injection */
    RUN_TEST(test_safety_fault_injection);
    RUN_TEST(test_safety_strict_mode);
    
    /* Hardware interlocks */
    RUN_TEST(test_interlocks_ok_normal);
    RUN_TEST(test_interlocks_fail_over_temp);
    RUN_TEST(test_interlocks_fail_over_current);
    RUN_TEST(test_interlocks_fail_fan);
    
    /* Sensor validation */
    RUN_TEST(test_sensors_valid_normal);
    RUN_TEST(test_sensors_invalid_rtd_open);
    RUN_TEST(test_sensors_invalid_rtd_short);
    RUN_TEST(test_sensors_invalid_rtd_nan);
    
    /* Watchdog */
    RUN_TEST(test_watchdog_feed_increments_count);
    RUN_TEST(test_secure_wdt_reset_ok_conditions);
    RUN_TEST(test_secure_wdt_reset_unsafe_no_feed);
    
    /* Safe mode */
    RUN_TEST(test_safe_mode_initially_inactive);
    RUN_TEST(test_enter_safe_mode_activates);
    RUN_TEST(test_hardware_shutdown_activates_safe_mode);
    
    /* Priority */
    RUN_TEST(test_over_temp_priority_over_current);
    RUN_TEST(test_current_priority_over_fan);
}
