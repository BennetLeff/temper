/**
 * @file test_max31865.c
 * @brief Host contract tests for MAX31865 threshold programming and faults.
 */

#include <math.h>

#include "unity/unity.h"

#include "../components/hal/include/hal.h"
#include "../components/hal/include/controller_pins.h"
#include "../components/sensors/include/max31865.h"
#include "../components/sensors/include/rtd_convert.h"
#include "../components/sensors/include/rtd_service.h"
#include "../config.h"
#include "../main/state_machine.h"

extern void mock_spi_reset(void);
extern void mock_spi_set_register(hal_spi_device_t device, uint8_t reg,
                                  uint8_t value);
extern uint8_t mock_spi_get_register(hal_spi_device_t device, uint8_t reg);
extern void mock_spi_fail_next_read(hal_status_t status);
extern void mock_spi_fail_next_write(hal_status_t status);
extern uint8_t mock_spi_previous_write(void);
extern bool mock_gpio_is_initialized(hal_pin_t pin);
extern void mock_timer_set_time(hal_time_us_t time_us);
extern void mock_timer_advance(hal_time_us_t delta_us);
extern void mock_sm_reset(void);
extern void mock_sm_set_pan_temperature(float temp);
extern void mock_sm_set_pan_sensor_failure(rtd_sensor_fail_t failure);
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
    mock_timer_set_time(1000u);
    rtd_service_set_drdy_source(fake_drdy_level, NULL);
}

void tearDown(void)
{
    (void)hal_deinit();
}

void test_max31865_init_writes_c46_threshold_words_and_bias_only(void)
{
    hal_spi_device_t spi_device = create_max31865_device();

    TEST_ASSERT_EQUAL(HAL_OK, max31865_initialize(&sensor, spi_device));

    TEST_ASSERT_EQUAL_HEX8(0x8A,
                           mock_spi_get_register(spi_device,
                                                 MAX31865_REG_HIGH_THRESHOLD_MSB));
    TEST_ASSERT_EQUAL_HEX8(0xD8,
                           mock_spi_get_register(spi_device,
                                                 MAX31865_REG_HIGH_THRESHOLD_MSB + 1u));
    TEST_ASSERT_EQUAL_HEX8(0x32,
                           mock_spi_get_register(spi_device,
                                                 MAX31865_REG_LOW_THRESHOLD_MSB));
    TEST_ASSERT_EQUAL_HEX8(0x2C,
                           mock_spi_get_register(spi_device,
                                                 MAX31865_REG_LOW_THRESHOLD_MSB + 1u));
    TEST_ASSERT_EQUAL_UINT16(35544u, MAX31865_HIGH_THRESHOLD_WORD);
    TEST_ASSERT_EQUAL_UINT16(12844u, MAX31865_LOW_THRESHOLD_WORD);
    /* VBIAS on, conversions off, no fault cycle and no fault clear (D1). */
    TEST_ASSERT_EQUAL_HEX8(0x80u,
                           mock_spi_get_register(spi_device,
                                                 MAX31865_REG_CONFIG));
}

void test_max31865_high_threshold_fault_reaches_terminal_open_path(void)
{
    hal_spi_device_t spi_device = create_max31865_device();
    TEST_ASSERT_EQUAL(HAL_OK, max31865_initialize(&sensor, spi_device));
    mock_spi_set_register(spi_device, MAX31865_REG_FAULT_STATUS,
                          MAX31865_FAULT_HIGH_THRESHOLD);

    TEST_ASSERT_EQUAL(HAL_OK, max31865_check_fault_status(&sensor, state_machine_report_rtd_device_fault, NULL, NULL));

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

    TEST_ASSERT_EQUAL(HAL_OK, max31865_check_fault_status(&sensor, state_machine_report_rtd_device_fault, NULL, NULL));

    TEST_ASSERT_EQUAL(STATE_FAULT, state_machine_get_state());
    TEST_ASSERT_EQUAL(FAULT_PROBE_SHORT, state_machine_get_fault());
    TEST_ASSERT_EQUAL_UINT32(1, mock_sm_get_trigger_shutdown_count());
}

