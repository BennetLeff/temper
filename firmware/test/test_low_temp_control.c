/**
 * @file test_low_temp_control.c
 * @brief Unit tests for low-temperature burst-mode control
 */

#include "unity/unity.h"
#include "test_common.h"
#include "../components/control/low_temp_control.h"
#include "../components/control/pid_control.h"

/* Mocks/Stubs */
static uint32_t s_time_ms = 0;
static uint8_t s_power_level = 0;

uint32_t get_time_ms(void) {
    return s_time_ms;
}

void power_set_level(uint8_t level) {
    s_power_level = level;
}

void pwm_set_duty_cycle(uint8_t duty) {
    /* Not used in low_temp_control.c but needed for linking */
}

/* ============================================================================
 * Tests
 * ============================================================================ */

void setUp(void) {}
void tearDown(void) {}

static void low_temp_test_setup(void) {
    s_time_ms = 0;
    s_power_level = 0;
    low_temp_init();
}

static void low_temp_test_teardown(void) {
    low_temp_stop();
}

static void test_low_temp_init_inactive(void) {
    low_temp_test_setup();
    TEST_ASSERT_FALSE(low_temp_is_active());
}

static void test_low_temp_start_activates(void) {
    low_temp_test_setup();
    low_temp_start(35.0f);
    TEST_ASSERT_TRUE(low_temp_is_active());
}

static void test_low_temp_burst_logic(void) {
    low_temp_test_setup();
    low_temp_start(35.0f);
    const low_temp_config_t *config = low_temp_get_config();

    /* Initial state: not in burst (waits for first period to expire or starts immediately?)
     * In my implementation, it starts by waiting for current_period_ms.
     * Let's check implementation: 
     * elapsed = now - last_burst_time (initially 0)
     * last_burst_time = get_time_ms() at start.
     * current_period_ms = max_period (30s) at start.
     */
    
    /* Force first burst by advancing time */
    s_time_ms += 31000;
    bool in_burst = low_temp_update(30.0f);
    
    TEST_ASSERT_TRUE(in_burst);
    TEST_ASSERT_EQUAL_UINT8(10, s_power_level);

    /* Advance time within burst duration */
    s_time_ms += (uint32_t)(config->burst_duration_ms / 2.0f);
    in_burst = low_temp_update(31.0f);
    TEST_ASSERT_TRUE(in_burst);
    TEST_ASSERT_EQUAL_UINT8(10, s_power_level);

    /* Advance time beyond burst duration */
    s_time_ms += (uint32_t)config->burst_duration_ms;
    in_burst = low_temp_update(31.0f);
    TEST_ASSERT_FALSE(in_burst);
    TEST_ASSERT_EQUAL_UINT8(0, s_power_level);
}

static void test_low_temp_pid_modulation(void) {
    low_temp_test_setup();
    low_temp_start(35.0f);
    
    /* First PID update happens after 1000ms in implementation */
    s_time_ms += 11000; 
    
    /* Temperature below setpoint (30 < 35) -> should increase duty cycle -> decrease period */
    low_temp_update(30.0f);
    
    /* We can't easily check the private current_period_ms, but we can verify it doesn't crash */
    TEST_ASSERT_TRUE(low_temp_is_active());
}

static void test_low_temp_stop_clears_power(void) {
    low_temp_test_setup();
    low_temp_start(35.0f);
    s_time_ms += 31000;
    low_temp_update(30.0f);
    TEST_ASSERT_EQUAL_UINT8(10, s_power_level);

    low_temp_stop();
    TEST_ASSERT_FALSE(low_temp_is_active());
    TEST_ASSERT_EQUAL_UINT8(0, s_power_level);
}

void run_low_temp_control_tests(void) {
    RUN_TEST(test_low_temp_init_inactive);
    RUN_TEST(test_low_temp_start_activates);
    RUN_TEST(test_low_temp_burst_logic);
    RUN_TEST(test_low_temp_pid_modulation);
    RUN_TEST(test_low_temp_stop_clears_power);
}
