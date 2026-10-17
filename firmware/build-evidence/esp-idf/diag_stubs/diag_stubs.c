/* DIAGNOSTIC ONLY - not part of the product build. Satisfies the linker for the functions that have
 * no production implementation (see README.md) so that size/map data can be produced. Every stub aborts. */
#include <stdlib.h>
void button_is_pressed(void) { abort(); }
void button_set_enabled(void) { abort(); }
void buzzer_beep(void) { abort(); }
void buzzer_beep_continuous(void) { abort(); }
void buzzer_stop(void) { abort(); }
void display_show_fault(void) { abort(); }
void display_show_message(void) { abort(); }
void display_update_countdown(void) { abort(); }
void display_update_temperature(void) { abort(); }
void eeprom_log_fault(void) { abort(); }
void fan_set_auto_mode(void) { abort(); }
void fan_set_speed(void) { abort(); }
void get_time_ms(void) { abort(); }
void led_set_pattern(void) { abort(); }
void peripherals_enter_low_power(void) { abort(); }
void peripherals_exit_low_power(void) { abort(); }
void peripherals_init(void) { abort(); }
void read_dc_bus_current(void) { abort(); }
void read_pan_temperature(void) { abort(); }
void read_rtd_resistance(void) { abort(); }
void test_adc_calibration(void) { abort(); }
void test_display_communication(void) { abort(); }
void test_eeprom_read(void) { abort(); }
void test_fan_operation(void) { abort(); }
void test_hardware_comparators(void) { abort(); }
void test_rtd_sensor(void) { abort(); }
