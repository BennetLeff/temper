/**
 * @file test_main.c
 * @brief Main test runner for Temper firmware
 * 
 * Runs unit test suites that use HAL mocks:
 * - PID controller tests
 * - Safety module tests
 * 
 * Note: State machine tests run separately (test_state_machine_only)
 * because state_machine.c has unique stub requirements.
 */

#include <stdio.h>
#include "unity/unity.h"
#include "test_common.h"

/* Forward declarations for Unity functions not in minimal header */
int UnityBeginWrapper(void);
int UnityEndWrapper(void);
#define UNITY_BEGIN() UnityBeginWrapper()
#define UNITY_END() UnityEndWrapper()

/* Declare test modules */
DECLARE_TEST_MODULE(pid_control);
DECLARE_TEST_MODULE(safety);

/* Unity required functions */
void setUp(void) {
    /* Called before each test */
    test_reset_all_mocks();
}

void tearDown(void) {
    /* Called after each test */
}

/* Wrapper implementations */
int UnityBeginWrapper(void) {
    UnityBegin("test_main.c");
    return 0;
}

int UnityEndWrapper(void) {
    return UnityEnd();
}

int main(void) {
    UNITY_BEGIN();
    
    printf("\n");
    printf("===========================================\n");
    printf(" Temper Induction Cooker Firmware Tests\n");
    printf("===========================================\n");
    printf("\n");
    
    /* Run all test modules */
    printf("--- PID Controller Tests ---\n");
    RUN_TEST_MODULE(pid_control);
    
    printf("\n--- Safety Module Tests ---\n");
    RUN_TEST_MODULE(safety);
    
    /* Note: State machine tests run separately via test_state_machine_only */
    printf("\n(State machine tests run separately: ./test_state_machine_only)\n");
    
    return UNITY_END();
}

/* ============================================================================
 * Test Fixture Implementations
 * ============================================================================ */

void test_reset_all_mocks(void) {
    /* Reset HAL mocks if available */
#ifdef HOST_BUILD
    /* These would call mock reset functions */
    /* mock_gpio_reset(); */
    /* mock_adc_reset(); */
    /* mock_pwm_reset(); */
    /* mock_timer_reset(); */
#endif
}

void test_setup_safe_state(void) {
    /* Set up normal operating conditions */
#ifndef ESP_PLATFORM
    extern void safety_sim_reset(void);
    safety_sim_reset();
#endif
}

void test_setup_pan_detection(float current_amps) {
    (void)current_amps;
    /* Would set mock ADC to return specified current */
}

void test_setup_thermal(float heatsink_temp_c, float igbt_temp_c) {
    (void)heatsink_temp_c;
    (void)igbt_temp_c;
    /* Would set mock ADC values for thermal sensors */
}

void test_advance_time_ms(uint32_t ms) {
    (void)ms;
    /* Would advance mock timer */
}

uint32_t test_get_emergency_stop_count(void) {
    return 0; /* Would return mock PWM emergency stop count */
}

uint32_t test_get_watchdog_feed_count(void) {
#ifndef ESP_PLATFORM
    extern uint32_t safety_sim_get_wdt_feeds(void);
    return safety_sim_get_wdt_feeds();
#else
    return 0;
#endif
}
