/**
 * @file test_pid_control.c
 * @brief Unit tests for PID temperature controller
 * 
 * Tests verify:
 * - Basic PID computation
 * - Integrator anti-windup
 * - Derivative on measurement (no setpoint kick)
 * - Output saturation
 * - NaN/Inf input handling
 */

#include <math.h>
#include "unity/unity.h"
#include "test_common.h"
#include "../components/control/pid_control.h"

/* Test fixtures */
static pid_handle_t test_pid;

/* Unity setup/teardown for this module */
static void pid_test_setup(void) {
    pid_init(&test_pid, 1.0f, 0.1f, 0.05f);
    pid_set_output_limits(&test_pid, 0.0f, 100.0f);
    pid_set_integrator_limit(&test_pid, 50.0f);
}

/* ============================================================================
 * Basic PID Tests
 * ============================================================================ */

static void test_pid_init_sets_gains(void) {
    pid_handle_t pid;
    pid_init(&pid, 2.0f, 0.5f, 0.1f);
    
    TEST_ASSERT_EQUAL_FLOAT(2.0f, pid.kp);
    TEST_ASSERT_EQUAL_FLOAT(0.5f, pid.ki);
    TEST_ASSERT_EQUAL_FLOAT(0.1f, pid.kd);
}

static void test_pid_init_clears_state(void) {
    pid_handle_t pid;
    pid.integrator = 999.0f;
    pid.prev_error = 999.0f;
    
    pid_init(&pid, 1.0f, 1.0f, 1.0f);
    
    TEST_ASSERT_EQUAL_FLOAT(0.0f, pid.integrator);
    TEST_ASSERT_EQUAL_FLOAT(0.0f, pid.prev_error);
}

static void test_pid_proportional_only(void) {
    pid_handle_t pid;
    pid_init(&pid, 2.0f, 0.0f, 0.0f);  /* P-only */
    pid_set_output_limits(&pid, 0.0f, 100.0f);
    
    /* Error = 50, Kp = 2, output = 100 (clamped) */
    float output = pid_compute(&pid, 100.0f, 50.0f, 0.01f);
    TEST_ASSERT_EQUAL_FLOAT(100.0f, output);
    
    /* Error = 10, Kp = 2, output = 20 */
    output = pid_compute(&pid, 100.0f, 90.0f, 0.01f);
    TEST_ASSERT_EQUAL_FLOAT(20.0f, output);
}

static void test_pid_integral_accumulates(void) {
    pid_handle_t pid;
    pid_init(&pid, 0.0f, 10.0f, 0.0f);  /* I-only */
    pid_set_output_limits(&pid, 0.0f, 100.0f);
    pid_set_integrator_limit(&pid, 100.0f);
    
    float dt = 0.1f;  /* 100ms */
    
    /* First call: error=10, integrator += 10*0.1 = 1.0, output = Ki*1.0 = 10 */
    float output = pid_compute(&pid, 100.0f, 90.0f, dt);
    TEST_ASSERT_FLOAT_WITHIN(0.1f, 10.0f, output);
    
    /* Second call: integrator += 10*0.1 = 2.0, output = Ki*2.0 = 20 */
    output = pid_compute(&pid, 100.0f, 90.0f, dt);
    TEST_ASSERT_FLOAT_WITHIN(0.1f, 20.0f, output);
}

static void test_pid_output_saturation_max(void) {
    pid_handle_t pid;
    pid_init(&pid, 100.0f, 0.0f, 0.0f);  /* Very high gain */
    pid_set_output_limits(&pid, 0.0f, 100.0f);
    
    /* Large error should saturate at max */
    float output = pid_compute(&pid, 200.0f, 0.0f, 0.01f);
    TEST_ASSERT_EQUAL_FLOAT(100.0f, output);
}

static void test_pid_output_saturation_min(void) {
    pid_handle_t pid;
    pid_init(&pid, 100.0f, 0.0f, 0.0f);
    pid_set_output_limits(&pid, 0.0f, 100.0f);
    
    /* Negative error should saturate at min (0) */
    float output = pid_compute(&pid, 0.0f, 200.0f, 0.01f);
    TEST_ASSERT_EQUAL_FLOAT(0.0f, output);
}

/* ============================================================================
 * Anti-Windup Tests
 * ============================================================================ */

