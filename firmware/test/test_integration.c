/**
 * @file test_integration.c
 * @brief Integration tests for induction cooker firmware
 * 
 * These tests verify complete operational sequences by exercising
 * the state machine with mock HAL implementations. Unlike unit tests
 * that test individual transitions, integration tests verify:
 * - Full startup sequences (INIT → IDLE → PAN_DET → PREHEAT → HEATING)
 * - Complete operational cycles (heating → stop → cooldown → idle)
 * - Fault injection and recovery flows
 * 
 * Uses the same state_machine_stubs.c as unit tests for mock control.
 */

#include "unity/unity.h"
#include "test_common.h"
#include "../main/state_machine.h"

/* Forward declare mock control functions from state_machine_stubs.c */
extern void mock_sm_reset(void);
extern void mock_sm_advance_time(uint32_t ms);
extern void mock_sm_set_time(uint32_t ms);
extern void mock_sm_set_pan_temperature(float temp_c);
extern void mock_sm_set_heatsink_temperature(float temp_c);
extern void mock_sm_set_dc_bus_current(float amps);
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

/* Pan status constants */
#define MOCK_PAN_ABSENT  0
#define MOCK_PAN_PRESENT 1

/* Test helper: Initialize state machine to a clean state */
static void setup_test(void) {
    mock_sm_reset();
    state_machine_init();
}

/* ============================================================================
 * STARTUP SEQUENCE TESTS
 * ============================================================================ */

/**
 * @test Verify INIT → IDLE transition on successful self-test
 */
void test_startup_init_to_idle(void) {
    setup_test();
    
    /* Verify initial state */
    TEST_ASSERT_EQUAL(STATE_INIT, state_machine_get_state());
    TEST_ASSERT_EQUAL(FAULT_NONE, state_machine_get_fault());
    
    /* Self-test passes by default in mocks */
    state_machine_update();
    
    /* Verify transition to IDLE */
    TEST_ASSERT_EQUAL(STATE_IDLE, state_machine_get_state());
    TEST_ASSERT_EQUAL(0, mock_sm_get_power_level());
    TEST_ASSERT_EQUAL(LED_STEADY_GREEN, mock_sm_get_led_pattern());
}

/**
 * @test Verify IDLE → PAN_DET transition on start button press
 */
void test_startup_idle_to_pan_detect(void) {
    setup_test();
    state_machine_update();  /* INIT -> IDLE */
    
    /* Set target temperature (required for start) */
    state_machine_set_target_temp(150.0f);
    
    /* Press start button */
    mock_sm_press_button(BUTTON_START);
    mock_sm_advance_time(100);
    state_machine_update();
    
    /* Verify transition to PAN_DET */
    TEST_ASSERT_EQUAL(STATE_PAN_DET, state_machine_get_state());
    TEST_ASSERT_EQUAL_STRING("PLACE PAN", mock_sm_get_last_display_message());
}

/**
 * @test Verify PAN_DET → PREHEAT transition when pan is detected
 */
void test_startup_pan_detect_to_preheat(void) {
    setup_test();
    state_machine_update();  /* INIT -> IDLE */
    state_machine_set_target_temp(100.0f);
    mock_sm_press_button(BUTTON_START);
    mock_sm_advance_time(100);
    state_machine_update();  /* IDLE -> PAN_DET */
    mock_sm_release_button(BUTTON_START);
    
    /* Simulate pan placement */
    mock_sm_set_pan_status(MOCK_PAN_PRESENT);
    mock_sm_set_pan_impedance(5.0f);  /* Valid ferromagnetic pan */
    
    /* Multiple updates to build detection confidence */
    for (int i = 0; i < 5; i++) {
        mock_sm_advance_time(100);
        state_machine_update();
    }
    
    /* Verify transition to PREHEAT */
    TEST_ASSERT_EQUAL(STATE_PREHEAT, state_machine_get_state());
    TEST_ASSERT_TRUE(mock_sm_get_pll_enabled());
}

/**
 * @test Verify PREHEAT → HEATING transition when near target temperature
 */
