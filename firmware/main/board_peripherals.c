/**
 * @file board_peripherals.c
 * @brief ESP-IDF target implementations of the peripheral functions the state
 *        machine, safety.c and pan_control.c declare `extern`.
 *
 * Host builds never compile this file: the host suites supply the same
 * symbols from firmware/test/state_machine_stubs.c and per-test stubs.
 *
 * Two kinds of function live here:
 *
 * - Real implementations, where the hardware path already exists in this
 *   firmware (esp_timer, the MAX31865 service, the heatsink NTC).
 *
 * - `TODO(hardware)` implementations, where no driver exists and the board
 *   path is not specified in firmware/config.yaml or config.h (pins in
 *   temper_hal/include/temper_pins.h are marked provisional). Each one fails
 *   safe: it never reports a plausible sensor value, inputs read as faults
 *   (temperatures and currents +INFINITY, fan stopped, buttons released,
 *   self-tests failed), and power outputs refuse any non-zero command, so the
 *   coil is never driven. Each logs once at ERROR the first time it is used.
 *
 * Consequence on the bench: the power-on self-test fails
 * (FAULT_SELF_TEST_FAILED) and the unit stays in FAULT with the coil off
 * until these are replaced by real drivers.
 */

#include <math.h>
#include <stdbool.h>
#include <stdint.h>

#include "esp_log.h"
#include "esp_timer.h"

#include "state_machine.h"
#include "pan_control.h"
#include "hs_ntc.h"

static const char *TAG = "board";

/* Log a TODO(hardware) use once per call site, so a 100 Hz caller cannot
 * flood the console. */
#define TODO_HW_ONCE(what)                                                    \
    do {                                                                      \
        static bool s_logged;                                                 \
        if (!s_logged) {                                                      \
            s_logged = true;                                                  \
            ESP_LOGE(TAG, "TODO(hardware): %s has no driver; failing safe",   \
                     what);                                                   \
        }                                                                     \
    } while (0)

/* ============================================================================
 * Real implementations
 * ============================================================================ */

uint32_t get_time_ms(void)
{
    /* Wraps after ~49.7 days; every consumer uses unsigned differences. */
    return (uint32_t)(esp_timer_get_time() / 1000);
}

float read_rtd_resistance(void)
{
    /* Latest MAX31865 conversion (NAN when there is none); safety.c treats a
     * non-finite value as a sensor fault. state_machine.c maps the same name
     * to this function by macro in C1 builds. */
    return pan_control_resistance_ohm();
}

/* ============================================================================
 * Board bring-up (TODO(hardware))
 * ============================================================================ */

void peripherals_init(void)
{
    /* hal_init() and the MAX31865 bootstrap run in main.c init_peripherals().
     * Display, buttons, buzzer, fan and LEDs have no drivers. */
    TODO_HW_ONCE("peripherals_init (display/buttons/buzzer/fan/LED)");
}

void peripherals_enter_low_power(void)
{
    /* CONFIG_PM_ENABLE=n: nothing to switch. */
}

void peripherals_exit_low_power(void)
{
}

/* ============================================================================
 * User interface outputs (TODO(hardware)): no-ops. They are indicators only;
 * the fault latch and coil-off paths do not depend on them.
 * ============================================================================ */

void led_set_pattern(led_pattern_t pattern)
{
    (void)pattern;
    TODO_HW_ONCE("led_set_pattern");
}

void display_show_message(const char *msg)
{
    /* The console stands in for the display. */
    ESP_LOGI(TAG, "display: %s", msg != NULL ? msg : "(null)");
}

void display_update_temperature(float temp)
{
    (void)temp;
    TODO_HW_ONCE("display_update_temperature");
}

void display_update_countdown(uint16_t seconds)
{
    (void)seconds;
    TODO_HW_ONCE("display_update_countdown");
}

void display_show_fault(fault_code_t code)
{
    ESP_LOGE(TAG, "display: FAULT %d (%s)", (int)code, state_machine_get_fault_string(code));
}

void buzzer_beep(uint32_t duration_ms)
{
    (void)duration_ms;
    TODO_HW_ONCE("buzzer_beep");
}

void buzzer_beep_continuous(void)
{
    TODO_HW_ONCE("buzzer_beep_continuous");
}

void buzzer_stop(void)
{
}

/* ============================================================================
 * User interface inputs (TODO(hardware)): every button reads released, so the
 * user cannot start a cook.
 * ============================================================================ */

bool button_is_pressed(button_id_t button)
{
    (void)button;
    TODO_HW_ONCE("button_is_pressed");
    return false;
}

void button_set_enabled(button_id_t button, bool enabled)
{
    (void)button;
    (void)enabled;
}

/* ============================================================================
 * Power stage (TODO(hardware)): no gate-drive path is wired. The MCPWM is
 * never initialised and the gate pins are never configured as outputs by
 * this image, so a zero command is already the hardware state and every
 * non-zero command is refused.
 * ============================================================================ */

void pwm_set_duty_cycle(uint8_t duty)
{
    if (duty != 0u) {
        TODO_HW_ONCE("pwm_set_duty_cycle (non-zero refused, coil off)");
    }
}

void pwm_disable_all(void)
{
    /* Nothing is driving: see the section comment. */
}

void power_set_level(uint8_t level)
{
    if (level != 0u) {
        TODO_HW_ONCE("power_set_level (non-zero refused, coil off)");
    }
}

