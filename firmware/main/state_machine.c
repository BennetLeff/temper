/**
 * @file state_machine.c
 * @brief State machine implementation for induction cooker
 *
 * States are defined by STATE_LIST in state_machine.h.
 * Fault codes are defined by FAULT_LIST in state_machine.h.
 */

#include "state_machine.h"
#include "state_handlers.h"
#include "config.h"
#include <stddef.h>
#include <math.h>

/* ESP-IDF includes */
#ifdef ESP_PLATFORM
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "esp_log.h"
static const char *TAG = "state_machine";
#endif

/* Include component headers */
/* These will resolve when building with ESP-IDF */
/* #include "pan_detect.h" */
/* #include "pid_control.h" */
/* #include "pll_control.h" */
/* #include "safety.h" */
/* #include "low_temp_control.h" */
#include "../components/control/thermal_mass.h"
#include "../components/control/profiles.h"

/* State machine context */
sm_context_t sm_ctx = {
    .current_state = STATE_INIT,
    .previous_state = STATE_INIT,
    .fault_code = FAULT_NONE,
    .target_temperature = 100.0f,
    .message_pending = false,
    .last_update_time_ms = 0,
};

/* External function stubs - implement in peripherals module */
extern uint32_t get_time_ms(void);
extern void peripherals_init(void);
extern void peripherals_enter_low_power(void);
extern void peripherals_exit_low_power(void);
extern void led_set_pattern(led_pattern_t pattern);
extern void display_show_message(const char *msg);
extern void display_update_temperature(float temp);
extern void display_update_countdown(uint16_t seconds);
extern void display_show_fault(fault_code_t code);
extern void buzzer_beep(uint32_t duration_ms);
extern void buzzer_beep_continuous(void);
extern void buzzer_stop(void);
extern bool button_is_pressed(button_id_t button);
extern void button_set_enabled(button_id_t button, bool enabled);
extern void pwm_set_duty_cycle(uint8_t duty);
extern void pwm_disable_all(void);
extern void power_set_level(uint8_t level);
extern void power_enable(void);
extern void fan_set_speed(fan_speed_t speed);
extern void fan_set_auto_mode(bool enabled);
extern float read_pan_temperature(void);
extern float read_heatsink_temperature(void);
extern float read_dc_bus_current(void);
extern float read_rtd_resistance(void);
extern bool is_fan_running(void);
extern void delay_ms(uint32_t ms);
extern void eeprom_log_fault(fault_code_t code, uint32_t timestamp);

/* Pan detection stubs */
typedef enum { PAN_ABSENT, PAN_PRESENT } pan_status_t;
extern pan_status_t detect_pan_presence(void);
extern float get_pan_impedance(void);

/* PID stubs */
extern void pid_set_tuning(float kp, float ki, float kd);
extern void pid_reset_integral(void);
extern float pid_update(float setpoint, float measurement);

/* PLL stubs */
extern void pll_enable(void);
extern void pll_disable(void);
extern void pll_update(void);

/* Safety stubs */
extern void watchdog_set_timeout(uint32_t timeout_ms);
extern void watchdog_feed(void);
extern void watchdog_hardware_feed(void);
extern void trigger_hardware_shutdown(void);

/* Self-test stubs */
extern bool test_adc_calibration(void);
extern bool test_pwm_generation(void);
extern bool test_fan_operation(void);
extern bool test_hardware_comparators(void);
extern bool test_rtd_sensor(void);
extern bool test_display_communication(void);
extern bool test_eeprom_read(void);

/* ============================================================================
 * Public API
 * ============================================================================ */

