/**
 * @file test_c1_rtd_service.c
 * @brief TEMPER_PAN_CONTROL_C1 MAX31865 service (CR-7, rtd_service.c) on the
 *        zapote CR-1 board: C1 thresholds, the MANUAL fault-detection cycle at
 *        power-up and before a probe-fault reset (DECISIONS.md D-FCYC),
 *        continuous conversion, fault flag, DRDY-stale and frozen-code faults,
 *        and the MCP3202 rail reading on the shared bus (D-RAIL), through the
 *        SPI mock's MAX31865 analog model (mock_max31865.c, settling from
 *        fault_cycle.py) and the real state machine.
 */

#include <math.h>

#include "unity/unity.h"

#include "../components/temper_hal/include/hal.h"
#include "../components/temper_hal/include/temper_pins.h"
#include "../components/temper_hal/mock/mock_max31865.h"
#include "../components/sensors/include/max31865.h"
#include "../components/sensors/include/rail_adc.h"
#include "../components/sensors/include/rim_ntc.h"
#include "../components/sensors/include/rtd_service.h"
#include "../components/sensors/include/tca9555.h"
#include "../config.h"
#include "../main/state_machine.h"

extern void mock_spi_reset(void);
extern void mock_spi_set_register(hal_spi_device_t device, uint8_t reg, uint8_t value);
extern uint8_t mock_spi_get_register(hal_spi_device_t device, uint8_t reg);
extern bool mock_spi_get_device_config(hal_spi_device_t device, hal_spi_config_t *out);
extern void mock_gpio_trigger_interrupt(hal_pin_t pin);
extern void mock_timer_reset(void);
extern void mock_timer_advance(hal_time_us_t delta_us);
extern void mock_sm_reset(void);
extern void mock_tca9555_install(void);
extern void mock_tca9555_set_fail(bool fail);
extern uint32_t mock_tca9555_reads(void);
extern uint8_t mock_tca9555_last_addr(void);

/* pan_control.c (linked through the C1 state machine) reads the rim NTC
 * through rim_ntc_board_hal(): a cold rim here (40 degC, ATTEN3 saturated). */
static bool rim_cold_node(void *ctx, rim_atten_t atten, float *mv)
{
    (void)ctx;
    (void)atten;
    *mv = 3236.0f;
    return true;
}
static const rim_ntc_hal_t s_rim_hal = {.read_node_mv = rim_cold_node, .read_v3v3_mv = NULL, .ctx = NULL};
const rim_ntc_hal_t *rim_ntc_board_hal(void) { return &s_rim_hal; }

#define DEV ((hal_spi_device_t)0)
#define RAIL_DEV ((hal_spi_device_t)1)
#define TICK_US 10000u

void setUp(void)
{
    hal_deinit();
    mock_spi_reset();
    mock_timer_reset();
    TEST_ASSERT_EQUAL(HAL_OK, hal_init_mock());
    mock_max31865_attach(0);
    mock_mcp3202_attach(1);
    rtd_service_set_drdy_source(RTD_DRDY_GPIO);
    tca9555_board_set_bus(NULL);
    mock_sm_reset();
    state_machine_init();
}

/* zapote/controller (D-DRDY): DRDY on TCA9555 P07, polled each control tick. */
static void use_expander_drdy(void)
{
    rtd_service_set_drdy_source(RTD_DRDY_EXPANDER);
    mock_tca9555_install();
    mock_max31865_set_drdy_expander(true);
}

void tearDown(void)
{
    (void)hal_deinit();
}

static void tick(void)
{
    mock_timer_advance(TICK_US);
    rtd_service_control_tick();
}

/* Power-up: bootstrap, then control ticks until the service starts converting. */
static void boot_to_converting(void)
{
    TEST_ASSERT_EQUAL(HAL_OK, rtd_service_bootstrap());
    for (int i = 0; i < 12 && !mock_max31865_converting(); i++) {
        tick();
    }
    TEST_ASSERT_TRUE(mock_max31865_converting());
}

static void convert(uint16_t code, bool fault_flag)
{
    const uint16_t word = (uint16_t)((code << 1) | (fault_flag ? 1u : 0u));
    mock_spi_set_register(DEV, MAX31865_REG_RTD_MSB, (uint8_t)(word >> 8));
    mock_spi_set_register(DEV, MAX31865_REG_RTD_MSB + 1u, (uint8_t)word);
    mock_max31865_drdy_assert();
    tick();
}

static uint16_t code_for(double r_ohm) { return (uint16_t)lround(r_ohm / 430.0 * 32768.0); }

/* n x 20 ms of a live sensor: a conversion every second tick, codes moving. */
static void live(int n)
{
    for (int i = 0; i < n; i++) {
        convert((uint16_t)(code_for(120.0) + (uint16_t)(i % 3)), false);
        tick();
    }
}

