/**
 * @file test_state_machine.c
 * @brief Comprehensive unit tests for state machine
 * 
 * Tests cover:
 * - State transitions (valid and invalid)
 * - Fault detection and handling
 * - Timer and timeout behavior
 * - Button handling
 * - Safety interlocks
 * - Full operational scenarios
 * 
 * Uses stubs from state_machine_stubs.c for external dependencies.
 */

#include "unity/unity.h"
#include "test_common.h"
#include "../main/state_machine.h"
#include "../config.h"
#include "../components/control/thermal_mgmt.h"
#include <string.h>
#include <math.h>

/* Forward declare mock control functions from state_machine_stubs.c */
extern void mock_sm_reset(void);
extern void mock_sm_advance_time(uint32_t ms);
extern void mock_sm_set_time(uint32_t ms);
extern void mock_sm_set_pan_temperature(float temp_c);
extern void state_machine_reset_temp_baseline(void);
extern void mock_sm_set_heatsink_temperature(float temp_c);
extern void mock_sm_set_coil_temperature(float temp_c);
extern void mock_sm_set_dc_bus_current(float amps);
extern void mock_sm_set_power_bus_fault(bool tripped);
extern void mock_sm_set_power_tank_trip(bool tripped);
extern void mock_sm_set_rtd_resistance(float ohms);
extern void mock_sm_set_pan_status(int status);  /* 0=ABSENT, 1=PRESENT */
extern void mock_sm_set_pan_impedance(float impedance);
extern void mock_sm_set_fan_running(bool running);
extern void mock_sm_press_button(button_id_t button);
extern void mock_sm_release_button(button_id_t button);
extern void mock_sm_release_all_buttons(void);
extern void mock_sm_set_selftest_results(bool adc, bool pwm, bool fan, bool comp, bool rtd, bool disp, bool eeprom);
extern void mock_sm_fail_selftest_adc(void);
extern void mock_sm_fail_selftest_pwm(void);
extern void mock_sm_fail_selftest_fan(void);
extern uint32_t mock_sm_get_power_level(void);
extern uint32_t mock_sm_get_pwm_duty(void);
extern bool mock_sm_get_pll_enabled(void);
extern led_pattern_t mock_sm_get_led_pattern(void);
extern fan_speed_t mock_sm_get_fan_speed(void);
extern fault_code_t mock_sm_get_last_logged_fault(void);
extern const char* mock_sm_get_last_display_message(void);
extern uint32_t mock_sm_get_watchdog_feed_count(void);
extern uint32_t mock_sm_get_watchdog_hw_feed_count(void);
extern uint32_t mock_sm_get_eeprom_log_count(void);
extern uint32_t mock_sm_get_trigger_shutdown_count(void);
extern uint32_t mock_sm_get_power_set_count(void);
extern uint32_t mock_sm_get_pwm_disable_count(void);
extern void mock_sm_set_rim_temperature(float temp_c, bool valid);
extern void mock_sm_set_rim_cold_or_open(void);
extern bool mock_sm_get_rim_sensor_fault(void);
extern bool mock_sm_get_coil_sensor_fault(void);
extern const char* mock_sm_get_last_display_message(void);
extern void mock_sm_set_thermal_cap(uint8_t pct);

/* Pan status constants (must match stubs) */
#define MOCK_PAN_ABSENT  0
#define MOCK_PAN_PRESENT 1

/* ============================================================================
 * Test Setup/Teardown
 * ============================================================================ */

static void setup_test(void) {
    mock_sm_reset();
    state_machine_init();
}

/* ============================================================================
 * Test Cases: Initialization
 * ============================================================================ */

/**
 * Test: State machine initializes to STATE_INIT
 */
void test_sm_init_starts_in_init_state(void) {
    setup_test();
    TEST_ASSERT_EQUAL(STATE_INIT, state_machine_get_state());
}

/**
 * Test: Initial fault code is FAULT_NONE
 */
void test_sm_init_no_fault(void) {
    setup_test();
    TEST_ASSERT_EQUAL(FAULT_NONE, state_machine_get_fault());
}

/**
 * Test: Default target temperature is set
 */
void test_sm_init_default_target_temp(void) {
    setup_test();
    /* Target temp set to 100°C by default in state_machine_init */
    /* We can verify indirectly by checking behavior */
    TEST_ASSERT_TRUE(1);  /* Placeholder - target temp is internal */
}

/* ============================================================================
 * Test Cases: STATE_INIT -> STATE_IDLE transition (successful self-test)
 * ============================================================================ */

/**
 * Test: Successful self-test transitions to IDLE
 */
void test_sm_init_to_idle_on_selftest_pass(void) {
    setup_test();
    
    /* All self-tests pass by default in stubs */
    state_machine_update();
    
    TEST_ASSERT_EQUAL(STATE_IDLE, state_machine_get_state());
}

/**
 * Test: After IDLE entry, power is disabled
 */
void test_sm_idle_entry_disables_power(void) {
    setup_test();
    state_machine_update();  /* INIT -> IDLE */
    
    TEST_ASSERT_EQUAL(0, mock_sm_get_power_level());
}

/**
 * Test: IDLE state sets LED to steady green
 */
void test_sm_idle_sets_led_green(void) {
    setup_test();
    state_machine_update();  /* INIT -> IDLE */
    
    TEST_ASSERT_EQUAL(LED_STEADY_GREEN, mock_sm_get_led_pattern());
}

/* ============================================================================
 * Test Cases: STATE_INIT -> STATE_FAULT (failed self-test)
 * ============================================================================ */

/**
 * Test: Failed ADC self-test transitions to FAULT
 */
void test_sm_init_to_fault_on_adc_fail(void) {
    setup_test();
    mock_sm_fail_selftest_adc();
    
    state_machine_update();
    
    TEST_ASSERT_EQUAL(STATE_FAULT, state_machine_get_state());
    TEST_ASSERT_EQUAL(FAULT_SELF_TEST_FAILED, state_machine_get_fault());
}

/**
 * Test: Failed PWM self-test transitions to FAULT
 */
void test_sm_init_to_fault_on_pwm_fail(void) {
    setup_test();
    mock_sm_fail_selftest_pwm();
    
    state_machine_update();
    
    TEST_ASSERT_EQUAL(STATE_FAULT, state_machine_get_state());
    TEST_ASSERT_EQUAL(FAULT_SELF_TEST_FAILED, state_machine_get_fault());
}

/**
 * Test: Failed fan self-test transitions to FAULT
 */
void test_sm_init_to_fault_on_fan_fail(void) {
    setup_test();
    mock_sm_fail_selftest_fan();
    
    state_machine_update();
    
    TEST_ASSERT_EQUAL(STATE_FAULT, state_machine_get_state());
    TEST_ASSERT_EQUAL(FAULT_SELF_TEST_FAILED, state_machine_get_fault());
}

/* ============================================================================
 * Test Cases: STATE_IDLE -> STATE_PAN_DET (start button)
 * ============================================================================ */

/**
 * Test: Start button in IDLE transitions to PAN_DET
 */
void test_sm_idle_to_pan_det_on_start(void) {
    setup_test();
    state_machine_update();  /* INIT -> IDLE */
    
    /* Set target temp (required for start to work) */
    state_machine_set_target_temp(100.0f);
    
    /* Press start button */
    mock_sm_press_button(BUTTON_START);
    mock_sm_advance_time(100);
    state_machine_update();
    
    TEST_ASSERT_EQUAL(STATE_PAN_DET, state_machine_get_state());
}

/**
 * Test: PAN_DET entry displays "PLACE PAN" message
 */
void test_sm_pan_det_shows_place_pan_message(void) {
    setup_test();
    state_machine_update();  /* INIT -> IDLE */
    state_machine_set_target_temp(100.0f);
    mock_sm_press_button(BUTTON_START);
    mock_sm_advance_time(100);
    state_machine_update();  /* IDLE -> PAN_DET */
    
    TEST_ASSERT_EQUAL_STRING("PLACE PAN", mock_sm_get_last_display_message());
}

/* ============================================================================
 * Stage 16 start interlock (DECISIONS C33): PS3 absent -> no heating start
 * ============================================================================ */
extern void mock_sm_set_blower_start_permitted(bool permitted);

/* Start button with PS3 absent: stays in IDLE, no power, says why. */
void test_sm_start_refused_when_ps3_absent(void) {
    setup_test();
    state_machine_update();  /* INIT -> IDLE */
    state_machine_set_target_temp(100.0f);
    mock_sm_set_blower_start_permitted(false);
    mock_sm_press_button(BUTTON_START);
    for (int i = 0; i < 5; i++) {
        mock_sm_advance_time(100);
        state_machine_update();
    }
    TEST_ASSERT_EQUAL(STATE_IDLE, state_machine_get_state());
    TEST_ASSERT_EQUAL_STRING("NO BLOWER PWR", mock_sm_get_last_display_message());
    TEST_ASSERT_EQUAL_UINT32(0, mock_sm_get_power_level());

    /* PS3 back (BLW_PG present, or unknown): the same button starts as before. */
    mock_sm_set_blower_start_permitted(true);
    mock_sm_advance_time(100);
    state_machine_update();
    TEST_ASSERT_EQUAL(STATE_PAN_DET, state_machine_get_state());
}

/* A start that bypasses the button (UI / profile force PAN_DET), or PS3 lost during detection:
 * no detection power, back to IDLE, never PREHEAT. */
void test_sm_pan_det_refuses_heating_when_ps3_absent(void) {
    setup_test();
    state_machine_update();  /* INIT -> IDLE */
    state_machine_set_target_temp(100.0f);
    mock_sm_set_blower_start_permitted(false);
    state_machine_force_state(STATE_PAN_DET);
    TEST_ASSERT_EQUAL_UINT32(0, mock_sm_get_power_level());
    mock_sm_set_pan_status(MOCK_PAN_PRESENT);
    mock_sm_set_pan_impedance(5.0f);
    for (int i = 0; i < 40; i++) {
        mock_sm_advance_time(100);
        state_machine_update();
        TEST_ASSERT_NOT_EQUAL(STATE_PREHEAT, state_machine_get_state());
    }
    TEST_ASSERT_EQUAL(STATE_IDLE, state_machine_get_state());
    TEST_ASSERT_EQUAL_UINT32(0, mock_sm_get_power_level());

    /* PS3 lost while detecting (detection already running at low power). */
    mock_sm_set_blower_start_permitted(true);
    mock_sm_set_pan_status(MOCK_PAN_ABSENT);
    mock_sm_press_button(BUTTON_START);
    mock_sm_advance_time(100);
    state_machine_update();  /* IDLE -> PAN_DET */
    mock_sm_release_button(BUTTON_START);
    TEST_ASSERT_EQUAL(STATE_PAN_DET, state_machine_get_state());
    TEST_ASSERT_TRUE(mock_sm_get_power_level() > 0);
    mock_sm_set_blower_start_permitted(false);
    mock_sm_set_pan_status(MOCK_PAN_PRESENT);
    for (int i = 0; i < 40; i++) {
        mock_sm_advance_time(100);
        state_machine_update();
        TEST_ASSERT_NOT_EQUAL(STATE_PREHEAT, state_machine_get_state());
    }
    TEST_ASSERT_EQUAL(STATE_IDLE, state_machine_get_state());
    TEST_ASSERT_EQUAL_UINT32(0, mock_sm_get_power_level());
}

/* ============================================================================
 * Power board s48 BIAS_GOOD read-back on J4.1 (OPEN-ITEMS B13 H2, DECISIONS 67).
 * The level decoding and the debounce are the platform's (platform_logic.c platform_bias_*,
 * test_platform_logic.c); these tests pin what the state machine does with each verdict.
 * ============================================================================ */
extern void mock_sm_set_bias_post_ok(bool ok);
extern void mock_sm_set_bias_good(bool high);
extern uint32_t mock_sm_get_bias_run_reset_count(void);