void state_machine_init(void) {
    /* Reset all state machine context to defaults */
    sm_ctx.current_state = STATE_INIT;
    sm_ctx.previous_state = STATE_INIT;
    sm_ctx.fault_code = FAULT_NONE;
    sm_ctx.state_entry_time = 0;
    sm_ctx.state_duration = 0;
    
    /* Reset state-specific data */
    sm_ctx.pan_detect_confidence = 0;
    sm_ctx.pan_absent_count = 0;
    sm_ctx.initial_pan_impedance = 0.0f;
    sm_ctx.cooldown_start_temp = 0.0f;
    sm_ctx.countdown_timer_ms = 0;
    
    /* Reset user inputs to defaults */
    sm_ctx.target_temperature = 100.0f;
    sm_ctx.cooking_time_ms = 0;
    sm_ctx.cooking_timer_enabled = false;
    sm_ctx.intensity_level = 10;

    /* Reset ADC stuck detection */
    sm_ctx.last_pan_temp = 0.0f;
    sm_ctx.pan_temp_stuck_count = 0;
    sm_ctx.last_heatsink_temp = 0.0f;
    sm_ctx.heatsink_temp_stuck_count = 0;
    
    /* Reset profile */
    profile_init_status(&sm_ctx.profile);

    /* Reset message display state */
    sm_ctx.message_pending = false;
    sm_ctx.message_next_state = STATE_INIT;
    sm_ctx.message_start_time = 0;
    
    /* Reset timing */
    sm_ctx.last_update_time_ms = 0;
    
    transition_to(STATE_INIT);
}

void state_machine_start_profile(const cooking_profile_t *profile) {
    if (sm_ctx.current_state != STATE_IDLE) return;
    
    profile_start(&sm_ctx.profile, profile, get_time_ms());
    transition_to(STATE_PAN_DET);
}

void state_machine_update(void) {
    /* Update state duration */
    uint32_t now = get_time_ms();
    sm_ctx.state_duration = now - sm_ctx.state_entry_time;
    
    /* Feed external hardware watchdog (TPS3823-33) at the TOP of the loop.
     * This ensures the watchdog is fed even if state processing hangs.
     * The WDI toggle provides a heartbeat to the hardware watchdog IC.
     * If this function stops being called (MCU lockup), the watchdog
     * will timeout after 1.6s and disable the power stage.
     * See SAFETY_INTERLOCK_DESIGN.md Section 7. */
    watchdog_hardware_feed();
    
    /* Handle non-blocking message display */
    if (sm_ctx.message_pending) {
        if ((now - sm_ctx.message_start_time) >= MESSAGE_DISPLAY_TIME_MS) {
            sm_ctx.message_pending = false;
            transition_to(sm_ctx.message_next_state);
            return;
        }
        /* Still displaying message - feed software watchdog but skip state logic */
        watchdog_feed();
        return;
    }
    
    /* Calculate dt for timer decrement */
    uint32_t dt_ms = 0;
    if (sm_ctx.last_update_time_ms > 0) {
        dt_ms = now - sm_ctx.last_update_time_ms;
    }
    sm_ctx.last_update_time_ms = now;
    
    /* Decrement cooking timer if active */
    if (sm_ctx.cooking_timer_enabled && sm_ctx.cooking_time_ms > 0) {
        if (dt_ms >= sm_ctx.cooking_time_ms) {
            sm_ctx.cooking_time_ms = 0;
        } else {
            sm_ctx.cooking_time_ms -= dt_ms;
        }
    }

    /* Run current state update function */
    switch (sm_ctx.current_state) {
        case STATE_INIT:     state_init_update();     break;
        case STATE_IDLE:     state_idle_update();     break;
        case STATE_PAN_DET:  state_pan_det_update();  break;
        case STATE_PREHEAT:  state_preheat_update();  break;
        case STATE_HEATING:  state_heating_update();  break;
        case STATE_NO_PAN:   state_no_pan_update();   break;
        case STATE_COOLDOWN: state_cooldown_update(); break;
        case STATE_FAULT:    state_fault_update();    break;
        default:
            sm_ctx.fault_code = FAULT_SELF_TEST_FAILED;
            transition_to(STATE_FAULT);
            break;
    }
}

void state_machine_set_target_temp(float temp_celsius) {
    if (temp_celsius >= MIN_TEMP && temp_celsius <= MAX_TEMP) {
        sm_ctx.target_temperature = temp_celsius;
    }
}