static void assert_no_automatic_cycle(void)
{
    TEST_ASSERT_EQUAL_UINT32(0u, mock_max31865_auto_cycles());
    TEST_ASSERT_EQUAL_UINT32(0u, mock_max31865_fast_steps());
    TEST_ASSERT_EQUAL_UINT32(0u, mock_max31865_early_restarts());
}

static void test_c1_bootstrap_programs_the_c1_window_without_a_fault_cycle(void)
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
    /* R(360 degC) = 233.2144 / R(-40 degC) = 84.27 ohm (CR-7), 15-bit code << 1:
     * within one code (0.0131 ohm) at or below the boundary */
    TEST_ASSERT_FLOAT_WITHIN(0.0066f, 233.2144f - 0.0066f,
                             (float)(MAX31865_C1_HIGH_THRESHOLD_WORD >> 1) / 32768.0f * 430.0f);
    TEST_ASSERT_FLOAT_WITHIN(0.02f, 84.27f, (float)(MAX31865_C1_LOW_THRESHOLD_WORD >> 1) / 32768.0f * 430.0f);
    /* VBIAS on, conversions off, 07h cleared (D1 self-clears): no cycle started */
    TEST_ASSERT_EQUAL_HEX8(MAX31865_CONFIG_VBIAS, mock_spi_get_register(DEV, MAX31865_REG_CONFIG));
    TEST_ASSERT_EQUAL_UINT32(0u, mock_max31865_auto_cycles());
    TEST_ASSERT_EQUAL_UINT32(0u, mock_max31865_manual_cycles());
}

/* D-FCYC: VBIAS-on, step 1, step 2 each >= 5.5 ms apart (measured, not
 * counted), 07h clean, the restart >= 11.5 ms after step 2, then 0xC0. */
static void test_c1_power_up_runs_the_manual_cycle_then_converts(void)
{
    TEST_ASSERT_EQUAL(HAL_OK, rtd_service_bootstrap());
    rtd_sample_t s;
    tick();   /* 10 ms after VBIAS-on: step 1 */
    TEST_ASSERT_EQUAL_HEX8(MAX31865_CONFIG_VBIAS | MAX31865_CONFIG_FAULT_CYCLE_MANUAL_1,
                           mock_spi_get_register(DEV, MAX31865_REG_CONFIG));
    TEST_ASSERT_FALSE(rtd_service_latest_sample(&s));
    tick();   /* step 2: the chip clears D3:D2 */
    TEST_ASSERT_EQUAL_UINT32(1u, mock_max31865_manual_cycles());
    TEST_ASSERT_EQUAL_HEX8(MAX31865_CONFIG_VBIAS, mock_spi_get_register(DEV, MAX31865_REG_CONFIG));
    tick();   /* D3:D2 = 00: 07h read clean */
    TEST_ASSERT_EQUAL_UINT32(1u, rtd_service_fault_cycles());
    TEST_ASSERT_EQUAL_HEX8(0u, rtd_service_last_fault_cycle_status());
    TEST_ASSERT_FALSE(mock_max31865_converting());   /* 10 ms < 11.5 ms + 1 ms after step 2 */
    tick();
    TEST_ASSERT_EQUAL_HEX8(MAX31865_CONFIG_VBIAS | MAX31865_CONFIG_AUTO_CONVERT,
                           mock_spi_get_register(DEV, MAX31865_REG_CONFIG));
    assert_no_automatic_cycle();
    convert(code_for(138.5055), false);
    TEST_ASSERT_TRUE(rtd_service_latest_sample(&s));
    TEST_ASSERT_TRUE(s.spi_ok);
    TEST_ASSERT_EQUAL_UINT8(0u, s.fault_status);
    /* CR-7 loading correction on (CR-1 fitted, C37): 138.5055 - (7.86e-4 R - 0.0331) */
    TEST_ASSERT_FLOAT_WITHIN(0.01f, 138.5055f - (7.86e-4f * 138.5055f - 0.0331f), s.r_ohm);
    TEST_ASSERT_EQUAL_INT(FAULT_NONE, state_machine_get_fault());
}

/* The model behind the evidence: on this filter a cycle run faster than the
 * input settles flags a healthy element, as does the automatic cycle; at the
 * board's waits it reads clean. */