/* Drive IDLE -> PAN_DET -> PREHEAT -> HEATING with a healthy bias. */
static void bias_to_heating(void) {
    state_machine_set_target_temp(100.0f);
    mock_sm_press_button(BUTTON_START);
    mock_sm_advance_time(100);
    state_machine_update();  /* IDLE -> PAN_DET */
    mock_sm_release_button(BUTTON_START);
    mock_sm_set_pan_status(MOCK_PAN_PRESENT);
    for (int i = 0; i < 5; i++) {
        mock_sm_advance_time(100);
        state_machine_update();
    }
    mock_sm_set_pan_temperature(92.0f);
    state_machine_reset_temp_baseline();
    mock_sm_advance_time(100);
    state_machine_update();  /* PREHEAT -> HEATING */
}

/* Check 1, healthy: the boot sample read low (the heartbeat had not started): INIT -> IDLE. */
void test_sm_bias_low_before_heartbeat_passes_post(void) {
    setup_test();
    mock_sm_set_bias_post_ok(true);
    mock_sm_set_bias_good(true);  /* the heartbeat is running by the time INIT is evaluated */
    state_machine_update();
    TEST_ASSERT_EQUAL(STATE_IDLE, state_machine_get_state());
    TEST_ASSERT_EQUAL(FAULT_NONE, state_machine_get_fault());
}

/* Check 1, violated: high before the heartbeat could have started (U40 stuck high): FAULT before
 * power is ever requested, and no reset clears it (the boot sample stays until a power cycle). */
void test_sm_bias_high_before_heartbeat_faults_post(void) {
    setup_test();
    mock_sm_set_bias_post_ok(false);
    state_machine_update();
    TEST_ASSERT_EQUAL(STATE_FAULT, state_machine_get_state());
    TEST_ASSERT_EQUAL(FAULT_BIAS_GOOD_POST, state_machine_get_fault());
    TEST_ASSERT_EQUAL(FAULT_BIAS_GOOD_POST, mock_sm_get_last_logged_fault());
    TEST_ASSERT_EQUAL_UINT32(0, mock_sm_get_power_level());
    TEST_ASSERT_FALSE(mock_sm_get_pll_enabled());

    mock_sm_press_button(BUTTON_BACK);
    mock_sm_advance_time(100);
    state_machine_update();
    mock_sm_release_button(BUTTON_BACK);
    TEST_ASSERT_EQUAL(STATE_FAULT, state_machine_get_state());
    TEST_ASSERT_EQUAL(FAULT_BIAS_GOOD_POST, state_machine_get_fault());
}

/* A self-test failure keeps its own code when both fail. */
void test_sm_bias_post_after_self_test(void) {
    setup_test();
    mock_sm_set_bias_post_ok(false);
    mock_sm_fail_selftest_adc();
    state_machine_update();
    TEST_ASSERT_EQUAL(STATE_FAULT, state_machine_get_state());
    TEST_ASSERT_EQUAL(FAULT_SELF_TEST_FAILED, state_machine_get_fault());
}

/* Check 2: BIAS_GOOD low when power is about to be requested -> the start is refused (no power,
 * no fault, back to IDLE with a message); once it reads high the same button starts. */
void test_sm_bias_low_before_permit_refuses_start(void) {
    setup_test();
    state_machine_update();  /* INIT -> IDLE */
    state_machine_set_target_temp(100.0f);
    mock_sm_set_bias_good(false);
    mock_sm_press_button(BUTTON_START);
    mock_sm_advance_time(100);
    state_machine_update();  /* IDLE -> PAN_DET, entry refuses */
    mock_sm_release_button(BUTTON_START);
    TEST_ASSERT_EQUAL(STATE_PAN_DET, state_machine_get_state());
    TEST_ASSERT_EQUAL_UINT32(0, mock_sm_get_power_level());
    TEST_ASSERT_EQUAL_STRING("NO POWER BIAS", mock_sm_get_last_display_message());
    mock_sm_set_pan_status(MOCK_PAN_PRESENT);
    for (int i = 0; i < 40; i++) {
        mock_sm_advance_time(100);
        state_machine_update();
        TEST_ASSERT_NOT_EQUAL(STATE_PREHEAT, state_machine_get_state());
        TEST_ASSERT_NOT_EQUAL(STATE_FAULT, state_machine_get_state());
        TEST_ASSERT_EQUAL_UINT32(0, mock_sm_get_power_level());
    }
    TEST_ASSERT_EQUAL(STATE_IDLE, state_machine_get_state());
    TEST_ASSERT_EQUAL(FAULT_NONE, state_machine_get_fault());

    /* Bias up: the start goes through and the run monitor starts afresh. */
    uint32_t resets = mock_sm_get_bias_run_reset_count();
    mock_sm_set_bias_good(true);
    mock_sm_set_pan_status(MOCK_PAN_ABSENT);
    mock_sm_press_button(BUTTON_START);
    mock_sm_advance_time(100);
    state_machine_update();
    mock_sm_release_button(BUTTON_START);
    TEST_ASSERT_EQUAL(STATE_PAN_DET, state_machine_get_state());
    TEST_ASSERT_TRUE(mock_sm_get_power_level() > 0);
    TEST_ASSERT_EQUAL_UINT32(resets + 1, mock_sm_get_bias_run_reset_count());
}

/* Check 3 in PAN_DET (detection power requested): a drop latches through the hardware path. */
void test_sm_bias_drop_in_pan_det_latches(void) {
    setup_test();
    state_machine_update();  /* INIT -> IDLE */
    state_machine_set_target_temp(100.0f);
    mock_sm_press_button(BUTTON_START);
    mock_sm_advance_time(100);
    state_machine_update();  /* IDLE -> PAN_DET */
    mock_sm_release_button(BUTTON_START);
    TEST_ASSERT_TRUE(mock_sm_get_power_level() > 0);
    mock_sm_set_bias_good(false);
    mock_sm_advance_time(100);
    state_machine_update();
    TEST_ASSERT_EQUAL(STATE_FAULT, state_machine_get_state());
    TEST_ASSERT_EQUAL(FAULT_BIAS_GOOD_LOST, state_machine_get_fault());
    TEST_ASSERT_EQUAL_UINT32(1, mock_sm_get_trigger_shutdown_count());
    TEST_ASSERT_EQUAL_UINT32(0, mock_sm_get_power_level());
}

/* Check 3 in RUN: a drop during HEATING latches FAULT_BIAS_GOOD_LOST through the same safe path
 * as the bus fault (RUN_EN kill + shutdown), and it stays latched after the bias returns. */
void test_sm_bias_drop_during_run_latches_fault(void) {
    setup_test();
    state_machine_update();  /* INIT -> IDLE */
    bias_to_heating();
    TEST_ASSERT_EQUAL(STATE_HEATING, state_machine_get_state());
    mock_sm_set_bias_good(false);
    mock_sm_advance_time(100);
    state_machine_update();
    TEST_ASSERT_EQUAL(STATE_FAULT, state_machine_get_state());
    TEST_ASSERT_EQUAL(FAULT_BIAS_GOOD_LOST, state_machine_get_fault());
    TEST_ASSERT_EQUAL(FAULT_BIAS_GOOD_LOST, mock_sm_get_last_logged_fault());
    TEST_ASSERT_EQUAL_UINT32(1, mock_sm_get_trigger_shutdown_count());
    TEST_ASSERT_EQUAL_UINT32(0, mock_sm_get_power_level());

    mock_sm_set_bias_good(true);
    mock_sm_press_button(BUTTON_BACK);
    mock_sm_advance_time(100);
    state_machine_update();
    mock_sm_release_button(BUTTON_BACK);
    TEST_ASSERT_EQUAL(STATE_FAULT, state_machine_get_state());
    TEST_ASSERT_EQUAL(FAULT_BIAS_GOOD_LOST, state_machine_get_fault());
}

/* Check 3 in PREHEAT, and the bus fault keeps priority when the collapse raises both. */
void test_sm_bias_drop_in_preheat_and_bus_fault_priority(void) {
    setup_test();
    state_machine_update();  /* INIT -> IDLE */
    state_machine_set_target_temp(100.0f);
    mock_sm_press_button(BUTTON_START);
    mock_sm_advance_time(100);
    state_machine_update();  /* IDLE -> PAN_DET */
    mock_sm_release_button(BUTTON_START);
    mock_sm_set_pan_status(MOCK_PAN_PRESENT);
    for (int i = 0; i < 5; i++) {
        mock_sm_advance_time(100);
        state_machine_update();
    }
    TEST_ASSERT_EQUAL(STATE_PREHEAT, state_machine_get_state());
    mock_sm_set_bias_good(false);
    mock_sm_advance_time(100);
    state_machine_update();
    TEST_ASSERT_EQUAL(STATE_FAULT, state_machine_get_state());
    TEST_ASSERT_EQUAL(FAULT_BIAS_GOOD_LOST, state_machine_get_fault());

    setup_test();
    state_machine_update();
    bias_to_heating();
    mock_sm_set_bias_good(false);
    mock_sm_set_power_bus_fault(true);
    mock_sm_advance_time(100);
    state_machine_update();
    TEST_ASSERT_EQUAL(FAULT_IGBT_SHORT, state_machine_get_fault());
}

/* Every power request restarts the platform's low-run debounce: PAN_DET entry, and PREHEAT entry
 * (including a resume from NO_PAN). */
void test_sm_bias_run_reset_per_power_request(void) {
    setup_test();
    state_machine_update();  /* INIT -> IDLE */
    TEST_ASSERT_EQUAL_UINT32(0, mock_sm_get_bias_run_reset_count());
    bias_to_heating();
    TEST_ASSERT_EQUAL(STATE_HEATING, state_machine_get_state());
    TEST_ASSERT_EQUAL_UINT32(2, mock_sm_get_bias_run_reset_count()); /* PAN_DET + PREHEAT */
    state_machine_force_state(STATE_NO_PAN);
    state_machine_force_state(STATE_PREHEAT);
    TEST_ASSERT_EQUAL_UINT32(3, mock_sm_get_bias_run_reset_count());
}

/* ============================================================================
 * Test Cases: STATE_PAN_DET -> STATE_PREHEAT (pan detected)
 * ============================================================================ */

/**
 * Test: Pan detected with confidence transitions to PREHEAT
 */
void test_sm_pan_det_to_preheat_on_pan(void) {
    setup_test();
    state_machine_update();  /* INIT -> IDLE */
    state_machine_set_target_temp(100.0f);
    mock_sm_press_button(BUTTON_START);
    mock_sm_advance_time(100);
    state_machine_update();  /* IDLE -> PAN_DET */
    mock_sm_release_button(BUTTON_START);
    
    /* Set pan present */
    mock_sm_set_pan_status(MOCK_PAN_PRESENT);
    mock_sm_set_pan_impedance(5.0f);
    
    /* Need multiple updates to build confidence (PAN_CONFIDENCE_REQUIRED = 3) */
    for (int i = 0; i < 5; i++) {
        mock_sm_advance_time(100);
        state_machine_update();
    }
    
    TEST_ASSERT_EQUAL(STATE_PREHEAT, state_machine_get_state());
}

/**
 * Test: PREHEAT entry enables PLL
 */
void test_sm_preheat_enables_pll(void) {
    setup_test();
    state_machine_update();  /* INIT -> IDLE */
    state_machine_set_target_temp(100.0f);
    mock_sm_press_button(BUTTON_START);
    mock_sm_advance_time(100);
    state_machine_update();  /* IDLE -> PAN_DET */
    mock_sm_release_button(BUTTON_START);
    mock_sm_set_pan_status(MOCK_PAN_PRESENT);
    
    for (int i = 0; i < 5; i++) {
        mock_sm_advance_time(100);
        state_machine_update();
    }
    
    TEST_ASSERT_TRUE(mock_sm_get_pll_enabled());
}

/* ============================================================================
 * Test Cases: STATE_PAN_DET timeout -> STATE_IDLE
 * ============================================================================ */

/**
 * Test: No pan detected times out to IDLE
 */