void test_startup_preheat_to_heating(void) {
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
    
    /* Simulate temperature approaching target (within 10C) */
    mock_sm_set_pan_temperature(92.0f);
    mock_sm_advance_time(100);
    state_machine_update();
    
    /* Verify transition to HEATING */
    TEST_ASSERT_EQUAL(STATE_HEATING, state_machine_get_state());
}

/**
 * @test Verify complete startup sequence: INIT → IDLE → PAN_DET → PREHEAT → HEATING
 */
void test_full_startup_sequence(void) {
    setup_test();
    
    /* Step 1: INIT → IDLE */
    TEST_ASSERT_EQUAL(STATE_INIT, state_machine_get_state());
    state_machine_update();
    TEST_ASSERT_EQUAL(STATE_IDLE, state_machine_get_state());
    
    /* Step 2: IDLE → PAN_DET */
    state_machine_set_target_temp(150.0f);
    mock_sm_press_button(BUTTON_START);
    mock_sm_advance_time(100);
    state_machine_update();
    TEST_ASSERT_EQUAL(STATE_PAN_DET, state_machine_get_state());
    mock_sm_release_button(BUTTON_START);
    
    /* Step 3: PAN_DET → PREHEAT */
    mock_sm_set_pan_status(MOCK_PAN_PRESENT);
    mock_sm_set_pan_impedance(5.0f);
    for (int i = 0; i < 5; i++) {
        mock_sm_advance_time(100);
        state_machine_update();
    }
    TEST_ASSERT_EQUAL(STATE_PREHEAT, state_machine_get_state());
    
    /* Step 4: PREHEAT → HEATING */
    mock_sm_set_pan_temperature(142.0f);  /* Within 10C of 150C target */
    mock_sm_advance_time(100);
    state_machine_update();
    TEST_ASSERT_EQUAL(STATE_HEATING, state_machine_get_state());
    
    /* Verify final state */
    TEST_ASSERT_EQUAL(FAULT_NONE, state_machine_get_fault());
    TEST_ASSERT_TRUE(mock_sm_get_pll_enabled());
}

/* ============================================================================
 * NORMAL OPERATION TESTS
 * ============================================================================ */

/**
 * @test Verify PID maintains setpoint during HEATING state
 */
void test_operation_temperature_regulation(void) {
    /* Reach HEATING state */
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
    mock_sm_advance_time(100);
    state_machine_update();  /* PREHEAT -> HEATING */
    
    /* Simulate temperature slightly below setpoint */
    mock_sm_set_pan_temperature(95.0f);
    mock_sm_advance_time(100);
    state_machine_update();
    
    /* Power should be non-zero to heat */
    uint32_t power_when_cold = mock_sm_get_power_level();
    
    /* Simulate temperature at setpoint */
    mock_sm_set_pan_temperature(100.0f);
    mock_sm_advance_time(100);
    state_machine_update();
    
    /* Power should be lower or zero at setpoint */
    uint32_t power_at_setpoint = mock_sm_get_power_level();
    
    /* Temperature below setpoint should have more power than at setpoint */
    TEST_ASSERT_GREATER_OR_EQUAL(power_at_setpoint, power_when_cold);
    
    /* Should still be in HEATING state */
    TEST_ASSERT_EQUAL(STATE_HEATING, state_machine_get_state());
}

/**
 * @test Verify power level responds to temperature delta
 */
void test_operation_power_level_adjustment(void) {
    /* Reach HEATING state */
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
    mock_sm_advance_time(100);
    state_machine_update();  /* PREHEAT -> HEATING */
    
    /* Large temperature delta - should have high power */
    mock_sm_set_pan_temperature(50.0f);
    mock_sm_advance_time(100);
    state_machine_update();
    uint32_t power_cold = mock_sm_get_power_level();
    
    /* Small temperature delta - should have lower power */
    mock_sm_set_pan_temperature(98.0f);
    mock_sm_advance_time(100);
    state_machine_update();
    uint32_t power_warm = mock_sm_get_power_level();
    
    /* Cold should require more power than warm */
    TEST_ASSERT_GREATER_OR_EQUAL(power_warm, power_cold);
}