void test_max31865_non_threshold_fault_fails_closed_as_probe_open(void)
{
    hal_spi_device_t spi_device = create_max31865_device();
    TEST_ASSERT_EQUAL(HAL_OK, max31865_initialize(&sensor, spi_device));
    mock_spi_set_register(spi_device, MAX31865_REG_FAULT_STATUS, 0x04u);

    TEST_ASSERT_EQUAL(HAL_OK, max31865_check_fault_status(&sensor, state_machine_report_rtd_device_fault, NULL, NULL));

    TEST_ASSERT_EQUAL(STATE_FAULT, state_machine_get_state());
    TEST_ASSERT_EQUAL(FAULT_PROBE_OPEN, state_machine_get_fault());
    TEST_ASSERT_EQUAL_UINT32(1, mock_sm_get_trigger_shutdown_count());
}

/* Data sheet manual cycle: 100X100Xb (step 1), then 100X110Xb (step 2). Writing step 2's code without
 * step 1 would run the automatic cycle, which is invalid behind the CR-1 filter (controller C37). */
void test_max31865_manual_cycle_config_words(void)
{
    hal_spi_device_t d = create_max31865_device();
    TEST_ASSERT_EQUAL(HAL_OK, max31865_initialize(&sensor, d));
    TEST_ASSERT_EQUAL(HAL_OK, max31865_manual_fault_step1(&sensor));
    TEST_ASSERT_EQUAL_HEX8(0x88u, mock_spi_get_register(d, MAX31865_REG_CONFIG));
    TEST_ASSERT_EQUAL(HAL_OK, max31865_manual_fault_step2(&sensor));
    TEST_ASSERT_EQUAL_HEX8(0x8Cu, mock_spi_get_register(d, MAX31865_REG_CONFIG));
}