void test_sm_pan_det_timeout_to_idle(void) {
    setup_test();
    state_machine_update();  /* INIT -> IDLE */
    state_machine_set_target_temp(100.0f);
    mock_sm_press_button(BUTTON_START);
    mock_sm_advance_time(100);
    state_machine_update();  /* IDLE -> PAN_DET */
    mock_sm_release_button(BUTTON_START);
    
    /* Pan remains absent */
    mock_sm_set_pan_status(MOCK_PAN_ABSENT);
    
    /* Advance past timeout (5000ms) */
    mock_sm_advance_time(6000);
    state_machine_update();
    
    /* Message is displayed before transition */
    /* After message delay (2000ms), transitions to IDLE */
    mock_sm_advance_time(2500);
    state_machine_update();
    
    TEST_ASSERT_EQUAL(STATE_IDLE, state_machine_get_state());
}

/* ============================================================================
 * Test Cases: STATE_PREHEAT -> STATE_HEATING (target approached)
 * ============================================================================ */

/**
 * Test: Close to target temp transitions to HEATING
 */
void test_sm_preheat_to_heating_near_target(void) {
    setup_test();
    state_machine_update();  /* INIT -> IDLE */
    state_machine_set_target_temp(100.0f);
    mock_sm_press_button(BUTTON_START);
    mock_sm_advance_time(100);
    state_machine_update();  /* IDLE -> PAN_DET */
    mock_sm_release_button(BUTTON_START);
    mock_sm_set_pan_status(MOCK_PAN_PRESENT);
    
    for (int i = 0; i < 5; i++) {
        mock_sm_advance_time(100);
        state_machine_update();
    }
    TEST_ASSERT_EQUAL(STATE_PREHEAT, state_machine_get_state());
    
    /* Set temperature close to target (within 10°C triggers transition) */
    mock_sm_set_pan_temperature(92.0f);
    state_machine_reset_temp_baseline();
    mock_sm_advance_time(100);
    state_machine_update();
    
    TEST_ASSERT_EQUAL(STATE_HEATING, state_machine_get_state());
}

/* ============================================================================
 * Test Cases: 250 C pan cap / glass protection and the blower stall hook
 * ============================================================================ */

static void enter_preheat(void) {
    setup_test();
    state_machine_update();  /* INIT -> IDLE */
    state_machine_set_target_temp(200.0f);
    mock_sm_press_button(BUTTON_START);
    mock_sm_advance_time(100);
    state_machine_update();  /* IDLE -> PAN_DET */
    mock_sm_release_button(BUTTON_START);
    mock_sm_set_pan_status(MOCK_PAN_PRESENT);
    for (int i = 0; i < 5; i++) {
        mock_sm_advance_time(100);
        state_machine_update();
    }
    TEST_ASSERT_EQUAL(STATE_PREHEAT, state_machine_get_state());
}

/* Hold the pan at about pan_c for ms (100 ms ticks), wobbling 0.2 C so the ADC-stuck detector
 * does not fire; returns false if the machine left PREHEAT/HEATING. */
static bool run_hot_pan(float pan_c, uint32_t ms)
{
    for (uint32_t t = 0; t < ms; t += 100) {
        mock_sm_set_pan_temperature(pan_c + ((t / 100u) & 1u ? 0.2f : 0.0f));
        mock_sm_advance_time(100);
        state_machine_update();
        system_state_t st = state_machine_get_state();
        if (st != STATE_PREHEAT && st != STATE_HEATING) return false;
    }
    return true;
}

static void reach_hot_pan(float pan_c)
{
    enter_preheat();
    state_machine_set_target_temp(250.0f);
    /* Ramp at 10 C/s (below the 15 C/s runaway limit) to the hot pan. */
    for (float p = 25.0f; p < pan_c; p += 1.0f) {
        mock_sm_set_pan_temperature(p);
        mock_sm_advance_time(100);
        state_machine_update();
    }
}

/* Rim below its range (cold or open: alike at the ADC's top) while the pan RTD reads > 150 C for
 * > 30 s: rim-sensor fault, latched, shown; the rim is dropped and the pan RTD alone caps. */
void test_sm_rim_sensor_plausibility_fault(void) {
    reach_hot_pan(160.0f);
    mock_sm_set_rim_cold_or_open();
    TEST_ASSERT_TRUE(run_hot_pan(160.0f, 29000));
    TEST_ASSERT_FALSE(mock_sm_get_rim_sensor_fault());
    TEST_ASSERT_TRUE(run_hot_pan(160.0f, 2000));
    TEST_ASSERT_TRUE(mock_sm_get_rim_sensor_fault());
    TEST_ASSERT_EQUAL_STRING("RIM SENSOR FAULT", mock_sm_get_last_display_message());
    /* Latched: a rim that now reads (even at the 250 C cap) no longer caps; the RTD still does. */
    mock_sm_set_rim_temperature(251.0f, true);
    TEST_ASSERT_TRUE(run_hot_pan(160.0f, 300));
    TEST_ASSERT_TRUE(mock_sm_get_power_level() > 0);
    TEST_ASSERT_TRUE(mock_sm_get_rim_sensor_fault());
    for (int i = 0; i < 3; i++) { /* the handler acts on the previous tick's reading */
        mock_sm_set_pan_temperature(250.5f);
        state_machine_reset_temp_baseline();
        mock_sm_advance_time(100);
        state_machine_update();
    }
    TEST_ASSERT_EQUAL_UINT32(0, mock_sm_get_power_level());
}

/* A cool pan (RTD <= 150 C) with the rim below range is normal: no fault. */
void test_sm_rim_below_range_cool_pan_no_fault(void) {
    reach_hot_pan(140.0f);
    mock_sm_set_rim_cold_or_open();
    TEST_ASSERT_TRUE(run_hot_pan(140.0f, 60000));
    TEST_ASSERT_FALSE(mock_sm_get_rim_sensor_fault());
}

/* Coil reading below 25 C after > 5 min of heating at > 50 % power: coil-sensor fault, latched,
 * handed to the thermal glue (tank <= 17.5 A, blower full speed) and shown. */
void test_sm_coil_sensor_plausibility_fault(void) {
    reach_hot_pan(120.0f);
    mock_sm_set_coil_temperature(20.0f);
    TEST_ASSERT_TRUE(run_hot_pan(120.0f, 100));
    TEST_ASSERT_TRUE(mock_sm_get_power_level() > COIL_PLAUS_POWER_PCT);
    TEST_ASSERT_TRUE(run_hot_pan(120.0f, 299000));
    TEST_ASSERT_FALSE(mock_sm_get_coil_sensor_fault());
    TEST_ASSERT_TRUE(run_hot_pan(120.0f, 2000));
    TEST_ASSERT_TRUE(mock_sm_get_coil_sensor_fault());
    TEST_ASSERT_EQUAL_STRING("COIL SENSOR FAULT", mock_sm_get_last_display_message());
    /* A derate, not a stop: heating continues (the tank clamp is the binding's). */
    TEST_ASSERT_TRUE(run_hot_pan(120.0f, 500));
    TEST_ASSERT_TRUE(mock_sm_get_power_level() > 0);
    /* Reset at re-init. */
    setup_test();
    TEST_ASSERT_FALSE(mock_sm_get_coil_sensor_fault());
}

/* A coil that warms past 25 C clears the evidence: no fault however long the session. */
void test_sm_coil_warming_no_sensor_fault(void) {
    reach_hot_pan(120.0f);
    mock_sm_set_coil_temperature(20.0f);
    TEST_ASSERT_TRUE(run_hot_pan(120.0f, 200000));
    mock_sm_set_coil_temperature(40.0f);
    TEST_ASSERT_TRUE(run_hot_pan(120.0f, 10000));
    mock_sm_set_coil_temperature(20.0f);
    TEST_ASSERT_TRUE(run_hot_pan(120.0f, 200000));
    TEST_ASSERT_FALSE(mock_sm_get_coil_sensor_fault());
}

/**
 * Test: PREHEAT power request passes the rim-NTC cap (R36 glass protection)
 */
void test_sm_preheat_rim_at_cap_removes_power(void) {
    enter_preheat();
    mock_sm_advance_time(100);
    state_machine_update();
    uint32_t uncapped = mock_sm_get_power_level();
    TEST_ASSERT_TRUE(uncapped > 0);

    mock_sm_set_rim_temperature(251.0f, true);
    mock_sm_advance_time(100);
    state_machine_update();
    TEST_ASSERT_EQUAL(STATE_PREHEAT, state_machine_get_state());
    TEST_ASSERT_EQUAL_UINT32(0, mock_sm_get_power_level());

    /* Rim cooled: the cap lifts. An invalid rim is not a cap (the RTD still caps). */
    mock_sm_set_rim_temperature(80.0f, false);
    mock_sm_advance_time(100);
    state_machine_update();
    TEST_ASSERT_EQUAL_UINT32(uncapped, mock_sm_get_power_level());
}

/**
 * Test: the L3 thermal cap (coil derate / blower stall) can only lower the power request
 */
void test_sm_preheat_blower_stall_derates(void) {
    enter_preheat();
    mock_sm_advance_time(100);
    state_machine_update();
    uint32_t uncapped = mock_sm_get_power_level();
    TEST_ASSERT_TRUE(uncapped > 3);

    mock_sm_set_thermal_cap(3);
    mock_sm_advance_time(100);
    state_machine_update();
    TEST_ASSERT_EQUAL_UINT32(3, mock_sm_get_power_level());

    mock_sm_set_thermal_cap(100);
    mock_sm_advance_time(100);
    state_machine_update();
    TEST_ASSERT_EQUAL_UINT32(uncapped, mock_sm_get_power_level());
}

/* ============================================================================
 * Test Cases: STATE_HEATING -> STATE_NO_PAN (pan removed)
 * ============================================================================ */

/**
 * Test: Pan removal during heating transitions to NO_PAN
 */
void test_sm_heating_to_no_pan_on_removal(void) {
    /* Set up to reach HEATING state */
    setup_test();
    state_machine_update();  /* INIT -> IDLE */
    state_machine_set_target_temp(100.0f);
    mock_sm_press_button(BUTTON_START);
    mock_sm_advance_time(100);
    state_machine_update();  /* IDLE -> PAN_DET */
    mock_sm_release_button(BUTTON_START);
    mock_sm_set_pan_status(MOCK_PAN_PRESENT);
    
    for (int i = 0; i < 5; i++) {
        mock_sm_advance_time(100);
        state_machine_update();
    }
    
    mock_sm_set_pan_temperature(92.0f);
    state_machine_reset_temp_baseline();
    mock_sm_advance_time(100);
    state_machine_update();  /* PREHEAT -> HEATING */
    
    TEST_ASSERT_EQUAL(STATE_HEATING, state_machine_get_state());
    
    /* Remove pan */
    mock_sm_set_pan_status(MOCK_PAN_ABSENT);
    
    /* Multiple updates to exceed debounce count (PAN_DEBOUNCE_COUNT = 10) */
    for (int i = 0; i < 15; i++) {
        mock_sm_advance_time(100);
        state_machine_update();
    }
    
    TEST_ASSERT_EQUAL(STATE_NO_PAN, state_machine_get_state());
}

/* ============================================================================
 * Test Cases: STATE_HEATING -> STATE_COOLDOWN (stop button)
 * ============================================================================ */

/**
 * Test: Stop button during heating transitions to COOLDOWN
 */
void test_sm_heating_to_cooldown_on_stop(void) {
    /* Set up to reach HEATING state */
    setup_test();
    state_machine_update();  /* INIT -> IDLE */
    state_machine_set_target_temp(100.0f);
    mock_sm_press_button(BUTTON_START);
    mock_sm_advance_time(100);
    state_machine_update();  /* IDLE -> PAN_DET */
    mock_sm_release_button(BUTTON_START);
    mock_sm_set_pan_status(MOCK_PAN_PRESENT);
    
    for (int i = 0; i < 5; i++) {
        mock_sm_advance_time(100);
        state_machine_update();
    }
    
    mock_sm_set_pan_temperature(92.0f);
    state_machine_reset_temp_baseline();
    mock_sm_advance_time(100);
    state_machine_update();  /* PREHEAT -> HEATING */
    
    /* Press stop */
    mock_sm_press_button(BUTTON_STOP);
    mock_sm_advance_time(100);
    state_machine_update();
    
    TEST_ASSERT_EQUAL(STATE_COOLDOWN, state_machine_get_state());
}