/**
 * @test Verify timer countdown transitions to COOLDOWN
 */
void test_operation_timer_countdown(void) {
    /* Reach HEATING state */
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
    mock_sm_advance_time(100);
    state_machine_update();  /* PREHEAT -> HEATING */
    
    /* Enable cooking timer for 1 second */
    state_machine_set_timer(true, 1000);
    
    /* Advance time past timer */
    mock_sm_advance_time(1500);
    state_machine_update();
    
    /* Allow for "COMPLETE" message display delay */
    mock_sm_advance_time(2500);
    state_machine_update();
    
    /* Should transition to COOLDOWN */
    TEST_ASSERT_EQUAL(STATE_COOLDOWN, state_machine_get_state());
}

/**
 * @test Verify stop button transitions to COOLDOWN
 */
void test_operation_manual_stop(void) {
    /* Reach HEATING state */
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
    mock_sm_advance_time(100);
    state_machine_update();  /* PREHEAT -> HEATING */
    
    /* Verify in HEATING state */
    TEST_ASSERT_EQUAL(STATE_HEATING, state_machine_get_state());
    
    /* Press stop button */
    mock_sm_press_button(BUTTON_STOP);
    mock_sm_advance_time(100);
    state_machine_update();
    
    /* Verify transition to COOLDOWN */
    TEST_ASSERT_EQUAL(STATE_COOLDOWN, state_machine_get_state());
    TEST_ASSERT_EQUAL(0, mock_sm_get_power_level());
    TEST_ASSERT_FALSE(mock_sm_get_pll_enabled());
}

/**
 * @test Verify COOLDOWN → IDLE when heatsink cools down
 */
void test_operation_cooldown_to_idle(void) {
    /* Reach HEATING state then stop */
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
    mock_sm_advance_time(100);
    state_machine_update();  /* PREHEAT -> HEATING */
    
    /* Stop heating */
    mock_sm_press_button(BUTTON_STOP);
    mock_sm_advance_time(100);
    state_machine_update();
    mock_sm_release_button(BUTTON_STOP);
    
    TEST_ASSERT_EQUAL(STATE_COOLDOWN, state_machine_get_state());
    
    /* Simulate heatsink cooling below safe idle temperature (50C) */
    mock_sm_set_heatsink_temperature(45.0f);
    mock_sm_advance_time(100);
    state_machine_update();
    
    /* Should transition to IDLE */
    TEST_ASSERT_EQUAL(STATE_IDLE, state_machine_get_state());
}

/**
 * @test Verify complete heating cycle: start → heat → stop → cooldown → idle
 */
void test_full_heating_cycle(void) {
    setup_test();
    
    /* Phase 1: Startup */
    state_machine_update();  /* INIT → IDLE */
    TEST_ASSERT_EQUAL(STATE_IDLE, state_machine_get_state());
    
    state_machine_set_target_temp(100.0f);
    mock_sm_press_button(BUTTON_START);
    mock_sm_advance_time(100);
    state_machine_update();  /* IDLE → PAN_DET */
    mock_sm_release_button(BUTTON_START);
    
    mock_sm_set_pan_status(MOCK_PAN_PRESENT);
    for (int i = 0; i < 5; i++) {
        mock_sm_advance_time(100);
        state_machine_update();
    }
    TEST_ASSERT_EQUAL(STATE_PREHEAT, state_machine_get_state());
    
    mock_sm_set_pan_temperature(92.0f);
    mock_sm_advance_time(100);
    state_machine_update();  /* PREHEAT → HEATING */
    TEST_ASSERT_EQUAL(STATE_HEATING, state_machine_get_state());
    
    /* Phase 2: Maintain temperature for several cycles */
    for (int i = 0; i < 10; i++) {
        mock_sm_set_pan_temperature(98.0f + (float)(i % 3));  /* Slight fluctuation */
        mock_sm_advance_time(100);
        state_machine_update();
        TEST_ASSERT_EQUAL(STATE_HEATING, state_machine_get_state());
    }
    
    /* Phase 3: Stop and cooldown */
    mock_sm_press_button(BUTTON_STOP);
    mock_sm_advance_time(100);
    state_machine_update();  /* HEATING → COOLDOWN */
    TEST_ASSERT_EQUAL(STATE_COOLDOWN, state_machine_get_state());
    mock_sm_release_button(BUTTON_STOP);
    
    /* Phase 4: Cool down to idle */
    mock_sm_set_heatsink_temperature(45.0f);
    mock_sm_advance_time(100);
    state_machine_update();  /* COOLDOWN → IDLE */
    TEST_ASSERT_EQUAL(STATE_IDLE, state_machine_get_state());
    
    /* Verify clean final state */
    TEST_ASSERT_EQUAL(FAULT_NONE, state_machine_get_fault());
    TEST_ASSERT_EQUAL(0, mock_sm_get_power_level());
}

