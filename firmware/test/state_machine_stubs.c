/**
 * @file state_machine_stubs.c
 * @brief Stub implementations for state_machine.c external dependencies
 * 
 * All state_machine.c extern functions are stubbed here with controllable
 * behavior for unit testing. Tests can use mock_sm_* functions to:
 * - Set return values for sensor readings
 * - Simulate button presses
 * - Inject faults
 * - Advance simulated time
 * 
 * This file is compiled for HOST_BUILD only (not ESP32).
 */

#include <stdint.h>
#include <stdbool.h>
#include <string.h>
#include "../main/state_machine.h"
#include "../main/state_handlers.h"
#include "../config.h"

/* Pan detection result type (matches state_machine.c local typedef) */
typedef enum { PAN_ABSENT, PAN_PRESENT } pan_status_t;

/* ============================================================================
 * Mock State (controllable from tests)
 * ============================================================================ */

static struct {
    /* Time simulation */
    uint32_t current_time_ms;
    
    /* Sensor readings */
    float pan_temperature;
    float heatsink_temperature;
    float dc_bus_current;
    float rtd_resistance;
    float pan_impedance;
    
    /* Pan detection */
    pan_status_t pan_status;
    
    /* Button states */
    bool button_start_pressed;
    bool button_stop_pressed;
    bool button_temp_up_pressed;
    bool button_temp_down_pressed;
    bool button_reset_pressed;
    bool button_start_enabled;
    
    /* System states */
    bool fan_running;
    uint8_t power_level;
    uint8_t pwm_duty_cycle;
    fan_speed_t fan_speed;
    bool pll_enabled;
    led_pattern_t led_pattern;
    
    /* Self-test results */
    bool test_adc_pass;
    bool test_pwm_pass;
    bool test_fan_pass;
    bool test_comparators_pass;
    bool test_rtd_pass;
    bool test_display_pass;
    bool test_eeprom_pass;
    
    /* Call counters for verification */
    uint32_t power_set_level_calls;
    uint32_t pwm_disable_calls;
    uint32_t watchdog_feed_calls;
    uint32_t watchdog_hw_feed_calls;
    uint32_t eeprom_log_fault_calls;
    uint32_t trigger_shutdown_calls;
    uint32_t buzzer_beep_calls;
    uint32_t display_message_calls;
    
    /* Last logged fault */
    fault_code_t last_logged_fault;
    
    /* Last display message */
    char last_display_message[64];
    
} mock_sm_state = {
    .current_time_ms = 0,
    .pan_temperature = 25.0f,
    .heatsink_temperature = 25.0f,
    .dc_bus_current = 0.0f,
    .rtd_resistance = 100.0f,  /* PT100 at ~25°C */
    .pan_impedance = 5.0f,
    .pan_status = PAN_ABSENT,
    .button_start_pressed = false,
    .button_stop_pressed = false,
    .button_temp_up_pressed = false,
    .button_temp_down_pressed = false,
    .button_reset_pressed = false,
    .button_start_enabled = true,
    .fan_running = true,
    .power_level = 0,
    .pwm_duty_cycle = 0,
    .fan_speed = FAN_SPEED_OFF,
    .pll_enabled = false,
    .led_pattern = LED_OFF,
    .test_adc_pass = true,
    .test_pwm_pass = true,
    .test_fan_pass = true,
    .test_comparators_pass = true,
    .test_rtd_pass = true,
    .test_display_pass = true,
    .test_eeprom_pass = true,
    .power_set_level_calls = 0,
    .pwm_disable_calls = 0,
    .watchdog_feed_calls = 0,
    .watchdog_hw_feed_calls = 0,
    .eeprom_log_fault_calls = 0,
    .trigger_shutdown_calls = 0,
    .buzzer_beep_calls = 0,
    .display_message_calls = 0,
    .last_logged_fault = FAULT_NONE,
    .last_display_message = "",
};

/* ============================================================================
 * Mock Control Functions (called from tests)
 * ============================================================================ */

void mock_sm_reset(void) {
    memset(&mock_sm_state, 0, sizeof(mock_sm_state));
    mock_sm_state.pan_temperature = 25.0f;
    mock_sm_state.heatsink_temperature = 25.0f;
    mock_sm_state.rtd_resistance = 100.0f;
    mock_sm_state.pan_impedance = 5.0f;
    mock_sm_state.fan_running = true;
    mock_sm_state.button_start_enabled = true;
    mock_sm_state.test_adc_pass = true;
    mock_sm_state.test_pwm_pass = true;
    mock_sm_state.test_fan_pass = true;
    mock_sm_state.test_comparators_pass = true;
    mock_sm_state.test_rtd_pass = true;
    mock_sm_state.test_display_pass = true;
    mock_sm_state.test_eeprom_pass = true;
}

void mock_sm_advance_time(uint32_t ms) {
    mock_sm_state.current_time_ms += ms;
}

void mock_sm_set_time(uint32_t ms) {
    mock_sm_state.current_time_ms = ms;
}

