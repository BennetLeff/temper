#include "unity.h"
#include "pwm_guard.h"
#include "hal_pwm.h"
#include "hal_timer.h"
#include <string.h>

// Mocks
static hal_pwm_state_t mock_pwm_state;
static hal_status_t mock_pwm_get_state_return = HAL_OK;

// Global HAL pointers
const hal_pwm_ops_t *hal_pwm = NULL;
const hal_timer_ops_t *hal_timer = NULL;

// Mock function
hal_status_t mock_get_state(hal_pwm_channel_t channel, hal_pwm_state_t *state) {
    (void)channel;
    *state = mock_pwm_state;
    return mock_pwm_get_state_return;
}

static const hal_pwm_ops_t mock_pwm_ops_impl = {
    .get_state = mock_get_state,
};

// Internal test helper from pwm_guard.c
extern void _pwm_guard_inject_freq(uint32_t freq_hz);

void setUp(void) {
    hal_pwm = &mock_pwm_ops_impl;
    
    // Default valid state
    mock_pwm_state.frequency_hz = 38000;
    mock_pwm_state.dead_time_ns = 500;
    mock_pwm_state.running = true;
    mock_pwm_get_state_return = HAL_OK;
    
    pwm_guard_init(0, 0);
}

void tearDown(void) {
}

void test_validate_frequency_ok(void) {
    TEST_ASSERT_EQUAL(PWM_GUARD_OK, pwm_guard_validate_frequency(38000));
    TEST_ASSERT_EQUAL(PWM_GUARD_OK, pwm_guard_validate_frequency(25000)); // Min
    TEST_ASSERT_EQUAL(PWM_GUARD_OK, pwm_guard_validate_frequency(60000)); // Max
}

void test_validate_frequency_fail(void) {
    TEST_ASSERT_EQUAL(PWM_GUARD_ERR_FREQ_LOW, pwm_guard_validate_frequency(24000));
    TEST_ASSERT_EQUAL(PWM_GUARD_ERR_FREQ_HIGH, pwm_guard_validate_frequency(61000));
}

void test_self_test_pass(void) {
    // Setup valid state
    mock_pwm_state.frequency_hz = 38000;
    mock_pwm_state.dead_time_ns = 500;
    
    TEST_ASSERT_EQUAL(PWM_GUARD_OK, pwm_guard_self_test());
}

void test_self_test_bad_freq(void) {
    mock_pwm_state.frequency_hz = 1000; // Way too low
    TEST_ASSERT_EQUAL(PWM_GUARD_ERR_FREQ_LOW, pwm_guard_self_test());
}

void test_self_test_mismatch(void) {
    mock_pwm_state.frequency_hz = 37000; // Valid range but not target (38k)
    // 37000 vs 38000 is > 1% diff
    TEST_ASSERT_EQUAL(PWM_GUARD_ERR_MISMATCH, pwm_guard_self_test());
}

void test_self_test_bad_deadtime(void) {
    mock_pwm_state.dead_time_ns = 100; // Too short (<300)
    TEST_ASSERT_EQUAL(PWM_GUARD_ERR_DEADTIME, pwm_guard_self_test());
}

void test_integrity_check_measured_pass(void) {
    // Initialize CRC
    pwm_guard_self_test();
    
    // Inject valid measured frequency
    _pwm_guard_inject_freq(38050); // Close to 38000
    
    TEST_ASSERT_EQUAL(PWM_GUARD_OK, pwm_guard_check_integrity());
}

void test_integrity_check_measured_fail(void) {
    pwm_guard_self_test();
    
    // Inject deviated frequency (e.g. drift)
    _pwm_guard_inject_freq(35000); // > 5% error
    
    TEST_ASSERT_EQUAL(PWM_GUARD_ERR_MISMATCH, pwm_guard_check_integrity());
}

void test_integrity_check_corruption(void) {
    pwm_guard_self_test(); // Calculates CRC based on 38000/500
    
    // Simulate register corruption (bit flip in RAM/Reg)
    mock_pwm_state.frequency_hz = 38001; 
    
    TEST_ASSERT_EQUAL(PWM_GUARD_ERR_CORRUPTION, pwm_guard_check_integrity());
}
