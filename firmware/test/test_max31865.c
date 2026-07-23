/**
 * @file test_max31865.c
 * @brief Host contract tests for MAX31865 threshold programming and faults.
 */

#include "unity/unity.h"

#include "../components/hal/include/hal.h"
#include "../components/hal/include/temper_pins.h"
#include "../components/sensors/include/max31865.h"
#include "../components/sensors/include/rtd_service.h"
#include "../config.h"
#include "../main/state_machine.h"

extern void mock_spi_reset(void);
extern void mock_spi_set_register(hal_spi_device_t device, uint8_t reg,
                                  uint8_t value);
extern uint8_t mock_spi_get_register(hal_spi_device_t device, uint8_t reg);
extern void mock_spi_fail_next_read(hal_status_t status);
extern void mock_spi_fail_next_write(hal_status_t status);
extern void mock_gpio_trigger_interrupt(hal_pin_t pin);
extern bool mock_gpio_is_initialized(hal_pin_t pin);
extern void mock_sm_reset(void);
extern uint32_t mock_sm_get_trigger_shutdown_count(void);

static max31865_device_t sensor;

static hal_spi_device_t create_max31865_device(void)
{
    const hal_spi_config_t config = {
        .clock_hz = 500000u,
        .mode = 1u,
        .pin_mosi = 11,
        .pin_miso = 12,
        .pin_sclk = 8,
        .pin_cs = 16,
        .cs_active_high = false,
    };
    hal_spi_device_t ignored_device;
    hal_spi_device_t device;

    TEST_ASSERT_EQUAL(HAL_OK, hal_spi->bus_init(0, &config));

    /* Mock SPI represents slot zero as NULL. Reserve it so the test exercises
     * the same non-null device-handle contract as the production HAL. */
    TEST_ASSERT_EQUAL(HAL_OK, hal_spi->device_add(0, &config, &ignored_device));
    TEST_ASSERT_EQUAL(HAL_OK, hal_spi->device_add(0, &config, &device));
    return device;
}

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

void test_max31865_init_writes_encoded_threshold_words_and_starts_async_cycle(void)
{
    hal_spi_device_t spi_device = create_max31865_device();

    TEST_ASSERT_EQUAL(HAL_OK, max31865_initialize(&sensor, spi_device));

    TEST_ASSERT_EQUAL_HEX8(0xB2,
                           mock_spi_get_register(spi_device,
                                                 MAX31865_REG_HIGH_THRESHOLD_MSB));
    TEST_ASSERT_EQUAL_HEX8(0x9A,
                           mock_spi_get_register(spi_device,
                                                 MAX31865_REG_HIGH_THRESHOLD_MSB + 1u));
    TEST_ASSERT_EQUAL_HEX8(0x05,
                           mock_spi_get_register(spi_device,
                                                 MAX31865_REG_LOW_THRESHOLD_MSB));
    TEST_ASSERT_EQUAL_HEX8(0xF6,
                           mock_spi_get_register(spi_device,
                                                 MAX31865_REG_LOW_THRESHOLD_MSB + 1u));
    TEST_ASSERT_EQUAL_UINT16(0xB29A, MAX31865_HIGH_THRESHOLD_WORD);
    TEST_ASSERT_EQUAL_UINT16(0x05F6, MAX31865_LOW_THRESHOLD_WORD);
    TEST_ASSERT_EQUAL_HEX8(MAX31865_CONFIG_VBIAS |
                               MAX31865_CONFIG_FAULT_CYCLE_AUTOMATIC,
                           mock_spi_get_register(spi_device,
                                                 MAX31865_REG_CONFIG));
}