static void test_manual_cycle_too_fast_or_automatic_flags_a_healthy_element(void)
{
    max31865_device_t d;
    TEST_ASSERT_EQUAL(HAL_OK, hal_spi->bus_init(0, &(hal_spi_config_t){.clock_hz = 500000u, .mode = 1u}));
    hal_spi_device_t h = NULL;
    TEST_ASSERT_EQUAL(HAL_OK, hal_spi->device_add(0, &(hal_spi_config_t){.clock_hz = 500000u, .mode = 1u}, &h));
    TEST_ASSERT_EQUAL(HAL_OK, max31865_attach(&d, h));
    uint8_t st = 0u;

    /* too fast: 0.5 ms between the steps (the healthy RTDIN- is still low) */
    TEST_ASSERT_EQUAL(HAL_OK, max31865_bias_on(&d));
    mock_timer_advance(RTD_C1_FAULT_CYCLE_STEP_US);
    TEST_ASSERT_EQUAL(HAL_OK, max31865_manual_fault_step1(&d));
    mock_timer_advance(500u);
    TEST_ASSERT_EQUAL(HAL_OK, max31865_manual_fault_step2(&d));
    TEST_ASSERT_EQUAL(HAL_OK, max31865_read_fault_status(&d, &st));
    TEST_ASSERT_EQUAL_HEX8(MAX31865_FAULT_REFIN_LOW | MAX31865_FAULT_RTDIN_LOW, st);
    TEST_ASSERT_EQUAL_UINT32(1u, mock_max31865_fast_steps());

    /* the board's waits: clean */
    mock_timer_advance(RTD_C1_FAULT_CYCLE_RESTART_US);
    TEST_ASSERT_EQUAL(HAL_OK, max31865_bias_on_clear(&d));
    mock_timer_advance(RTD_C1_FAULT_CYCLE_STEP_US);
    TEST_ASSERT_EQUAL(HAL_OK, max31865_manual_fault_step1(&d));
    mock_timer_advance(RTD_C1_FAULT_CYCLE_STEP_US);
    TEST_ASSERT_EQUAL(HAL_OK, max31865_manual_fault_step2(&d));
    TEST_ASSERT_EQUAL(HAL_OK, max31865_read_fault_status(&d, &st));
    TEST_ASSERT_EQUAL_HEX8(0u, st);
    TEST_ASSERT_EQUAL_UINT32(1u, mock_max31865_fast_steps());

    /* the automatic cycle's 100 us delays: a false D4/D3 on a healthy element */
    mock_timer_advance(RTD_C1_FAULT_CYCLE_RESTART_US);
    TEST_ASSERT_EQUAL(HAL_OK, max31865_bias_on_clear(&d));
    mock_timer_advance(20000u);
    TEST_ASSERT_EQUAL(HAL_OK, max31865_start_fault_detection(&d));
    TEST_ASSERT_EQUAL(HAL_OK, max31865_read_fault_status(&d, &st));
    TEST_ASSERT_EQUAL_HEX8(MAX31865_FAULT_REFIN_LOW | MAX31865_FAULT_RTDIN_LOW, st);
    TEST_ASSERT_EQUAL_UINT32(1u, mock_max31865_auto_cycles());

    /* step 2 without step 1 runs the automatic cycle (data sheet) */
    mock_timer_advance(RTD_C1_FAULT_CYCLE_RESTART_US);
    TEST_ASSERT_EQUAL(HAL_OK, max31865_bias_on_clear(&d));
    mock_timer_advance(20000u);
    TEST_ASSERT_EQUAL(HAL_OK, max31865_manual_fault_step2(&d));
    TEST_ASSERT_EQUAL_UINT32(2u, mock_max31865_auto_cycles());
}

static void boot_with_input(mock_max31865_input_t input)
{
    mock_max31865_set_input(input);
    TEST_ASSERT_EQUAL(HAL_OK, rtd_service_bootstrap());
    for (int i = 0; i < 6; i++) {
        tick();
    }
}

/* Open and shorted inputs at power-up: the manual cycle's bit, reported, and
 * the service stays down (D-RESET then refuses every reset). */
static void test_c1_power_up_cycle_detects_an_open_element(void)
{
    boot_with_input(MOCK_MAX31865_INPUT_ELEMENT_OPEN);
    /* D5: REFIN- at VBIAS with FORCE- closed (no current path). D3 depends on
     * how far the open S- side has charged (fault-cycle.json), so only D5 is
     * asserted. */
    TEST_ASSERT_BITS_HIGH(MAX31865_FAULT_REFIN_HIGH, rtd_service_last_fault_cycle_status());
    TEST_ASSERT_EQUAL_INT(STATE_FAULT, state_machine_get_state());
    TEST_ASSERT_EQUAL_INT(FAULT_PROBE_OPEN, state_machine_get_fault());
    TEST_ASSERT_FALSE(rtd_service_is_ready());
    TEST_ASSERT_FALSE(mock_max31865_converting());
    assert_no_automatic_cycle();
}

