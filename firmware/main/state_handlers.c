/**
 * @file state_handlers.c
 * @brief Per-state entry and update handler implementations
 *
 * Contains all 16 state handler functions (entry + update for each of the
 * 8 system states). Extracted from state_machine.c to keep the orchestration
 * shell under the 1000-line cap.
 */

#include "state_handlers.h"
#include "config.h"
#include <stddef.h>
#include <math.h>

/* ESP-IDF includes */
#ifdef ESP_PLATFORM
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "esp_log.h"
static const char *TAG = "state_handlers";
#endif

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
 * STATE_INIT Implementation
 * ============================================================================ */

void state_init_entry(void) {
    /* Initialize all peripherals */
    peripherals_init();

    /* Initialize thermal mass estimation */
    thermal_mass_init(&sm_ctx.thermal_mass, NULL);
    sm_ctx.thermal_mass_estimation_done = false;

    /* Visual feedback */
    led_set_pattern(LED_BLINK_FAST);
    display_show_message("SELF TEST");

    /* Set watchdog - longer timeout for POST */
    watchdog_set_timeout(5000);
}

void state_init_update(void) {
    /* Run power-on self-test */
    bool post_passed = run_self_test();

    if (post_passed) {
        transition_to(STATE_IDLE);
    } else {
        sm_ctx.fault_code = FAULT_SELF_TEST_FAILED;
        transition_to(STATE_FAULT);
    }
}

/* ============================================================================
 * STATE_IDLE Implementation
 * ============================================================================ */

void state_idle_entry(void) {
    /* Disable power output */
    pwm_set_duty_cycle(0);
    power_set_level(0);

    /* Minimum fan speed */
    fan_set_speed(FAN_SPEED_MIN);

    /* Visual feedback */
    led_set_pattern(LED_STEADY_GREEN);
    display_show_message("READY");

    /* Re-enable start button (disabled in cooldown) */
    button_set_enabled(BUTTON_START, true);

    /* Enable sleep mode for power savings */
    peripherals_enter_low_power();

    /* Set watchdog to longer timeout */
    watchdog_set_timeout(10000);
}

void state_idle_update(void) {
    /* Check for start button */
    if (button_is_pressed(BUTTON_START) && sm_ctx.target_temperature > 0) {
        transition_to(STATE_PAN_DET);
        return;
    }

    /* Handle temperature adjustment */
    if (button_is_pressed(BUTTON_TEMP_UP)) {
        sm_ctx.target_temperature += 5.0f;
        if (sm_ctx.target_temperature > MAX_TEMP) {
            sm_ctx.target_temperature = MAX_TEMP;
        }
        display_update_temperature(sm_ctx.target_temperature);
    }

    if (button_is_pressed(BUTTON_TEMP_DOWN)) {
        sm_ctx.target_temperature -= 5.0f;
        if (sm_ctx.target_temperature < MIN_TEMP) {
            sm_ctx.target_temperature = MIN_TEMP;
        }
        display_update_temperature(sm_ctx.target_temperature);
    }

    /* Background monitoring */
    (void)read_heatsink_temperature();
    (void)is_fan_running();

    /* Feed watchdog */
    watchdog_feed();
}

/* ============================================================================
 * STATE_PAN_DET Implementation
 * ============================================================================ */

void state_pan_det_entry(void) {
    /* Wake up from low power */
    peripherals_exit_low_power();

    /* Enable low-power detection mode */
    power_set_level(5);

    /* Visual feedback */
    display_show_message("PLACE PAN");
    led_set_pattern(LED_BLINK_SLOW);

    /* Reset detection state */
    sm_ctx.pan_detect_confidence = 0;
    sm_ctx.countdown_timer_ms = PAN_DETECT_TIMEOUT_MS;
    sm_ctx.thermal_mass_estimation_done = false;

    /* Start thermal mass estimation */
    float initial_temp = read_pan_temperature();
    thermal_mass_start_estimation(&sm_ctx.thermal_mass, initial_temp);

    /* Set watchdog */
    watchdog_set_timeout(2000);
}