void test_max31865_high_threshold_fault_reaches_terminal_open_path(void)
{
    hal_spi_device_t spi_device = create_max31865_device();
    TEST_ASSERT_EQUAL(HAL_OK, max31865_initialize(&sensor, spi_device));
    mock_spi_set_register(spi_device, MAX31865_REG_FAULT_STATUS,
                          MAX31865_FAULT_HIGH_THRESHOLD);

    /* The service call occurs only after the production owner has observed
     * DRDY or an equivalent verified completion delay. */
    TEST_ASSERT_EQUAL(HAL_OK, max31865_service_fault_cycle(
                                  &sensor,
                                  state_machine_report_rtd_device_fault,
                                  NULL));

    TEST_ASSERT_EQUAL(STATE_FAULT, state_machine_get_state());
    TEST_ASSERT_EQUAL(FAULT_PROBE_OPEN, state_machine_get_fault());
    TEST_ASSERT_EQUAL_UINT32(1, mock_sm_get_trigger_shutdown_count());
}

void test_max31865_low_threshold_fault_reaches_terminal_short_path(void)
{
    hal_spi_device_t spi_device = create_max31865_device();
    TEST_ASSERT_EQUAL(HAL_OK, max31865_initialize(&sensor, spi_device));
    mock_spi_set_register(spi_device, MAX31865_REG_FAULT_STATUS,
                          MAX31865_FAULT_LOW_THRESHOLD);

    TEST_ASSERT_EQUAL(HAL_OK, max31865_service_fault_cycle(
                                  &sensor,
                                  state_machine_report_rtd_device_fault,
                                  NULL));

    TEST_ASSERT_EQUAL(STATE_FAULT, state_machine_get_state());
    TEST_ASSERT_EQUAL(FAULT_PROBE_SHORT, state_machine_get_fault());
    TEST_ASSERT_EQUAL_UINT32(1, mock_sm_get_trigger_shutdown_count());
}

void test_max31865_non_threshold_fault_fails_closed_as_probe_open(void)
{
    hal_spi_device_t spi_device = create_max31865_device();
    TEST_ASSERT_EQUAL(HAL_OK, max31865_initialize(&sensor, spi_device));
    mock_spi_set_register(spi_device, MAX31865_REG_FAULT_STATUS, 0x04u);

    TEST_ASSERT_EQUAL(HAL_OK, max31865_service_fault_cycle(
                                  &sensor,
                                  state_machine_report_rtd_device_fault,
                                  NULL));

    TEST_ASSERT_EQUAL(STATE_FAULT, state_machine_get_state());
    TEST_ASSERT_EQUAL(FAULT_PROBE_OPEN, state_machine_get_fault());
    TEST_ASSERT_EQUAL_UINT32(1, mock_sm_get_trigger_shutdown_count());
}

void test_max31865_restart_write_failure_fails_closed_as_probe_open(void)
{
    hal_spi_device_t spi_device = create_max31865_device();
    TEST_ASSERT_EQUAL(HAL_OK, max31865_initialize(&sensor, spi_device));
    mock_spi_fail_next_write(HAL_ERROR);

    TEST_ASSERT_EQUAL(HAL_ERROR, max31865_service_fault_cycle(
                                     &sensor,
                                     state_machine_report_rtd_device_fault,
                                     NULL));

    TEST_ASSERT_EQUAL(STATE_FAULT, state_machine_get_state());
    TEST_ASSERT_EQUAL(FAULT_PROBE_OPEN, state_machine_get_fault());
    TEST_ASSERT_EQUAL_UINT32(1, mock_sm_get_trigger_shutdown_count());
}

void test_max31865_status_read_failure_fails_closed_as_probe_open(void)
{
    hal_spi_device_t spi_device = create_max31865_device();
    TEST_ASSERT_EQUAL(HAL_OK, max31865_initialize(&sensor, spi_device));
    mock_spi_fail_next_read(HAL_ERROR);

    TEST_ASSERT_EQUAL(HAL_ERROR, max31865_service_fault_cycle(
                                     &sensor,
                                     state_machine_report_rtd_device_fault,
                                     NULL));

    TEST_ASSERT_EQUAL(STATE_FAULT, state_machine_get_state());
    TEST_ASSERT_EQUAL(FAULT_PROBE_OPEN, state_machine_get_fault());
    TEST_ASSERT_EQUAL_UINT32(1, mock_sm_get_trigger_shutdown_count());
}