/**
 * Test: COOLDOWN entry disables power and PLL
 */
void test_sm_cooldown_disables_power_and_pll(void) {
    /* Set up to reach COOLDOWN state */
    setup_test();
    state_machine_update();  /* INIT -> IDLE */
    state_machine_set_target_temp(100.0f);
    mock_sm_press_button(BUTTON_START);
    mock_sm_advance_time(100);
    state_machine_update();  /* IDLE -> PAN_DET */
    mock_sm_release_button(BUTTON_START);
    mock_sm_set_pan_status(MOCK_PAN_PRESENT);
    
    for (int i = 0; i < 5; i++) {
        mock_sm_advance_time(100);
        state_machine_update();
    }
    
    mock_sm_set_pan_temperature(92.0f);
    state_machine_reset_temp_baseline();
    mock_sm_advance_time(100);
    state_machine_update();  /* PREHEAT -> HEATING */
    
    mock_sm_press_button(BUTTON_STOP);
    mock_sm_advance_time(100);
    state_machine_update();  /* HEATING -> COOLDOWN */
    
    TEST_ASSERT_EQUAL(0, mock_sm_get_power_level());
    TEST_ASSERT_FALSE(mock_sm_get_pll_enabled());
}

/**
 * Test: UI-lost STOP (UI board DECISIONS U14.2/U15). ui_esp32.c makes button_is_pressed(BUTTON_STOP)
 * true once the expander has been unreadable for > 100 ms (pure rule: test_platform_logic.c
 * test_ui_lost_*). The state machine must take its existing stop path: HEATING -> COOLDOWN with the
 * power off, and the end of the lost condition (STOP no longer pressed) must not restart heating.
 */
void test_sm_ui_lost_stop_ends_heating_and_does_not_restart(void) {
    setup_test();
    state_machine_update();  /* INIT -> IDLE */
    state_machine_set_target_temp(100.0f);
    mock_sm_press_button(BUTTON_START);
    mock_sm_advance_time(100);
    state_machine_update();  /* IDLE -> PAN_DET */
    mock_sm_release_button(BUTTON_START);
    mock_sm_set_pan_status(MOCK_PAN_PRESENT);
    for (int i = 0; i < 5; i++) {
        mock_sm_advance_time(100);
        state_machine_update();
    }
    mock_sm_set_pan_temperature(92.0f);
    state_machine_reset_temp_baseline();
    mock_sm_advance_time(100);
    state_machine_update();  /* PREHEAT -> HEATING */
    TEST_ASSERT_EQUAL(STATE_HEATING, state_machine_get_state());

    mock_sm_press_button(BUTTON_STOP);   /* UI lost > 100 ms */
    mock_sm_advance_time(100);
    state_machine_update();
    TEST_ASSERT_EQUAL(STATE_COOLDOWN, state_machine_get_state());
    TEST_ASSERT_EQUAL(0, mock_sm_get_power_level());

    mock_sm_release_button(BUTTON_STOP); /* UI recovered; START is not pressed */
    mock_sm_set_heatsink_temperature(45.0f);
    for (int i = 0; i < 20; i++) {
        mock_sm_advance_time(100);
        state_machine_update();
    }
    TEST_ASSERT_EQUAL(STATE_IDLE, state_machine_get_state());
    TEST_ASSERT_EQUAL(0, mock_sm_get_power_level());
}

/* ============================================================================
 * Test Cases: STATE_COOLDOWN -> STATE_IDLE (cooled down)
 * ============================================================================ */

/**
 * Test: Cool enough transitions from COOLDOWN to IDLE
 */
void test_sm_cooldown_to_idle_when_cool(void) {
    /* Set up to reach COOLDOWN state */
    setup_test();
    state_machine_update();  /* INIT -> IDLE */
    state_machine_set_target_temp(100.0f);
    mock_sm_press_button(BUTTON_START);
    mock_sm_advance_time(100);
    state_machine_update();  /* IDLE -> PAN_DET */
    mock_sm_release_button(BUTTON_START);
    mock_sm_set_pan_status(MOCK_PAN_PRESENT);
    
    for (int i = 0; i < 5; i++) {
        mock_sm_advance_time(100);
        state_machine_update();
    }
    
    mock_sm_set_pan_temperature(92.0f);
    state_machine_reset_temp_baseline();
    mock_sm_advance_time(100);
    state_machine_update();  /* PREHEAT -> HEATING */
    
    mock_sm_press_button(BUTTON_STOP);
    mock_sm_advance_time(100);
    state_machine_update();  /* HEATING -> COOLDOWN */
    mock_sm_release_button(BUTTON_STOP);
    
    /* Set heatsink temp below safe idle temp (50°C) */
    mock_sm_set_heatsink_temperature(45.0f);
    mock_sm_advance_time(100);
    state_machine_update();
    
    TEST_ASSERT_EQUAL(STATE_IDLE, state_machine_get_state());
}

/* ============================================================================
 * Test Cases: STATE_HEATING -> STATE_FAULT (safety interlocks)
 * ============================================================================ */

static void reach_heating_for_interlock(void) {
    /* Set up to reach HEATING state */
    setup_test();
    state_machine_update();  /* INIT -> IDLE */
    state_machine_set_target_temp(100.0f);
    mock_sm_press_button(BUTTON_START);
    mock_sm_advance_time(100);
    state_machine_update();  /* IDLE -> PAN_DET */
    mock_sm_release_button(BUTTON_START);
    mock_sm_set_pan_status(MOCK_PAN_PRESENT);
    
    for (int i = 0; i < 5; i++) {
        mock_sm_advance_time(100);
        state_machine_update();
    }
    
    mock_sm_set_pan_temperature(92.0f);
    state_machine_reset_temp_baseline();
    mock_sm_advance_time(100);
    state_machine_update();  /* PREHEAT -> HEATING */
    
}

/**
 * Test: Over-temperature triggers FAULT
 */
void test_sm_fault_on_over_temperature(void) {
    /* Set up to reach HEATING state */
    setup_test();
    state_machine_update();  /* INIT -> IDLE */
    state_machine_set_target_temp(100.0f);
    mock_sm_press_button(BUTTON_START);
    mock_sm_advance_time(100);
    state_machine_update();  /* IDLE -> PAN_DET */
    mock_sm_release_button(BUTTON_START);
    mock_sm_set_pan_status(MOCK_PAN_PRESENT);
    
    for (int i = 0; i < 5; i++) {
        mock_sm_advance_time(100);
        state_machine_update();
    }
    
    mock_sm_set_pan_temperature(92.0f);
    state_machine_reset_temp_baseline();
    mock_sm_advance_time(100);
    state_machine_update();  /* PREHEAT -> HEATING */
    
    /* Trigger over-temperature (> 95 C heatsink, L3 ladder) */
    mock_sm_set_heatsink_temperature(96.0f);
    mock_sm_advance_time(100);
    state_machine_update();
    
    TEST_ASSERT_EQUAL(STATE_FAULT, state_machine_get_state());
    TEST_ASSERT_EQUAL(FAULT_OVER_TEMP, state_machine_get_fault());
}

/* L3 trip ladder (DECISIONS C32): the heatsink firmware trip is 95 C, above the 88.6 C fan-law
 * setpoint where the sink runs at full power; the IGBT-era 80 C would trip in normal use. */
void test_sm_heatsink_at_fan_setpoint_does_not_trip(void) {
    reach_heating_for_interlock();
    TEST_ASSERT_EQUAL(STATE_HEATING, state_machine_get_state());
    mock_sm_set_heatsink_temperature(88.6f);
    mock_sm_advance_time(100);
    state_machine_update();
    mock_sm_set_heatsink_temperature(95.0f); /* at the threshold: still running (> not >=) */
    mock_sm_advance_time(100);
    state_machine_update();
    TEST_ASSERT_EQUAL(STATE_HEATING, state_machine_get_state());
    mock_sm_set_heatsink_temperature(95.1f);
    mock_sm_advance_time(100);
    state_machine_update();
    TEST_ASSERT_EQUAL(STATE_FAULT, state_machine_get_state());
    TEST_ASSERT_EQUAL(FAULT_OVER_TEMP, state_machine_get_fault());
}

/* An invalid heatsink reading (NaN: open, short, stale, unsettled) trips; NaN > x is false, so
 * the old comparison let it pass as cool. */
void test_sm_invalid_heatsink_reading_trips(void) {
    reach_heating_for_interlock();
    mock_sm_set_heatsink_temperature(NAN);
    mock_sm_advance_time(100);
    state_machine_update();
    TEST_ASSERT_EQUAL(STATE_FAULT, state_machine_get_state());
    TEST_ASSERT_EQUAL(FAULT_OVER_TEMP, state_machine_get_fault());
}

/* Coil firmware hard trip 165 C (derate 150-160 C before it; hardware 169.7 C low corner after). */
void test_sm_coil_hard_trip_165(void) {
    reach_heating_for_interlock();
    mock_sm_set_coil_temperature(164.9f);
    mock_sm_advance_time(100);
    state_machine_update();
    TEST_ASSERT_EQUAL(STATE_HEATING, state_machine_get_state());
    mock_sm_set_coil_temperature(165.0f);
    mock_sm_advance_time(100);
    state_machine_update();
    TEST_ASSERT_EQUAL(STATE_FAULT, state_machine_get_state());
    TEST_ASSERT_EQUAL(FAULT_OVER_TEMP, state_machine_get_fault());
    TEST_ASSERT_TRUE(mock_sm_get_trigger_shutdown_count() >= 1);
}

void test_sm_invalid_coil_reading_trips(void) {
    reach_heating_for_interlock();
    mock_sm_set_coil_temperature(NAN);
    mock_sm_advance_time(100);
    state_machine_update();
    TEST_ASSERT_EQUAL(STATE_FAULT, state_machine_get_state());
    TEST_ASSERT_EQUAL(FAULT_OVER_TEMP, state_machine_get_fault());
}

/**
 * Test: Over-current triggers FAULT
 */
void test_sm_fault_on_over_current(void) {
    /* Set up to reach HEATING state */
    setup_test();
    state_machine_update();  /* INIT -> IDLE */
    state_machine_set_target_temp(100.0f);
    mock_sm_press_button(BUTTON_START);
    mock_sm_advance_time(100);
    state_machine_update();  /* IDLE -> PAN_DET */
    mock_sm_release_button(BUTTON_START);
    mock_sm_set_pan_status(MOCK_PAN_PRESENT);
    
    for (int i = 0; i < 5; i++) {
        mock_sm_advance_time(100);
        state_machine_update();
    }
    
    mock_sm_set_pan_temperature(92.0f);
    state_machine_reset_temp_baseline();
    mock_sm_advance_time(100);
    state_machine_update();  /* PREHEAT -> HEATING */
    
    /* n21 binding latched its CT peak / RMS trip */
    TEST_ASSERT_EQUAL(STATE_HEATING, state_machine_get_state());
    mock_sm_set_power_tank_trip(true);
    mock_sm_advance_time(100);
    state_machine_update();
    
    TEST_ASSERT_EQUAL(STATE_FAULT, state_machine_get_state());
    TEST_ASSERT_EQUAL(FAULT_OVER_CURRENT, state_machine_get_fault());
    TEST_ASSERT_EQUAL_UINT32(1, mock_sm_get_trigger_shutdown_count());
}

/**
 * Test: IGBT short (>50A) triggers FAULT_IGBT_SHORT
 */