void state_pan_det_update(void) {
    /* Run pan detection */
    pan_status_t result = detect_pan_presence();

    /* Update thermal mass estimation */
    float current_temp = read_pan_temperature();
    uint32_t current_time = get_time_ms();
    bool estimation_complete = thermal_mass_update(&sm_ctx.thermal_mass, current_temp, current_time);

    if (result == PAN_PRESENT) {
        sm_ctx.pan_detect_confidence++;
        if (sm_ctx.pan_detect_confidence >= PAN_CONFIDENCE_REQUIRED) {
            /* Record initial pan impedance for tracking */
            sm_ctx.initial_pan_impedance = get_pan_impedance();
            
            /* Apply thermal mass estimated PID gains if available */
            if (thermal_mass_is_classified(&sm_ctx.thermal_mass)) {
                pid_gains_t gains = thermal_mass_get_pid_gains(&sm_ctx.thermal_mass);
                pid_set_tuning(gains.kp, gains.ki, gains.kd);
                sm_ctx.thermal_mass_estimation_done = true;
            }
            
            transition_to(STATE_PREHEAT);
            return;
        }
    } else {
        sm_ctx.pan_detect_confidence = 0;
    }

    /* Check for timeout */
    if (sm_ctx.state_duration > sm_ctx.countdown_timer_ms) {
        show_message_then_transition("NO PAN", STATE_IDLE);
        return;
    }

    /* Check for cancel */
    if (button_is_pressed(BUTTON_STOP)) {
        transition_to(STATE_IDLE);
        return;
    }

    /* Feed watchdog */
    watchdog_feed();
}

/* ============================================================================
 * STATE_PREHEAT Implementation
 * ============================================================================ */

void state_preheat_entry(void) {
    /* Enable full power */
    power_enable();

    /* Initialize PID with aggressive tuning */
    pid_set_tuning(2.0f, 0.1f, 0.5f);

    /* Enable ZVS tracking */
    pll_enable();

    /* Visual feedback */
    display_show_message("PREHEATING");
    led_set_pattern(LED_STEADY_ORANGE);

    /* Fan to moderate speed */
    fan_set_speed(FAN_SPEED_MEDIUM);

    /* Set watchdog */
    watchdog_set_timeout(1000);
}

void state_preheat_update(void) {
    /* Read current temperature */
    float current_temp = read_pan_temperature();
    float temp_error = sm_ctx.target_temperature - current_temp;

    /* Check for preheat timeout - safety limit */
    if (sm_ctx.state_duration > MAX_PREHEAT_TIME_MS) {
        sm_ctx.fault_code = FAULT_THERMAL_RUNAWAY;
        transition_to(STATE_FAULT);
        return;
    }
    
    /* Aggressive power control with intensity limiting */
    uint8_t requested_power = 0;
    if (temp_error > 50.0f) {
        requested_power = 100;
    } else if (temp_error > 10.0f) {
        requested_power = 50;
    } else {
        /* Close to target: switch to precision control */
        transition_to(STATE_HEATING);
        return;
    }

    float intensity_max[] = {0.1f, 0.2f, 0.3f, 0.4f, 0.5f, 0.6f, 0.7f, 0.8f, 0.9f, 1.0f};
    uint8_t clamped_power = (uint8_t)fminf((float)requested_power, intensity_max[sm_ctx.intensity_level - 1] * 100.0f);
    power_set_level(clamped_power);

    /* Safety checks */
    check_safety_interlocks();

    /* Check for pan removal */
    if (detect_pan_presence() == PAN_ABSENT) {
        transition_to(STATE_NO_PAN);
        return;
    }

    /* Check for stop button */
    if (button_is_pressed(BUTTON_STOP)) {
        transition_to(STATE_COOLDOWN);
        return;
    }

    /* Update display */
    display_update_temperature(current_temp);

    /* Feed watchdog */
    watchdog_feed();
}

/* ============================================================================
 * STATE_HEATING Implementation
 * ============================================================================ */

void state_heating_entry(void) {
    if (sm_ctx.target_temperature < 50.0f) {
        /* low_temp_start(sm_ctx.target_temperature); */
        /* Switch to precision PID tuning for low temp */
        pid_set_tuning(0.5f, 0.01f, 0.1f);
        pid_reset_integral();
    } else {
        /* Switch to precision PID tuning */
        pid_set_tuning(1.0f, 0.05f, 0.2f);
        pid_reset_integral();
    }

    /* Visual feedback */
    display_show_message("HEATING");
    led_set_pattern(LED_STEADY_GREEN);

    /* Fan to automatic control */
    fan_set_auto_mode(true);

    /* Set watchdog */
    watchdog_set_timeout(1000);
    
    /* Reset pan absent counter */
    sm_ctx.pan_absent_count = 0;
}