void test_rtd_service_defers_spi_and_state_mutation_until_drdy_control_tick(void)
{
    TEST_ASSERT_EQUAL(HAL_OK, rtd_service_bootstrap());
    TEST_ASSERT_TRUE(rtd_service_is_ready());
    TEST_ASSERT_TRUE(mock_gpio_is_initialized(PIN_RTD_DRDY));

    /* Device zero is valid in the mock. A changed status alone must not cause
     * a transfer or state mutation before the DRDY ISR hands work to control. */
    mock_spi_set_register((hal_spi_device_t)0, MAX31865_REG_FAULT_STATUS,
                          MAX31865_FAULT_HIGH_THRESHOLD);
    rtd_service_control_tick();
    TEST_ASSERT_EQUAL(STATE_INIT, state_machine_get_state());
    TEST_ASSERT_EQUAL_UINT32(0, mock_sm_get_trigger_shutdown_count());

    mock_gpio_trigger_interrupt(PIN_RTD_DRDY);
    TEST_ASSERT_EQUAL(STATE_INIT, state_machine_get_state());
    TEST_ASSERT_EQUAL_UINT32(0, mock_sm_get_trigger_shutdown_count());

    rtd_service_control_tick();
    TEST_ASSERT_EQUAL(STATE_FAULT, state_machine_get_state());
    TEST_ASSERT_EQUAL(FAULT_PROBE_OPEN, state_machine_get_fault());
    TEST_ASSERT_EQUAL_UINT32(1, mock_sm_get_trigger_shutdown_count());
}

void test_rtd_service_bootstrap_failure_fails_closed_from_control_task(void)
{
    (void)hal_deinit();
    TEST_ASSERT_EQUAL(HAL_ERROR_NOT_READY, rtd_service_bootstrap());
    TEST_ASSERT_FALSE(rtd_service_is_ready());
    TEST_ASSERT_EQUAL(STATE_INIT, state_machine_get_state());

    rtd_service_control_tick();
    TEST_ASSERT_EQUAL(STATE_FAULT, state_machine_get_state());
    TEST_ASSERT_EQUAL(FAULT_PROBE_OPEN, state_machine_get_fault());
    TEST_ASSERT_EQUAL_UINT32(1, mock_sm_get_trigger_shutdown_count());
}

void test_rtd_service_silent_drdy_fails_closed_within_control_bound(void)
{
    uint8_t tick;

    TEST_ASSERT_EQUAL(HAL_OK, rtd_service_bootstrap());
    for (tick = 0u; tick < RTD_DRDY_TIMEOUT_CONTROL_TICKS - 1u; tick++) {
        rtd_service_control_tick();
        TEST_ASSERT_EQUAL(STATE_INIT, state_machine_get_state());
    }

    rtd_service_control_tick();
    TEST_ASSERT_EQUAL(STATE_FAULT, state_machine_get_state());
    TEST_ASSERT_EQUAL(FAULT_PROBE_OPEN, state_machine_get_fault());
    TEST_ASSERT_EQUAL_UINT32(1, mock_sm_get_trigger_shutdown_count());
    TEST_ASSERT_FALSE(rtd_service_is_ready());
}

void run_max31865_tests(void)
{
    RUN_TEST(test_max31865_init_writes_encoded_threshold_words_and_starts_async_cycle);
    RUN_TEST(test_max31865_high_threshold_fault_reaches_terminal_open_path);
    RUN_TEST(test_max31865_low_threshold_fault_reaches_terminal_short_path);
    RUN_TEST(test_max31865_non_threshold_fault_fails_closed_as_probe_open);
    RUN_TEST(test_max31865_restart_write_failure_fails_closed_as_probe_open);
    RUN_TEST(test_max31865_status_read_failure_fails_closed_as_probe_open);
    RUN_TEST(test_rtd_service_defers_spi_and_state_mutation_until_drdy_control_tick);
    RUN_TEST(test_rtd_service_bootstrap_failure_fails_closed_from_control_task);
    RUN_TEST(test_rtd_service_silent_drdy_fails_closed_within_control_bound);
}