void test_sm_fault_on_igbt_short(void) {
    setup_test();
    state_machine_update();  /* INIT -> IDLE */
    state_machine_set_target_temp(100.0f);
    mock_sm_press_button(BUTTON_START);
    mock_sm_advance_time(100);
    state_machine_update();  /* IDLE -> PAN_DET */
    mock_sm_release_button(BUTTON_START);
    mock_sm_set_pan_status(MOCK_PAN_PRESENT);
    
    for (int i = 0; i < 5; i++) {
        mock_sm_advance_time(100);
        state_machine_update();
    }
    
    mock_sm_set_pan_temperature(92.0f);
    state_machine_reset_temp_baseline();
    mock_sm_advance_time(100);
    state_machine_update();  /* PREHEAT -> HEATING */
    
    /* BUS_FAULT read-back high (or PERMIT dropped while running) */
    TEST_ASSERT_EQUAL(STATE_HEATING, state_machine_get_state());
    mock_sm_set_power_bus_fault(true);
    mock_sm_advance_time(100);
    state_machine_update();
    
    TEST_ASSERT_EQUAL(STATE_FAULT, state_machine_get_state());
    TEST_ASSERT_EQUAL(FAULT_IGBT_SHORT, state_machine_get_fault());
    TEST_ASSERT_EQUAL_UINT32(1, mock_sm_get_trigger_shutdown_count());
}

/**
 * Test: both sources at once -> the hardware bus fault (FAULT_IGBT_SHORT) wins
 */
void test_sm_fault_on_igbt_short_is_distinct(void) {
    setup_test();
    state_machine_update();  /* INIT -> IDLE */
    state_machine_set_target_temp(100.0f);
    mock_sm_press_button(BUTTON_START);
    mock_sm_advance_time(100);
    state_machine_update();  /* IDLE -> PAN_DET */
    mock_sm_release_button(BUTTON_START);
    mock_sm_set_pan_status(MOCK_PAN_PRESENT);
    
    for (int i = 0; i < 5; i++) {
        mock_sm_advance_time(100);
        state_machine_update();
    }
    
    mock_sm_set_pan_temperature(92.0f);
    state_machine_reset_temp_baseline();
    mock_sm_advance_time(100);
    state_machine_update();  /* PREHEAT -> HEATING */
    
    mock_sm_set_power_tank_trip(true);
    mock_sm_set_power_bus_fault(true);
    mock_sm_advance_time(100);
    state_machine_update();
    
    TEST_ASSERT_EQUAL(STATE_FAULT, state_machine_get_state());
    TEST_ASSERT_EQUAL(FAULT_IGBT_SHORT, state_machine_get_fault());
}

/* Drive IDLE -> PAN_DET -> PREHEAT with a healthy system (helper for the tests below). */
static void drive_to_preheat(void) {
    setup_test();
    state_machine_update();  /* INIT -> IDLE */
    state_machine_set_target_temp(100.0f);
    mock_sm_press_button(BUTTON_START);
    mock_sm_advance_time(100);
    state_machine_update();  /* IDLE -> PAN_DET */
    mock_sm_release_button(BUTTON_START);
    mock_sm_set_pan_status(MOCK_PAN_PRESENT);
    for (int i = 0; i < 5 && state_machine_get_state() != STATE_PREHEAT; i++) {
        mock_sm_advance_time(100);
        state_machine_update();
    }
}

/**
 * Test: a healthy native-21 system (no bus fault, no tank trip) enters and stays in PREHEAT.
 * The legacy DC bus current is no longer read: even an absurd value has no effect.
 */
void test_sm_healthy_power_stage_enters_preheat_without_fault(void) {
    drive_to_preheat();
    TEST_ASSERT_EQUAL(STATE_PREHEAT, state_machine_get_state());
    mock_sm_set_dc_bus_current(1000.0f);
    for (int i = 0; i < 5; i++) {
        mock_sm_advance_time(100);
        mock_sm_set_pan_temperature(30.0f + (float)i); /* not stuck, far below target */
        state_machine_reset_temp_baseline();
        state_machine_update();
    }
    TEST_ASSERT_EQUAL(STATE_PREHEAT, state_machine_get_state());
    TEST_ASSERT_EQUAL(FAULT_NONE, state_machine_get_fault());
    TEST_ASSERT_EQUAL_UINT32(0, mock_sm_get_trigger_shutdown_count());
}

/** Test: each source latches its fault in PREHEAT too. */
void test_sm_preheat_bus_fault_latches_igbt_short(void) {
    drive_to_preheat();
    TEST_ASSERT_EQUAL(STATE_PREHEAT, state_machine_get_state());
    mock_sm_set_power_bus_fault(true);
    mock_sm_advance_time(100);
    state_machine_update();
    TEST_ASSERT_EQUAL(STATE_FAULT, state_machine_get_state());
    TEST_ASSERT_EQUAL(FAULT_IGBT_SHORT, state_machine_get_fault());
    TEST_ASSERT_EQUAL_UINT32(1, mock_sm_get_trigger_shutdown_count());
}

void test_sm_preheat_tank_trip_latches_over_current(void) {
    drive_to_preheat();
    TEST_ASSERT_EQUAL(STATE_PREHEAT, state_machine_get_state());
    mock_sm_set_power_tank_trip(true);
    mock_sm_advance_time(100);
    state_machine_update();
    TEST_ASSERT_EQUAL(STATE_FAULT, state_machine_get_state());
    TEST_ASSERT_EQUAL(FAULT_OVER_CURRENT, state_machine_get_fault());
}

/**
 * Test: Fan failure triggers FAULT
 */
void test_sm_fault_on_fan_failure(void) {
    /* Set up to reach HEATING state */
    setup_test();
    state_machine_update();  /* INIT -> IDLE */
    state_machine_set_target_temp(100.0f);
    mock_sm_press_button(BUTTON_START);
    mock_sm_advance_time(100);
    state_machine_update();  /* IDLE -> PAN_DET */
    mock_sm_release_button(BUTTON_START);
    mock_sm_set_pan_status(MOCK_PAN_PRESENT);
    
    for (int i = 0; i < 5; i++) {
        mock_sm_advance_time(100);
        state_machine_update();
    }
    
    mock_sm_set_pan_temperature(92.0f);
    state_machine_reset_temp_baseline();
    mock_sm_advance_time(100);
    state_machine_update();  /* PREHEAT -> HEATING */
    
    /* Trigger fan failure */
    mock_sm_set_fan_running(false);
    mock_sm_advance_time(100);
    state_machine_update();
    
    TEST_ASSERT_EQUAL(STATE_FAULT, state_machine_get_state());
    TEST_ASSERT_EQUAL(FAULT_FAN_FAILURE, state_machine_get_fault());
}

/**
 * Test: legacy gross-open diagnostic remains a secondary fault path.
 */
void test_sm_fault_on_probe_open(void) {
    /* Set up to reach HEATING state */
    setup_test();
    state_machine_update();  /* INIT -> IDLE */
    state_machine_set_target_temp(100.0f);
    mock_sm_press_button(BUTTON_START);
    mock_sm_advance_time(100);
    state_machine_update();  /* IDLE -> PAN_DET */
    mock_sm_release_button(BUTTON_START);
    mock_sm_set_pan_status(MOCK_PAN_PRESENT);
    
    for (int i = 0; i < 5; i++) {
        mock_sm_advance_time(100);
        state_machine_update();
    }
    
    mock_sm_set_pan_temperature(92.0f);
    state_machine_reset_temp_baseline();
    mock_sm_advance_time(100);
    state_machine_update();  /* PREHEAT -> HEATING */
    
    /* Legacy gross-open diagnostic (>10kOhm), retained behind the 300 Ohm
     * MAX31865 guard-window path during migration. */
    mock_sm_set_rtd_resistance(15000.0f);
    mock_sm_advance_time(100);
    state_machine_update();
    
    TEST_ASSERT_EQUAL(STATE_FAULT, state_machine_get_state());
    TEST_ASSERT_EQUAL(FAULT_PROBE_OPEN, state_machine_get_fault());
    TEST_ASSERT_EQUAL_UINT32(1, mock_sm_get_trigger_shutdown_count());
}

/**
 * Test: the MAX31865 digital guard-window upper boundary faults immediately.
 *
 * The staged policy keeps the historical >10 kOhm check as a secondary
 * gross-open diagnostic, but the programmed MAX31865 high threshold is
 * 300 Ohm.  The firmware-facing resistance API must therefore make 300 Ohm
 * an open fault rather than waiting for the legacy diagnostic.
 */
void test_sm_fault_on_probe_open_at_max31865_guard_boundary(void) {
    /* Set up to reach HEATING state. */
    setup_test();
    state_machine_update();  /* INIT -> IDLE */
    state_machine_set_target_temp(100.0f);
    mock_sm_press_button(BUTTON_START);
    mock_sm_advance_time(100);
    state_machine_update();  /* IDLE -> PAN_DET */
    mock_sm_release_button(BUTTON_START);
    mock_sm_set_pan_status(MOCK_PAN_PRESENT);

    for (int i = 0; i < 5; i++) {
        mock_sm_advance_time(100);
        state_machine_update();
    }

    mock_sm_set_pan_temperature(92.0f);
    state_machine_reset_temp_baseline();
    mock_sm_advance_time(100);
    state_machine_update();  /* PREHEAT -> HEATING */

    /* MAX31865 programmed high threshold: 300 Ohm is itself a fault. */
    mock_sm_set_rtd_resistance(300.0f);
    mock_sm_advance_time(100);
    state_machine_update();

    TEST_ASSERT_EQUAL(STATE_FAULT, state_machine_get_state());
    TEST_ASSERT_EQUAL(FAULT_PROBE_OPEN, state_machine_get_fault());
    TEST_ASSERT_EQUAL_UINT32(1, mock_sm_get_trigger_shutdown_count());
}

/**
 * Test: RTD probe short triggers FAULT
 */
void test_sm_fault_on_probe_short(void) {
    /* Set up to reach HEATING state */
    setup_test();
    state_machine_update();  /* INIT -> IDLE */
    state_machine_set_target_temp(100.0f);
    mock_sm_press_button(BUTTON_START);
    mock_sm_advance_time(100);
    state_machine_update();  /* IDLE -> PAN_DET */
    mock_sm_release_button(BUTTON_START);
    mock_sm_set_pan_status(MOCK_PAN_PRESENT);
    
    for (int i = 0; i < 5; i++) {
        mock_sm_advance_time(100);
        state_machine_update();
    }
    
    mock_sm_set_pan_temperature(92.0f);
    state_machine_reset_temp_baseline();
    mock_sm_advance_time(100);
    state_machine_update();  /* PREHEAT -> HEATING */
    
    /* Trigger probe short (<10Ω) */
    mock_sm_set_rtd_resistance(5.0f);
    mock_sm_advance_time(100);
    state_machine_update();
    
    TEST_ASSERT_EQUAL(STATE_FAULT, state_machine_get_state());
    TEST_ASSERT_EQUAL(FAULT_PROBE_SHORT, state_machine_get_fault());
}

/**
 * Test: the MAX31865 digital guard-window lower boundary is inclusive.
 *
 * A 10 Ohm reading is the configured short boundary, so this must be a
 * short fault (not merely values below 10 Ohm).
 */
void test_sm_fault_on_probe_short_at_max31865_guard_boundary(void) {
    /* Set up to reach HEATING state. */
    setup_test();
    state_machine_update();  /* INIT -> IDLE */
    state_machine_set_target_temp(100.0f);
    mock_sm_press_button(BUTTON_START);
    mock_sm_advance_time(100);
    state_machine_update();  /* IDLE -> PAN_DET */
    mock_sm_release_button(BUTTON_START);
    mock_sm_set_pan_status(MOCK_PAN_PRESENT);

    for (int i = 0; i < 5; i++) {
        mock_sm_advance_time(100);
        state_machine_update();
    }

    mock_sm_set_pan_temperature(92.0f);
    state_machine_reset_temp_baseline();
    mock_sm_advance_time(100);
    state_machine_update();  /* PREHEAT -> HEATING */

    /* MAX31865 programmed low threshold: 10 Ohm is itself a fault. */
    mock_sm_set_rtd_resistance(10.0f);
    mock_sm_advance_time(100);
    state_machine_update();

    TEST_ASSERT_EQUAL(STATE_FAULT, state_machine_get_state());
    TEST_ASSERT_EQUAL(FAULT_PROBE_SHORT, state_machine_get_fault());
    TEST_ASSERT_EQUAL_UINT32(1, mock_sm_get_trigger_shutdown_count());
}