void state_heating_update(void) {
    /* Read current temperature */
    float current_temp = read_pan_temperature();
    uint32_t now = get_time_ms();

    /* 1. Update Profile if active */
    if (sm_ctx.profile.active) {
        bool stage_changed = profile_update(&sm_ctx.profile, current_temp, now);
        
        if (sm_ctx.profile.completed) {
            show_message_then_transition("COMPLETE", STATE_COOLDOWN);
            return;
        }

        if (stage_changed) {
            buzzer_beep(200);
            /* Optional: display new stage name/info */
        }

        /* Override user settings with profile settings */
        float p_target;
        uint8_t p_intensity;
        bool p_use_probe;
        profile_get_current_settings(&sm_ctx.profile, &p_target, &p_intensity, &p_use_probe);
        
        sm_ctx.target_temperature = p_target;
        sm_ctx.intensity_level = p_intensity;
        /* TODO: Handle p_use_probe for cascade control when integrated */
    }

    if (sm_ctx.target_temperature < 50.0f) {
        /* Run low-temperature burst control */
        /* low_temp_update(current_temp); */
        /* Use standard PID for now */
        float pid_output = pid_update(sm_ctx.target_temperature, current_temp);
        power_set_level((uint8_t)(pid_output * 10));
    } else {
        /* Run standard PID controller */
        float pid_output = pid_update(sm_ctx.target_temperature, current_temp);
        
        /* Apply intensity limiting */
        float intensity_max[] = {0.1f, 0.2f, 0.3f, 0.4f, 0.5f, 0.6f, 0.7f, 0.8f, 0.9f, 1.0f};
        float clamped_output = fminf(pid_output, intensity_max[sm_ctx.intensity_level - 1] * 100.0f);
        power_set_level((uint8_t)clamped_output);
    }

    /* Update PLL for ZVS tracking */
    pll_update();

    /* Safety checks */
    check_safety_interlocks();

    /* Thermal runaway detection */
    if (current_temp > (sm_ctx.target_temperature + 10.0f)) {
        sm_ctx.fault_code = FAULT_THERMAL_RUNAWAY;
        transition_to(STATE_FAULT);
        return;
    }

    /* Pan removal detection (with debouncing) */
    if (detect_pan_presence() == PAN_ABSENT) {
        sm_ctx.pan_absent_count++;
        if (sm_ctx.pan_absent_count > PAN_DEBOUNCE_COUNT) {
            transition_to(STATE_NO_PAN);
            return;
        }
    } else {
        sm_ctx.pan_absent_count = 0;
    }

    /* User input */
    if (button_is_pressed(BUTTON_STOP)) {
        transition_to(STATE_COOLDOWN);
        return;
    }

    if (button_is_pressed(BUTTON_TEMP_UP)) {
        sm_ctx.target_temperature += 5.0f;
        if (sm_ctx.target_temperature > MAX_TEMP) {
            sm_ctx.target_temperature = MAX_TEMP;
        }
    }

    if (button_is_pressed(BUTTON_TEMP_DOWN)) {
        sm_ctx.target_temperature -= 5.0f;
        if (sm_ctx.target_temperature < MIN_TEMP) {
            sm_ctx.target_temperature = MIN_TEMP;
        }
    }

    /* Timer check */
    if (sm_ctx.cooking_timer_enabled && sm_ctx.cooking_time_ms == 0) {
        show_message_then_transition("COMPLETE", STATE_COOLDOWN);
        return;
    }

    /* Update display */
    display_update_temperature(current_temp);

    /* Feed watchdog */
    watchdog_feed();
}

/* ============================================================================
 * STATE_NO_PAN Implementation
 * ============================================================================ */

void state_no_pan_entry(void) {
    /* Immediately cut power */
    power_set_level(0);

    /* Alert user */
    display_show_message("PAN REMOVED");
    led_set_pattern(LED_BLINK_FAST);
    buzzer_beep(500);

    /* Start countdown */
    sm_ctx.countdown_timer_ms = NO_PAN_TIMEOUT_MS;

    /* Reset thermal mass estimation for new pan */
    thermal_mass_reset(&sm_ctx.thermal_mass);
    sm_ctx.thermal_mass_estimation_done = false;

    /* Set watchdog */
    watchdog_set_timeout(5000);
}

