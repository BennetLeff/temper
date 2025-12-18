#include "unity.h"
#include "cascade_pid.h"
#include <string.h>
#include <math.h>

// Mock time provider
extern void cascade_pid_test_advance_time_us(uint64_t delta_us);

void setUp(void) {
    // Reset simulated time
    // Assuming cascade_pid.c has a way to reset time for tests
    // or we just handle it via initialization
}

void tearDown(void) {}

void test_probe_init_defaults(void) {
    cascade_pid_handle_t cascade;
    cascade_pid_init_default(&cascade);
    
    TEST_ASSERT_TRUE(cascade_pid_is_probe_in_food(&cascade));
    TEST_ASSERT_EQUAL(PROBE_STATE_UNKNOWN, cascade.probe_state);
}

void test_probe_detects_air_on_rapid_rise(void) {
    cascade_pid_handle_t cascade;
    cascade_pid_init_default(&cascade);
    
    // Connect probe
    // Initial update to set baseline
    cascade_pid_update(&cascade, 100.0f, 25.0f, 25.0f, 0.1f);
    TEST_ASSERT_TRUE(cascade_pid_probe_connected(&cascade));
    
    // Simulate rapid temp rise (in air)
    // PROBE_DT_THRESHOLD_AIR is 2.0C/s
    // Rise 1.0C over 0.1s -> 10C/s
    // Need PWM output > 20.0f for detection to run.
    // Setting target much higher than actual to force high PWM.
    for (int i = 0; i < 60; i++) { // 6 seconds
        cascade_pid_update(&cascade, 200.0f, 25.0f + (float)i * 1.0f, 50.0f, 0.1f);
        cascade_pid_test_advance_time_us(100000);
    }
    
    // Should be in AIR state now
    TEST_ASSERT_FALSE(cascade_pid_is_probe_in_food(&cascade));
    TEST_ASSERT_EQUAL(CASCADE_MODE_SINGLE, cascade_pid_get_mode(&cascade));
}

void test_probe_detects_food_on_slow_rise(void) {
    cascade_pid_handle_t cascade;
    cascade_pid_init_default(&cascade);
    
    // Initial update
    cascade_pid_update(&cascade, 100.0f, 25.0f, 25.0f, 0.1f);
    
    // Simulate slow temp rise (in food)
    // Rise 0.01C over 0.1s -> 0.1C/s (< 0.5C/s threshold)
    for (int i = 0; i < 60; i++) { // 6 seconds
        cascade_pid_update(&cascade, 200.0f, 25.0f + (float)i * 0.01f, 50.0f, 0.1f);
        cascade_pid_test_advance_time_us(100000);
    }
    
    // Should be in FOOD state
    TEST_ASSERT_TRUE(cascade_pid_is_probe_in_food(&cascade));
    TEST_ASSERT_EQUAL(CASCADE_MODE_DUAL, cascade_pid_get_mode(&cascade));
}

void test_probe_fallback_logic(void) {
    cascade_pid_handle_t cascade;
    cascade_pid_init_default(&cascade);
    
    // 1. Initial state: Single loop (probe disconnected)
    TEST_ASSERT_EQUAL(CASCADE_MODE_SINGLE, cascade_pid_get_mode(&cascade));
    
    // 2. Connect probe in food: Switch to DUAL
    cascade_pid_update(&cascade, 200.0f, 25.0f, 25.0f, 0.1f);
    TEST_ASSERT_EQUAL(CASCADE_MODE_DUAL, cascade_pid_get_mode(&cascade));
    
    // 3. Detect probe in air: Fallback to SINGLE
    for (int i = 0; i < 60; i++) {
        cascade_pid_update(&cascade, 200.0f, 25.0f + (float)i * 1.0f, 50.0f, 0.1f);
        cascade_pid_test_advance_time_us(100000);
    }
    TEST_ASSERT_FALSE(cascade_pid_is_probe_in_food(&cascade));
    TEST_ASSERT_EQUAL(CASCADE_MODE_SINGLE, cascade_pid_get_mode(&cascade));
    
    // 4. Probe re-enters food: Recovery to DUAL
    for (int i = 0; i < 60; i++) {
        cascade_pid_update(&cascade, 200.0f, 100.0f, 50.0f, 0.1f); // Stable at 100C
        cascade_pid_test_advance_time_us(100000);
    }
    TEST_ASSERT_TRUE(cascade_pid_is_probe_in_food(&cascade));
    TEST_ASSERT_EQUAL(CASCADE_MODE_DUAL, cascade_pid_get_mode(&cascade));
}