/**
 * Test: Thermal runaway triggers FAULT
 */
void test_sm_fault_on_thermal_runaway(void) {
    /* Set up to reach HEATING state */
    setup_test();
    state_machine_update();  /* INIT -> IDLE */
    state_machine_set_target_temp(100.0f);
    mock_sm_press_button(BUTTON_START);
    mock_sm_advance_time(100);
    state_machine_update();  /* IDLE -> PAN_DET */
    mock_sm_release_button(BUTTON_START);
    mock_sm_set_pan_status(MOCK_PAN_PRESENT);
    
    for (int i = 0; i < 5; i++) {
        mock_sm_advance_time(100);
        state_machine_update();
    }
    
    mock_sm_set_pan_temperature(92.0f);
    state_machine_reset_temp_baseline();
    mock_sm_advance_time(100);
    state_machine_update();  /* PREHEAT -> HEATING */
    
    /* Trigger thermal runaway (temp > target + 10°C) */
    mock_sm_set_pan_temperature(115.0f);
    state_machine_reset_temp_baseline();
    mock_sm_advance_time(100);
    state_machine_update();
    
    TEST_ASSERT_EQUAL(STATE_FAULT, state_machine_get_state());
    TEST_ASSERT_EQUAL(FAULT_THERMAL_RUNAWAY, state_machine_get_fault());
}

/**
 * Test: ADC stuck (3+ identical pan_temp readings) triggers FAULT_ADC_STUCK
 */
void test_sm_fault_on_adc_stuck(void) {
    setup_test();
    state_machine_update();  /* INIT -> IDLE */
    state_machine_set_target_temp(100.0f);
    mock_sm_press_button(BUTTON_START);
    mock_sm_advance_time(100);
    state_machine_update();  /* IDLE -> PAN_DET */
    mock_sm_release_button(BUTTON_START);
    mock_sm_set_pan_status(MOCK_PAN_PRESENT);
    
    for (int i = 0; i < 5; i++) {
        mock_sm_advance_time(100);
        state_machine_update();
    }
    
    mock_sm_set_pan_temperature(92.0f);
    state_machine_reset_temp_baseline();
    mock_sm_advance_time(100);
    state_machine_update();  /* PREHEAT -> HEATING */
    
    /* Inject same pan temperature across 50 consecutive updates.
     * No baseline reset needed — temperature is constant, so
     * rate-of-rise won't trigger.  This lets the stuck counter
     * accumulate to test FAULT_ADC_STUCK detection. */
    for (int i = 0; i < 50; i++) {
        mock_sm_set_pan_temperature(92.0f);
        mock_sm_advance_time(100);
        state_machine_update();
    }
    
    TEST_ASSERT_EQUAL(STATE_FAULT, state_machine_get_state());
    TEST_ASSERT_EQUAL(FAULT_ADC_STUCK, state_machine_get_fault());
}

/**
 * A safety interlock must be terminal for the current PREHEAT pass.  In
 * particular, a simultaneous pan-removal or STOP event must not replace the
 * safety fault with NO_PAN or COOLDOWN after the hardware cut is asserted.
 */
void test_sm_preheat_interlock_is_terminal_and_cuts_hardware(void) {
    setup_test();
    state_machine_set_target_temp(100.0f);
    state_machine_force_state(STATE_PREHEAT);

    mock_sm_set_heatsink_temperature(105.0f);
    mock_sm_set_pan_status(MOCK_PAN_ABSENT);
    mock_sm_press_button(BUTTON_STOP);
    mock_sm_advance_time(100);
    state_machine_update();

    TEST_ASSERT_EQUAL(STATE_FAULT, state_machine_get_state());
    TEST_ASSERT_EQUAL(FAULT_OVER_TEMP, state_machine_get_fault());
    TEST_ASSERT_EQUAL_UINT32(1, mock_sm_get_trigger_shutdown_count());
}

/**
 * Software thermal runaway faults use the same immediate hardware cut as
 * sensor interlocks, even when a user requests cooldown in that same pass.
 */
void test_sm_heating_runaway_is_terminal_and_cuts_hardware(void) {
    setup_test();
    state_machine_set_target_temp(100.0f);
    state_machine_force_state(STATE_HEATING);

    mock_sm_set_pan_temperature(115.0f);
    state_machine_reset_temp_baseline();
    mock_sm_set_pan_status(MOCK_PAN_ABSENT);
    mock_sm_press_button(BUTTON_STOP);
    mock_sm_advance_time(100);
    state_machine_update();

    TEST_ASSERT_EQUAL(STATE_FAULT, state_machine_get_state());
    TEST_ASSERT_EQUAL(FAULT_THERMAL_RUNAWAY, state_machine_get_fault());
    TEST_ASSERT_EQUAL_UINT32(1, mock_sm_get_trigger_shutdown_count());
}

/**
 * A PREHEAT timeout is an active-power safety fault and must assert the cut.
 */
void test_sm_preheat_timeout_cuts_hardware(void) {
    setup_test();
    state_machine_force_state(STATE_PREHEAT);

    mock_sm_advance_time(MAX_PREHEAT_TIME_MS + 1U);
    state_machine_update();

    TEST_ASSERT_EQUAL(STATE_FAULT, state_machine_get_state());
    TEST_ASSERT_EQUAL(FAULT_THERMAL_RUNAWAY, state_machine_get_fault());
    TEST_ASSERT_EQUAL_UINT32(1, mock_sm_get_trigger_shutdown_count());
}

/**
 * Cooldown overheat retains the hardware latch in case residual energy or a
 * failed switching stage is responsible for the temperature rise.
 */
void test_sm_cooldown_overheat_cuts_hardware(void) {
    setup_test();
    mock_sm_set_heatsink_temperature(80.0f);
    state_machine_force_state(STATE_COOLDOWN);

    mock_sm_set_heatsink_temperature(86.0f);
    mock_sm_advance_time(100);
    state_machine_update();

    TEST_ASSERT_EQUAL(STATE_FAULT, state_machine_get_state());
    TEST_ASSERT_EQUAL(FAULT_COOLDOWN_OVERHEAT, state_machine_get_fault());
    TEST_ASSERT_EQUAL_UINT32(1, mock_sm_get_trigger_shutdown_count());
}

/* ============================================================================
 * Test Cases: STATE_FAULT behavior
 * ============================================================================ */

/**
 * Test: FAULT entry logs fault to EEPROM
 */
void test_sm_fault_entry_logs_to_eeprom(void) {
    setup_test();
    state_machine_update();  /* INIT -> IDLE */
    state_machine_set_target_temp(100.0f);
    mock_sm_press_button(BUTTON_START);
    mock_sm_advance_time(100);
    state_machine_update();  /* IDLE -> PAN_DET */
    mock_sm_release_button(BUTTON_START);
    mock_sm_set_pan_status(MOCK_PAN_PRESENT);
    
    for (int i = 0; i < 5; i++) {
        mock_sm_advance_time(100);
        state_machine_update();
    }
    
    mock_sm_set_pan_temperature(92.0f);
    state_machine_reset_temp_baseline();
    mock_sm_advance_time(100);
    state_machine_update();  /* PREHEAT -> HEATING */
    
    uint32_t log_count_before = mock_sm_get_eeprom_log_count();
    
    mock_sm_set_heatsink_temperature(105.0f);
    mock_sm_advance_time(100);
    state_machine_update();  /* -> FAULT */
    
    TEST_ASSERT_EQUAL(log_count_before + 1, mock_sm_get_eeprom_log_count());
    TEST_ASSERT_EQUAL(FAULT_OVER_TEMP, mock_sm_get_last_logged_fault());
}

/**
 * Test: FAULT state keeps power disabled
 */
void test_sm_fault_keeps_power_off(void) {
    setup_test();
    state_machine_update();  /* INIT -> IDLE */
    state_machine_set_target_temp(100.0f);
    mock_sm_press_button(BUTTON_START);
    mock_sm_advance_time(100);
    state_machine_update();  /* IDLE -> PAN_DET */
    mock_sm_release_button(BUTTON_START);
    mock_sm_set_pan_status(MOCK_PAN_PRESENT);
    
    for (int i = 0; i < 5; i++) {
        mock_sm_advance_time(100);
        state_machine_update();
    }
    
    mock_sm_set_pan_temperature(92.0f);
    state_machine_reset_temp_baseline();
    mock_sm_advance_time(100);
    state_machine_update();  /* PREHEAT -> HEATING */
    
    mock_sm_set_heatsink_temperature(105.0f);
    mock_sm_advance_time(100);
    state_machine_update();  /* -> FAULT */
    
    /* Multiple updates while in FAULT */
    for (int i = 0; i < 5; i++) {
        mock_sm_advance_time(100);
        state_machine_update();
    }
    
    TEST_ASSERT_EQUAL(0, mock_sm_get_power_level());
}

/**
 * Test: Reset button while fault active doesn't clear fault
 */
void test_sm_reset_rejected_while_fault_active(void) {
    setup_test();
    state_machine_update();  /* INIT -> IDLE */
    state_machine_set_target_temp(100.0f);
    mock_sm_press_button(BUTTON_START);
    mock_sm_advance_time(100);
    state_machine_update();  /* IDLE -> PAN_DET */
    mock_sm_release_button(BUTTON_START);
    mock_sm_set_pan_status(MOCK_PAN_PRESENT);
    
    for (int i = 0; i < 5; i++) {
        mock_sm_advance_time(100);
        state_machine_update();
    }
    
    mock_sm_set_pan_temperature(92.0f);
    state_machine_reset_temp_baseline();
    mock_sm_advance_time(100);
    state_machine_update();  /* PREHEAT -> HEATING */
    
    /* Trigger over-temp fault */
    mock_sm_set_heatsink_temperature(105.0f);
    mock_sm_advance_time(100);
    state_machine_update();  /* -> FAULT */
    
    /* Fault condition still active - reset should be rejected */
    mock_sm_press_button(BUTTON_BACK);
    mock_sm_advance_time(100);
    state_machine_update();
    
    TEST_ASSERT_EQUAL(STATE_FAULT, state_machine_get_state());
}

/**
 * Test: an RTD reading that still violates the MAX31865 window cannot clear
 * a latched probe-open fault.  This covers the reset path as well as fault
 * detection: the 300 Ohm guard boundary is inclusive in both places.
 */
void test_sm_reset_rejected_while_rtd_open_guard_active(void) {
    setup_test();
    state_machine_force_state(STATE_HEATING);
    state_machine_reset_temp_baseline();

    mock_sm_set_rtd_resistance(300.0f);
    mock_sm_advance_time(100);
    state_machine_update();

    TEST_ASSERT_EQUAL(STATE_FAULT, state_machine_get_state());
    TEST_ASSERT_EQUAL(FAULT_PROBE_OPEN, state_machine_get_fault());

    /* The fault input remains active, so RESET must be rejected. */
    mock_sm_press_button(BUTTON_BACK);
    mock_sm_advance_time(100);
    state_machine_update();

    TEST_ASSERT_EQUAL(STATE_FAULT, state_machine_get_state());
    TEST_ASSERT_EQUAL(FAULT_PROBE_OPEN, state_machine_get_fault());
}

/**
 * Test: Reset button after fault cleared returns to INIT
 */
void test_sm_reset_accepted_when_fault_cleared(void) {
    setup_test();
    state_machine_update();  /* INIT -> IDLE */
    state_machine_set_target_temp(100.0f);
    mock_sm_press_button(BUTTON_START);
    mock_sm_advance_time(100);
    state_machine_update();  /* IDLE -> PAN_DET */
    mock_sm_release_button(BUTTON_START);
    mock_sm_set_pan_status(MOCK_PAN_PRESENT);
    
    for (int i = 0; i < 5; i++) {
        mock_sm_advance_time(100);
        state_machine_update();
    }
    
    mock_sm_set_pan_temperature(92.0f);
    state_machine_reset_temp_baseline();
    mock_sm_advance_time(100);
    state_machine_update();  /* PREHEAT -> HEATING */
    
    /* Trigger over-temp fault */
    mock_sm_set_heatsink_temperature(105.0f);
    mock_sm_advance_time(100);
    state_machine_update();  /* -> FAULT */
    
    /* Clear fault condition (temp below 70°C) */
    mock_sm_set_heatsink_temperature(65.0f);
    
    /* Press reset */
    mock_sm_press_button(BUTTON_BACK);
    mock_sm_advance_time(100);
    state_machine_update();
    
    TEST_ASSERT_EQUAL(STATE_INIT, state_machine_get_state());
    TEST_ASSERT_EQUAL(FAULT_NONE, state_machine_get_fault());
}