static void test_c1_power_up_cycle_detects_an_open_force_lead(void)
{
    boot_with_input(MOCK_MAX31865_INPUT_FORCE_N_OPEN);
    TEST_ASSERT_EQUAL_HEX8(MAX31865_FAULT_REFIN_HIGH, rtd_service_last_fault_cycle_status());
    TEST_ASSERT_EQUAL_INT(FAULT_PROBE_OPEN, state_machine_get_fault());
    TEST_ASSERT_FALSE(rtd_service_is_ready());
}

static void test_c1_power_up_cycle_detects_inputs_shorted_to_ground(void)
{
    boot_with_input(MOCK_MAX31865_INPUT_FORCE_P_TO_GND);
    TEST_ASSERT_EQUAL_HEX8(MAX31865_FAULT_REFIN_LOW | MAX31865_FAULT_RTDIN_LOW,
                           rtd_service_last_fault_cycle_status());
    TEST_ASSERT_EQUAL_INT(FAULT_PROBE_SHORT, state_machine_get_fault());
    TEST_ASSERT_FALSE(rtd_service_is_ready());

    setUp();
    boot_with_input(MOCK_MAX31865_INPUT_SENSE_N_TO_GND);
    TEST_ASSERT_EQUAL_HEX8(MAX31865_FAULT_REFIN_LOW | MAX31865_FAULT_RTDIN_LOW,
                           rtd_service_last_fault_cycle_status());
    TEST_ASSERT_EQUAL_INT(FAULT_PROBE_SHORT, state_machine_get_fault());
}

/* A cycle step that never finishes (D3:D2 stuck) fails open, bounded. */
static void test_c1_stuck_fault_cycle_fails_open(void)
{
    TEST_ASSERT_EQUAL(HAL_OK, rtd_service_bootstrap());
    tick();
    tick();   /* step 2 written; the chip has cleared D3:D2 ... */
    for (int i = 0; i < 30 && rtd_service_is_ready(); i++) {
        /* ... but a stuck chip reports the cycle running for ever */
        mock_spi_set_register(DEV, MAX31865_REG_CONFIG,
                              MAX31865_CONFIG_VBIAS | MAX31865_CONFIG_FAULT_CYCLE_MANUAL_2);
        tick();
    }
    TEST_ASSERT_FALSE(rtd_service_is_ready());
    TEST_ASSERT_EQUAL_INT(FAULT_PROBE_OPEN, state_machine_get_fault());
}

static void test_c1_conversion_fault_flag_reports_register_07h(void)
{
    boot_to_converting();
    mock_spi_set_register(DEV, MAX31865_REG_FAULT_STATUS, MAX31865_FAULT_HIGH_THRESHOLD);
    convert(0x7FFFu, true);
    TEST_ASSERT_EQUAL_INT(STATE_FAULT, state_machine_get_state());
    TEST_ASSERT_EQUAL_INT(FAULT_PROBE_OPEN, state_machine_get_fault());
}

static void test_c1_no_drdy_for_six_ticks_is_an_open_fault(void)
{
    boot_to_converting();
    convert(code_for(150.0), false);
    for (unsigned i = 0; i < RTD_C1_STALE_CONTROL_TICKS - 1u; i++) {
        tick();
        TEST_ASSERT_EQUAL_INT(FAULT_NONE, state_machine_get_fault());
    }
    tick();
    TEST_ASSERT_EQUAL_INT(STATE_FAULT, state_machine_get_state());
    TEST_ASSERT_EQUAL_INT(FAULT_PROBE_OPEN, state_machine_get_fault());
}

/* The first conversion after 0xC0 takes the single-conversion time (data
 * sheet Note 5, <= 55 ms at the 60 Hz notch): it gets 8 ticks, not 6. */
static void test_c1_first_conversion_gets_the_single_conversion_allowance(void)
{
    boot_to_converting();
    for (unsigned i = 0; i < RTD_C1_FIRST_DRDY_CONTROL_TICKS - 1u; i++) {
        tick();
        TEST_ASSERT_EQUAL_INT(FAULT_NONE, state_machine_get_fault());
    }
    tick();
    TEST_ASSERT_EQUAL_INT(FAULT_PROBE_OPEN, state_machine_get_fault());
}

