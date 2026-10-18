/**
 * @file test_power_gate.c
 * @brief RUN_EN rises only with the gate PWM idle (zapote C23 / C39)
 *
 * power_gate.c through the GPIO and PWM mocks: RUN_EN (GPIO14) may be raised
 * only while every gate PWM channel is idle (running == false and every
 * output held low), and may always be lowered.
 */

#include <stdbool.h>
#include <stdint.h>

#include "unity/unity.h"
#include "hal.h"
#include "temper_pins.h"
#include "../components/safety/power_gate.h"

extern void mock_gpio_reset(void);
extern hal_gpio_level_t mock_gpio_get_output_level(hal_pin_t pin);
extern hal_gpio_mode_t mock_gpio_get_mode(hal_pin_t pin);
extern bool mock_gpio_is_initialized(hal_pin_t pin);
extern void mock_pwm_reset(void);
extern const hal_pwm_ops_t hal_pwm_mock_ops;
extern const hal_gpio_ops_t hal_gpio_mock_ops;

static const hal_pwm_config_t GATE_CFG = {
    .frequency_hz = 47000u,
    .duty_percent = 50.0f,
    .dead_time_ns = 500u,
    .pin_high = PIN_PWM_HA,
    .pin_low = PIN_PWM_LA,
    .complementary = true,
};

void power_gate_test_setup(void)
{
    (void)hal_init_mock();
    hal_gpio_set_ops(&hal_gpio_mock_ops);
    hal_pwm_set_ops(&hal_pwm_mock_ops);
    mock_gpio_reset();
    mock_pwm_reset();
}

static bool run_en_high(void)
{
    return mock_gpio_get_output_level(PIN_RUN_EN) == HAL_GPIO_HIGH;
}

void test_power_gate_init_drives_run_en_low(void)
{
    TEST_ASSERT_EQUAL(HAL_OK, power_gate_init());
    TEST_ASSERT_TRUE(mock_gpio_is_initialized(PIN_RUN_EN));
    TEST_ASSERT_EQUAL(HAL_GPIO_MODE_OUTPUT, mock_gpio_get_mode(PIN_RUN_EN));
    TEST_ASSERT_FALSE(run_en_high());
    TEST_ASSERT_FALSE(power_gate_is_enabled());
    TEST_ASSERT_EQUAL_INT(14, PIN_RUN_EN);   /* zapote GPIO14 (C23) */
}

void test_power_gate_enable_refused_before_init(void)
{
    /* An init that cannot configure the pin leaves the gate uninitialised. */
    hal_gpio_set_ops(NULL);
    TEST_ASSERT_EQUAL(HAL_ERROR_NOT_READY, power_gate_init());
    hal_gpio_set_ops(&hal_gpio_mock_ops);
    TEST_ASSERT_EQUAL(HAL_ERROR_NOT_READY, power_gate_enable());
    TEST_ASSERT_FALSE(power_gate_is_enabled());
    TEST_ASSERT_FALSE(run_en_high());
}

void test_power_gate_enable_with_no_gate_channel(void)
{
    /* No gate PWM channel initialised: nothing can drive the gate pins. */
    TEST_ASSERT_EQUAL(HAL_OK, power_gate_init());
    TEST_ASSERT_TRUE(power_gate_pwm_idle());
    TEST_ASSERT_EQUAL(HAL_OK, power_gate_enable());
    TEST_ASSERT_TRUE(run_en_high());
    TEST_ASSERT_TRUE(power_gate_is_enabled());
}

void test_power_gate_enable_with_no_pwm_driver(void)
{
    hal_pwm_set_ops(NULL);
    TEST_ASSERT_EQUAL(HAL_OK, power_gate_init());
    TEST_ASSERT_EQUAL(HAL_OK, power_gate_enable());
    TEST_ASSERT_TRUE(run_en_high());
}

void test_power_gate_enable_with_initialised_idle_channel(void)
{
    TEST_ASSERT_EQUAL(HAL_OK, power_gate_init());
    TEST_ASSERT_EQUAL(HAL_OK, hal_pwm->init(HAL_PWM_CHANNEL_GATE, &GATE_CFG));
    TEST_ASSERT_EQUAL(HAL_OK, power_gate_enable());
    TEST_ASSERT_TRUE(run_en_high());
}

void test_power_gate_refuses_while_pwm_running(void)
{
    TEST_ASSERT_EQUAL(HAL_OK, power_gate_init());
    TEST_ASSERT_EQUAL(HAL_OK, hal_pwm->init(HAL_PWM_CHANNEL_GATE, &GATE_CFG));
    TEST_ASSERT_EQUAL(HAL_OK, hal_pwm->start(HAL_PWM_CHANNEL_GATE));
    TEST_ASSERT_FALSE(power_gate_pwm_idle());
    TEST_ASSERT_EQUAL(HAL_ERROR_BUSY, power_gate_enable());
    TEST_ASSERT_FALSE(run_en_high());
    TEST_ASSERT_FALSE(power_gate_is_enabled());
    TEST_ASSERT_EQUAL_UINT32(1u, power_gate_refusals());
}