void mock_sm_set_pan_temperature(float temp_c) {
    mock_sm_state.pan_temperature = temp_c;
}

void mock_sm_set_heatsink_temperature(float temp_c) {
    mock_sm_state.heatsink_temperature = temp_c;
}

void mock_sm_set_dc_bus_current(float amps) {
    mock_sm_state.dc_bus_current = amps;
}

void mock_sm_set_rtd_resistance(float ohms) {
    mock_sm_state.rtd_resistance = ohms;
}

void mock_sm_set_pan_status(pan_status_t status) {
    mock_sm_state.pan_status = status;
}

void mock_sm_set_pan_impedance(float impedance) {
    mock_sm_state.pan_impedance = impedance;
}

void mock_sm_set_fan_running(bool running) {
    mock_sm_state.fan_running = running;
}

void mock_sm_press_button(button_id_t button) {
    switch (button) {
        case BUTTON_START: mock_sm_state.button_start_pressed = true; break;
        case BUTTON_STOP: mock_sm_state.button_stop_pressed = true; break;
        case BUTTON_TEMP_UP: mock_sm_state.button_temp_up_pressed = true; break;
        case BUTTON_TEMP_DOWN: mock_sm_state.button_temp_down_pressed = true; break;
        case BUTTON_RESET: mock_sm_state.button_reset_pressed = true; break;
    }
}

void mock_sm_release_button(button_id_t button) {
    switch (button) {
        case BUTTON_START: mock_sm_state.button_start_pressed = false; break;
        case BUTTON_STOP: mock_sm_state.button_stop_pressed = false; break;
        case BUTTON_TEMP_UP: mock_sm_state.button_temp_up_pressed = false; break;
        case BUTTON_TEMP_DOWN: mock_sm_state.button_temp_down_pressed = false; break;
        case BUTTON_RESET: mock_sm_state.button_reset_pressed = false; break;
    }
}

void mock_sm_release_all_buttons(void) {
    mock_sm_state.button_start_pressed = false;
    mock_sm_state.button_stop_pressed = false;
    mock_sm_state.button_temp_up_pressed = false;
    mock_sm_state.button_temp_down_pressed = false;
    mock_sm_state.button_reset_pressed = false;
}

void mock_sm_set_selftest_results(bool adc, bool pwm, bool fan, bool comp, bool rtd, bool disp, bool eeprom) {
    mock_sm_state.test_adc_pass = adc;
    mock_sm_state.test_pwm_pass = pwm;
    mock_sm_state.test_fan_pass = fan;
    mock_sm_state.test_comparators_pass = comp;
    mock_sm_state.test_rtd_pass = rtd;
    mock_sm_state.test_display_pass = disp;
    mock_sm_state.test_eeprom_pass = eeprom;
}

void mock_sm_fail_selftest_adc(void) { mock_sm_state.test_adc_pass = false; }
void mock_sm_fail_selftest_pwm(void) { mock_sm_state.test_pwm_pass = false; }
void mock_sm_fail_selftest_fan(void) { mock_sm_state.test_fan_pass = false; }

/* Query mock state */
uint32_t mock_sm_get_power_level(void) { return mock_sm_state.power_level; }
uint32_t mock_sm_get_pwm_duty(void) { return mock_sm_state.pwm_duty_cycle; }
bool mock_sm_get_pll_enabled(void) { return mock_sm_state.pll_enabled; }
led_pattern_t mock_sm_get_led_pattern(void) { return mock_sm_state.led_pattern; }
fan_speed_t mock_sm_get_fan_speed(void) { return mock_sm_state.fan_speed; }
fault_code_t mock_sm_get_last_logged_fault(void) { return mock_sm_state.last_logged_fault; }
const char* mock_sm_get_last_display_message(void) { return mock_sm_state.last_display_message; }

/* Call counters */
uint32_t mock_sm_get_watchdog_feed_count(void) { return mock_sm_state.watchdog_feed_calls; }
uint32_t mock_sm_get_watchdog_hw_feed_count(void) { return mock_sm_state.watchdog_hw_feed_calls; }
uint32_t mock_sm_get_eeprom_log_count(void) { return mock_sm_state.eeprom_log_fault_calls; }
uint32_t mock_sm_get_trigger_shutdown_count(void) { return mock_sm_state.trigger_shutdown_calls; }
uint32_t mock_sm_get_power_set_count(void) { return mock_sm_state.power_set_level_calls; }
uint32_t mock_sm_get_pwm_disable_count(void) { return mock_sm_state.pwm_disable_calls; }

/* ============================================================================
 * Stub Implementations for state_machine.c extern functions
 * ============================================================================ */

/* Time */
uint32_t get_time_ms(void) {
    return mock_sm_state.current_time_ms;
}

void delay_ms(uint32_t ms) {
    mock_sm_state.current_time_ms += ms;
}

/* Peripherals */
void peripherals_init(void) {
    /* No-op for tests */
}

void peripherals_enter_low_power(void) {
    /* No-op for tests */
}

