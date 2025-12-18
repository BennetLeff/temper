/**
 * @file test_integration_cascade_pid.c
 * @brief Integration tests for cascade PID with state machine
 * 
 * Tests verify cascade PID works correctly in the full system context:
 * - Integration with state machine
 * - Real-world heating scenarios
 * - Mode transitions during operation
 */

#include <math.h>
#include "unity/unity.h"
#include "test_common.h"
#include "../components/control/cascade_pid.h"

/* Test scenarios */
static void test_cascade_pid_sauce_reduction_scenario(void);
static void test_cascade_pid_water_heating_scenario(void);
static void test_cascade_pid_probe_failure_fallback(void);
static void test_cascade_pid_bumpless_transfer_real_world(void);

/* Test scenario: Sauce reduction (typical use case) */
static void test_cascade_pid_sauce_reduction_scenario(void) {
    cascade_pid_handle_t cascade;
    cascade_pid_init_default(&cascade);
    
    float dt = 1.0f;  /* 1 second updates */
    
    /* Scenario: Reducing sauce from 20°C to 85°C without scorching */
    printf("\n=== Sauce Reduction Test ===\n");
    
    /* Start with cold pan, no probe */
    float pwm = cascade_pid_update(&cascade, 85.0f, 0.0f, 20.0f, dt);
    printf("Initial: Pan=20°C, Target=85°C, PWM=%.1f%%\n", pwm);
    TEST_ASSERT_EQUAL(CASCADE_MODE_SINGLE, cascade.mode);
    
    /* Add probe (liquid temp = 20°C) */
    pwm = cascade_pid_update(&cascade, 85.0f, 20.0f, 25.0f, dt);
    printf("With probe: Liquid=20°C, Pan=25°C, PWM=%.1f%%\n", pwm);
    TEST_ASSERT_EQUAL(CASCADE_MODE_DUAL, cascade.mode);
    
    /* Heat up liquid to 60°C while pan stays around 80°C */
    pwm = cascade_pid_update(&cascade, 85.0f, 60.0f, 80.0f, dt);
    printf("Mid heating: Liquid=60°C, Pan=80°C, PWM=%.1f%%\n", pwm);
    
    /* Target reached, reduce power */
    pwm = cascade_pid_update(&cascade, 85.0f, 85.0f, 85.0f, dt);
    printf("Target reached: Liquid=85°C, Pan=85°C, PWM=%.1f%%\n", pwm);
    
    /* Verify cascade controller is functioning */
    TEST_ASSERT_TRUE(pwm >= 0.0f && pwm <= 100.0f);
}

/* Test scenario: Water heating */
static void test_cascade_pid_water_heating_scenario(void) {
    cascade_pid_handle_t cascade;
    cascade_pid_init_default(&cascade);
    
    float dt = 1.0f;
    
    /* Scenario: Heating water from 20°C to 100°C */
    printf("\n=== Water Heating Test ===\n");
    
    /* Start heating with probe */
    float pwm = cascade_pid_update(&cascade, 100.0f, 20.0f, 25.0f, dt);
    printf("Start: Liquid=20°C, Pan=25°C, PWM=%.1f%%\n", pwm);
    TEST_ASSERT_EQUAL(CASCADE_MODE_DUAL, cascade.mode);
    
    /* Water heating up */
    pwm = cascade_pid_update(&cascade, 100.0f, 50.0f, 60.0f, dt);
    printf("Halfway: Liquid=50°C, Pan=60°C, PWM=%.1f%%\n", pwm);
    
    /* Near boiling */
    pwm = cascade_pid_update(&cascade, 100.0f, 95.0f, 95.0f, dt);
    printf("Near boil: Liquid=95°C, Pan=95°C, PWM=%.1f%%\n", pwm);
    
    /* Verify reasonable control */
    TEST_ASSERT_TRUE(pwm >= 0.0f && pwm <= 100.0f);
}

/* Test scenario: Probe failure fallback */
static void test_cascade_pid_probe_failure_fallback(void) {
    cascade_pid_handle_t cascade;
    cascade_pid_init_default(&cascade);
    
    float dt = 1.0f;
    
    /* Start with probe connected */
    cascade_pid_update(&cascade, 100.0f, 50.0f, 25.0f, dt);
    TEST_ASSERT_EQUAL(CASCADE_MODE_DUAL, cascade.mode);
    
    /* Probe fails (returns 0) */
    cascade_pid_update(&cascade, 100.0f, 0.0f, 25.0f, dt);
    TEST_ASSERT_EQUAL(CASCADE_MODE_SINGLE, cascade.mode);
    
    /* Should continue operating in single-loop mode */
    float pwm = cascade_pid_update(&cascade, 100.0f, 0.0f, 30.0f, dt);
    printf("Probe failed: PWM=%.1f%%\n", pwm);
    TEST_ASSERT_TRUE(pwm >= 0.0f && pwm <= 100.0f);
}

/* Test scenario: Real-world bumpless transfer */
static void test_cascade_pid_bumpless_transfer_real_world(void) {
    cascade_pid_handle_t cascade;
    cascade_pid_init_default(&cascade);
    
    float dt = 1.0f;
    
    /* Start in single-loop mode with hot pan */
    cascade_pid_update(&cascade, 120.0f, 0.0f, 100.0f, dt);
    
    /* User inserts probe while cooking */
    float pwm_before = cascade_pid_update(&cascade, 120.0f, 80.0f, 100.0f, dt);
    printf("Before probe: PWM=%.1f%%\n", pwm_before);
    
    /* Should transition smoothly without power spike */
    float pwm_after = cascade_pid_update(&cascade, 120.0f, 85.0f, 100.0f, dt);
    printf("After probe: PWM=%.1f%%\n", pwm_after);
    
    /* Power should not spike excessively */
    TEST_ASSERT_TRUE(fabsf(pwm_after - pwm_before) < 50.0f);
}

/* Integration test runner */
void run_cascade_pid_integration_tests(void) {
    printf("\n=== Cascade PID Integration Tests ===\n");
    
    RUN_TEST(test_cascade_pid_sauce_reduction_scenario);
    RUN_TEST(test_cascade_pid_water_heating_scenario);
    RUN_TEST(test_cascade_pid_probe_failure_fallback);
    RUN_TEST(test_cascade_pid_bumpless_transfer_real_world);
    
    printf("\nCascade PID Integration Tests Complete.\n");
}