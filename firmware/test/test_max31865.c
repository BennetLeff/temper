/**
 * @file test_max31865.c
 * @brief Host contract tests for MAX31865 threshold programming and faults.
 */

#include "unity/unity.h"

#include <stddef.h>
#include <math.h>

#include "../components/temper_hal/include/hal.h"
#include "../components/temper_hal/include/temper_pins.h"
#include "../components/sensors/include/max31865.h"
#include "../components/sensors/include/rtd_service.h"
#include "../config.h"
#include "../main/state_machine.h"

extern void mock_spi_reset(void);
extern void mock_spi_set_register(hal_spi_device_t device, uint8_t reg,
                                  uint8_t value);
extern void mock_spi_set_register_block(hal_spi_device_t device,
                                        uint8_t start_reg,
                                        const uint8_t *data, size_t len);
extern uint8_t mock_spi_get_register(hal_spi_device_t device, uint8_t reg);
extern void mock_spi_fail_next_read(hal_status_t status);
extern void mock_spi_fail_next_write(hal_status_t status);
extern void mock_gpio_trigger_interrupt(hal_pin_t pin);
extern bool mock_gpio_is_initialized(hal_pin_t pin);
extern void mock_timer_set_time(hal_time_us_t time_us);
extern void mock_sm_reset(void);
extern void mock_sm_set_pan_temperature(float temp_c);
extern uint32_t mock_sm_get_trigger_shutdown_count(void);

static max31865_device_t sensor;

static void arm_continuous_for_test(hal_spi_device_t spi_device)
{
    (void)spi_device;
    TEST_ASSERT_EQUAL(HAL_OK, max31865_start_fault_detection(&sensor));
    TEST_ASSERT_EQUAL(HAL_OK, max31865_start_continuous(&sensor));
}

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

void test_max31865_init_writes_thresholds_and_enables_bias_only(void)
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
    TEST_ASSERT_EQUAL_HEX8(MAX31865_CONFIG_VBIAS,
                           mock_spi_get_register(spi_device,
                                                 MAX31865_REG_CONFIG));
}

void test_max31865_continuous_conversion_is_started_after_fault_cycle(void)
{
    hal_spi_device_t spi_device = create_max31865_device();
    TEST_ASSERT_EQUAL(HAL_OK, max31865_initialize(&sensor, spi_device));
    TEST_ASSERT_EQUAL(HAL_OK, max31865_start_fault_detection(&sensor));
    TEST_ASSERT_EQUAL_HEX8(MAX31865_CONFIG_VBIAS |
                               MAX31865_CONFIG_FAULT_CYCLE_AUTOMATIC |
                               MAX31865_CONFIG_FILTER_60HZ,
                           mock_spi_get_register(spi_device,
                                                 MAX31865_REG_CONFIG));
    TEST_ASSERT_EQUAL(HAL_OK, max31865_start_continuous(&sensor));
    TEST_ASSERT_EQUAL_HEX8(MAX31865_CONFIG_VBIAS |
                               MAX31865_CONFIG_CONVERSION_AUTOMATIC |
                               MAX31865_CONFIG_FILTER_60HZ,
                           mock_spi_get_register(spi_device,
                                                 MAX31865_REG_CONFIG));
}

void test_max31865_rtd_read_right_aligns_code_and_consumes_data_register(void)
{
    const uint8_t rtd_data[] = {0x12u, 0x35u};
    uint16_t rtd_code = 0u;
    hal_spi_device_t spi_device = create_max31865_device();
    TEST_ASSERT_EQUAL(HAL_OK, max31865_initialize(&sensor, spi_device));
    mock_spi_set_register_block(spi_device, MAX31865_REG_RTD_MSB,
                                rtd_data, sizeof(rtd_data));
    TEST_ASSERT_EQUAL(HAL_OK, max31865_read_rtd_code(&sensor, &rtd_code));
    TEST_ASSERT_EQUAL_UINT16(0x091Au, rtd_code);
}

