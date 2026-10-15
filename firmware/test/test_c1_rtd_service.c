/**
 * @file test_c1_rtd_service.c
 * @brief TEMPER_PAN_CONTROL_C1 MAX31865 service (CR-7, rtd_service.c): C1
 *        thresholds, power-up fault cycle, continuous conversion, fault flag,
 *        DRDY-stale and frozen-code faults, through the SPI mock and the real
 *        state machine.
 */

#include <math.h>

#include "unity/unity.h"

#include "../components/temper_hal/include/hal.h"
#include "../components/temper_hal/include/temper_pins.h"
#include "../components/sensors/include/max31865.h"
#include "../components/sensors/include/rtd_service.h"
#include "../config.h"
#include "../main/state_machine.h"

extern void mock_spi_reset(void);
extern void mock_spi_set_register(hal_spi_device_t device, uint8_t reg, uint8_t value);
extern uint8_t mock_spi_get_register(hal_spi_device_t device, uint8_t reg);
extern void mock_gpio_trigger_interrupt(hal_pin_t pin);
extern void mock_sm_reset(void);

/* pan_control.c (linked through the C1 state machine) reads the rim NTC. */
float read_rim_ntc_temperature(void) { return 40.0f; }

#define DEV ((hal_spi_device_t)0)

void setUp(void)
{
    hal_deinit();
    mock_spi_reset();
    TEST_ASSERT_EQUAL(HAL_OK, hal_init_mock());
    mock_sm_reset();
    state_machine_init();
}

void tearDown(void)
{
    (void)hal_deinit();
}

static void finish_fault_cycle(uint8_t status)
{
    mock_spi_set_register(DEV, MAX31865_REG_FAULT_STATUS, status);
    mock_spi_set_register(DEV, MAX31865_REG_CONFIG,
                          (uint8_t)(mock_spi_get_register(DEV, MAX31865_REG_CONFIG) &
                                    (uint8_t)~MAX31865_CONFIG_FAULT_CYCLE_MASK));
    rtd_service_control_tick();
}

static void convert(uint16_t code, bool fault_flag)
{
    const uint16_t word = (uint16_t)((code << 1) | (fault_flag ? 1u : 0u));
    mock_spi_set_register(DEV, MAX31865_REG_RTD_MSB, (uint8_t)(word >> 8));
    mock_spi_set_register(DEV, MAX31865_REG_RTD_MSB + 1u, (uint8_t)word);
    mock_gpio_trigger_interrupt(PIN_RTD_DRDY);
    rtd_service_control_tick();
}

static uint16_t code_for(double r_ohm) { return (uint16_t)lround(r_ohm / 430.0 * 32768.0); }

static void test_c1_bootstrap_programs_the_c1_window(void)
{
    TEST_ASSERT_EQUAL(HAL_OK, rtd_service_bootstrap());
    TEST_ASSERT_EQUAL_HEX8((uint8_t)(MAX31865_C1_HIGH_THRESHOLD_WORD >> 8),
                           mock_spi_get_register(DEV, MAX31865_REG_HIGH_THRESHOLD_MSB));
    TEST_ASSERT_EQUAL_HEX8((uint8_t)MAX31865_C1_HIGH_THRESHOLD_WORD,
                           mock_spi_get_register(DEV, MAX31865_REG_HIGH_THRESHOLD_MSB + 1u));
    TEST_ASSERT_EQUAL_HEX8((uint8_t)(MAX31865_C1_LOW_THRESHOLD_WORD >> 8),
                           mock_spi_get_register(DEV, MAX31865_REG_LOW_THRESHOLD_MSB));
    TEST_ASSERT_EQUAL_HEX8((uint8_t)MAX31865_C1_LOW_THRESHOLD_WORD,
                           mock_spi_get_register(DEV, MAX31865_REG_LOW_THRESHOLD_MSB + 1u));
    /* 233.21 / 84.27 ohm (CR-7), 15-bit code << 1 */
    TEST_ASSERT_FLOAT_WITHIN(0.02f, 233.21f, (float)(MAX31865_C1_HIGH_THRESHOLD_WORD >> 1) / 32768.0f * 430.0f);
    TEST_ASSERT_FLOAT_WITHIN(0.02f, 84.27f, (float)(MAX31865_C1_LOW_THRESHOLD_WORD >> 1) / 32768.0f * 430.0f);
}