void test_power_gate_refuses_after_bare_stop(void)
{
    /* stop() halts the timer but leaves the outputs at their last level:
     * not idle. */
    TEST_ASSERT_EQUAL(HAL_OK, power_gate_init());
    TEST_ASSERT_EQUAL(HAL_OK, hal_pwm->init(HAL_PWM_CHANNEL_GATE, &GATE_CFG));
    TEST_ASSERT_EQUAL(HAL_OK, hal_pwm->start(HAL_PWM_CHANNEL_GATE));
    TEST_ASSERT_EQUAL(HAL_OK, hal_pwm->stop(HAL_PWM_CHANNEL_GATE));
    TEST_ASSERT_EQUAL(HAL_ERROR_BUSY, power_gate_enable());
    TEST_ASSERT_FALSE(run_en_high());
}

void test_power_gate_enable_after_emergency_stop(void)
{
    TEST_ASSERT_EQUAL(HAL_OK, power_gate_init());
    TEST_ASSERT_EQUAL(HAL_OK, hal_pwm->init(HAL_PWM_CHANNEL_GATE, &GATE_CFG));
    TEST_ASSERT_EQUAL(HAL_OK, hal_pwm->start(HAL_PWM_CHANNEL_GATE));
    TEST_ASSERT_EQUAL(HAL_ERROR_BUSY, power_gate_enable());
    TEST_ASSERT_EQUAL(HAL_OK, hal_pwm->emergency_stop());
    TEST_ASSERT_TRUE(power_gate_pwm_idle());
    TEST_ASSERT_EQUAL(HAL_OK, power_gate_enable());
    TEST_ASSERT_TRUE(run_en_high());
}

void test_power_gate_disable_is_never_refused(void)
{
    TEST_ASSERT_EQUAL(HAL_OK, power_gate_init());
    TEST_ASSERT_EQUAL(HAL_OK, power_gate_enable());
    TEST_ASSERT_TRUE(run_en_high());
    /* Bursts start with RUN_EN already high. */
    TEST_ASSERT_EQUAL(HAL_OK, hal_pwm->init(HAL_PWM_CHANNEL_GATE, &GATE_CFG));
    TEST_ASSERT_EQUAL(HAL_OK, hal_pwm->start(HAL_PWM_CHANNEL_GATE));
    /* Already high: no new rising edge, so nothing to refuse. */
    TEST_ASSERT_EQUAL(HAL_OK, power_gate_enable());
    TEST_ASSERT_TRUE(run_en_high());
    power_gate_disable();
    TEST_ASSERT_FALSE(run_en_high());
    TEST_ASSERT_FALSE(power_gate_is_enabled());
    /* Raising it again while the PWM still runs is refused. */
    TEST_ASSERT_EQUAL(HAL_ERROR_BUSY, power_gate_enable());
    TEST_ASSERT_FALSE(run_en_high());
}

/* A PWM driver whose state cannot be read is not idle. */
static hal_status_t broken_get_state(hal_pwm_channel_t channel, hal_pwm_state_t *state)
{
    (void)channel;
    (void)state;
    return HAL_ERROR;
}

void test_power_gate_unreadable_pwm_state_is_not_idle(void)
{
    hal_pwm_ops_t broken = hal_pwm_mock_ops;
    broken.get_state = broken_get_state;
    hal_pwm_set_ops(&broken);
    TEST_ASSERT_EQUAL(HAL_OK, power_gate_init());
    TEST_ASSERT_FALSE(power_gate_pwm_idle());
    TEST_ASSERT_EQUAL(HAL_ERROR_BUSY, power_gate_enable());
    TEST_ASSERT_FALSE(run_en_high());
    hal_pwm_set_ops(&hal_pwm_mock_ops);
}

void run_power_gate_tests(void)
{
    RUN_TEST(test_power_gate_init_drives_run_en_low);
    RUN_TEST(test_power_gate_enable_refused_before_init);
    RUN_TEST(test_power_gate_enable_with_no_gate_channel);
    RUN_TEST(test_power_gate_enable_with_no_pwm_driver);
    RUN_TEST(test_power_gate_enable_with_initialised_idle_channel);
    RUN_TEST(test_power_gate_refuses_while_pwm_running);
    RUN_TEST(test_power_gate_refuses_after_bare_stop);
    RUN_TEST(test_power_gate_enable_after_emergency_stop);
    RUN_TEST(test_power_gate_disable_is_never_refused);
    RUN_TEST(test_power_gate_unreadable_pwm_state_is_not_idle);
}