system_state_t state_machine_get_state(void) {
    return sm_ctx.current_state;
}

fault_code_t state_machine_get_fault(void) {
    return sm_ctx.fault_code;
}

const char* state_machine_get_fault_string(fault_code_t code) {
    for (size_t i = 0; i < FAULT_COUNT; i++) {
        if (fault_name_table[i].value == code) return fault_name_table[i].name;
    }
    return "UNKNOWN FAULT";
}

const char* state_machine_get_state_string(system_state_t state) {
    for (size_t i = 0; i < STATE_COUNT; i++) {
        if (state_name_table[i].value == state) return state_name_table[i].name;
    }
    return "UNKNOWN";
}

const char* state_machine_get_event_string(event_t event) {
    for (size_t i = 0; i < EVENT_COUNT; i++) {
        if (event_name_table[i].value == event) return event_name_table[i].name;
    }
    return "UNKNOWN EVENT";
}

void state_machine_set_timer(bool enabled, uint32_t time_ms) {
    sm_ctx.cooking_timer_enabled = enabled;
    sm_ctx.cooking_time_ms = time_ms;
}

void state_machine_set_intensity(uint8_t level) {
    if (level >= 1 && level <= 10) {
        sm_ctx.intensity_level = level;
    }
}

uint8_t state_machine_get_intensity(void) {
    return sm_ctx.intensity_level;
}

void state_machine_force_state(system_state_t new_state) {
    transition_to(new_state);
}

bool run_self_test(void) {
    bool passed = true;

    /* Test ADC channels */
    passed &= test_adc_calibration();
    if (!passed) return false;

    /* Test PWM output */
    passed &= test_pwm_generation();
    if (!passed) return false;

    /* Test fan */
    passed &= test_fan_operation();
    if (!passed) return false;

    /* Test safety interlocks */
    passed &= test_hardware_comparators();
    if (!passed) return false;

    /* Test temperature sensors */
    passed &= test_rtd_sensor();
    if (!passed) return false;

    /* Test display */
    passed &= test_display_communication();
    if (!passed) return false;

    /* Test EEPROM */
    passed &= test_eeprom_read();
    if (!passed) return false;

    return true;
}

/* ============================================================================
 * Helper Functions
 * ============================================================================ */

void transition_to(system_state_t new_state) {
    /* Stop low-temperature control if transitioning out of heating state */
    if (sm_ctx.current_state == STATE_HEATING) {
        /* low_temp_stop(); */
    }

    /* Record previous state */
    sm_ctx.previous_state = sm_ctx.current_state;
    sm_ctx.current_state = new_state;
    sm_ctx.state_entry_time = get_time_ms();
    sm_ctx.state_duration = 0;

    /* Reset burst mode on any transition */
    /* low_temp_stop(); */

#ifdef ESP_PLATFORM
    ESP_LOGI(TAG, "State transition: %s -> %s",
             state_machine_get_state_string(sm_ctx.previous_state),
             state_machine_get_state_string(new_state));
#endif

    /* Call entry function for new state */
    switch (new_state) {
        case STATE_INIT:     state_init_entry();     break;
        case STATE_IDLE:     state_idle_entry();     break;
        case STATE_PAN_DET:  state_pan_det_entry();  break;
        case STATE_PREHEAT:  state_preheat_entry();  break;
        case STATE_HEATING:  state_heating_entry();  break;
        case STATE_NO_PAN:   state_no_pan_entry();   break;
        case STATE_COOLDOWN: state_cooldown_entry(); break;
        case STATE_FAULT:    state_fault_entry();    break;
        default:
            sm_ctx.fault_code = FAULT_SELF_TEST_FAILED;
            transition_to(STATE_FAULT);
            break;
    }
}