/* ============================================================================
 * FAULT INJECTION TESTS
 * ============================================================================ */

/**
 * @test Verify over-current fault during heating via mock ADC
 */
void test_fault_ocp_during_heating(void) {
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
    mock_sm_advance_time(100);
    state_machine_update();  /* PREHEAT -> HEATING */
    
    /* Inject over-current condition (>35A) */
    mock_sm_set_dc_bus_current(40.0f);
    mock_sm_advance_time(100);
    state_machine_update();
    
    /* Verify fault state */
    TEST_ASSERT_EQUAL(STATE_FAULT, state_machine_get_state());
    TEST_ASSERT_EQUAL(FAULT_OVER_CURRENT, state_machine_get_fault());
    TEST_ASSERT_EQUAL(0, mock_sm_get_power_level());
}

/**
 * @test Verify over-temperature fault during heating (heatsink)
 */
void test_fault_ovp_during_heating(void) {
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
    mock_sm_advance_time(100);
    state_machine_update();  /* PREHEAT -> HEATING */
    
    /* Inject over-temperature condition */
    mock_sm_set_heatsink_temperature(105.0f);
    mock_sm_advance_time(100);
    state_machine_update();
    
    /* Verify fault state */
    TEST_ASSERT_EQUAL(STATE_FAULT, state_machine_get_state());
    TEST_ASSERT_EQUAL(FAULT_OVER_TEMP, state_machine_get_fault());
}

/**
 * @test Verify IGBT over-temperature fault via mock thermal reading
 */
void test_fault_thermal_igbt(void) {
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
    mock_sm_advance_time(100);
    state_machine_update();  /* PREHEAT -> HEATING */
    
    /* Inject IGBT over-temperature (heatsink >100C) */
    mock_sm_set_heatsink_temperature(110.0f);
    mock_sm_advance_time(100);
    state_machine_update();
    
    /* Verify fault state */
    TEST_ASSERT_EQUAL(STATE_FAULT, state_machine_get_state());
    TEST_ASSERT_EQUAL(FAULT_OVER_TEMP, state_machine_get_fault());
    TEST_ASSERT_EQUAL(FAULT_OVER_TEMP, mock_sm_get_last_logged_fault());
}

/**
 * @test Verify RTD open circuit fault (resistance >10k ohms)
 */
void test_fault_rtd_open(void) {
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
    mock_sm_advance_time(100);
    state_machine_update();  /* PREHEAT -> HEATING */
    
    /* Inject RTD open circuit (>10k ohms) */
    mock_sm_set_rtd_resistance(15000.0f);
    mock_sm_advance_time(100);
    state_machine_update();
    
    /* Verify fault state */
    TEST_ASSERT_EQUAL(STATE_FAULT, state_machine_get_state());
    TEST_ASSERT_EQUAL(FAULT_PROBE_OPEN, state_machine_get_fault());
}

/**
 * @test Verify RTD short circuit fault (resistance <10 ohms)
 */