static void test_c1_waits_for_the_fault_cycle_then_converts_continuously(void)
{
    TEST_ASSERT_EQUAL(HAL_OK, rtd_service_bootstrap());
    rtd_sample_t s;
    /* fault cycle still running (CONFIG D3:D2 != 0): no sample, no fault */
    rtd_service_control_tick();
    TEST_ASSERT_FALSE(rtd_service_latest_sample(&s));
    finish_fault_cycle(0u);
    TEST_ASSERT_EQUAL_HEX8(MAX31865_CONFIG_VBIAS | MAX31865_CONFIG_AUTO_CONVERT,
                           mock_spi_get_register(DEV, MAX31865_REG_CONFIG));
    convert(code_for(138.5055), false);
    TEST_ASSERT_TRUE(rtd_service_latest_sample(&s));
    TEST_ASSERT_TRUE(s.spi_ok);
    TEST_ASSERT_EQUAL_UINT8(0u, s.fault_status);
    TEST_ASSERT_FLOAT_WITHIN(0.03f, 100.0f - 0.061f, s.t_c);
    TEST_ASSERT_EQUAL_INT(FAULT_NONE, state_machine_get_fault());
}

static void test_c1_power_up_fault_cycle_short_is_terminal(void)
{
    TEST_ASSERT_EQUAL(HAL_OK, rtd_service_bootstrap());
    finish_fault_cycle(MAX31865_FAULT_LOW_THRESHOLD);
    TEST_ASSERT_EQUAL_INT(STATE_FAULT, state_machine_get_state());
    TEST_ASSERT_EQUAL_INT(FAULT_PROBE_SHORT, state_machine_get_fault());
    TEST_ASSERT_FALSE(rtd_service_is_ready());
}

static void test_c1_conversion_fault_flag_reports_register_07h(void)
{
    TEST_ASSERT_EQUAL(HAL_OK, rtd_service_bootstrap());
    finish_fault_cycle(0u);
    mock_spi_set_register(DEV, MAX31865_REG_FAULT_STATUS, MAX31865_FAULT_HIGH_THRESHOLD);
    convert(0x7FFFu, true);
    TEST_ASSERT_EQUAL_INT(STATE_FAULT, state_machine_get_state());
    TEST_ASSERT_EQUAL_INT(FAULT_PROBE_OPEN, state_machine_get_fault());
}

static void test_c1_no_drdy_for_six_ticks_is_an_open_fault(void)
{
    TEST_ASSERT_EQUAL(HAL_OK, rtd_service_bootstrap());
    finish_fault_cycle(0u);
    convert(code_for(150.0), false);
    for (unsigned i = 0; i < RTD_C1_STALE_CONTROL_TICKS - 1u; i++) {
        rtd_service_control_tick();
        TEST_ASSERT_EQUAL_INT(FAULT_NONE, state_machine_get_fault());
    }
    rtd_service_control_tick();
    TEST_ASSERT_EQUAL_INT(STATE_FAULT, state_machine_get_state());
    TEST_ASSERT_EQUAL_INT(FAULT_PROBE_OPEN, state_machine_get_fault());
}

static void test_c1_identical_codes_are_normal_until_the_frozen_limit(void)
{
    TEST_ASSERT_EQUAL(HAL_OK, rtd_service_bootstrap());
    finish_fault_cycle(0u);
    const uint16_t c = code_for(175.0);
    /* a different code resets the count */
    for (unsigned i = 0; i < RTD_C1_FROZEN_CONVERSIONS - 1u; i++) {
        convert(c, false);
    }
    convert((uint16_t)(c + 1u), false);
    for (unsigned i = 0; i < RTD_C1_FROZEN_CONVERSIONS - 1u; i++) {
        convert(c, false);
    }
    TEST_ASSERT_EQUAL_INT(FAULT_NONE, state_machine_get_fault());
    convert(c, false);
    TEST_ASSERT_EQUAL_INT(STATE_FAULT, state_machine_get_state());
    TEST_ASSERT_EQUAL_INT(FAULT_ADC_STUCK, state_machine_get_fault());
    TEST_ASSERT_FALSE(rtd_service_is_ready());
}

void run_c1_rtd_service_tests(void)
{
    RUN_TEST(test_c1_bootstrap_programs_the_c1_window);
    RUN_TEST(test_c1_waits_for_the_fault_cycle_then_converts_continuously);
    RUN_TEST(test_c1_power_up_fault_cycle_short_is_terminal);
    RUN_TEST(test_c1_conversion_fault_flag_reports_register_07h);
    RUN_TEST(test_c1_no_drdy_for_six_ticks_is_an_open_fault);
    RUN_TEST(test_c1_identical_codes_are_normal_until_the_frozen_limit);
}