void check_safety_interlocks(void) {
    /* Over-temperature check */
    if (read_heatsink_temperature() > 100.0f) {
        sm_ctx.fault_code = FAULT_OVER_TEMP;
        transition_to(STATE_FAULT);
        return;
    }

    /* IGBT short-circuit detection (hard short > 50A)
     * Catches the hard-fault case before the steady-state 35A limit */
    if (read_dc_bus_current() > 50.0f) {
        sm_ctx.fault_code = FAULT_IGBT_SHORT;
        transition_to(STATE_FAULT);
        return;
    }

    /* Over-current check */
    if (read_dc_bus_current() > 35.0f) {
        sm_ctx.fault_code = FAULT_OVER_CURRENT;
        transition_to(STATE_FAULT);
        return;
    }

    /* Fan failure check */
    if (!is_fan_running()) {
        sm_ctx.fault_code = FAULT_FAN_FAILURE;
        transition_to(STATE_FAULT);
        return;
    }

    /* RTD probe checks */
    float rtd_resistance = read_rtd_resistance();
    if (rtd_resistance > 10000.0f) {
        sm_ctx.fault_code = FAULT_PROBE_OPEN;
        transition_to(STATE_FAULT);
        return;
    }
    if (rtd_resistance < 10.0f) {
        sm_ctx.fault_code = FAULT_PROBE_SHORT;
        transition_to(STATE_FAULT);
        return;
    }

    /* ADC stuck-at detection: same value across 50+ consecutive reads
     * A stuck ADC is a silent failure that existing threshold checks
     * may miss. Uses float equality because a stuck ADC register returns
     * bit-identical values after conversion. Threshold of 50 (5 seconds
     * at 100ms/tick) avoids false positives during normal state transitions,
     * pan removal debounce, and constant-sensor trace replay. */
    {
        float pan_temp = read_pan_temperature();
        if (pan_temp == sm_ctx.last_pan_temp) {
            sm_ctx.pan_temp_stuck_count++;
            if (sm_ctx.pan_temp_stuck_count >= 50) {
                sm_ctx.fault_code = FAULT_ADC_STUCK;
                transition_to(STATE_FAULT);
                return;
            }
        } else {
            sm_ctx.last_pan_temp = pan_temp;
            sm_ctx.pan_temp_stuck_count = 0;
        }
    }
    {
        float hs_temp = read_heatsink_temperature();
        if (hs_temp == sm_ctx.last_heatsink_temp) {
            sm_ctx.heatsink_temp_stuck_count++;
            if (sm_ctx.heatsink_temp_stuck_count >= 50) {
                sm_ctx.fault_code = FAULT_ADC_STUCK;
                transition_to(STATE_FAULT);
                return;
            }
        } else {
            sm_ctx.last_heatsink_temp = hs_temp;
            sm_ctx.heatsink_temp_stuck_count = 0;
        }
    }
}

bool fault_cleared(void) {
    float rtd_resistance;
    
    switch (sm_ctx.fault_code) {
        case FAULT_OVER_TEMP:
            return (read_heatsink_temperature() < 70.0f);

        case FAULT_OVER_CURRENT:
        case FAULT_IGBT_SHORT:
            return false;  /* requires power cycle */

        case FAULT_FAN_FAILURE:
            return is_fan_running();

        case FAULT_PROBE_OPEN:
        case FAULT_PROBE_SHORT:
            rtd_resistance = read_rtd_resistance();
            return (rtd_resistance > 50.0f && rtd_resistance < 500.0f);

        case FAULT_SELF_TEST_FAILED:
            return run_self_test();

        default:
            return false;  /* Most faults require power cycle */
    }
}

/**
 * @brief Non-blocking message display with state transition
 * 
 * Shows a message for MESSAGE_DISPLAY_TIME_MS then transitions to next_state.
 * This replaces blocking delay_ms() calls.
 */
void show_message_then_transition(const char *msg, system_state_t next_state) {
    display_show_message(msg);
    sm_ctx.message_pending = true;
    sm_ctx.message_next_state = next_state;
    sm_ctx.message_start_time = get_time_ms();
}