void test_fault_rtd_short(void) {
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
    mock_sm_advance_time(100);
    state_machine_update();  /* PREHEAT -> HEATING */
    
    /* Inject RTD short circuit (<10 ohms) */
    mock_sm_set_rtd_resistance(5.0f);
    mock_sm_advance_time(100);
    state_machine_update();
    
    /* Verify fault state */
    TEST_ASSERT_EQUAL(STATE_FAULT, state_machine_get_state());
    TEST_ASSERT_EQUAL(FAULT_PROBE_SHORT, state_machine_get_fault());
}

/**
 * @test Verify fan failure fault
 */
void test_fault_fan_failure(void) {
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
    mock_sm_advance_time(100);
    state_machine_update();  /* PREHEAT -> HEATING */
    
    /* Inject fan failure */
    mock_sm_set_fan_running(false);
    mock_sm_advance_time(100);
    state_machine_update();
    
    /* Verify fault state */
    TEST_ASSERT_EQUAL(STATE_FAULT, state_machine_get_state());
    TEST_ASSERT_EQUAL(FAULT_FAN_FAILURE, state_machine_get_fault());
}

/**
 * @test Verify thermal runaway fault (temperature exceeds target by margin)
 */
void test_fault_thermal_runaway(void) {
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
    mock_sm_advance_time(100);
    state_machine_update();  /* PREHEAT -> HEATING */
    
    /* Inject thermal runaway (temp > target + 10C) */
    mock_sm_set_pan_temperature(115.0f);
    mock_sm_advance_time(100);
    state_machine_update();
    
    /* Verify fault state */
    TEST_ASSERT_EQUAL(STATE_FAULT, state_machine_get_state());
    TEST_ASSERT_EQUAL(FAULT_THERMAL_RUNAWAY, state_machine_get_fault());
}

/**
 * @test Verify watchdog monitoring (hardware watchdog fed on every update)
 */
void test_fault_watchdog_timeout(void) {
    setup_test();
    
    uint32_t initial_count = mock_sm_get_watchdog_hw_feed_count();
    
    /* Run several update cycles */
    for (int i = 0; i < 10; i++) {
        state_machine_update();
        mock_sm_advance_time(100);
    }
    
    /* Verify watchdog was fed on each update */
    TEST_ASSERT_EQUAL(initial_count + 10, mock_sm_get_watchdog_hw_feed_count());
}

/**
 * @test Verify fault recovery: reset button clears fault after condition resolved
 */
void test_fault_recovery_after_condition_cleared(void) {
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
    mock_sm_advance_time(100);
    state_machine_update();  /* PREHEAT -> HEATING */
    
    /* Trigger over-temp fault */
    mock_sm_set_heatsink_temperature(105.0f);
    mock_sm_advance_time(100);
    state_machine_update();
    TEST_ASSERT_EQUAL(STATE_FAULT, state_machine_get_state());
    
    /* Clear fault condition (temp below 70C) */
    mock_sm_set_heatsink_temperature(65.0f);
    
    /* Press reset button */
    mock_sm_press_button(BUTTON_RESET);
    mock_sm_advance_time(100);
    state_machine_update();
    
    /* Verify recovery to INIT state */
    TEST_ASSERT_EQUAL(STATE_INIT, state_machine_get_state());
    TEST_ASSERT_EQUAL(FAULT_NONE, state_machine_get_fault());
}

/**
 * @test Verify reset is rejected while fault condition is still active
 */
void test_fault_reset_rejected_while_active(void) {
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
    mock_sm_advance_time(100);
    state_machine_update();  /* PREHEAT -> HEATING */
    
    /* Trigger over-temp fault */
    mock_sm_set_heatsink_temperature(105.0f);
    mock_sm_advance_time(100);
    state_machine_update();
    TEST_ASSERT_EQUAL(STATE_FAULT, state_machine_get_state());
    
    /* Try reset while condition still active */
    mock_sm_press_button(BUTTON_RESET);
    mock_sm_advance_time(100);
    state_machine_update();
    
    /* Should remain in FAULT state */
    TEST_ASSERT_EQUAL(STATE_FAULT, state_machine_get_state());
    TEST_ASSERT_EQUAL(FAULT_OVER_TEMP, state_machine_get_fault());
}