void test_max31865_status_read_failure_fails_closed_as_probe_open(void)
{
    hal_spi_device_t spi_device = create_max31865_device();
    TEST_ASSERT_EQUAL(HAL_OK, max31865_initialize(&sensor, spi_device));
    mock_spi_fail_next_read(HAL_ERROR);

    TEST_ASSERT_EQUAL(HAL_ERROR, max31865_check_fault_status(&sensor, state_machine_report_rtd_device_fault, NULL, NULL));

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

/* ---------------------------------------------------------------- manual fault cycle, conversions */
#define RTD_DEV ((hal_spi_device_t)0)
#define CFG_BIAS  0x80u
#define CFG_STEP1 0x88u
#define CFG_STEP2 0x8Cu

static uint8_t config_reg(void) { return mock_spi_get_register(RTD_DEV, MAX31865_REG_CONFIG); }

static void tick_after(uint32_t us)
{
    mock_timer_advance(us);
    rtd_service_control_tick();
}
static void tick(void) { tick_after(10000u); }

/* The MAX31865 clears CONFIG D3:D2 once step 2 has finished. */
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

static void bootstrap_to_step2(void)
{
    TEST_ASSERT_EQUAL(HAL_OK, rtd_service_bootstrap());
    TEST_ASSERT_EQUAL_HEX8(CFG_BIAS, config_reg());
    tick();
    TEST_ASSERT_EQUAL_HEX8(CFG_STEP1, config_reg());
    tick();
    TEST_ASSERT_EQUAL_HEX8(CFG_STEP2, config_reg());
}

static void bootstrap_to_converting(void)
{
    bootstrap_to_step2();
    mock_fault_cycle_finishes();
    tick(); /* 07h read; restart wait running (12.5 ms from step 2) */
    TEST_ASSERT_FALSE(rtd_service_converting());
    tick();
    TEST_ASSERT_TRUE(rtd_service_converting());
    TEST_ASSERT_EQUAL_HEX8(MAX31865_CONFIG_CONVERTING, config_reg());
}

/* One conversion: DRDY falls, the service reads the word on this tick. */
static void conversion(uint16_t w)
{
    set_rtd_word(w);
    drdy.low = true;
    tick();
}

void test_rtd_config_words_are_4wire_60hz(void)
{
    TEST_ASSERT_EQUAL_HEX8(0x80u, MAX31865_CONFIG_BIAS_ON);
    TEST_ASSERT_EQUAL_HEX8(0x88u, MAX31865_CONFIG_MANUAL_STEP1);
    TEST_ASSERT_EQUAL_HEX8(0x8Cu, MAX31865_CONFIG_MANUAL_STEP2);
    TEST_ASSERT_EQUAL_HEX8(0xC0u, MAX31865_CONFIG_CONVERTING);
    TEST_ASSERT_EQUAL_HEX8(0u, MAX31865_CONFIG_CONVERTING & (MAX31865_CONFIG_3WIRE | MAX31865_CONFIG_FILTER_50HZ));
    /* sensor-r3 fault-cycle.json: tau_max 1009.9 us, worst 15-bit settle 5533 us. */
    TEST_ASSERT_TRUE(RTD_FAULT_CYCLE_STEP_US >= 5u * 1010u);
    TEST_ASSERT_TRUE(RTD_FAULT_CYCLE_RESTART_US >= 1000u + 2u * 5533u + 400u);
}

/* Every wait is measured on the microsecond clock: short ticks (jitter, a late first tick) never
 * advance the cycle early. */
void test_rtd_service_manual_cycle_waits_are_timed_not_counted(void)
{
    unsigned i;
    TEST_ASSERT_EQUAL(HAL_OK, rtd_service_bootstrap());
    tick_after(5000u);
    TEST_ASSERT_EQUAL_HEX8(CFG_BIAS, config_reg());
    tick_after(500u);                                   /* 5.5 ms since VBIAS */
    TEST_ASSERT_EQUAL_HEX8(CFG_STEP1, config_reg());
    tick_after(5000u);
    TEST_ASSERT_EQUAL_HEX8(CFG_STEP1, config_reg());
    tick_after(500u);                                   /* 5.5 ms since step 1 */
    TEST_ASSERT_EQUAL_HEX8(CFG_STEP2, config_reg());
    mock_fault_cycle_finishes();
    for (i = 0u; i < 6u; i++) {                         /* 12 ms since step 2 */
        tick_after(2000u);
        TEST_ASSERT_FALSE(rtd_service_converting());
    }
    tick_after(500u);                                   /* 12.5 ms */
    TEST_ASSERT_TRUE(rtd_service_converting());
}

void test_rtd_service_startup_cycle_then_conversions(void)
{
    bootstrap_to_step2();
    drdy.low = true; /* a DRDY low during the cycle is not a conversion */
    tick();          /* still busy */
    TEST_ASSERT_FALSE(rtd_service_converting());
    TEST_ASSERT_FALSE(rtd_service_latest_word(NULL, NULL));
    mock_fault_cycle_finishes();
    tick();
    TEST_ASSERT_TRUE(rtd_service_converting()); /* step 2 was > 12.5 ms ago */
    TEST_ASSERT_FALSE(drdy.low);                /* released by the discard read */
    TEST_ASSERT_FALSE(rtd_service_latest_word(NULL, NULL));
    TEST_ASSERT_EQUAL(STATE_INIT, state_machine_get_state());
}

void test_rtd_service_startup_fault_cycle_reports_fault(void)
{
    bootstrap_to_step2();
    mock_spi_set_register(RTD_DEV, MAX31865_REG_FAULT_STATUS, 0x28u); /* element open (D-FCYC) */
    mock_fault_cycle_finishes();
    tick();
    TEST_ASSERT_EQUAL(STATE_FAULT, state_machine_get_state());
    TEST_ASSERT_EQUAL(FAULT_PROBE_OPEN, state_machine_get_fault());
    TEST_ASSERT_FALSE(rtd_service_is_ready());
    TEST_ASSERT_FALSE(rtd_service_converting());
    TEST_ASSERT_FALSE(rtd_service_latest_word(NULL, NULL));
}

void test_rtd_service_fault_cycle_never_finishing_fails_closed(void)
{
    uint8_t n;
    bootstrap_to_step2();
    for (n = 0u; n < RTD_DRDY_TIMEOUT_CONTROL_TICKS - 1u; n++) {
        tick();
        TEST_ASSERT_EQUAL(STATE_INIT, state_machine_get_state());
    }
    tick();
    TEST_ASSERT_EQUAL(STATE_FAULT, state_machine_get_state());
    TEST_ASSERT_EQUAL(FAULT_PROBE_OPEN, state_machine_get_fault());
    TEST_ASSERT_EQUAL_UINT32(1, mock_sm_get_trigger_shutdown_count());
    TEST_ASSERT_FALSE(rtd_service_is_ready());
}

/* A stopped clock must not leave the sensor unmonitored. */
void test_rtd_service_stopped_clock_fails_closed(void)
{
    uint8_t n;
    TEST_ASSERT_EQUAL(HAL_OK, rtd_service_bootstrap());
    for (n = 0u; n < RTD_DRDY_TIMEOUT_CONTROL_TICKS; n++) tick_after(0u);
    TEST_ASSERT_EQUAL(FAULT_PROBE_OPEN, state_machine_get_fault());
    TEST_ASSERT_FALSE(rtd_service_is_ready());
}

/* A failed step-1 write must not be followed by step 2's code (it would run the automatic cycle). */
void test_rtd_service_failed_step_write_aborts(void)
{
    TEST_ASSERT_EQUAL(HAL_OK, rtd_service_bootstrap());
    mock_spi_fail_next_write(HAL_ERROR);
    tick();
    TEST_ASSERT_EQUAL(FAULT_PROBE_OPEN, state_machine_get_fault());
    tick();
    tick();
    TEST_ASSERT_EQUAL_HEX8(CFG_BIAS, config_reg());
}

void test_rtd_service_restart_write_failure_fails_closed(void)
{
    bootstrap_to_step2();
    mock_fault_cycle_finishes();
    tick();
    mock_spi_fail_next_write(HAL_ERROR);
    tick();
    TEST_ASSERT_EQUAL(FAULT_PROBE_OPEN, state_machine_get_fault());
    TEST_ASSERT_FALSE(rtd_service_converting());
}

/* No fault cycle runs while converting: it cannot fit the 100 ms word age (rtd_service.h). */
void test_rtd_service_no_cycle_while_converting(void)
{
    unsigned n;
    bootstrap_to_converting();
    for (n = 0u; n < 400u; n++) {
        if (n % 2u == 0u) { set_rtd_word((uint16_t)(0x4000u + (n << 1))); drdy.low = true; }
        tick();
        TEST_ASSERT_TRUE(rtd_service_converting());
        TEST_ASSERT_EQUAL_HEX8(MAX31865_CONFIG_CONVERTING, config_reg());
    }
    TEST_ASSERT_EQUAL(STATE_INIT, state_machine_get_state());
}

/* ---------------------------------------------------------------- startup before the control task */
/* The runaway boundary check latches on any tick without a pan temperature, so main.c runs the
 * service to its first reading before the control task starts. */
static struct { unsigned steps, word_at, fault_at; } boot;

static void boot_step(void *context)
{
    (void)context;
    boot.steps++;
    mock_timer_advance(10000u);
    if (config_reg() == CFG_STEP2) {
        mock_fault_cycle_finishes();
        if (boot.fault_at) mock_spi_set_register(RTD_DEV, MAX31865_REG_FAULT_STATUS, 0x28u);
    }
    if (rtd_service_converting() && boot.word_at && boot.steps >= boot.word_at) {
        set_rtd_word(0x4000u);
        drdy.low = true;
    } else {
        drdy.low = false;
    }
}

void test_rtd_startup_runs_to_first_word(void)
{
    boot.steps = 0u; boot.word_at = 10u; boot.fault_at = 0u;
    TEST_ASSERT_EQUAL(HAL_OK, rtd_service_bootstrap());
    TEST_ASSERT_TRUE(rtd_service_startup(boot_step, NULL));
    TEST_ASSERT_TRUE(rtd_service_latest_word(NULL, NULL));
    TEST_ASSERT_EQUAL_UINT32(10u, boot.steps);
    TEST_ASSERT_EQUAL(STATE_INIT, state_machine_get_state());
}

/* Why startup exists: a state-machine tick without a reading is a latched probe fault. */
void test_state_machine_tick_without_reading_is_a_probe_fault(void)
{
    mock_sm_set_pan_temperature(NAN);
    mock_sm_set_pan_sensor_failure(RTD_SENSOR_FAIL_OPEN);
    state_machine_update();
    TEST_ASSERT_EQUAL(STATE_FAULT, state_machine_get_state());
    TEST_ASSERT_EQUAL(FAULT_PROBE_OPEN, state_machine_get_fault());
    state_machine_update(); /* and it does not escalate */
    TEST_ASSERT_EQUAL(STATE_FAULT, state_machine_get_state());
    TEST_ASSERT_EQUAL(FAULT_PROBE_OPEN, state_machine_get_fault());
}

void test_rtd_startup_reports_power_up_fault(void)
{
    boot.steps = 0u; boot.word_at = 10u; boot.fault_at = 1u;
    TEST_ASSERT_EQUAL(HAL_OK, rtd_service_bootstrap());
    TEST_ASSERT_FALSE(rtd_service_startup(boot_step, NULL));
    TEST_ASSERT_EQUAL(FAULT_PROBE_OPEN, state_machine_get_fault());
}

void test_rtd_startup_silent_converter_is_bounded(void)
{
    boot.steps = 0u; boot.word_at = 0u; boot.fault_at = 0u;
    TEST_ASSERT_EQUAL(HAL_OK, rtd_service_bootstrap());
    TEST_ASSERT_FALSE(rtd_service_startup(boot_step, NULL));
    TEST_ASSERT_EQUAL(FAULT_PROBE_OPEN, state_machine_get_fault());
    TEST_ASSERT_TRUE(boot.steps <= RTD_STARTUP_MAX_TICKS);
    TEST_ASSERT_TRUE(RTD_STARTUP_MAX_TICKS * 10u < 1000u); /* inside the TPS3823's 1.6 s */
}

void test_rtd_startup_failed_bootstrap_reports(void)
{
    boot.steps = 0u; boot.word_at = 0u; boot.fault_at = 0u;
    rtd_service_set_drdy_source(NULL, NULL);
    TEST_ASSERT_EQUAL(HAL_ERROR_NOT_READY, rtd_service_bootstrap());
    TEST_ASSERT_FALSE(rtd_service_startup(boot_step, NULL));
    TEST_ASSERT_EQUAL(FAULT_PROBE_OPEN, state_machine_get_fault());
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

/* A threshold fault during a conversion is reported (short preferred) and the converter keeps
 * running, so a reset can verify the probe. The latched code stays the first one. */
void test_rtd_service_fault_mid_conversion_reports_and_keeps_converting(void)
{
    bootstrap_to_converting();
    conversion(0x4000u);
    TEST_ASSERT_EQUAL(STATE_INIT, state_machine_get_state());
    mock_spi_set_register(RTD_DEV, MAX31865_REG_FAULT_STATUS, MAX31865_FAULT_LOW_THRESHOLD);
    conversion((uint16_t)(0x0010u | MAX31865_RTD_WORD_FAULT));
    TEST_ASSERT_EQUAL(STATE_FAULT, state_machine_get_state());
    TEST_ASSERT_EQUAL(FAULT_PROBE_SHORT, state_machine_get_fault());
    TEST_ASSERT_TRUE(rtd_service_is_ready());
    TEST_ASSERT_EQUAL_UINT32(1, mock_sm_get_trigger_shutdown_count());
    mock_spi_set_register(RTD_DEV, MAX31865_REG_FAULT_STATUS, MAX31865_FAULT_HIGH_THRESHOLD);
    conversion((uint16_t)(0xFFFEu | MAX31865_RTD_WORD_FAULT));
    TEST_ASSERT_EQUAL(FAULT_PROBE_SHORT, state_machine_get_fault());
    TEST_ASSERT_EQUAL_UINT32(2, mock_sm_get_trigger_shutdown_count()); /* the cut is re-asserted */
}

/* Short bits: RTD low, REFIN- low and RTDIN- low (sensor-r3 D-SM). */
void test_rtd_service_input_low_bits_are_short(void)
{
    bootstrap_to_converting();
    mock_spi_set_register(RTD_DEV, MAX31865_REG_FAULT_STATUS, 0x08u);
    conversion((uint16_t)(0x4000u | MAX31865_RTD_WORD_FAULT));
    TEST_ASSERT_EQUAL(FAULT_PROBE_SHORT, state_machine_get_fault());
}

/* ---------------------------------------------------------------- samples */
void test_rtd_service_sample_is_converted_with_cr7(void)
{
    rtd_sample_t s;
    bootstrap_to_converting();
    TEST_ASSERT_FALSE(rtd_service_latest_sample(&s));
    conversion(0x4000u);  /* code 8192 = 107.5 ohm measured */
    TEST_ASSERT_TRUE(rtd_service_latest_sample(&s));
    TEST_ASSERT_EQUAL_UINT16(8192u, s.code);
    TEST_ASSERT_FLOAT_WITHIN(0.002f, 107.4486f, s.r_ohm); /* - (7.86e-4 x 107.5 - 0.0331) */
    TEST_ASSERT_FLOAT_WITHIN(0.02f, 19.11f - 0.061f, s.t_c);
    TEST_ASSERT_EQUAL_UINT32(1u, s.seq);
    TEST_ASSERT_TRUE(s.spi_ok);
    TEST_ASSERT_EQUAL_HEX8(0u, s.fault_status);
    conversion(0x4002u);
    TEST_ASSERT_TRUE(rtd_service_latest_sample(&s));
    TEST_ASSERT_EQUAL_UINT32(2u, s.seq);
}

/* The flagged sample keeps its code and status: a real over-temperature above 360 degC must stay a
 * temperature (D-OPEN), while an open element (full scale) is a failure. */
void test_rtd_service_flagged_sample_keeps_code_and_status(void)
{
    rtd_sample_t s;
    bootstrap_to_converting();
    mock_spi_set_register(RTD_DEV, MAX31865_REG_FAULT_STATUS, MAX31865_FAULT_HIGH_THRESHOLD);
    conversion((uint16_t)((18200u << 1) | MAX31865_RTD_WORD_FAULT)); /* about 375 degC */
    TEST_ASSERT_TRUE(rtd_service_latest_sample(&s));
    TEST_ASSERT_EQUAL_UINT16(18200u, s.code);
    TEST_ASSERT_EQUAL_HEX8(MAX31865_FAULT_HIGH_THRESHOLD, s.fault_status);
    TEST_ASSERT_TRUE(s.t_c > 360.0f && s.t_c < 390.0f);
    TEST_ASSERT_EQUAL(RTD_SENSOR_OK, rtd_convert_classify_failure(s.code, s.fault_status));
    conversion((uint16_t)((32767u << 1) | MAX31865_RTD_WORD_FAULT));
    TEST_ASSERT_TRUE(rtd_service_latest_sample(&s));
    TEST_ASSERT_EQUAL(RTD_SENSOR_FAIL_OPEN, rtd_convert_classify_failure(s.code, s.fault_status));
}

void test_rtd_service_frozen_code_is_adc_stuck(void)
{
    unsigned n;
    bootstrap_to_converting();
    for (n = 1u; n < RTD_FROZEN_CONVERSIONS; n++) {
        conversion(0x4000u);
        TEST_ASSERT_EQUAL(STATE_INIT, state_machine_get_state());
    }
    conversion(0x4000u);
    TEST_ASSERT_EQUAL(FAULT_ADC_STUCK, state_machine_get_fault());
    TEST_ASSERT_FALSE(rtd_service_is_ready());
}

/* ---------------------------------------------------------------- reset verification (D-RESET) */
static void flag_and_heal(void)
{
    bootstrap_to_converting();
    mock_spi_set_register(RTD_DEV, MAX31865_REG_FAULT_STATUS, MAX31865_FAULT_HIGH_THRESHOLD);
    conversion((uint16_t)((32767u << 1) | MAX31865_RTD_WORD_FAULT));
    mock_spi_set_register(RTD_DEV, MAX31865_REG_FAULT_STATUS, 0u);
    conversion(0x4000u);
}

/* From the request to the restart: 0x82 (clears 07h), step 1, step 2, 07h, 0xC0. */
static void run_verification(uint8_t cycle_status)
{
    TEST_ASSERT_FALSE(rtd_service_fault_status_clean());
    tick();
    TEST_ASSERT_EQUAL_HEX8(CFG_STEP1, config_reg());
    TEST_ASSERT_EQUAL_HEX8(0x82u, mock_spi_previous_write()); /* 07h cleared, conversions off */
    tick();
    TEST_ASSERT_EQUAL_HEX8(CFG_STEP2, config_reg());
    mock_spi_set_register(RTD_DEV, MAX31865_REG_FAULT_STATUS, cycle_status);
    mock_fault_cycle_finishes();
    tick();
    tick();
    TEST_ASSERT_TRUE(rtd_service_converting());
    TEST_ASSERT_FALSE(rtd_service_fault_status_clean()); /* no conversion since the cycle */
}

void test_rtd_reset_needs_a_clean_cycle_and_a_clean_conversion(void)
{
    flag_and_heal();
    run_verification(0u);
    conversion(0x4002u);
    TEST_ASSERT_TRUE(rtd_service_fault_status_clean());
    TEST_ASSERT_FALSE(rtd_service_fault_status_clean()); /* used once */
}

/* RTDIN- shorted to ground converts inside the window: only the cycle sees it. */
void test_rtd_reset_refused_by_a_flagged_cycle(void)
{
    flag_and_heal();
    TEST_ASSERT_FALSE(rtd_service_fault_status_clean());
    tick();
    tick();
    mock_spi_set_register(RTD_DEV, MAX31865_REG_FAULT_STATUS, 0x08u);
    mock_fault_cycle_finishes();
    tick();
    tick();
    TEST_ASSERT_TRUE(rtd_service_converting()); /* not terminal after power-up */
    mock_spi_set_register(RTD_DEV, MAX31865_REG_FAULT_STATUS, 0u);
    conversion(0x4002u);
    TEST_ASSERT_FALSE(rtd_service_fault_status_clean());
    TEST_ASSERT_EQUAL(FAULT_PROBE_OPEN, state_machine_get_fault()); /* first code kept */
}

void test_rtd_reset_refused_by_a_flagged_conversion_after_the_cycle(void)
{
    flag_and_heal();
    run_verification(0u);
    mock_spi_set_register(RTD_DEV, MAX31865_REG_FAULT_STATUS, MAX31865_FAULT_LOW_THRESHOLD);
    conversion((uint16_t)(0x0010u | MAX31865_RTD_WORD_FAULT));
    mock_spi_set_register(RTD_DEV, MAX31865_REG_FAULT_STATUS, 0u);
    conversion(0x4002u);
    TEST_ASSERT_FALSE(rtd_service_fault_status_clean());
}

void test_rtd_reset_refused_after_a_power_up_fault(void)
{
    bootstrap_to_step2();
    mock_spi_set_register(RTD_DEV, MAX31865_REG_FAULT_STATUS, 0x28u);
    mock_fault_cycle_finishes();
    tick();
    mock_spi_set_register(RTD_DEV, MAX31865_REG_FAULT_STATUS, 0u);
    tick();
    TEST_ASSERT_FALSE(rtd_service_fault_status_clean());
    tick();
    TEST_ASSERT_FALSE(rtd_service_fault_status_clean());
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
    RUN_TEST(test_max31865_init_writes_c46_threshold_words_and_bias_only);
    RUN_TEST(test_max31865_high_threshold_fault_reaches_terminal_open_path);
    RUN_TEST(test_max31865_low_threshold_fault_reaches_terminal_short_path);
    RUN_TEST(test_max31865_non_threshold_fault_fails_closed_as_probe_open);
    RUN_TEST(test_max31865_manual_cycle_config_words);
    RUN_TEST(test_max31865_status_read_failure_fails_closed_as_probe_open);
    RUN_TEST(test_rtd_service_bootstrap_failure_fails_closed_from_control_task);
    RUN_TEST(test_rtd_service_requires_drdy_source);
    RUN_TEST(test_rtd_config_words_are_4wire_60hz);
    RUN_TEST(test_rtd_service_manual_cycle_waits_are_timed_not_counted);
    RUN_TEST(test_rtd_service_startup_cycle_then_conversions);
    RUN_TEST(test_rtd_service_startup_fault_cycle_reports_fault);
    RUN_TEST(test_rtd_service_fault_cycle_never_finishing_fails_closed);
    RUN_TEST(test_rtd_service_stopped_clock_fails_closed);
    RUN_TEST(test_rtd_service_failed_step_write_aborts);
    RUN_TEST(test_rtd_service_restart_write_failure_fails_closed);
    RUN_TEST(test_rtd_service_no_cycle_while_converting);
    RUN_TEST(test_rtd_startup_runs_to_first_word);
    RUN_TEST(test_state_machine_tick_without_reading_is_a_probe_fault);
    RUN_TEST(test_rtd_startup_reports_power_up_fault);
    RUN_TEST(test_rtd_startup_silent_converter_is_bounded);
    RUN_TEST(test_rtd_startup_failed_bootstrap_reports);
    RUN_TEST(test_rtd_service_conversion_reads_word_and_releases_drdy);
    RUN_TEST(test_rtd_service_word_ages_out_when_conversions_stop);
    RUN_TEST(test_rtd_service_fault_mid_conversion_reports_and_keeps_converting);
    RUN_TEST(test_rtd_service_input_low_bits_are_short);
    RUN_TEST(test_rtd_service_sample_is_converted_with_cr7);
    RUN_TEST(test_rtd_service_flagged_sample_keeps_code_and_status);
    RUN_TEST(test_rtd_service_frozen_code_is_adc_stuck);
    RUN_TEST(test_rtd_reset_needs_a_clean_cycle_and_a_clean_conversion);
    RUN_TEST(test_rtd_reset_refused_by_a_flagged_cycle);
    RUN_TEST(test_rtd_reset_refused_by_a_flagged_conversion_after_the_cycle);
    RUN_TEST(test_rtd_reset_refused_after_a_power_up_fault);
    RUN_TEST(test_rtd_service_fault_bit_with_clean_status_fails_closed_open);
    RUN_TEST(test_rtd_service_drdy_stuck_low_is_one_conversion);
    RUN_TEST(test_rtd_service_failed_data_read_invalidates_word);
    RUN_TEST(test_max31865_rref_matches_threshold_words);
}
