/**
 * @file test_max31865.c
 * @brief Host contract tests for MAX31865 threshold programming and faults.
 */

#include "unity/unity.h"

#include "../components/hal/include/hal.h"
#include "../components/hal/include/controller_pins.h"
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
extern bool mock_gpio_is_initialized(hal_pin_t pin);
extern void mock_sm_reset(void);
extern uint32_t mock_sm_get_trigger_shutdown_count(void);

static max31865_device_t sensor;

/* Fake expander DRDY (P07) level source. release_on_read models the MAX31865: reading the RTD
 * data word returns DRDY high, which the service sees on its refresh sample. */
static struct {
    bool available;
    bool low;
    bool release_on_read;
    unsigned polls;
    unsigned refreshes;
} drdy;

static bool fake_drdy_level(void *context, bool refresh, bool *drdy_low)
{
    (void)context;
    drdy.polls++;
    if (refresh) {
        drdy.refreshes++;
        if (drdy.release_on_read) drdy.low = false;
    }
    *drdy_low = drdy.low;
    return drdy.available;
}

static hal_spi_device_t create_max31865_device(void)
{
    const hal_spi_config_t config = {
        .clock_hz = 500000u,
        .mode = CTRL_RTD_SPI_MODE,
        .pin_mosi = CTRL_GPIO_RTD_SDI,
        .pin_miso = CTRL_GPIO_RTD_SDO,
        .pin_sclk = CTRL_GPIO_RTD_SCK,
        .pin_cs = CTRL_GPIO_RTD_CS_N,
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
    drdy.available = true;
    drdy.low = false;
    drdy.release_on_read = true;
    drdy.polls = 0u;
    drdy.refreshes = 0u;
    rtd_service_set_drdy_source(fake_drdy_level, NULL);
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

void test_rtd_service_requires_drdy_source(void)
{
    rtd_service_set_drdy_source(NULL, NULL);
    TEST_ASSERT_EQUAL(HAL_ERROR_NOT_READY, rtd_service_bootstrap());
    TEST_ASSERT_FALSE(rtd_service_is_ready());
    rtd_service_control_tick();
    TEST_ASSERT_EQUAL(STATE_FAULT, state_machine_get_state());
    TEST_ASSERT_EQUAL(FAULT_PROBE_OPEN, state_machine_get_fault());
}

/* ---------------------------------------------------------------- conversion / fault-cycle schedule */
#define RTD_DEV ((hal_spi_device_t)0)

static uint8_t config_reg(void) { return mock_spi_get_register(RTD_DEV, MAX31865_REG_CONFIG); }

/* The MAX31865 clears CONFIG D3:D2 when the automatic fault cycle has finished. */
static void mock_fault_cycle_finishes(void)
{
    mock_spi_set_register(RTD_DEV, MAX31865_REG_CONFIG,
                          (uint8_t)(config_reg() & (uint8_t)~MAX31865_CONFIG_FAULT_CYCLE_MASK));
}

static void set_rtd_word(uint16_t w)
{
    mock_spi_set_register(RTD_DEV, MAX31865_REG_RTD_MSB, (uint8_t)(w >> 8));
    mock_spi_set_register(RTD_DEV, MAX31865_REG_RTD_MSB + 1u, (uint8_t)w);
}

static void bootstrap_to_converting(void)
{
    TEST_ASSERT_EQUAL(HAL_OK, rtd_service_bootstrap());
    TEST_ASSERT_EQUAL_HEX8(MAX31865_CONFIG_FAULT_CYCLE, config_reg());
    TEST_ASSERT_FALSE(rtd_service_converting());
    mock_fault_cycle_finishes();
    rtd_service_control_tick();
    TEST_ASSERT_TRUE(rtd_service_converting());
    TEST_ASSERT_EQUAL_HEX8(MAX31865_CONFIG_CONVERTING, config_reg());
}

/* One conversion: DRDY falls, the service reads the word on this tick. */
static void conversion(uint16_t w)
{
    set_rtd_word(w);
    drdy.low = true;
    rtd_service_control_tick();
}

void test_rtd_config_words_are_4wire_60hz(void)
{
    /* Fault cycle 100X010Xb with conversions off; converting = bias + auto. D4 = 0 (4-wire,
     * modules.ato:2122), D0 = 0 (60 Hz notch, power-stage-120v DECISIONS.md:299). */
    TEST_ASSERT_EQUAL_HEX8(0x84u, MAX31865_CONFIG_FAULT_CYCLE);
    TEST_ASSERT_EQUAL_HEX8(0xC0u, MAX31865_CONFIG_CONVERTING);
    TEST_ASSERT_EQUAL_HEX8(0u, MAX31865_CONFIG_FAULT_CYCLE & MAX31865_CONFIG_CONVERSION_AUTO);
    TEST_ASSERT_EQUAL_HEX8(0u, MAX31865_CONFIG_CONVERTING & (MAX31865_CONFIG_3WIRE | MAX31865_CONFIG_FILTER_50HZ));
}

void test_rtd_service_startup_fault_cycle_then_conversions(void)
{
    TEST_ASSERT_EQUAL(HAL_OK, rtd_service_bootstrap());
    /* Thresholds then the startup fault cycle, conversions off. */
    TEST_ASSERT_EQUAL_HEX8(MAX31865_CONFIG_FAULT_CYCLE, config_reg());
    /* Not finished yet: wait, no state change, no word. */
    drdy.low = true; /* a DRDY low during the fault cycle is not a conversion */
    rtd_service_control_tick();
    TEST_ASSERT_FALSE(rtd_service_converting());
    TEST_ASSERT_FALSE(rtd_service_latest_word(NULL, NULL));
    TEST_ASSERT_EQUAL(STATE_INIT, state_machine_get_state());
    /* Finished, clean status: conversions start; the stale DRDY was released by a discard read. */
    mock_fault_cycle_finishes();
    rtd_service_control_tick();
    TEST_ASSERT_TRUE(rtd_service_converting());
    TEST_ASSERT_EQUAL_HEX8(MAX31865_CONFIG_CONVERTING, config_reg());
    TEST_ASSERT_FALSE(drdy.low);
    TEST_ASSERT_FALSE(rtd_service_latest_word(NULL, NULL));
    TEST_ASSERT_EQUAL(STATE_INIT, state_machine_get_state());
}

void test_rtd_service_startup_fault_cycle_reports_fault(void)
{
    TEST_ASSERT_EQUAL(HAL_OK, rtd_service_bootstrap());
    mock_spi_set_register(RTD_DEV, MAX31865_REG_FAULT_STATUS, MAX31865_FAULT_HIGH_THRESHOLD);
    mock_fault_cycle_finishes();
    rtd_service_control_tick();
    TEST_ASSERT_EQUAL(STATE_FAULT, state_machine_get_state());
    TEST_ASSERT_EQUAL(FAULT_PROBE_OPEN, state_machine_get_fault());
    TEST_ASSERT_FALSE(rtd_service_is_ready());
    TEST_ASSERT_FALSE(rtd_service_latest_word(NULL, NULL));
}

void test_rtd_service_fault_cycle_never_finishing_fails_closed(void)
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

void test_rtd_service_conversion_reads_word_and_releases_drdy(void)
{
    uint16_t word = 0u;
    uint8_t age = 0xFFu;

    bootstrap_to_converting();
    /* A stale expander snapshot reporting low is not a conversion. */
    set_rtd_word(0x2A3Cu);
    drdy.available = false;
    drdy.low = true;
    rtd_service_control_tick();
    TEST_ASSERT_FALSE(rtd_service_latest_word(&word, &age));
    drdy.available = true;
    rtd_service_control_tick();
    TEST_ASSERT_TRUE(rtd_service_latest_word(&word, &age));
    TEST_ASSERT_EQUAL_HEX16(0x2A3Cu, word);
    TEST_ASSERT_EQUAL_UINT8(0u, age);
    TEST_ASSERT_FALSE(drdy.low); /* the data read released DRDY */
    TEST_ASSERT_EQUAL(STATE_INIT, state_machine_get_state());
}

/* Schedule: conversions every 2 ticks (16.7 ms at 60 Hz vs the 10 ms tick). The periodic fault
 * cycle starts on the first conversion at or after RTD_FAULT_CYCLE_PERIOD_TICKS, pauses
 * conversions, and they resume once it finishes; the word never goes stale across the pause. */
void test_rtd_service_periodic_fault_cycle_schedule(void)
{
    unsigned t, started_at = 0u, cycles = 0u;

    bootstrap_to_converting();
    for (t = 1u; t <= 3u * RTD_FAULT_CYCLE_PERIOD_TICKS; t++) {
        if (rtd_service_converting()) {
            if (t % 2u == 0u) {
                set_rtd_word((uint16_t)(0x4000u + (t << 1)));
                drdy.low = true;
            }
            rtd_service_control_tick();
            if (!rtd_service_converting()) {
                /* A fault cycle started this tick: with conversions off. */
                TEST_ASSERT_EQUAL_HEX8(MAX31865_CONFIG_FAULT_CYCLE, config_reg());
                TEST_ASSERT_TRUE(t - started_at >= RTD_FAULT_CYCLE_PERIOD_TICKS);
                TEST_ASSERT_TRUE(t - started_at <= RTD_FAULT_CYCLE_PERIOD_TICKS + 2u);
                cycles++;
            }
        } else {
            /* In the fault cycle: a DRDY low is not consumed as a conversion. */
            drdy.low = true;
            mock_fault_cycle_finishes();
            rtd_service_control_tick();
            TEST_ASSERT_TRUE(rtd_service_converting());
            TEST_ASSERT_EQUAL_HEX8(MAX31865_CONFIG_CONVERTING, config_reg());
            started_at = t;
        }
        if (t > 2u) {
            uint8_t age = 0xFFu;
            TEST_ASSERT_TRUE(rtd_service_latest_word(NULL, &age));
            TEST_ASSERT_TRUE(age <= 3u);
        }
        TEST_ASSERT_EQUAL(STATE_INIT, state_machine_get_state());
    }
    /* 300 ticks: cycles start at t = 100 and t = 202 (first even tick >= 100 after a resume). */
    TEST_ASSERT_EQUAL_UINT32(2u, cycles);
}

/* Staleness: conversions stop. The word stays usable for RTD_DRDY_TIMEOUT_CONTROL_TICKS - 1 more
 * ticks, then the service fails closed and the word is gone (readers: +inf / NaN). */
void test_rtd_service_word_ages_out_when_conversions_stop(void)
{
    uint8_t tick, age = 0xFFu;

    bootstrap_to_converting();
    conversion(0x2A3Cu);
    TEST_ASSERT_TRUE(rtd_service_latest_word(NULL, &age));
    for (tick = 1u; tick < RTD_DRDY_TIMEOUT_CONTROL_TICKS; tick++) {
        rtd_service_control_tick();
        TEST_ASSERT_TRUE(rtd_service_latest_word(NULL, &age));
        TEST_ASSERT_EQUAL_UINT8(tick, age);
    }
    rtd_service_control_tick();
    TEST_ASSERT_FALSE(rtd_service_is_ready());
    TEST_ASSERT_FALSE(rtd_service_latest_word(NULL, &age));
    TEST_ASSERT_EQUAL(FAULT_PROBE_OPEN, state_machine_get_fault());
}

/* A threshold fault detected during a conversion: the word carries the fault bit, the latched
 * status is read and reported at once (short preferred), and the service ends. */
void test_rtd_service_fault_mid_conversion_reports_and_stops(void)
{
    bootstrap_to_converting();
    conversion(0x4000u);
    TEST_ASSERT_EQUAL(STATE_INIT, state_machine_get_state());
    mock_spi_set_register(RTD_DEV, MAX31865_REG_FAULT_STATUS, MAX31865_FAULT_LOW_THRESHOLD);
    conversion((uint16_t)(0x0010u | MAX31865_RTD_WORD_FAULT));
    TEST_ASSERT_EQUAL(STATE_FAULT, state_machine_get_state());
    TEST_ASSERT_EQUAL(FAULT_PROBE_SHORT, state_machine_get_fault());
    TEST_ASSERT_FALSE(rtd_service_is_ready());
    TEST_ASSERT_FALSE(rtd_service_latest_word(NULL, NULL));
    TEST_ASSERT_EQUAL_UINT32(1, mock_sm_get_trigger_shutdown_count());
    /* Terminal: later conversions do not report again. */
    conversion((uint16_t)(0x0010u | MAX31865_RTD_WORD_FAULT));
    TEST_ASSERT_EQUAL_UINT32(1, mock_sm_get_trigger_shutdown_count());
}

void test_rtd_service_fault_bit_with_clean_status_fails_closed_open(void)
{
    bootstrap_to_converting();
    conversion((uint16_t)(0x4000u | MAX31865_RTD_WORD_FAULT));
    TEST_ASSERT_EQUAL(STATE_FAULT, state_machine_get_state());
    TEST_ASSERT_EQUAL(FAULT_PROBE_OPEN, state_machine_get_fault());
}

void test_rtd_service_drdy_stuck_low_is_one_conversion(void)
{
    uint8_t tick;

    bootstrap_to_converting();
    drdy.release_on_read = false; /* DRDY never returns high */
    conversion(0x4000u);
    TEST_ASSERT_TRUE(rtd_service_latest_word(NULL, NULL));
    for (tick = 1u; tick < RTD_DRDY_TIMEOUT_CONTROL_TICKS; tick++) {
        rtd_service_control_tick();
        TEST_ASSERT_EQUAL(STATE_INIT, state_machine_get_state());
    }
    rtd_service_control_tick();
    TEST_ASSERT_EQUAL(STATE_FAULT, state_machine_get_state());
    TEST_ASSERT_EQUAL(FAULT_PROBE_OPEN, state_machine_get_fault());
}

void test_rtd_service_failed_data_read_invalidates_word(void)
{
    bootstrap_to_converting();
    conversion(0x4000u);
    TEST_ASSERT_TRUE(rtd_service_latest_word(NULL, NULL));
    mock_spi_fail_next_read(HAL_ERROR);
    conversion(0x4002u);
    TEST_ASSERT_FALSE(rtd_service_latest_word(NULL, NULL));
    TEST_ASSERT_TRUE(rtd_service_is_ready());
    TEST_ASSERT_EQUAL(STATE_INIT, state_machine_get_state());
}

void test_max31865_rref_matches_threshold_words(void)
{
    const float lsb = MAX31865_RREF_OHM / 32768.0f;

    TEST_ASSERT_FLOAT_WITHIN(lsb, RTD_SHORT_FAULT_OHM,
        max31865_rtd_word_to_ohm(MAX31865_LOW_THRESHOLD_WORD, MAX31865_RREF_OHM));
    TEST_ASSERT_FLOAT_WITHIN(lsb, RTD_OPEN_FAULT_OHM,
        max31865_rtd_word_to_ohm(MAX31865_HIGH_THRESHOLD_WORD, MAX31865_RREF_OHM));
}

void run_max31865_tests(void)
{
    RUN_TEST(test_max31865_init_writes_encoded_threshold_words_and_starts_async_cycle);
    RUN_TEST(test_max31865_high_threshold_fault_reaches_terminal_open_path);
    RUN_TEST(test_max31865_low_threshold_fault_reaches_terminal_short_path);
    RUN_TEST(test_max31865_non_threshold_fault_fails_closed_as_probe_open);
    RUN_TEST(test_max31865_restart_write_failure_fails_closed_as_probe_open);
    RUN_TEST(test_max31865_status_read_failure_fails_closed_as_probe_open);
    RUN_TEST(test_rtd_service_bootstrap_failure_fails_closed_from_control_task);
    RUN_TEST(test_rtd_service_requires_drdy_source);
    RUN_TEST(test_rtd_config_words_are_4wire_60hz);
    RUN_TEST(test_rtd_service_startup_fault_cycle_then_conversions);
    RUN_TEST(test_rtd_service_startup_fault_cycle_reports_fault);
    RUN_TEST(test_rtd_service_fault_cycle_never_finishing_fails_closed);
    RUN_TEST(test_rtd_service_conversion_reads_word_and_releases_drdy);
    RUN_TEST(test_rtd_service_periodic_fault_cycle_schedule);
    RUN_TEST(test_rtd_service_word_ages_out_when_conversions_stop);
    RUN_TEST(test_rtd_service_fault_mid_conversion_reports_and_stops);
    RUN_TEST(test_rtd_service_fault_bit_with_clean_status_fails_closed_open);
    RUN_TEST(test_rtd_service_drdy_stuck_low_is_one_conversion);
    RUN_TEST(test_rtd_service_failed_data_read_invalidates_word);
    RUN_TEST(test_max31865_rref_matches_threshold_words);
}