/* ============================================================================
 * POWER CYCLE TESTS
 * ============================================================================ */

/**
 * @test Verify clean restart after graceful shutdown (IDLE state)
 */
void test_power_cycle_from_idle(void) {
    /* First power cycle: reach IDLE */
    setup_test();
    state_machine_update();  /* INIT -> IDLE */
    TEST_ASSERT_EQUAL(STATE_IDLE, state_machine_get_state());
    
    /* Simulate power cycle by re-initializing */
    state_machine_init();
    TEST_ASSERT_EQUAL(STATE_INIT, state_machine_get_state());
    
    /* Verify clean startup after power cycle */
    state_machine_update();  /* INIT -> IDLE */
    TEST_ASSERT_EQUAL(STATE_IDLE, state_machine_get_state());
    TEST_ASSERT_EQUAL(FAULT_NONE, state_machine_get_fault());
}

/**
 * @test Verify restart after power loss during heating
 * 
 * When power is lost during heating and restored, system should
 * start fresh in INIT state (no state persistence expected).
 */
void test_power_cycle_during_heating(void) {
    /* First power cycle: reach HEATING state */
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
    mock_sm_advance_time(100);
    state_machine_update();  /* PREHEAT -> HEATING */
    TEST_ASSERT_EQUAL(STATE_HEATING, state_machine_get_state());
    
    /* Simulate power loss and restore (re-initialize) */
    mock_sm_reset();
    state_machine_init();
    
    /* Should start fresh, not resume heating */
    TEST_ASSERT_EQUAL(STATE_INIT, state_machine_get_state());
    TEST_ASSERT_EQUAL(FAULT_NONE, state_machine_get_fault());
    TEST_ASSERT_EQUAL(0, mock_sm_get_power_level());
    
    /* Verify can complete normal startup */
    state_machine_update();  /* INIT -> IDLE */
    TEST_ASSERT_EQUAL(STATE_IDLE, state_machine_get_state());
}

/**
 * @test Verify restart after power loss during fault state
 */
void test_power_cycle_from_fault(void) {
    /* First power cycle: trigger fault */
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
    mock_sm_advance_time(100);
    state_machine_update();  /* PREHEAT -> HEATING */
    
    /* Trigger fault */
    mock_sm_set_heatsink_temperature(110.0f);
    mock_sm_advance_time(100);
    state_machine_update();
    TEST_ASSERT_EQUAL(STATE_FAULT, state_machine_get_state());
    
    /* Simulate power cycle (reset clears fault condition) */
    mock_sm_reset();
    state_machine_init();
    
    /* Should start fresh with no fault */
    TEST_ASSERT_EQUAL(STATE_INIT, state_machine_get_state());
    TEST_ASSERT_EQUAL(FAULT_NONE, state_machine_get_fault());
    
    /* Verify normal startup works */
    state_machine_update();  /* INIT -> IDLE */
    TEST_ASSERT_EQUAL(STATE_IDLE, state_machine_get_state());
}

/**
 * @test Verify restart after cooldown completes
 */
void test_power_cycle_after_cooldown(void) {
    /* Complete a full cycle to IDLE via cooldown */
    setup_test();
    state_machine_update();  /* INIT -> IDLE */
    state_machine_set_target_temp(100.0f);
    mock_sm_press_button(BUTTON_START);
    mock_sm_advance_time(100);
    state_machine_update();
    mock_sm_release_button(BUTTON_START);
    mock_sm_set_pan_status(MOCK_PAN_PRESENT);
    for (int i = 0; i < 5; i++) {
        mock_sm_advance_time(100);
        state_machine_update();
    }
    mock_sm_set_pan_temperature(92.0f);
    mock_sm_advance_time(100);
    state_machine_update();  /* PREHEAT -> HEATING */
    
    /* Stop and cooldown */
    mock_sm_press_button(BUTTON_STOP);
    mock_sm_advance_time(100);
    state_machine_update();
    mock_sm_release_button(BUTTON_STOP);
    mock_sm_set_heatsink_temperature(45.0f);
    mock_sm_advance_time(100);
    state_machine_update();  /* COOLDOWN -> IDLE */
    TEST_ASSERT_EQUAL(STATE_IDLE, state_machine_get_state());
    
    /* Power cycle from clean IDLE */
    state_machine_init();
    state_machine_update();
    
    /* Should be in IDLE with no issues */
    TEST_ASSERT_EQUAL(STATE_IDLE, state_machine_get_state());
    TEST_ASSERT_EQUAL(FAULT_NONE, state_machine_get_fault());
}