void peripherals_exit_low_power(void) {
    /* No-op for tests */
}

/* LED */
void led_set_pattern(led_pattern_t pattern) {
    mock_sm_state.led_pattern = pattern;
}

/* Display */
void display_show_message(const char *msg) {
    mock_sm_state.display_message_calls++;
    if (msg) {
        strncpy(mock_sm_state.last_display_message, msg, sizeof(mock_sm_state.last_display_message) - 1);
        mock_sm_state.last_display_message[sizeof(mock_sm_state.last_display_message) - 1] = '\0';
    }
}

void display_update_temperature(float temp) {
    (void)temp;
}

void display_update_countdown(uint16_t seconds) {
    (void)seconds;
}

void display_show_fault(fault_code_t code) {
    (void)code;
}

/* Buzzer */
void buzzer_beep(uint32_t duration_ms) {
    mock_sm_state.buzzer_beep_calls++;
    (void)duration_ms;
}

void buzzer_beep_continuous(void) {
    mock_sm_state.buzzer_beep_calls++;
}

void buzzer_stop(void) {
    /* No-op */
}

/* Buttons */
bool button_is_pressed(button_id_t button) {
    switch (button) {
        case BUTTON_START: return mock_sm_state.button_start_pressed && mock_sm_state.button_start_enabled;
        case BUTTON_STOP: return mock_sm_state.button_stop_pressed;
        case BUTTON_TEMP_UP: return mock_sm_state.button_temp_up_pressed;
        case BUTTON_TEMP_DOWN: return mock_sm_state.button_temp_down_pressed;
        case BUTTON_RESET: return mock_sm_state.button_reset_pressed;
        default: return false;
    }
}

void button_set_enabled(button_id_t button, bool enabled) {
    if (button == BUTTON_START) {
        mock_sm_state.button_start_enabled = enabled;
    }
}

/* PWM */
void pwm_set_duty_cycle(uint8_t duty) {
    mock_sm_state.pwm_duty_cycle = duty;
}

void pwm_disable_all(void) {
    mock_sm_state.pwm_disable_calls++;
    mock_sm_state.pwm_duty_cycle = 0;
}

/* Power */
void power_set_level(uint8_t level) {
    mock_sm_state.power_set_level_calls++;
    mock_sm_state.power_level = level;
}

void power_enable(void) {
    /* No-op */
}

/* Fan */
void fan_set_speed(fan_speed_t speed) {
    mock_sm_state.fan_speed = speed;
}

void fan_set_auto_mode(bool enabled) {
    (void)enabled;
}

bool is_fan_running(void) {
    return mock_sm_state.fan_running;
}

/* Sensors */
float read_pan_temperature(void) {
    return mock_sm_state.pan_temperature;
}

float read_heatsink_temperature(void) {
    return mock_sm_state.heatsink_temperature;
}

float read_dc_bus_current(void) {
    return mock_sm_state.dc_bus_current;
}

float read_rtd_resistance(void) {
    return mock_sm_state.rtd_resistance;
}

/* Pan detection */
pan_status_t detect_pan_presence(void) {
    return mock_sm_state.pan_status;
}

float get_pan_impedance(void) {
    return mock_sm_state.pan_impedance;
}

/* PLL */
void pll_enable(void) {
    mock_sm_state.pll_enabled = true;
}

void pll_disable(void) {
    mock_sm_state.pll_enabled = false;
}

void pll_update(void) {
    /* No-op */
}

/* Watchdog */
void watchdog_set_timeout(uint32_t timeout_ms) {
    (void)timeout_ms;
}

void watchdog_feed(void) {
    mock_sm_state.watchdog_feed_calls++;
}

void watchdog_hardware_feed(void) {
    mock_sm_state.watchdog_hw_feed_calls++;
}

void trigger_hardware_shutdown(void) {
    mock_sm_state.trigger_shutdown_calls++;
}

/* Self-test stubs */
bool test_adc_calibration(void) { return mock_sm_state.test_adc_pass; }
bool test_pwm_generation(void) { return mock_sm_state.test_pwm_pass; }
bool test_fan_operation(void) { return mock_sm_state.test_fan_pass; }
bool test_hardware_comparators(void) { return mock_sm_state.test_comparators_pass; }
bool test_rtd_sensor(void) { return mock_sm_state.test_rtd_pass; }
bool test_display_communication(void) { return mock_sm_state.test_display_pass; }
bool test_eeprom_read(void) { return mock_sm_state.test_eeprom_pass; }

/* EEPROM */
void eeprom_log_fault(fault_code_t code, uint32_t timestamp) {
    mock_sm_state.eeprom_log_fault_calls++;
    mock_sm_state.last_logged_fault = code;
    (void)timestamp;
}

/* ============================================================================
 * Global State Stubs (required by state_machine.c and state_handlers.c)
 * ============================================================================ */

config_t g_config;

sm_context_t sm_ctx;

bool run_self_test(void) {
    return true;  /* stub: all self-tests pass */
}