void test_max31865_high_threshold_fault_reaches_terminal_open_path(void)
{
    hal_spi_device_t spi_device = create_max31865_device();
    TEST_ASSERT_EQUAL(HAL_OK, max31865_initialize(&sensor, spi_device));
    arm_continuous_for_test(spi_device);
    mock_spi_set_register(spi_device, MAX31865_REG_FAULT_STATUS,
                          MAX31865_FAULT_HIGH_THRESHOLD);

    /* The service call occurs only after the production owner has observed
     * DRDY or an equivalent verified completion delay. */
    TEST_ASSERT_EQUAL(HAL_OK, max31865_service_fault_cycle(
                                  &sensor,
                                  NULL,
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
    arm_continuous_for_test(spi_device);
    mock_spi_set_register(spi_device, MAX31865_REG_FAULT_STATUS,
                          MAX31865_FAULT_LOW_THRESHOLD);

    TEST_ASSERT_EQUAL(HAL_OK, max31865_service_fault_cycle(
                                  &sensor,
                                  NULL,
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
    arm_continuous_for_test(spi_device);
    mock_spi_set_register(spi_device, MAX31865_REG_FAULT_STATUS, 0x04u);

    TEST_ASSERT_EQUAL(HAL_OK, max31865_service_fault_cycle(
                                  &sensor,
                                  NULL,
                                  state_machine_report_rtd_device_fault,
                                  NULL));

    TEST_ASSERT_EQUAL(STATE_FAULT, state_machine_get_state());
    TEST_ASSERT_EQUAL(FAULT_PROBE_OPEN, state_machine_get_fault());
    TEST_ASSERT_EQUAL_UINT32(1, mock_sm_get_trigger_shutdown_count());
}

void test_max31865_service_does_not_rearm_fault_cycle(void)
{
    hal_spi_device_t spi_device = create_max31865_device();
    TEST_ASSERT_EQUAL(HAL_OK, max31865_initialize(&sensor, spi_device));
    arm_continuous_for_test(spi_device);
    mock_spi_fail_next_write(HAL_ERROR);

    TEST_ASSERT_EQUAL(HAL_OK, max31865_service_fault_cycle(
                                     &sensor,
                                     NULL,
                                     state_machine_report_rtd_device_fault,
                                     NULL));

    TEST_ASSERT_EQUAL(STATE_INIT, state_machine_get_state());
    TEST_ASSERT_EQUAL_UINT32(0, mock_sm_get_trigger_shutdown_count());
}

void test_max31865_status_read_failure_fails_closed_as_probe_open(void)
{
    hal_spi_device_t spi_device = create_max31865_device();
    TEST_ASSERT_EQUAL(HAL_OK, max31865_initialize(&sensor, spi_device));
    arm_continuous_for_test(spi_device);
    mock_spi_fail_next_read(HAL_ERROR);

    TEST_ASSERT_EQUAL(HAL_ERROR, max31865_service_fault_cycle(
                                     &sensor,
                                     NULL,
                                     state_machine_report_rtd_device_fault,
                                     NULL));

    TEST_ASSERT_EQUAL(STATE_FAULT, state_machine_get_state());
    TEST_ASSERT_EQUAL(FAULT_PROBE_OPEN, state_machine_get_fault());
    TEST_ASSERT_EQUAL_UINT32(1, mock_sm_get_trigger_shutdown_count());
}

void test_rtd_service_defers_spi_and_state_mutation_until_drdy_control_tick(void)
{
    TEST_ASSERT_EQUAL(HAL_OK, rtd_service_bootstrap());
    TEST_ASSERT_FALSE(rtd_service_is_ready());
    TEST_ASSERT_FALSE(rtd_service_has_sample());
    TEST_ASSERT_TRUE(mock_gpio_is_initialized(PIN_RTD_DRDY));

    /* Device zero is valid in the mock. A changed status alone must not cause
     * a transfer or state mutation before the explicit 0x84 -> 0xC0 phases. */
    mock_spi_set_register((hal_spi_device_t)0, MAX31865_REG_FAULT_STATUS,
                          MAX31865_FAULT_HIGH_THRESHOLD);
    rtd_service_control_tick();
    TEST_ASSERT_EQUAL(STATE_INIT, state_machine_get_state());
    TEST_ASSERT_EQUAL_UINT32(0, mock_sm_get_trigger_shutdown_count());

    rtd_service_control_tick();
    TEST_ASSERT_EQUAL_HEX8(MAX31865_CONFIG_VBIAS |
                               MAX31865_CONFIG_FAULT_CYCLE_AUTOMATIC |
                               MAX31865_CONFIG_FILTER_60HZ,
                           mock_spi_get_register((hal_spi_device_t)0,
                                                 MAX31865_REG_CONFIG));
    rtd_service_control_tick();
    TEST_ASSERT_EQUAL_HEX8(MAX31865_CONFIG_VBIAS |
                               MAX31865_CONFIG_CONVERSION_AUTOMATIC |
                               MAX31865_CONFIG_FILTER_60HZ,
                           mock_spi_get_register((hal_spi_device_t)0,
                                                 MAX31865_REG_CONFIG));

    mock_gpio_trigger_interrupt(PIN_RTD_DRDY);
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

void test_rtd_service_reads_repeated_drdy_without_restarting_fault_cycle(void)
{
    TEST_ASSERT_EQUAL(HAL_OK, rtd_service_bootstrap());
    rtd_sample_status_t status = rtd_service_sample_status();
    TEST_ASSERT_FALSE(status.ready);
    TEST_ASSERT_EQUAL_UINT32(0u, status.generation);

    /* Bias startup, automatic fault cycle, then continuous conversion. */
    rtd_service_control_tick();
    rtd_service_control_tick();
    TEST_ASSERT_EQUAL_HEX8(MAX31865_CONFIG_VBIAS |
                               MAX31865_CONFIG_FAULT_CYCLE_AUTOMATIC |
                               MAX31865_CONFIG_FILTER_60HZ,
                           mock_spi_get_register((hal_spi_device_t)0,
                                                 MAX31865_REG_CONFIG));
    rtd_service_control_tick();
    TEST_ASSERT_EQUAL_HEX8(MAX31865_CONFIG_VBIAS |
                               MAX31865_CONFIG_CONVERSION_AUTOMATIC |
                               MAX31865_CONFIG_FILTER_60HZ,
                           mock_spi_get_register((hal_spi_device_t)0,
                                                 MAX31865_REG_CONFIG));

    {
        const uint8_t rtd_data[] = {0x3Bu, 0x88u}; /* code 0x1DC4 */
        mock_spi_set_register_block((hal_spi_device_t)0,
                                    MAX31865_REG_RTD_MSB,
                                    rtd_data, sizeof(rtd_data));
    }
    mock_gpio_trigger_interrupt(PIN_RTD_DRDY);
    rtd_service_control_tick();
    TEST_ASSERT_TRUE(rtd_service_is_ready());
    TEST_ASSERT_TRUE(rtd_service_has_sample());
    status = rtd_service_sample_status();
    TEST_ASSERT_TRUE(status.ready);
    TEST_ASSERT_EQUAL_UINT32(1u, status.generation);
    TEST_ASSERT_FLOAT_WITHIN(0.01f, 100.0f, rtd_service_get_resistance());
    TEST_ASSERT_EQUAL_HEX8(MAX31865_CONFIG_VBIAS |
                               MAX31865_CONFIG_CONVERSION_AUTOMATIC |
                               MAX31865_CONFIG_FILTER_60HZ,
                           mock_spi_get_register((hal_spi_device_t)0,
                                                 MAX31865_REG_CONFIG));
    mock_gpio_trigger_interrupt(PIN_RTD_DRDY);
    rtd_service_control_tick();
    TEST_ASSERT_TRUE(rtd_service_is_ready());
    status = rtd_service_sample_status();
    TEST_ASSERT_TRUE(status.ready);
    TEST_ASSERT_EQUAL_UINT32(2u, status.generation);
    TEST_ASSERT_EQUAL(STATE_INIT, state_machine_get_state());
}

void test_rtd_service_stall_invalidates_cached_sample(void)
{
    TEST_ASSERT_EQUAL(HAL_OK, rtd_service_bootstrap());
    rtd_service_control_tick();
    rtd_service_control_tick();
    rtd_service_control_tick();
    const uint8_t rtd_data[] = {0x3Bu, 0x88u};
    mock_spi_set_register_block((hal_spi_device_t)0, MAX31865_REG_RTD_MSB,
                                rtd_data, sizeof(rtd_data));
    mock_gpio_trigger_interrupt(PIN_RTD_DRDY);
    rtd_service_control_tick();
    TEST_ASSERT_TRUE(rtd_service_sample_status().ready);
    TEST_ASSERT_EQUAL_UINT32(1u, rtd_service_sample_status().generation);

    for (uint8_t tick = 0u; tick < RTD_DRDY_TIMEOUT_CONTROL_TICKS; tick++) {
        rtd_service_control_tick();
    }
    rtd_sample_status_t status = rtd_service_sample_status();
    TEST_ASSERT_FALSE(status.ready);
    TEST_ASSERT_EQUAL_UINT32(1u, status.generation);
    TEST_ASSERT_TRUE(rtd_service_has_sample());
    TEST_ASSERT_TRUE(rtd_service_get_resistance() > RTD_OPEN_FAULT_OHM);
    TEST_ASSERT_EQUAL(STATE_FAULT, state_machine_get_state());
}

void test_rtd_service_faulted_conversion_does_not_publish_generation(void)
{
    TEST_ASSERT_EQUAL(HAL_OK, rtd_service_bootstrap());
    rtd_service_control_tick();
    rtd_service_control_tick();
    rtd_service_control_tick();
    const uint8_t rtd_data[] = {0x3Bu, 0x88u};
    mock_spi_set_register_block((hal_spi_device_t)0, MAX31865_REG_RTD_MSB,
                                rtd_data, sizeof(rtd_data));
    mock_gpio_trigger_interrupt(PIN_RTD_DRDY);
    rtd_service_control_tick();
    TEST_ASSERT_TRUE(rtd_service_sample_status().ready);
    TEST_ASSERT_EQUAL_UINT32(1u, rtd_service_sample_status().generation);

    mock_spi_set_register((hal_spi_device_t)0, MAX31865_REG_FAULT_STATUS,
                          MAX31865_FAULT_HIGH_THRESHOLD);
    mock_gpio_trigger_interrupt(PIN_RTD_DRDY);
    rtd_service_control_tick();
    rtd_sample_status_t status = rtd_service_sample_status();
    TEST_ASSERT_FALSE(status.ready);
    TEST_ASSERT_EQUAL_UINT32(1u, status.generation);
    TEST_ASSERT_TRUE(rtd_service_get_resistance() > RTD_OPEN_FAULT_OHM);
    TEST_ASSERT_EQUAL(STATE_FAULT, state_machine_get_state());
}

void test_rtd_service_transport_failure_invalidates_cached_sample(void)
{
    TEST_ASSERT_EQUAL(HAL_OK, rtd_service_bootstrap());
    rtd_service_control_tick();
    rtd_service_control_tick();
    rtd_service_control_tick();
    const uint8_t rtd_data[] = {0x3Bu, 0x88u};
    mock_spi_set_register_block((hal_spi_device_t)0, MAX31865_REG_RTD_MSB,
                                rtd_data, sizeof(rtd_data));
    mock_gpio_trigger_interrupt(PIN_RTD_DRDY);
    rtd_service_control_tick();
    TEST_ASSERT_TRUE(rtd_service_sample_status().ready);

    mock_spi_fail_next_read(HAL_ERROR);
    mock_gpio_trigger_interrupt(PIN_RTD_DRDY);
    rtd_service_control_tick();
    rtd_sample_status_t status = rtd_service_sample_status();
    TEST_ASSERT_FALSE(status.ready);
    TEST_ASSERT_EQUAL_UINT32(1u, status.generation);
    TEST_ASSERT_TRUE(rtd_service_get_resistance() > RTD_OPEN_FAULT_OHM);
    TEST_ASSERT_EQUAL(STATE_FAULT, state_machine_get_state());
}

void test_rtd_service_generation_wrap_keeps_healthy_sample_ready(void)
{
    TEST_ASSERT_EQUAL(HAL_OK, rtd_service_bootstrap());
    rtd_service_control_tick();
    rtd_service_control_tick();
    rtd_service_control_tick();
    const uint8_t rtd_data[] = {0x3Bu, 0x88u};
    mock_spi_set_register_block((hal_spi_device_t)0, MAX31865_REG_RTD_MSB,
                                rtd_data, sizeof(rtd_data));
    mock_gpio_trigger_interrupt(PIN_RTD_DRDY);
    rtd_service_control_tick();
    TEST_ASSERT_TRUE(rtd_service_sample_status().ready);

    rtd_service_test_seed_generation(0x7ffffffeu);
    mock_gpio_trigger_interrupt(PIN_RTD_DRDY);
    rtd_service_control_tick();
    rtd_sample_status_t status = rtd_service_sample_status();
    TEST_ASSERT_TRUE(status.ready);
    TEST_ASSERT_EQUAL_UINT32(0x7fffffffu, status.generation);

    mock_gpio_trigger_interrupt(PIN_RTD_DRDY);
    rtd_service_control_tick();
    status = rtd_service_sample_status();
    TEST_ASSERT_TRUE(status.ready);
    TEST_ASSERT_EQUAL_UINT32(1u, status.generation);
    TEST_ASSERT_EQUAL(STATE_INIT, state_machine_get_state());
}

void test_rtd_service_sample_age_tracks_real_time_and_new_conversion(void)
{
    TEST_ASSERT_EQUAL(HAL_OK, rtd_service_bootstrap());
    rtd_service_control_tick();
    rtd_service_control_tick();
    rtd_service_control_tick();
    const uint8_t rtd_data[] = {0x3Bu, 0x88u};
    mock_spi_set_register_block((hal_spi_device_t)0, MAX31865_REG_RTD_MSB,
                                rtd_data, sizeof(rtd_data));

    rtd_sample_status_t status = rtd_service_sample_status();
    TEST_ASSERT_FALSE(status.ready);
    TEST_ASSERT_EQUAL_UINT32(UINT32_MAX, status.age_ms);
    TEST_ASSERT_TRUE(isnan(rtd_service_pan_temperature_c()));

    mock_timer_set_time(1000000u);
    mock_gpio_trigger_interrupt(PIN_RTD_DRDY);
    rtd_service_control_tick();
    status = rtd_service_sample_status();
    TEST_ASSERT_TRUE(status.ready);
    TEST_ASSERT_EQUAL_UINT32(1u, status.generation);
    TEST_ASSERT_EQUAL_UINT32(0u, status.age_ms);
    TEST_ASSERT_TRUE(isfinite(rtd_service_pan_temperature_c()));

    /* A stalled control task cannot keep a cached conversion young. */
    mock_timer_set_time(1150000u);
    status = rtd_service_sample_status();
    TEST_ASSERT_TRUE(status.ready);
    TEST_ASSERT_EQUAL_UINT32(1u, status.generation);
    TEST_ASSERT_EQUAL_UINT32(150u, status.age_ms);
    TEST_ASSERT_TRUE(isnan(rtd_service_pan_temperature_c()));

    mock_gpio_trigger_interrupt(PIN_RTD_DRDY);
    rtd_service_control_tick();
    status = rtd_service_sample_status();
    TEST_ASSERT_EQUAL_UINT32(2u, status.generation);
    TEST_ASSERT_EQUAL_UINT32(0u, status.age_ms);
    TEST_ASSERT_TRUE(isfinite(rtd_service_pan_temperature_c()));
}

void test_pt100_conversion_matches_max31865_reference_table(void)
{
    /* MAX31865 data sheet Table 9: PT100 resistance rounded to 0.01 ohm. */
    TEST_ASSERT_FLOAT_WITHIN(0.1f, -40.0f,
                             rtd_pt100_temperature_c(84.27f));
    TEST_ASSERT_FLOAT_WITHIN(0.01f, 0.0f,
                             rtd_pt100_temperature_c(100.0f));
    TEST_ASSERT_FLOAT_WITHIN(0.1f, 100.0f,
                             rtd_pt100_temperature_c(138.51f));
    TEST_ASSERT_FLOAT_WITHIN(0.1f, 250.0f,
                             rtd_pt100_temperature_c(194.10f));
    TEST_ASSERT_TRUE(isnan(rtd_pt100_temperature_c(NAN)));
    TEST_ASSERT_TRUE(isnan(rtd_pt100_temperature_c(0.0f)));
    TEST_ASSERT_TRUE(isnan(rtd_pt100_temperature_c(400.0f)));
}

void test_init_waits_for_first_rtd_conversion_without_runaway(void)
{
    TEST_ASSERT_EQUAL(HAL_OK, rtd_service_bootstrap());
    mock_sm_set_pan_temperature(NAN);
    TEST_ASSERT_FALSE(state_machine_update());
    TEST_ASSERT_EQUAL(STATE_INIT, state_machine_get_state());
    TEST_ASSERT_EQUAL(FAULT_NONE, state_machine_get_fault());

    rtd_service_control_tick();
    rtd_service_control_tick();
    rtd_service_control_tick();
    const uint8_t rtd_data[] = {0x3Bu, 0x88u};
    mock_spi_set_register_block((hal_spi_device_t)0, MAX31865_REG_RTD_MSB,
                                rtd_data, sizeof(rtd_data));
    mock_gpio_trigger_interrupt(PIN_RTD_DRDY);
    rtd_service_control_tick();
    TEST_ASSERT_TRUE(rtd_service_is_ready());

    mock_sm_set_pan_temperature(25.0f);
    TEST_ASSERT_TRUE(state_machine_update());
    TEST_ASSERT_EQUAL(STATE_IDLE, state_machine_get_state());
}

void test_missing_first_rtd_conversion_keeps_probe_fault_diagnosis(void)
{
    TEST_ASSERT_EQUAL(HAL_OK, rtd_service_bootstrap());
    mock_sm_set_pan_temperature(NAN);
    for (uint8_t tick = 0u;
         tick < RTD_BIAS_STARTUP_CONTROL_TICKS +
                    RTD_FAULT_CYCLE_SETTLE_CONTROL_TICKS +
                    RTD_DRDY_TIMEOUT_CONTROL_TICKS;
         ++tick) {
        rtd_service_control_tick();
    }
    TEST_ASSERT_EQUAL(STATE_FAULT, state_machine_get_state());
    TEST_ASSERT_EQUAL(FAULT_PROBE_OPEN, state_machine_get_fault());
    TEST_ASSERT_FALSE(state_machine_update());
    TEST_ASSERT_EQUAL(STATE_FAULT, state_machine_get_state());
    TEST_ASSERT_EQUAL(FAULT_PROBE_OPEN, state_machine_get_fault());
}

void test_rtd_service_sample_age_handles_timer_wrap_and_invalidation(void)
{
    TEST_ASSERT_EQUAL(HAL_OK, rtd_service_bootstrap());
    rtd_service_control_tick();
    rtd_service_control_tick();
    rtd_service_control_tick();
    const uint8_t rtd_data[] = {0x3Bu, 0x88u};
    mock_spi_set_register_block((hal_spi_device_t)0, MAX31865_REG_RTD_MSB,
                                rtd_data, sizeof(rtd_data));
    mock_timer_set_time((hal_time_us_t)(UINT32_MAX - 9u) * 1000u);
    mock_gpio_trigger_interrupt(PIN_RTD_DRDY);
    rtd_service_control_tick();

    mock_timer_set_time(((hal_time_us_t)UINT32_MAX + 11u) * 1000u);
    rtd_sample_status_t status = rtd_service_sample_status();
    TEST_ASSERT_TRUE(status.ready);
    TEST_ASSERT_EQUAL_UINT32(20u, status.age_ms);

    for (uint8_t tick = 0u; tick < RTD_DRDY_TIMEOUT_CONTROL_TICKS; tick++) {
        rtd_service_control_tick();
    }
    status = rtd_service_sample_status();
    TEST_ASSERT_FALSE(status.ready);
    TEST_ASSERT_EQUAL_UINT32(UINT32_MAX, status.age_ms);
    TEST_ASSERT_TRUE(isnan(rtd_service_pan_temperature_c()));
}

void test_rtd_service_missing_clock_rejects_conversion(void)
{
    TEST_ASSERT_EQUAL(HAL_OK, rtd_service_bootstrap());
    rtd_service_control_tick();
    rtd_service_control_tick();
    rtd_service_control_tick();
    const uint8_t rtd_data[] = {0x3Bu, 0x88u};
    mock_spi_set_register_block((hal_spi_device_t)0, MAX31865_REG_RTD_MSB,
                                rtd_data, sizeof(rtd_data));
    mock_gpio_trigger_interrupt(PIN_RTD_DRDY);
    rtd_service_control_tick();
    TEST_ASSERT_TRUE(rtd_service_sample_status().ready);

    hal_timer_set_ops(NULL);
    rtd_sample_status_t status = rtd_service_sample_status();
    TEST_ASSERT_FALSE(status.ready);
    TEST_ASSERT_EQUAL_UINT32(UINT32_MAX, status.age_ms);

    mock_gpio_trigger_interrupt(PIN_RTD_DRDY);
    rtd_service_control_tick();
    status = rtd_service_sample_status();
    TEST_ASSERT_FALSE(status.ready);
    TEST_ASSERT_EQUAL(STATE_FAULT, state_machine_get_state());
    TEST_ASSERT_EQUAL(FAULT_PROBE_OPEN, state_machine_get_fault());
}

void test_rtd_service_silent_drdy_fails_closed_within_control_bound(void)
{
    uint8_t tick;

    TEST_ASSERT_EQUAL(HAL_OK, rtd_service_bootstrap());
    for (tick = 0u; tick < RTD_BIAS_STARTUP_CONTROL_TICKS +
                            RTD_FAULT_CYCLE_SETTLE_CONTROL_TICKS +
                            RTD_DRDY_TIMEOUT_CONTROL_TICKS - 1u; tick++) {
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
    RUN_TEST(test_max31865_init_writes_thresholds_and_enables_bias_only);
    RUN_TEST(test_max31865_continuous_conversion_is_started_after_fault_cycle);
    RUN_TEST(test_max31865_rtd_read_right_aligns_code_and_consumes_data_register);
    RUN_TEST(test_max31865_high_threshold_fault_reaches_terminal_open_path);
    RUN_TEST(test_max31865_low_threshold_fault_reaches_terminal_short_path);
    RUN_TEST(test_max31865_non_threshold_fault_fails_closed_as_probe_open);
    RUN_TEST(test_max31865_service_does_not_rearm_fault_cycle);
    RUN_TEST(test_max31865_status_read_failure_fails_closed_as_probe_open);
    RUN_TEST(test_rtd_service_defers_spi_and_state_mutation_until_drdy_control_tick);
    RUN_TEST(test_rtd_service_bootstrap_failure_fails_closed_from_control_task);
    RUN_TEST(test_rtd_service_reads_repeated_drdy_without_restarting_fault_cycle);
    RUN_TEST(test_rtd_service_stall_invalidates_cached_sample);
    RUN_TEST(test_rtd_service_faulted_conversion_does_not_publish_generation);
    RUN_TEST(test_rtd_service_transport_failure_invalidates_cached_sample);
    RUN_TEST(test_rtd_service_generation_wrap_keeps_healthy_sample_ready);
    RUN_TEST(test_rtd_service_sample_age_tracks_real_time_and_new_conversion);
    RUN_TEST(test_pt100_conversion_matches_max31865_reference_table);
    RUN_TEST(test_init_waits_for_first_rtd_conversion_without_runaway);
    RUN_TEST(test_missing_first_rtd_conversion_keeps_probe_fault_diagnosis);
    RUN_TEST(test_rtd_service_sample_age_handles_timer_wrap_and_invalidation);
    RUN_TEST(test_rtd_service_missing_clock_rejects_conversion);
    RUN_TEST(test_rtd_service_silent_drdy_fails_closed_within_control_bound);
}