/* ============================================================================
 * STRESS TESTS
 * ============================================================================ */

/**
 * @test Verify rapid state transitions don't cause issues
 */
void test_stress_rapid_start_stop(void) {
    setup_test();
    state_machine_update();  /* INIT -> IDLE */
    
    /* Rapid start/stop cycles */
    for (int cycle = 0; cycle < 5; cycle++) {
        /* Start */
        state_machine_set_target_temp(100.0f);
        mock_sm_press_button(BUTTON_START);
        mock_sm_advance_time(100);
        state_machine_update();
        mock_sm_release_button(BUTTON_START);
        
        /* Quick stop before pan detected */
        mock_sm_press_button(BUTTON_STOP);
        mock_sm_advance_time(100);
        state_machine_update();
        mock_sm_release_button(BUTTON_STOP);
        
        /* Should be back in IDLE */
        TEST_ASSERT_EQUAL(STATE_IDLE, state_machine_get_state());
        TEST_ASSERT_EQUAL(FAULT_NONE, state_machine_get_fault());
    }
}

/**
 * @test Verify many update cycles without state change
 */
void test_stress_long_idle(void) {
    setup_test();
    state_machine_update();  /* INIT -> IDLE */
    
    /* Many update cycles in IDLE */
    for (int i = 0; i < 1000; i++) {
        mock_sm_advance_time(100);
        state_machine_update();
    }
    
    /* Should still be in IDLE with no faults */
    TEST_ASSERT_EQUAL(STATE_IDLE, state_machine_get_state());
    TEST_ASSERT_EQUAL(FAULT_NONE, state_machine_get_fault());
}

/**
 * @test Verify long heating session stays stable
 */
void test_stress_long_heating(void) {
    /* Reach HEATING state */
    setup_test();
    state_machine_update();  /* INIT -> IDLE */
    state_machine_set_target_temp(100.0f);
    mock_sm_press_button(BUTTON_START);
    mock_sm_advance_time(100);
    state_machine_update();
    mock_sm_release_button(BUTTON_START);
    mock_sm_set_pan_status(MOCK_PAN_PRESENT);
    for (int i = 0; i < 5; i++) {
        mock_sm_advance_time(100);
        state_machine_update();
    }
    mock_sm_set_pan_temperature(92.0f);
    mock_sm_advance_time(100);
    state_machine_update();  /* PREHEAT -> HEATING */
    
    /* Simulate 10 minutes of heating at setpoint */
    for (int i = 0; i < 6000; i++) {  /* 6000 * 100ms = 600 seconds */
        /* Temperature fluctuates slightly around setpoint */
        float temp = 99.0f + (float)(i % 3) - 1.0f;
        mock_sm_set_pan_temperature(temp);
        mock_sm_advance_time(100);
        state_machine_update();
        
        /* Should stay in HEATING */
        TEST_ASSERT_EQUAL(STATE_HEATING, state_machine_get_state());
    }
    
    /* Clean shutdown */
    mock_sm_press_button(BUTTON_STOP);
    mock_sm_advance_time(100);
    state_machine_update();
    TEST_ASSERT_EQUAL(STATE_COOLDOWN, state_machine_get_state());
}

/**
 * @test Verify button debouncing (rapid presses)
 */