static void test_c1_identical_codes_are_normal_until_the_frozen_limit(void)
{
    boot_to_converting();
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

/* D-OPEN + D-FCYC: register 07h latches until cleared, and a reset needs a
 * manual cycle (coil off) that reads 07h = 0 and a later clean conversion.
 * The verdict is used once. */
static void test_c1_reset_hook_runs_a_manual_cycle_then_needs_a_clean_conversion(void)
{
    boot_to_converting();
    convert(code_for(109.73), false);
    mock_spi_set_register(DEV, MAX31865_REG_FAULT_STATUS, MAX31865_FAULT_HIGH_THRESHOLD);
    convert(0x7FFFu, true);
    TEST_ASSERT_EQUAL_INT(FAULT_PROBE_OPEN, state_machine_get_fault());
    /* the element reconnects, but 07h is still latched: the flag stays set */
    convert(code_for(109.73), true);
    TEST_ASSERT_FALSE(rtd_service_fault_status_clean());   /* asks for a verification */
    tick();   /* 0x82 (clears 07h, stops conversions), then step 1 */
    TEST_ASSERT_EQUAL_HEX8(MAX31865_CONFIG_VBIAS | MAX31865_CONFIG_FAULT_CYCLE_MANUAL_1,
                           mock_spi_get_register(DEV, MAX31865_REG_CONFIG));
    TEST_ASSERT_EQUAL_HEX8(0u, mock_spi_get_register(DEV, MAX31865_REG_FAULT_STATUS));
    TEST_ASSERT_FALSE(rtd_service_fault_status_clean());
    for (int i = 0; i < 6 && !mock_max31865_converting(); i++) {
        tick();
    }
    TEST_ASSERT_TRUE(mock_max31865_converting());
    TEST_ASSERT_EQUAL_UINT32(2u, rtd_service_fault_cycles());
    TEST_ASSERT_EQUAL_UINT32(2u, mock_max31865_manual_cycles());
    /* no conversion since the cycle: still not clean */
    TEST_ASSERT_FALSE(rtd_service_fault_status_clean());
    convert(code_for(109.73), false);
    TEST_ASSERT_TRUE(rtd_service_fault_status_clean());
    /* used once: the next reset asks for a new cycle */
    TEST_ASSERT_FALSE(rtd_service_fault_status_clean());
    assert_no_automatic_cycle();
}

/* An input shorted to ground still converts inside the window (it reads high
 * by the lead and switch), so only the manual cycle sees it: the reset stays
 * refused and conversions resume. */
static void test_c1_reset_verification_finds_an_input_shorted_to_ground(void)
{
    boot_to_converting();
    mock_spi_set_register(DEV, MAX31865_REG_FAULT_STATUS, MAX31865_FAULT_HIGH_THRESHOLD);
    convert(0x7FFFu, true);
    TEST_ASSERT_EQUAL_INT(FAULT_PROBE_OPEN, state_machine_get_fault());
    mock_max31865_set_input(MOCK_MAX31865_INPUT_SENSE_N_TO_GND);
    convert(code_for(111.8), true);
    TEST_ASSERT_FALSE(rtd_service_fault_status_clean());
    for (int i = 0; i < 7 && !(rtd_service_fault_cycles() == 2u && mock_max31865_converting()); i++) {
        tick();
    }
    TEST_ASSERT_EQUAL_UINT32(2u, rtd_service_fault_cycles());
    TEST_ASSERT_EQUAL_HEX8(MAX31865_FAULT_REFIN_LOW | MAX31865_FAULT_RTDIN_LOW,
                           rtd_service_last_fault_cycle_status());
    TEST_ASSERT_TRUE(rtd_service_is_ready());
    TEST_ASSERT_TRUE(mock_max31865_converting());
    convert(code_for(111.8), true);   /* 07h holds the cycle's bits */
    TEST_ASSERT_FALSE(rtd_service_fault_status_clean());
    TEST_ASSERT_EQUAL_INT(FAULT_PROBE_OPEN, state_machine_get_fault());   /* first fault kept */
}

static void test_c1_reset_hook_stays_dirty_while_the_fault_persists(void)
{
    boot_to_converting();
    mock_spi_set_register(DEV, MAX31865_REG_FAULT_STATUS, MAX31865_FAULT_HIGH_THRESHOLD);
    convert(0x7FFFu, true);
    TEST_ASSERT_FALSE(rtd_service_fault_status_clean());
    for (int i = 0; i < 6 && !(rtd_service_fault_cycles() == 2u && mock_max31865_converting()); i++) {
        tick();
    }
    mock_spi_set_register(DEV, MAX31865_REG_FAULT_STATUS, MAX31865_FAULT_HIGH_THRESHOLD);
    convert(0x7FFFu, true);   /* still open: the chip flags it again */
    TEST_ASSERT_FALSE(rtd_service_fault_status_clean());
}

/* ---- D-RAIL: the MCP3202 on the shared bus ---- */

static void test_rail_decode_and_conversion(void)
{
    uint8_t tx[3];
    rail_adc_command(tx);
    TEST_ASSERT_EQUAL_HEX8(0x01u, tx[0]);
    TEST_ASSERT_EQUAL_HEX8(0xE0u, tx[1]);
    uint16_t code = 0u;
    const uint8_t rx[3] = {0xFFu, 0xEBu, 0xCDu};
    TEST_ASSERT_TRUE(rail_adc_decode(rx, &code));
    TEST_ASSERT_EQUAL_UINT16(0xBCDu, code);
    const uint8_t floating[3] = {0xFFu, 0xFFu, 0xFFu};
    TEST_ASSERT_FALSE(rail_adc_decode(floating, &code));
    /* 2.5 V on a 3.300 V reference: code floor(3103.03) = 3103 -> 3299.5 mV (centred) */
    TEST_ASSERT_FLOAT_WITHIN(0.6f, 3300.0f, rail_adc_code_to_v3v3_mv(3103.0f));
    TEST_ASSERT_FLOAT_WITHIN(0.6f, 3242.0f, rail_adc_code_to_v3v3_mv(floorf(4096.0f * 2500.0f / 3242.0f)));
}

static void test_rail_device_shares_the_bus_with_its_own_mode_clock_and_cs(void)
{
    boot_to_converting();
    hal_spi_config_t max_cfg, rail_cfg;
    TEST_ASSERT_TRUE(mock_spi_get_device_config(DEV, &max_cfg));
    TEST_ASSERT_TRUE(mock_spi_get_device_config(RAIL_DEV, &rail_cfg));
    TEST_ASSERT_EQUAL_UINT8(1u, max_cfg.mode);         /* MAX31865: CPHA 1 */
    TEST_ASSERT_EQUAL_UINT8(0u, rail_cfg.mode);        /* MCP3202: mode 0,0; CPOL 0 as the MAX */
    TEST_ASSERT_EQUAL_UINT32(500000u, rail_cfg.clock_hz);
    TEST_ASSERT_EQUAL_INT(PIN_SPI_CS_EXT_ADC, rail_cfg.pin_cs);
    TEST_ASSERT_EQUAL_INT(max_cfg.pin_sclk, rail_cfg.pin_sclk);
    TEST_ASSERT_FALSE(rail_cfg.cs_active_high);
}

static void test_rail_reading_feeds_the_seam_and_tracks_the_rail(void)
{
    boot_to_converting();
    float mv = 0.0f;
    TEST_ASSERT_TRUE(rail_adc_board_v3v3_mv(&mv));
    TEST_ASSERT_FLOAT_WITHIN(1.0f, 3300.0f, mv);
    mock_mcp3202_set_v3v3_mv(3242.0f);
    live(5);
    TEST_ASSERT_TRUE(rail_adc_board_v3v3_mv(&mv));
    TEST_ASSERT_FLOAT_WITHIN(1.0f, 3242.0f, mv);
    mock_mcp3202_set_v3v3_mv(3367.0f);
    live(5);
    TEST_ASSERT_TRUE(rail_adc_board_v3v3_mv(&mv));
    TEST_ASSERT_FLOAT_WITHIN(1.2f, 3367.0f, mv);
    TEST_ASSERT_EQUAL_INT(RAIL_ADC_MEASURED, rail_adc_board_state());
}

static void test_rail_unknown_states_fall_back_without_a_fault(void)
{
    boot_to_converting();
    float mv = 0.0f;
    /* LM4040 open: CH1 at the rail, code 4095 -> 2500 mV, outside the window */
    mock_mcp3202_set_ref_mv(3300.0f);
    live(5);
    TEST_ASSERT_EQUAL_INT(RAIL_ADC_UNKNOWN_RANGE, rail_adc_board_state());
    TEST_ASSERT_FALSE(rail_adc_board_v3v3_mv(&mv));
    /* converter absent: DOUT floats, the null bit is high */
    mock_mcp3202_set_ref_mv(2500.0f);
    mock_mcp3202_set_absent(true);
    live(5);
    TEST_ASSERT_EQUAL_INT(RAIL_ADC_UNKNOWN_SPI, rail_adc_board_state());
    /* a rail outside the widened contract is a broken measurement, not a rail */
    mock_mcp3202_set_absent(false);
    mock_mcp3202_set_v3v3_mv(3150.0f);
    live(5);
    TEST_ASSERT_EQUAL_INT(RAIL_ADC_UNKNOWN_RANGE, rail_adc_board_state());
    mock_mcp3202_set_v3v3_mv(3300.0f);
    live(5);
    TEST_ASSERT_EQUAL_INT(RAIL_ADC_MEASURED, rail_adc_board_state());
    /* no service for 1 s: stale */
    mock_timer_advance(RAIL_ADC_STALE_US + TICK_US);
    TEST_ASSERT_EQUAL_INT(RAIL_ADC_UNKNOWN_STALE, rail_adc_board_state());
    TEST_ASSERT_FALSE(rail_adc_board_v3v3_mv(&mv));
    /* none of it is a fault */
    TEST_ASSERT_EQUAL_INT(FAULT_NONE, state_machine_get_fault());
}

/* Arbitration: 5 s at the real cadence (a conversion every 20 ms, the rail
 * every 100 ms) with changing codes: every DRDY is consumed, the rail is read
 * 10 times a second, and neither the stale nor the frozen check trips. */
static void test_rail_and_rtd_share_the_bus_without_starving(void)
{
    boot_to_converting();
    rtd_sample_t s0, s1;
    convert(code_for(120.0), false);
    TEST_ASSERT_TRUE(rtd_service_latest_sample(&s0));
    const uint32_t xfer0 = mock_mcp3202_transfers();
    live(250);
    TEST_ASSERT_TRUE(rtd_service_latest_sample(&s1));
    TEST_ASSERT_EQUAL_UINT32(s0.seq + 250u, s1.seq);
    TEST_ASSERT_EQUAL_UINT32(50u * RAIL_ADC_SAMPLES, mock_mcp3202_transfers() - xfer0);
    TEST_ASSERT_EQUAL_INT(FAULT_NONE, state_machine_get_fault());
    TEST_ASSERT_TRUE(rtd_service_is_ready());
    TEST_ASSERT_EQUAL_INT(RAIL_ADC_MEASURED, rail_adc_board_state());
}

/* D-DRDY: the expander poll reads every conversion once (DRDY is a level the
 * RTD read returns high), at the board's expander address, and the C1 rules
 * see the same sequence as with the interrupt. */
static void test_expander_drdy_reads_each_conversion_once(void)
{
    use_expander_drdy();
    boot_to_converting();
    TEST_ASSERT_EQUAL_INT(RTD_DRDY_EXPANDER, rtd_service_drdy_source());
    rtd_sample_t s0, s1;
    convert(code_for(120.0), false);
    TEST_ASSERT_TRUE(rtd_service_latest_sample(&s0));
    TEST_ASSERT_TRUE(mock_max31865_drdy_high());   /* the read returned DRDY high */
    for (int i = 0; i < 4; i++) {
        tick();   /* no new conversion: the level stays high, nothing read */
    }
    TEST_ASSERT_TRUE(rtd_service_latest_sample(&s1));
    TEST_ASSERT_EQUAL_UINT32(s0.seq, s1.seq);
    live(20);
    TEST_ASSERT_TRUE(rtd_service_latest_sample(&s1));
    TEST_ASSERT_EQUAL_UINT32(s0.seq + 20u, s1.seq);
    TEST_ASSERT_EQUAL_HEX8(0x20u, mock_tca9555_last_addr());
    TEST_ASSERT_TRUE(mock_tca9555_reads() >= 24u);   /* one poll per control tick */
    TEST_ASSERT_EQUAL_INT(FAULT_NONE, state_machine_get_fault());
    assert_no_automatic_cycle();
}

/* A conversion left unread when the reset verification stops the converter
 * holds DRDY low through the cycle. The service reads the RTD registers before
 * the restart, so that level cannot pass for the first post-cycle conversion
 * and clear the reset (a level poll has no edge to tell them apart). */
static void test_expander_drdy_left_low_before_the_cycle_is_not_a_new_conversion(void)
{
    use_expander_drdy();
    boot_to_converting();
    mock_spi_set_register(DEV, MAX31865_REG_FAULT_STATUS, MAX31865_FAULT_HIGH_THRESHOLD);
    convert(0x7FFFu, true);
    TEST_ASSERT_EQUAL_INT(FAULT_PROBE_OPEN, state_machine_get_fault());
    TEST_ASSERT_FALSE(rtd_service_fault_status_clean());   /* request */
    /* a conversion completes just as the verification starts: unread */
    mock_spi_set_register(DEV, MAX31865_REG_RTD_MSB, (uint8_t)((code_for(109.73) << 1) >> 8));
    mock_spi_set_register(DEV, MAX31865_REG_RTD_MSB + 1u, (uint8_t)(code_for(109.73) << 1));
    mock_max31865_drdy_assert();
    tick();   /* the poll sees DRDY low, but the verification starts: 0x82, step 1 */
    TEST_ASSERT_FALSE(mock_max31865_converting());
    TEST_ASSERT_FALSE(mock_max31865_drdy_high());   /* still unread */
    for (int i = 0; i < 6 && !mock_max31865_converting(); i++) {
        tick();
    }
    TEST_ASSERT_TRUE(mock_max31865_converting());
    TEST_ASSERT_TRUE(mock_max31865_drdy_high());    /* read before the restart */
    rtd_sample_t a, b;
    TEST_ASSERT_TRUE(rtd_service_latest_sample(&a));
    tick();
    tick();
    TEST_ASSERT_TRUE(rtd_service_latest_sample(&b));
    TEST_ASSERT_EQUAL_UINT32(a.seq, b.seq);
    TEST_ASSERT_FALSE(rtd_service_fault_status_clean());
    convert(code_for(109.73), false);   /* the first real post-cycle conversion */
    TEST_ASSERT_TRUE(rtd_service_fault_status_clean());
}

/* A failed I2C read is no DRDY this tick: six in a row is the stale open
 * fault, as for a silent converter (D-STALE unchanged). */
static void test_expander_i2c_failure_is_stale_open(void)
{
    use_expander_drdy();
    boot_to_converting();
    live(5);
    mock_tca9555_set_fail(true);
    int n = 0;
    while (n < 20 && state_machine_get_fault() == FAULT_NONE) {
        mock_max31865_drdy_assert();   /* the converter runs; the bus does not answer */
        tick();
        n++;
    }
    /* live() ended one tick after its last conversion: 5 or 6 failed polls */
    TEST_ASSERT_TRUE(n >= (int)RTD_C1_STALE_CONTROL_TICKS - 1 && n <= (int)RTD_C1_STALE_CONTROL_TICKS);
    TEST_ASSERT_EQUAL_INT(FAULT_PROBE_OPEN, state_machine_get_fault());
    TEST_ASSERT_FALSE(rtd_service_is_ready());
    TEST_ASSERT_EQUAL_UINT32((uint32_t)n, rtd_service_drdy_poll_failures());
}

/* No expander answer at bootstrap: the service fails closed. */
static void test_expander_absent_at_bootstrap_fails_closed(void)
{
    use_expander_drdy();
    mock_tca9555_set_fail(true);
    TEST_ASSERT_NOT_EQUAL(HAL_OK, rtd_service_bootstrap());
    TEST_ASSERT_FALSE(rtd_service_is_ready());
    tick();
    TEST_ASSERT_EQUAL_INT(FAULT_PROBE_OPEN, state_machine_get_fault());
}

/* AUTO: a DRDY GPIO in the pin map keeps the interrupt (host); the target's
 * HAL_PIN_INVALID selects the expander. */
static void test_auto_drdy_source_follows_the_pin_map(void)
{
    rtd_service_set_drdy_source(RTD_DRDY_AUTO);
    mock_tca9555_install();
    TEST_ASSERT_EQUAL(HAL_OK, rtd_service_bootstrap());
    TEST_ASSERT_EQUAL_INT(PIN_RTD_DRDY != HAL_PIN_INVALID ? RTD_DRDY_GPIO : RTD_DRDY_EXPANDER,
                          rtd_service_drdy_source());
}

void run_c1_rtd_service_tests(void)
{
    RUN_TEST(test_c1_bootstrap_programs_the_c1_window_without_a_fault_cycle);
    RUN_TEST(test_c1_power_up_runs_the_manual_cycle_then_converts);
    RUN_TEST(test_manual_cycle_too_fast_or_automatic_flags_a_healthy_element);
    RUN_TEST(test_c1_power_up_cycle_detects_an_open_element);
    RUN_TEST(test_c1_power_up_cycle_detects_an_open_force_lead);
    RUN_TEST(test_c1_power_up_cycle_detects_inputs_shorted_to_ground);
    RUN_TEST(test_c1_stuck_fault_cycle_fails_open);
    RUN_TEST(test_c1_conversion_fault_flag_reports_register_07h);
    RUN_TEST(test_c1_no_drdy_for_six_ticks_is_an_open_fault);
    RUN_TEST(test_c1_first_conversion_gets_the_single_conversion_allowance);
    RUN_TEST(test_c1_identical_codes_are_normal_until_the_frozen_limit);
    RUN_TEST(test_c1_reset_hook_runs_a_manual_cycle_then_needs_a_clean_conversion);
    RUN_TEST(test_c1_reset_verification_finds_an_input_shorted_to_ground);
    RUN_TEST(test_c1_reset_hook_stays_dirty_while_the_fault_persists);
    RUN_TEST(test_rail_decode_and_conversion);
    RUN_TEST(test_rail_device_shares_the_bus_with_its_own_mode_clock_and_cs);
    RUN_TEST(test_rail_reading_feeds_the_seam_and_tracks_the_rail);
    RUN_TEST(test_rail_unknown_states_fall_back_without_a_fault);
    RUN_TEST(test_rail_and_rtd_share_the_bus_without_starving);
    RUN_TEST(test_expander_drdy_reads_each_conversion_once);
    RUN_TEST(test_expander_drdy_left_low_before_the_cycle_is_not_a_new_conversion);
    RUN_TEST(test_expander_i2c_failure_is_stale_open);
    RUN_TEST(test_expander_absent_at_bootstrap_fails_closed);
    RUN_TEST(test_auto_drdy_source_follows_the_pin_map);
}