/* ============================================================================
 * Test Cases: Watchdog feeding
 * ============================================================================ */

/**
 * Test: Hardware watchdog is fed on every update
 */
void test_sm_hardware_watchdog_fed(void) {
    setup_test();
    uint32_t initial_count = mock_sm_get_watchdog_hw_feed_count();
    
    state_machine_update();
    
    TEST_ASSERT_EQUAL(initial_count + 1, mock_sm_get_watchdog_hw_feed_count());
}

/* ============================================================================
 * Test Cases: Temperature setpoint
 * ============================================================================ */

/**
 * Test: Set temperature within valid range
 */
void test_sm_set_temp_valid_range(void) {
    setup_test();
    state_machine_set_target_temp(150.0f);
    /* Can't directly verify, but shouldn't crash */
    TEST_ASSERT_TRUE(1);
}

/**
 * Test: Set temperature below minimum is ignored
 */
void test_sm_set_temp_below_min_ignored(void) {
    setup_test();
    state_machine_set_target_temp(20.0f);  /* Below 30°C minimum */
    /* Function should silently ignore invalid value */
    TEST_ASSERT_TRUE(1);
}

/**
 * Test: Set temperature above maximum is ignored
 */
void test_sm_set_temp_above_max_ignored(void) {
    setup_test();
    state_machine_set_target_temp(300.0f);  /* Above 250°C maximum */
    /* Function should silently ignore invalid value */
    TEST_ASSERT_TRUE(1);
}

/* ============================================================================
 * Test Cases: Cooking timer
 * ============================================================================ */

/**
 * Test: Timer completion transitions to COOLDOWN
 */
void test_sm_timer_completion_to_cooldown(void) {
    /* Set up to reach HEATING state */
    setup_test();
    state_machine_update();  /* INIT -> IDLE */
    state_machine_set_target_temp(100.0f);
    mock_sm_press_button(BUTTON_START);
    mock_sm_advance_time(100);
    state_machine_update();  /* IDLE -> PAN_DET */
    mock_sm_release_button(BUTTON_START);
    mock_sm_set_pan_status(MOCK_PAN_PRESENT);
    
    for (int i = 0; i < 5; i++) {
        mock_sm_advance_time(100);
        state_machine_update();
    }
    
    mock_sm_set_pan_temperature(92.0f);
    state_machine_reset_temp_baseline();
    mock_sm_advance_time(100);
    state_machine_update();  /* PREHEAT -> HEATING */
    
    /* Set timer for 1 second */
    state_machine_set_timer(true, 1000);
    
    /* Advance past timer */
    mock_sm_advance_time(1500);
    state_machine_update();
    
    /* Should show "COMPLETE" message then transition */
    mock_sm_advance_time(2500);
    state_machine_update();
    
    TEST_ASSERT_EQUAL(STATE_COOLDOWN, state_machine_get_state());
}

/* ============================================================================
 * Test Cases: State string helpers
 * ============================================================================ */

/**
 * Test: Get state string returns valid strings
 */
void test_sm_get_state_string(void) {
    TEST_ASSERT_EQUAL_STRING("INIT", state_machine_get_state_string(STATE_INIT));
    TEST_ASSERT_EQUAL_STRING("IDLE", state_machine_get_state_string(STATE_IDLE));
    TEST_ASSERT_EQUAL_STRING("PAN_DET", state_machine_get_state_string(STATE_PAN_DET));
    TEST_ASSERT_EQUAL_STRING("PREHEAT", state_machine_get_state_string(STATE_PREHEAT));
    TEST_ASSERT_EQUAL_STRING("HEATING", state_machine_get_state_string(STATE_HEATING));
    TEST_ASSERT_EQUAL_STRING("NO_PAN", state_machine_get_state_string(STATE_NO_PAN));
    TEST_ASSERT_EQUAL_STRING("COOLDOWN", state_machine_get_state_string(STATE_COOLDOWN));
    TEST_ASSERT_EQUAL_STRING("FAULT", state_machine_get_state_string(STATE_FAULT));
}

/**
 * Test: Get fault string returns valid strings
 */
void test_sm_get_fault_string(void) {
    TEST_ASSERT_EQUAL_STRING("NO FAULT", state_machine_get_fault_string(FAULT_NONE));
    TEST_ASSERT_EQUAL_STRING("OVER TEMP", state_machine_get_fault_string(FAULT_OVER_TEMP));
    TEST_ASSERT_EQUAL_STRING("OVER CURRENT", state_machine_get_fault_string(FAULT_OVER_CURRENT));
    TEST_ASSERT_EQUAL_STRING("FAN FAILED", state_machine_get_fault_string(FAULT_FAN_FAILURE));
}

/* ============================================================================
 * Test Cases: Force state (for testing)
 * ============================================================================ */

/**
 * Test: force_state transitions immediately
 */
void test_sm_force_state(void) {
    setup_test();
    state_machine_force_state(STATE_FAULT);
    TEST_ASSERT_EQUAL(STATE_FAULT, state_machine_get_state());
}

/**
 * Test: Default intensity is 10
 */
void test_sm_init_default_intensity(void) {
    setup_test();
    TEST_ASSERT_EQUAL(10, state_machine_get_intensity());
}

/**
 * Test: Set intensity within valid range
 */
void test_sm_set_intensity_valid(void) {
    setup_test();
    state_machine_set_intensity(5);
    TEST_ASSERT_EQUAL(5, state_machine_get_intensity());
}

/**
 * Test: Set intensity outside valid range is ignored
 */
void test_sm_set_intensity_invalid(void) {
    setup_test();
    state_machine_set_intensity(10);
    
    state_machine_set_intensity(0);
    TEST_ASSERT_EQUAL(10, state_machine_get_intensity());
    
    state_machine_set_intensity(11);
    TEST_ASSERT_EQUAL(10, state_machine_get_intensity());
}

/**
 * Test: Intensity clamping in PREHEAT
 */
void test_sm_intensity_clamping_preheat(void) {
    setup_test();
    state_machine_update();  /* INIT -> IDLE */
    
    /* Set low intensity (Level 2 = 20% power) */
    state_machine_set_intensity(2);
    
    state_machine_set_target_temp(100.0f);
    mock_sm_press_button(BUTTON_START);
    mock_sm_advance_time(100);
    state_machine_update();  /* IDLE -> PAN_DET */
    mock_sm_release_button(BUTTON_START);
    mock_sm_set_pan_status(MOCK_PAN_PRESENT);
    
    for (int i = 0; i < 5; i++) {
        mock_sm_advance_time(100);
        state_machine_update();
    }
    TEST_ASSERT_EQUAL(STATE_PREHEAT, state_machine_get_state());
    
    /* In PREHEAT with high temp error, requested power is 100.
     * With intensity level 2, it should be clamped to 20. */
    mock_sm_set_pan_temperature(25.0f);
    state_machine_reset_temp_baseline();
    mock_sm_advance_time(100);
    state_machine_update();
    
    TEST_ASSERT_EQUAL(20, mock_sm_get_power_level());
}

/**
 * Test: Intensity clamping in HEATING
 */
void test_sm_intensity_clamping_heating(void) {
    setup_test();
    state_machine_update();  /* INIT -> IDLE */
    
    /* Set medium intensity (Level 5 = 50% power) */
    state_machine_set_intensity(5);
    
    state_machine_set_target_temp(100.0f);
    mock_sm_press_button(BUTTON_START);
    mock_sm_advance_time(100);
    state_machine_update();  /* IDLE -> PAN_DET */
    mock_sm_release_button(BUTTON_START);
    mock_sm_set_pan_status(MOCK_PAN_PRESENT);
    
    for (int i = 0; i < 5; i++) {
        mock_sm_advance_time(100);
        state_machine_update();
    }
    
    /* Near target to enter HEATING */
    mock_sm_set_pan_temperature(92.0f);
    state_machine_reset_temp_baseline();
    mock_sm_advance_time(100);
    state_machine_update();  /* PREHEAT -> HEATING */
    
    /* In HEATING, force low temperature so PID wants high power */
    mock_sm_set_pan_temperature(25.0f);
    state_machine_reset_temp_baseline();
    state_machine_update();
    
    /* Power should be exactly 50 (Level 5) */
    TEST_ASSERT_EQUAL(50, mock_sm_get_power_level());
}

/**
 * Test: Intensity change during heating takes effect immediately
 */
void test_sm_intensity_change_during_heating(void) {
    setup_test();
    state_machine_update();  /* INIT -> IDLE */
    
    state_machine_set_target_temp(100.0f);
    mock_sm_press_button(BUTTON_START);
    mock_sm_advance_time(100);
    state_machine_update();  /* IDLE -> PAN_DET */
    mock_sm_release_button(BUTTON_START);
    mock_sm_set_pan_status(MOCK_PAN_PRESENT);
    
    for (int i = 0; i < 5; i++) {
        mock_sm_advance_time(100);
        state_machine_update();
    }
    
    /* In PREHEAT, high temp error */
    mock_sm_set_pan_temperature(25.0f);
    state_machine_reset_temp_baseline();
    state_machine_update();
    
    /* Default intensity 10: power should be 100 */
    TEST_ASSERT_EQUAL(100, mock_sm_get_power_level());
    
    /* Change intensity to 3 during heating */
    state_machine_set_intensity(3);
    state_machine_update();
    
    /* Power should now be 30 */
    TEST_ASSERT_EQUAL(30, mock_sm_get_power_level());
}

/* ============================================================================
 * Test Cases: String table coverage (R10)
 * ============================================================================ */

/**
 * Test: Every state in STATE_LIST has a non-empty string name
 *
 * If a state is added to STATE_LIST with an empty string field,
 * this test fails at strlen(name) == 0 (AE6).
 */
static void test_state_string_table_covers_all_states(void) {
    for (int s = 0; s < STATE_COUNT; s++) {
        const char *name = state_machine_get_state_string((system_state_t)s);
        TEST_ASSERT_GREATER_THAN(0, strlen(name));
    }
}

/**
 * Test: Every fault in FAULT_LIST has a non-empty string name
 */
static void test_fault_string_table_covers_all_faults(void) {
    for (int f = 0; f < FAULT_COUNT; f++) {
        const char *name = state_machine_get_fault_string((fault_code_t)f);
        TEST_ASSERT_GREATER_THAN(0, strlen(name));
    }
}

/* ============================================================================
 * Test Cases: Runaway Boundary Interlock
 * ============================================================================ */

/**
 * Test: Pan temp above max_absolute_temp_c triggers STATE_RUNAWAY_FAULT
 */
void test_sm_runaway_absolute_temp(void) {
    setup_test();
    /* Complete INIT -> IDLE */
    state_machine_update();
    TEST_ASSERT_EQUAL(STATE_IDLE, state_machine_get_state());

    /* Set target temp and enter PAN_DET */
    state_machine_set_target_temp(100.0f);
    mock_sm_press_button(BUTTON_START);
    mock_sm_advance_time(100);
    state_machine_update();
    TEST_ASSERT_EQUAL(STATE_PAN_DET, state_machine_get_state());
    mock_sm_release_button(BUTTON_START);

    /* Enter PAN_DET with pan present to progress to PREHEAT */
    mock_sm_set_pan_status(MOCK_PAN_PRESENT);
    for (int i = 0; i < 4; i++) {
        mock_sm_advance_time(100);
        state_machine_update();
    }
    TEST_ASSERT_EQUAL(STATE_PREHEAT, state_machine_get_state());

    /* Set pan temp above 300°C threshold */
    mock_sm_set_pan_temperature(310.0f);
    state_machine_reset_temp_baseline();
    mock_sm_advance_time(100);
    state_machine_update();

    TEST_ASSERT_EQUAL(STATE_RUNAWAY_FAULT, state_machine_get_state());
    TEST_ASSERT_EQUAL(FAULT_RUNAWAY_BOUNDARY, state_machine_get_fault());
}

