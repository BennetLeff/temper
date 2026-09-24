/* Link-only cooker interface for the explicitly selected diagnostic image.
 * These are not production peripheral implementations. app_main never calls
 * the cooker state machine, and every power request terminates the image. */
#if !defined(TEMPER_DIAGNOSTIC_LOCKOUT) || TEMPER_DIAGNOSTIC_LOCKOUT != 1
#error "Diagnostic cooker hooks cannot be linked into a production image"
#endif

#include "state_machine.h"

#include <stdbool.h>
#include <stdint.h>

extern void diagnostic_lockout_reject_power_request(void);

uint32_t get_time_ms(void) { return 0; }
void peripherals_init(void) {}
void peripherals_enter_low_power(void) {}
void peripherals_exit_low_power(void) { diagnostic_lockout_reject_power_request(); }
void led_set_pattern(led_pattern_t pattern) { (void)pattern; }
void display_show_message(const char *msg) { (void)msg; }
void display_update_temperature(float temp) { (void)temp; }
void display_update_countdown(uint16_t seconds) { (void)seconds; }
void display_show_fault(fault_code_t code) { (void)code; }
void buzzer_beep(uint32_t duration_ms) { (void)duration_ms; }
void buzzer_beep_continuous(void) {}
void buzzer_stop(void) {}
bool button_is_pressed(button_id_t button) { (void)button; return false; }
void button_set_enabled(button_id_t button, bool enabled) {
    (void)button;
    (void)enabled;
}
void pwm_set_duty_cycle(uint8_t duty) {
    (void)duty;
    diagnostic_lockout_reject_power_request();
}
void pwm_disable_all(void) { diagnostic_lockout_reject_power_request(); }
void power_set_level(uint8_t level) {
    (void)level;
    diagnostic_lockout_reject_power_request();
}
void power_enable(void) { diagnostic_lockout_reject_power_request(); }
void fan_set_speed(fan_speed_t speed) { (void)speed; }
void fan_set_auto_mode(bool enabled) { (void)enabled; }
bool is_fan_running(void) { return false; }
float read_pan_temperature(void) { return 0.0f; }
float read_heatsink_temperature(void) { return 0.0f; }
float read_dc_bus_current(void) { return 0.0f; }
void eeprom_log_fault(fault_code_t code, uint32_t timestamp) {
    (void)code;
    (void)timestamp;
}
bool test_adc_calibration(void) { return false; }
bool test_pwm_generation(void) { return false; }
bool test_fan_operation(void) { return false; }
bool test_hardware_comparators(void) { return false; }
bool test_rtd_sensor(void) { return false; }
bool test_display_communication(void) { return false; }
bool test_eeprom_read(void) { return false; }