static void test_pid_integrator_windup_limit(void) {
    pid_handle_t pid;
    pid_init(&pid, 0.0f, 100.0f, 0.0f);  /* I-only, high Ki */
    pid_set_output_limits(&pid, 0.0f, 100.0f);
    pid_set_integrator_limit(&pid, 10.0f);
    
    /* Many iterations with constant error */
    for (int i = 0; i < 100; i++) {
        pid_compute(&pid, 100.0f, 0.0f, 0.1f);
    }
    
    /* Integrator should be clamped to limit */
    TEST_ASSERT_FLOAT_WITHIN(0.01f, 10.0f, pid.integrator);
}

static void test_pid_integrator_negative_windup(void) {
    pid_handle_t pid;
    pid_init(&pid, 0.0f, 100.0f, 0.0f);
    pid_set_integrator_limit(&pid, 10.0f);
    
    /* Negative error */
    for (int i = 0; i < 100; i++) {
        pid_compute(&pid, 0.0f, 100.0f, 0.1f);
    }
    
    /* Negative integrator should be clamped */
    TEST_ASSERT_FLOAT_WITHIN(0.01f, -10.0f, pid.integrator);
}

/* ============================================================================
 * Derivative Tests
 * ============================================================================ */

static void test_pid_derivative_on_measurement(void) {
    pid_handle_t pid;
    pid_init(&pid, 0.0f, 0.0f, 1.0f);  /* D-only */
    pid_set_output_limits(&pid, -100.0f, 100.0f);
    
    float dt = 0.01f;
    
    /* First call: no derivative (prev_measurement = 0) */
    float output1 = pid_compute(&pid, 100.0f, 50.0f, dt);
    
    /* Second call: measurement increased by 10, dM/dt = 10/0.01 = 1000 */
    /* D-term = -Kd * dM/dt = -1.0 * 1000 = -1000 (clamped to -100) */
    float output2 = pid_compute(&pid, 100.0f, 60.0f, dt);
    
    /* Derivative should be negative (opposes measurement increase) */
    TEST_ASSERT_TRUE(output2 < output1);
}

static void test_pid_no_setpoint_kick(void) {
    pid_handle_t pid;
    pid_init(&pid, 1.0f, 0.0f, 10.0f);  /* P + D */
    pid_set_output_limits(&pid, -100.0f, 100.0f);
    
    float dt = 0.01f;
    
    /* Steady state: setpoint=100, measurement=100 */
    pid_compute(&pid, 100.0f, 100.0f, dt);
    float output1 = pid_compute(&pid, 100.0f, 100.0f, dt);
    
    /* Change setpoint suddenly (would cause kick with d-error) */
    float output2 = pid_compute(&pid, 150.0f, 100.0f, dt);
    
    /* P-term increases (error = 50), but D-term should NOT spike */
    /* because we use derivative-on-measurement, not derivative-on-error */
    /* Expected: output2 = P-term only = 50 (no D spike) */
    TEST_ASSERT_FLOAT_WITHIN(1.0f, 50.0f, output2);
}

/* ============================================================================
 * Edge Case Tests
 * ============================================================================ */

static void test_pid_nan_setpoint_returns_min(void) {
    pid_handle_t pid;
    pid_init(&pid, 1.0f, 1.0f, 1.0f);
    pid_set_output_limits(&pid, 0.0f, 100.0f);
    
    float output = pid_compute(&pid, NAN, 50.0f, 0.01f);
    TEST_ASSERT_EQUAL_FLOAT(0.0f, output);
}

static void test_pid_nan_measurement_returns_min(void) {
    pid_handle_t pid;
    pid_init(&pid, 1.0f, 1.0f, 1.0f);
    pid_set_output_limits(&pid, 0.0f, 100.0f);
    
    float output = pid_compute(&pid, 100.0f, NAN, 0.01f);
    TEST_ASSERT_EQUAL_FLOAT(0.0f, output);
}

static void test_pid_inf_measurement_returns_min(void) {
    pid_handle_t pid;
    pid_init(&pid, 1.0f, 1.0f, 1.0f);
    pid_set_output_limits(&pid, 0.0f, 100.0f);
    
    float output = pid_compute(&pid, 100.0f, INFINITY, 0.01f);
    TEST_ASSERT_EQUAL_FLOAT(0.0f, output);
}