void test_stress_button_debounce(void) {
    setup_test();
    state_machine_update();  /* INIT -> IDLE */
    state_machine_set_target_temp(100.0f);
    
    /* Rapid button presses */
    for (int i = 0; i < 10; i++) {
        mock_sm_press_button(BUTTON_START);
        mock_sm_advance_time(10);  /* Very short press */
        state_machine_update();
        mock_sm_release_button(BUTTON_START);
        mock_sm_advance_time(10);
        state_machine_update();
    }
    
    /* State machine should handle this gracefully */
    TEST_ASSERT_TRUE(state_machine_get_state() == STATE_IDLE || 
                     state_machine_get_state() == STATE_PAN_DET);
    TEST_ASSERT_EQUAL(FAULT_NONE, state_machine_get_fault());
}

/**
 * @test Verify temperature sensor noise doesn't cause false faults
 */
void test_stress_sensor_noise(void) {
    /* Reach HEATING state */
    setup_test();
    state_machine_update();  /* INIT -> IDLE */
    state_machine_set_target_temp(100.0f);
    mock_sm_press_button(BUTTON_START);
    mock_sm_advance_time(100);
    state_machine_update();
    mock_sm_release_button(BUTTON_START);
    mock_sm_set_pan_status(MOCK_PAN_PRESENT);
    for (int i = 0; i < 5; i++) {
        mock_sm_advance_time(100);
        state_machine_update();
    }
    mock_sm_set_pan_temperature(92.0f);
    mock_sm_advance_time(100);
    state_machine_update();  /* PREHEAT -> HEATING */
    
    /* Simulate noisy temperature readings */
    for (int i = 0; i < 100; i++) {
        /* Temperature varies ±5°C around setpoint (within runaway margin) */
        float noise = (float)((i * 7) % 11) - 5.0f;  /* Pseudo-random -5 to +5 */
        float temp = 100.0f + noise;
        mock_sm_set_pan_temperature(temp);
        mock_sm_advance_time(100);
        state_machine_update();
    }
    
    /* Should still be heating, no false runaway fault */
    TEST_ASSERT_EQUAL(STATE_HEATING, state_machine_get_state());
    TEST_ASSERT_EQUAL(FAULT_NONE, state_machine_get_fault());
}

/* ============================================================================
 * Test Runner
 * ============================================================================ */

void run_integration_tests(void) {
    /* Startup sequence tests */
    RUN_TEST(test_startup_init_to_idle);
    RUN_TEST(test_startup_idle_to_pan_detect);
    RUN_TEST(test_startup_pan_detect_to_preheat);
    RUN_TEST(test_startup_preheat_to_heating);
    RUN_TEST(test_full_startup_sequence);
    
    /* Normal operation tests */
    RUN_TEST(test_operation_temperature_regulation);
    RUN_TEST(test_operation_power_level_adjustment);
    RUN_TEST(test_operation_timer_countdown);
    RUN_TEST(test_operation_manual_stop);
    RUN_TEST(test_operation_cooldown_to_idle);
    RUN_TEST(test_full_heating_cycle);
    
    /* Fault injection tests */
    RUN_TEST(test_fault_ocp_during_heating);
    RUN_TEST(test_fault_ovp_during_heating);
    RUN_TEST(test_fault_thermal_igbt);
    RUN_TEST(test_fault_rtd_open);
    RUN_TEST(test_fault_rtd_short);
    RUN_TEST(test_fault_fan_failure);
    RUN_TEST(test_fault_thermal_runaway);
    RUN_TEST(test_fault_watchdog_timeout);
    RUN_TEST(test_fault_recovery_after_condition_cleared);
    RUN_TEST(test_fault_reset_rejected_while_active);
    
    /* Power cycle tests */
    RUN_TEST(test_power_cycle_from_idle);
    RUN_TEST(test_power_cycle_during_heating);
    RUN_TEST(test_power_cycle_from_fault);
    RUN_TEST(test_power_cycle_after_cooldown);
    
    /* Stress tests */
    RUN_TEST(test_stress_rapid_start_stop);
    RUN_TEST(test_stress_long_idle);
    RUN_TEST(test_stress_long_heating);
    RUN_TEST(test_stress_button_debounce);
    RUN_TEST(test_stress_sensor_noise);
}