void state_no_pan_update(void) {
    /* Check if pan replaced */
    if (detect_pan_presence() == PAN_PRESENT) {
        /* Verify impedance matches (within 10%) */
        float current_impedance = get_pan_impedance();
        
        /* Guard against division by zero */
        if (sm_ctx.initial_pan_impedance <= 0.0f) {
            /* No valid initial impedance - accept any pan */
            transition_to(STATE_PREHEAT);
            return;
        }
        
        float impedance_error = fabsf(current_impedance - sm_ctx.initial_pan_impedance) /
                               sm_ctx.initial_pan_impedance;

        if (impedance_error < 0.10f) {
            /* Same pan: resume heating */
            transition_to(STATE_PREHEAT);
            return;
        } else {
            /* Different pan detected */
            show_message_then_transition("DIFFERENT PAN", STATE_COOLDOWN);
            return;
        }
    }

    /* Check timeout */
    if (sm_ctx.state_duration > sm_ctx.countdown_timer_ms) {
        transition_to(STATE_COOLDOWN);
        return;
    }

    /* Update countdown display */
    uint16_t seconds_remaining = (uint16_t)((sm_ctx.countdown_timer_ms - sm_ctx.state_duration) / 1000);
    display_update_countdown(seconds_remaining);

    /* Check for immediate cancel */
    if (button_is_pressed(BUTTON_STOP)) {
        transition_to(STATE_COOLDOWN);
        return;
    }

    /* Feed watchdog */
    watchdog_feed();
}

/* ============================================================================
 * STATE_COOLDOWN Implementation
 * ============================================================================ */

void state_cooldown_entry(void) {
    /* Disable all power */
    power_set_level(0);
    pwm_set_duty_cycle(0);

    /* Disable PLL */
    pll_disable();

    /* Maximum fan speed */
    fan_set_speed(FAN_SPEED_MAX);

    /* Record starting temperature */
    sm_ctx.cooldown_start_temp = read_heatsink_temperature();

    /* Visual feedback */
    display_show_message("COOLING");
    led_set_pattern(LED_BLINK_SLOW);

    /* Disable start button */
    button_set_enabled(BUTTON_START, false);

    /* Set watchdog */
    watchdog_set_timeout(2000);
}

void state_cooldown_update(void) {
    /* Read temperature */
    float current_temp = read_heatsink_temperature();

    /* Check if cool enough */
    if (current_temp < SAFE_IDLE_TEMP) {
        transition_to(STATE_IDLE);
        return;
    }

    /* Safety check: temperature should NOT rise during cooldown */
    if (current_temp > (sm_ctx.cooldown_start_temp + 5.0f)) {
        sm_ctx.fault_code = FAULT_COOLDOWN_OVERHEAT;
        transition_to(STATE_FAULT);
        return;
    }

    /* Update display */
    display_update_temperature(current_temp);

    /* Feed watchdog */
    watchdog_feed();
}

/* ============================================================================
 * STATE_FAULT Implementation
 * ============================================================================ */

void state_fault_entry(void) {
    /* EMERGENCY SHUTDOWN */
    power_set_level(0);
    pwm_disable_all();
    pll_disable();

    /* Maximum cooling */
    fan_set_speed(FAN_SPEED_MAX);

    /* Alert user */
    led_set_pattern(LED_FAULT);
    display_show_fault(sm_ctx.fault_code);
    buzzer_beep_continuous();

    /* Log to EEPROM */
    eeprom_log_fault(sm_ctx.fault_code, get_time_ms());

    /* Set watchdog */
    watchdog_set_timeout(5000);
}

void state_fault_update(void) {
    /* Ensure power stays off */
    power_set_level(0);

    /* Display fault info */
    display_show_message(state_machine_get_fault_string(sm_ctx.fault_code));

    /* Check for user reset */
    if (button_is_pressed(BUTTON_RESET)) {
        if (fault_cleared()) {
            /* Fault condition has cleared: reinitialize */
            sm_ctx.fault_code = FAULT_NONE;
            buzzer_stop();
            transition_to(STATE_INIT);
            return;
        } else {
            /* Fault persists */
            display_show_message("FAULT PERSISTS");
            buzzer_beep(1000);
        }
    }

    /* Monitor critical temperature even in fault */
    if (read_heatsink_temperature() > 125.0f) {
        trigger_hardware_shutdown();
    }

    /* Feed watchdog */
    watchdog_feed();
}