static void test_pid_zero_dt_uses_fallback(void) {
    pid_handle_t pid;
    pid_init(&pid, 1.0f, 0.0f, 0.0f);  /* P-only for simple test */
    pid_set_output_limits(&pid, 0.0f, 100.0f);
    
    /* dt=0 should not crash, should use fallback */
    float output = pid_compute(&pid, 100.0f, 90.0f, 0.0f);
    TEST_ASSERT_EQUAL_FLOAT(10.0f, output);  /* P-term only */
}

static void test_pid_negative_dt_uses_fallback(void) {
    pid_handle_t pid;
    pid_init(&pid, 1.0f, 0.0f, 0.0f);
    pid_set_output_limits(&pid, 0.0f, 100.0f);
    
    float output = pid_compute(&pid, 100.0f, 90.0f, -0.1f);
    TEST_ASSERT_EQUAL_FLOAT(10.0f, output);
}

/* ============================================================================
 * Temperature Control Specific Tests
 * ============================================================================ */

static void test_pid_temperature_precision(void) {
    pid_handle_t pid;
    pid_init(&pid, 1.0f, 0.05f, 0.2f);  /* Typical temp control gains */
    pid_set_output_limits(&pid, 0.0f, 100.0f);
    
    float setpoint = 100.0f;
    float measurement = 99.5f;  /* Within 0.5°C precision */
    float dt = 0.01f;
    
    /* Small error should produce small output */
    float output = pid_compute(&pid, setpoint, measurement, dt);
    TEST_ASSERT_FLOAT_WITHIN(1.0f, 0.5f, output);
}

static void test_pid_rapid_heating_response(void) {
    pid_handle_t pid;
    pid_init(&pid, 2.0f, 0.1f, 0.5f);  /* Aggressive preheat gains */
    pid_set_output_limits(&pid, 0.0f, 100.0f);
    
    /* Large error during preheat */
    float output = pid_compute(&pid, 200.0f, 25.0f, 0.01f);
    
    /* Should request maximum power */
    TEST_ASSERT_EQUAL_FLOAT(100.0f, output);
}

/* ============================================================================
 * Global API Tests
 * ============================================================================ */

static void test_pid_global_set_tuning(void) {
    pid_set_tuning(3.0f, 0.2f, 0.1f);
    pid_reset_integral();
    
    /* Verify by computing - use simplified API */
    float output = pid_update(100.0f, 90.0f);
    
    /* P-term = 3.0 * 10 = 30, I and D small on first call */
    TEST_ASSERT_GREATER_THAN(25.0f, output);
}

static void test_pid_reset_integral_clears_state(void) {
    pid_set_tuning(0.0f, 10.0f, 0.0f);  /* I-only */
    
    /* Build up integrator */
    pid_update(100.0f, 90.0f);
    pid_update(100.0f, 90.0f);
    pid_update(100.0f, 90.0f);
    
    /* Reset should clear */
    pid_reset_integral();
    
    /* Next output should be small (no accumulated integral) */
    float output = pid_update(100.0f, 99.0f);
    TEST_ASSERT_LESS_THAN(5.0f, output);
}

/* ============================================================================
 * Test Runner
 * ============================================================================ */

void run_pid_control_tests(void) {
    /* Basic tests */
    RUN_TEST(test_pid_init_sets_gains);
    RUN_TEST(test_pid_init_clears_state);
    RUN_TEST(test_pid_proportional_only);
    RUN_TEST(test_pid_integral_accumulates);
    RUN_TEST(test_pid_output_saturation_max);
    RUN_TEST(test_pid_output_saturation_min);
    
    /* Anti-windup */
    RUN_TEST(test_pid_integrator_windup_limit);
    RUN_TEST(test_pid_integrator_negative_windup);
    
    /* Derivative */
    RUN_TEST(test_pid_derivative_on_measurement);
    RUN_TEST(test_pid_no_setpoint_kick);
    
    /* Edge cases */
    RUN_TEST(test_pid_nan_setpoint_returns_min);
    RUN_TEST(test_pid_nan_measurement_returns_min);
    RUN_TEST(test_pid_inf_measurement_returns_min);
    RUN_TEST(test_pid_zero_dt_uses_fallback);
    RUN_TEST(test_pid_negative_dt_uses_fallback);
    
    /* Temperature specific */
    RUN_TEST(test_pid_temperature_precision);
    RUN_TEST(test_pid_rapid_heating_response);
    
    /* Global API */
    RUN_TEST(test_pid_global_set_tuning);
    RUN_TEST(test_pid_reset_integral_clears_state);
}