void power_enable(void)
{
    TODO_HW_ONCE("power_enable (refused, coil off)");
}

/* ============================================================================
 * Fan (TODO(hardware)): reads stopped, so any fan check faults.
 * ============================================================================ */

void fan_set_speed(fan_speed_t speed)
{
    (void)speed;
    TODO_HW_ONCE("fan_set_speed");
}

void fan_set_auto_mode(bool enabled)
{
    (void)enabled;
    TODO_HW_ONCE("fan_set_auto_mode");
}

bool is_fan_running(void)
{
    TODO_HW_ONCE("is_fan_running (reads stopped)");
    return false;
}

/* ============================================================================
 * Heatsink NTC (real): the NTCALUG01A104GA on HS_ADC = GPIO6 / ADC1_CH5
 * through components/sensors/hs_ntc.c (output/temper-sensor-r3/firmware/
 * DECISIONS.md D-HSNTC).
 *
 * read_heatsink_temperature() callers and what they get:
 *   state_machine.c check_safety_interlocks()   > OVER_TEMP_THRESHOLD (95)
 *   state_machine.c fault_cleared()             < 70 releases FAULT_OVER_TEMP
 *   state_handlers.c state_idle_update()        background read (discarded)
 *   state_handlers.c state_cooldown_entry/update < SAFE_IDLE_TEMP (50) ends
 *                                               COOLDOWN; > start + 5 K latches
 *   state_handlers.c state_fault_update()       > FAULT_STATE_MAX_TEMP_C (125)
 *                                               triggers the hardware shutdown
 *   components/safety/safety.c check_hardware_interlocks(),
 *   run_safety_check()                         non-finite or > 80: over-temp
 *                                               (linked, no caller in this image)
 * VALID gives the filtered reading; SATURATED (colder than about 32 degC,
 * the normal room-temperature state of this channel) gives the upper bound,
 * which is below every limit and release above; no reading or a latched
 * driver fault (short, over-range, ADC) gives +INFINITY, as the former
 * TODO(hardware) stub always did: the `>` limits trip (FAULT_OVER_TEMP),
 * the `<` releases refuse, and in FAULT the hardware shutdown is asserted.
 * A driver fault stays latched until power-up. An open sensor reads
 * SATURATED; the board's HS_OPEN comparator latches it in hardware.
 * ============================================================================ */

static hs_ntc_t s_hs;
static bool s_hs_inited;

bool read_heatsink_ntc(hs_ntc_reading_t *out)
{
    if (!s_hs_inited) {
        hs_ntc_params_t p;
        hs_ntc_default_params(&p);
        s_hs_inited = hs_ntc_init(&s_hs, &p);
    }
    hs_ntc_reading_t rd = {.state = HS_NTC_FAULT, .diag = HS_NTC_DIAG_ADC, .t_c = NAN};
    if (s_hs_inited) {
        hs_ntc_poll(&s_hs, hs_ntc_board_hal(), get_time_ms(), &rd);
    }
    if (rd.state == HS_NTC_FAULT) {
        static bool s_logged;
        if (!s_logged) {
            s_logged = true;
            ESP_LOGE(TAG, "heatsink NTC fault (diag %d): reads +INF", (int)rd.diag);
        }
    }
    if (out != NULL) {
        *out = rd;
    }
    return rd.state == HS_NTC_VALID;
}

float read_heatsink_temperature(void)
{
    hs_ntc_reading_t rd;
    (void)read_heatsink_ntc(&rd);
    return hs_ntc_interlock_c(&rd);
}

/* ============================================================================
 * Bus current (TODO(hardware)). +INFINITY, not NAN: state_machine.c tests it
 * with `>` (a NAN would pass every over-limit check), and pan_control.c
 * rejects any non-finite value. The channel exists in temper_pins.h, but its
 * scaling is not specified in config.yaml.
 * ============================================================================ */

float read_dc_bus_current(void)
{
    TODO_HW_ONCE("read_dc_bus_current (reads +INF, invalid)");
    return INFINITY;
}

/* ============================================================================
 * Power-on self-test (TODO(hardware)): a test that does not exist cannot pass.
 * ============================================================================ */

bool test_adc_calibration(void)
{
    TODO_HW_ONCE("test_adc_calibration (fails)");
    return false;
}

bool test_pwm_generation(void)
{
    TODO_HW_ONCE("test_pwm_generation (fails)");
    return false;
}

bool test_fan_operation(void)
{
    TODO_HW_ONCE("test_fan_operation (fails)");
    return false;
}

bool test_hardware_comparators(void)
{
    TODO_HW_ONCE("test_hardware_comparators (fails)");
    return false;
}

bool test_rtd_sensor(void)
{
    TODO_HW_ONCE("test_rtd_sensor (fails)");
    return false;
}

bool test_display_communication(void)
{
    TODO_HW_ONCE("test_display_communication (fails)");
    return false;
}

bool test_eeprom_read(void)
{
    TODO_HW_ONCE("test_eeprom_read (fails)");
    return false;
}

/* ============================================================================
 * Fault log (TODO(hardware)): console only, not persisted.
 * ============================================================================ */

void eeprom_log_fault(fault_code_t code, uint32_t timestamp)
{
    ESP_LOGE(TAG, "fault %d (%s) at %lu ms [TODO(hardware): not persisted]", (int)code,
             state_machine_get_fault_string(code), (unsigned long)timestamp);
}