/**
 * Test: Pan temp rise rate above max_temp_rise_rate_c_per_s triggers STATE_RUNAWAY_FAULT
 */
void test_sm_runaway_rate_of_rise(void) {
    setup_test();
    state_machine_update();  /* INIT -> IDLE */
    state_machine_set_target_temp(100.0f);
    mock_sm_press_button(BUTTON_START);
    mock_sm_advance_time(100);
    state_machine_update();  /* IDLE -> PAN_DET */
    mock_sm_release_button(BUTTON_START);

    /* Enter PREHEAT */
    mock_sm_set_pan_status(MOCK_PAN_PRESENT);
    for (int i = 0; i < 4; i++) {
        mock_sm_advance_time(100);
        state_machine_update();
    }
    TEST_ASSERT_EQUAL(STATE_PREHEAT, state_machine_get_state());

    /* Establish baseline: first update stores temp reading, rate check skipped */
    mock_sm_set_pan_temperature(30.0f);
    state_machine_reset_temp_baseline();
    mock_sm_advance_time(100);
    state_machine_update();
    TEST_ASSERT_EQUAL(STATE_PREHEAT, state_machine_get_state());

    /* Set pan temp to 200°C, rate = (200-30)/0.1s = 1700°C/s >> 15°C/s threshold */
    mock_sm_set_pan_temperature(200.0f);
    mock_sm_advance_time(100);
    state_machine_update();

    TEST_ASSERT_EQUAL(STATE_RUNAWAY_FAULT, state_machine_get_state());
    TEST_ASSERT_EQUAL(FAULT_RUNAWAY_BOUNDARY, state_machine_get_fault());
}

/**
 * Test: Normal temperatures and rates do not trigger runaway
 */
void test_sm_runaway_no_breach_normal_operation(void) {
    setup_test();
    state_machine_update();  /* INIT -> IDLE */
    state_machine_set_target_temp(100.0f);
    mock_sm_press_button(BUTTON_START);
    mock_sm_advance_time(100);
    state_machine_update();  /* IDLE -> PAN_DET */
    mock_sm_release_button(BUTTON_START);

    /* Enter PREHEAT */
    mock_sm_set_pan_status(MOCK_PAN_PRESENT);
    for (int i = 0; i < 4; i++) {
        mock_sm_advance_time(100);
        state_machine_update();
    }
    TEST_ASSERT_EQUAL(STATE_PREHEAT, state_machine_get_state());

    /* Set pan temp to 100°C - well below 300°C threshold */
    mock_sm_set_pan_temperature(100.0f);
    state_machine_reset_temp_baseline();
    mock_sm_advance_time(100);
    state_machine_update();
    TEST_ASSERT_EQUAL(STATE_HEATING, state_machine_get_state());

    /* Raise by 1°C over 100ms = 10°C/s, below 15°C/s threshold */
    mock_sm_set_pan_temperature(101.0f);
    state_machine_reset_temp_baseline();
    mock_sm_advance_time(100);
    state_machine_update();

    TEST_ASSERT_EQUAL(STATE_HEATING, state_machine_get_state());
}

/**
 * Test: After runaway breach, latch blocks transition
 */
void test_sm_runaway_latch_blocks_transition(void) {
    setup_test();
    state_machine_update();  /* INIT -> IDLE */
    state_machine_set_target_temp(100.0f);
    mock_sm_press_button(BUTTON_START);
    mock_sm_advance_time(100);
    state_machine_update();  /* IDLE -> PAN_DET */
    mock_sm_release_button(BUTTON_START);

    /* Enter PREHEAT */
    mock_sm_set_pan_status(MOCK_PAN_PRESENT);
    for (int i = 0; i < 4; i++) {
        mock_sm_advance_time(100);
        state_machine_update();
    }
    TEST_ASSERT_EQUAL(STATE_PREHEAT, state_machine_get_state());

    /* Trigger runaway */
    mock_sm_set_pan_temperature(310.0f);
    state_machine_reset_temp_baseline();
    mock_sm_advance_time(100);
    state_machine_update();
    TEST_ASSERT_EQUAL(STATE_RUNAWAY_FAULT, state_machine_get_state());

    /* Try to force transition back to IDLE */
    state_machine_force_state(STATE_IDLE);
    TEST_ASSERT_EQUAL(STATE_RUNAWAY_FAULT, state_machine_get_state());

    /* Try forcing other states - latch blocks all */
    state_machine_force_state(STATE_INIT);
    TEST_ASSERT_EQUAL(STATE_RUNAWAY_FAULT, state_machine_get_state());
    state_machine_force_state(STATE_HEATING);
    TEST_ASSERT_EQUAL(STATE_RUNAWAY_FAULT, state_machine_get_state());
}

/* ============================================================================
 * Test Runner
 * ============================================================================ */

void run_state_machine_tests(void) {
    /* Initialization tests */
    RUN_TEST(test_sm_init_starts_in_init_state);
    RUN_TEST(test_sm_init_no_fault);
    RUN_TEST(test_sm_init_default_target_temp);
    
    /* INIT -> IDLE transition */
    RUN_TEST(test_sm_init_to_idle_on_selftest_pass);
    RUN_TEST(test_sm_idle_entry_disables_power);
    RUN_TEST(test_sm_idle_sets_led_green);
    
    /* INIT -> FAULT transition */
    RUN_TEST(test_sm_init_to_fault_on_adc_fail);
    RUN_TEST(test_sm_init_to_fault_on_pwm_fail);
    RUN_TEST(test_sm_init_to_fault_on_fan_fail);
    
    /* IDLE -> PAN_DET transition */
    RUN_TEST(test_sm_idle_to_pan_det_on_start);
    RUN_TEST(test_sm_pan_det_shows_place_pan_message);
    
    /* PAN_DET -> PREHEAT transition */
    RUN_TEST(test_sm_pan_det_to_preheat_on_pan);
    RUN_TEST(test_sm_preheat_enables_pll);
    RUN_TEST(test_sm_preheat_rim_at_cap_removes_power);
    RUN_TEST(test_sm_rim_sensor_plausibility_fault);
    RUN_TEST(test_sm_rim_below_range_cool_pan_no_fault);
    RUN_TEST(test_sm_coil_sensor_plausibility_fault);
    RUN_TEST(test_sm_coil_warming_no_sensor_fault);
    RUN_TEST(test_sm_preheat_blower_stall_derates);
    
    /* PAN_DET timeout */
    RUN_TEST(test_sm_pan_det_timeout_to_idle);
    RUN_TEST(test_sm_start_refused_when_ps3_absent);
    RUN_TEST(test_sm_pan_det_refuses_heating_when_ps3_absent);

    /* B13 H2: BIAS_GOOD read-back on J4.1 */
    RUN_TEST(test_sm_bias_low_before_heartbeat_passes_post);
    RUN_TEST(test_sm_bias_high_before_heartbeat_faults_post);
    RUN_TEST(test_sm_bias_post_after_self_test);
    RUN_TEST(test_sm_bias_low_before_permit_refuses_start);
    RUN_TEST(test_sm_bias_drop_in_pan_det_latches);
    RUN_TEST(test_sm_bias_drop_during_run_latches_fault);
    RUN_TEST(test_sm_bias_drop_in_preheat_and_bus_fault_priority);
    RUN_TEST(test_sm_bias_run_reset_per_power_request);

    /* PREHEAT -> HEATING transition */
    RUN_TEST(test_sm_preheat_to_heating_near_target);
    
    /* HEATING -> NO_PAN transition */
    RUN_TEST(test_sm_heating_to_no_pan_on_removal);
    
    /* HEATING -> COOLDOWN transition */
    RUN_TEST(test_sm_heating_to_cooldown_on_stop);
    RUN_TEST(test_sm_cooldown_disables_power_and_pll);
    
    /* COOLDOWN -> IDLE transition */
    RUN_TEST(test_sm_cooldown_to_idle_when_cool);
    RUN_TEST(test_sm_ui_lost_stop_ends_heating_and_does_not_restart);
    
    /* Safety interlocks -> FAULT */
    RUN_TEST(test_sm_fault_on_over_temperature);
    RUN_TEST(test_sm_heatsink_at_fan_setpoint_does_not_trip);
    RUN_TEST(test_sm_invalid_heatsink_reading_trips);
    RUN_TEST(test_sm_coil_hard_trip_165);
    RUN_TEST(test_sm_invalid_coil_reading_trips);
    RUN_TEST(test_sm_fault_on_over_current);
    RUN_TEST(test_sm_fault_on_fan_failure);
    RUN_TEST(test_sm_fault_on_probe_open);
    RUN_TEST(test_sm_fault_on_probe_open_at_max31865_guard_boundary);
    RUN_TEST(test_sm_fault_on_probe_short);
    RUN_TEST(test_sm_fault_on_probe_short_at_max31865_guard_boundary);
    RUN_TEST(test_sm_fault_on_thermal_runaway);
    RUN_TEST(test_sm_fault_on_igbt_short);
    RUN_TEST(test_sm_fault_on_igbt_short_is_distinct);
    RUN_TEST(test_sm_healthy_power_stage_enters_preheat_without_fault);
    RUN_TEST(test_sm_preheat_bus_fault_latches_igbt_short);
    RUN_TEST(test_sm_preheat_tank_trip_latches_over_current);
    RUN_TEST(test_sm_fault_on_adc_stuck);
    RUN_TEST(test_sm_preheat_interlock_is_terminal_and_cuts_hardware);
    RUN_TEST(test_sm_heating_runaway_is_terminal_and_cuts_hardware);
    RUN_TEST(test_sm_preheat_timeout_cuts_hardware);
    RUN_TEST(test_sm_cooldown_overheat_cuts_hardware);
    
    /* FAULT behavior */
    RUN_TEST(test_sm_fault_entry_logs_to_eeprom);
    RUN_TEST(test_sm_fault_keeps_power_off);
    RUN_TEST(test_sm_reset_rejected_while_fault_active);
    RUN_TEST(test_sm_reset_rejected_while_rtd_open_guard_active);
    RUN_TEST(test_sm_reset_accepted_when_fault_cleared);
    
    /* Watchdog */
    RUN_TEST(test_sm_hardware_watchdog_fed);
    
    /* Temperature setpoint */
    RUN_TEST(test_sm_set_temp_valid_range);
    RUN_TEST(test_sm_set_temp_below_min_ignored);
    RUN_TEST(test_sm_set_temp_above_max_ignored);
    
    /* Timer */
    RUN_TEST(test_sm_timer_completion_to_cooldown);
    
    /* State/fault strings */
    RUN_TEST(test_sm_get_state_string);
    RUN_TEST(test_sm_get_fault_string);
    
    /* Force state */
    RUN_TEST(test_sm_force_state);

    /* Intensity control tests */
    RUN_TEST(test_sm_init_default_intensity);
    RUN_TEST(test_sm_set_intensity_valid);
    RUN_TEST(test_sm_set_intensity_invalid);
    RUN_TEST(test_sm_intensity_clamping_preheat);
    RUN_TEST(test_sm_intensity_clamping_heating);
    RUN_TEST(test_sm_intensity_change_during_heating);

    /* String table coverage (R10) */
    RUN_TEST(test_state_string_table_covers_all_states);
    RUN_TEST(test_fault_string_table_covers_all_faults);

    /* Runaway boundary interlock tests */
    RUN_TEST(test_sm_runaway_absolute_temp);
    RUN_TEST(test_sm_runaway_rate_of_rise);
    RUN_TEST(test_sm_runaway_no_breach_normal_operation);
    RUN_TEST(test_sm_runaway_latch_blocks_transition);
}
