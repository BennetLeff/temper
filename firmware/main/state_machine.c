/**
 * @file state_machine.c
 * @brief State machine implementation for induction cooker
 *
 * States are defined by STATE_LIST in state_machine.h.
 * Fault codes are defined by FAULT_LIST in state_machine.h.
 */

#include "state_machine.h"
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
#include "../components/safety/safety.h"

/* State machine context */
static struct {
    system_state_t current_state;
    system_state_t previous_state;
    fault_code_t fault_code;
    uint32_t state_entry_time;
    uint32_t state_duration;

    /* State-specific data */
    uint8_t pan_detect_confidence;
    uint8_t pan_absent_count;
    float initial_pan_impedance;
    float cooldown_start_temp;
    uint16_t countdown_timer_ms;

    /* User inputs */
    float target_temperature;
    uint32_t cooking_time_ms;
    bool cooking_timer_enabled;
    uint8_t intensity_level;  /**< Heat rate limiter (1-10) */
    
    /* Profile execution */
    profile_status_t profile;
    
    /* Non-blocking message display */
    bool message_pending;
    system_state_t message_next_state;
    uint32_t message_start_time;
    
    /* Last update timestamp for timer decrement */
    uint32_t last_update_time_ms;

    /* Thermal mass estimation */
    thermal_mass_handle_t thermal_mass;
    bool thermal_mass_estimation_done;

    /* Runaway interlock */
    bool runaway_latched;
    float last_pan_temp_c;
    uint32_t last_pan_temp_time_ms;
    uint8_t pan_temp_stuck_count;
    uint8_t heatsink_temp_stuck_count;
    float prev_stuck_check_temp;

} sm_ctx = {
    .current_state = STATE_INIT,
    .previous_state = STATE_INIT,
    .fault_code = FAULT_NONE,
    .target_temperature = 100.0f,
    .message_pending = false,
    .last_update_time_ms = 0,
};

/* Forward declarations - state handlers */
static void state_init_entry(void);
static void state_init_update(void);
static void state_idle_entry(void);
static void state_idle_update(void);
static void state_pan_det_entry(void);
static void state_pan_det_update(void);
static void state_preheat_entry(void);
static void state_preheat_update(void);
static void state_heating_entry(void);
static void state_heating_update(void);
static void state_no_pan_entry(void);
static void state_no_pan_update(void);
static void state_cooldown_entry(void);
static void state_cooldown_update(void);
static void state_fault_entry(void);
static void state_fault_update(void);
static void state_runaway_fault_entry(void);
static void state_runaway_fault_update(void);

/* Forward declarations - helpers */
void transition_to(system_state_t new_state);
static bool run_self_test(void);
static void check_safety_interlocks(void);
static void check_runaway_boundary(void);
static bool fault_cleared(void);
static void show_message_then_transition(const char *msg, system_state_t next_state);

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
    
    /* Reset profile */
    profile_init_status(&sm_ctx.profile);

    /* Reset message display state */
    sm_ctx.message_pending = false;
    sm_ctx.message_next_state = STATE_INIT;
    sm_ctx.message_start_time = 0;
    
    /* Reset timing */
    sm_ctx.last_update_time_ms = 0;
    
    /* Reset runaway interlock latch */
    sm_ctx.runaway_latched = false;

    /* Reset stuck-sensor counters */
    sm_ctx.pan_temp_stuck_count = 0;
    sm_ctx.heatsink_temp_stuck_count = 0;
    sm_ctx.prev_stuck_check_temp = -1.0f;

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
    
    /* Runaway boundary interlock: check before ALL state-specific logic.
     * This fires even during message display to ensure safety-critical
     * events preempt all normal operation. */
    check_runaway_boundary();
    
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
        case STATE_RUNAWAY_FAULT: state_runaway_fault_update(); break;
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

/* ============================================================================
 * STATE_INIT Implementation
 * ============================================================================ */

static void state_init_entry(void) {
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

static void state_init_update(void) {
    /* Run power-on self-test */
    bool post_passed = run_self_test();

    if (post_passed) {
        transition_to(STATE_IDLE);
    } else {
        sm_ctx.fault_code = FAULT_SELF_TEST_FAILED;
        transition_to(STATE_FAULT);
    }
}

static bool run_self_test(void) {
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
 * STATE_IDLE Implementation
 * ============================================================================ */

static void state_idle_entry(void) {
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

static void state_idle_update(void) {
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

static void state_pan_det_entry(void) {
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

static void state_pan_det_update(void) {
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

static void state_preheat_entry(void) {
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

static void state_preheat_update(void) {
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

static void state_heating_entry(void) {
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

static void state_heating_update(void) {
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

static void state_no_pan_entry(void) {
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

static void state_no_pan_update(void) {
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

static void state_cooldown_entry(void) {
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

static void state_cooldown_update(void) {
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

static void state_fault_entry(void) {
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

static void state_fault_update(void) {
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

/* ============================================================================
 * STATE_RUNAWAY_FAULT Implementation
 * ============================================================================ */

static void state_runaway_fault_entry(void) {
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

static void state_runaway_fault_update(void) {
    /* Dead-end state: power stays off, no button processing */
    /* Feed watchdog to prevent unwanted MCU reset */
    watchdog_feed();
}

/* ============================================================================
 * Helper Functions
 * ============================================================================ */

void transition_to(system_state_t new_state) {
    /* Runaway interlock: block all transitions once latched */
    if (sm_ctx.runaway_latched && new_state != STATE_RUNAWAY_FAULT) {
        return;
    }

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
        case STATE_RUNAWAY_FAULT: state_runaway_fault_entry(); break;
        default:
            sm_ctx.fault_code = FAULT_SELF_TEST_FAILED;
            transition_to(STATE_FAULT);
            break;
    }
}

static void check_safety_interlocks(void) {
    /* Over-temperature check */
    if (read_heatsink_temperature() > 100.0f) {
        sm_ctx.fault_code = FAULT_OVER_TEMP;
        transition_to(STATE_FAULT);
        return;
    }

    /* Over-current check — IGBT short (>50A) takes priority over over-current */
    if (read_dc_bus_current() > 50.0f) {
        sm_ctx.fault_code = FAULT_IGBT_SHORT;
        transition_to(STATE_FAULT);
        return;
    }
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

    /* ADC stuck check — identical pan temperature across consecutive reads
     * indicates a frozen sensor. Uses its own tracking separate from the
     * runaway rate-of-rise tracker (which updates every pass). */
    float pan_temp = read_pan_temperature();
    if (sm_ctx.prev_stuck_check_temp == pan_temp) {
        sm_ctx.pan_temp_stuck_count++;
        if (sm_ctx.pan_temp_stuck_count >= 49) {
            sm_ctx.fault_code = FAULT_ADC_STUCK;
            transition_to(STATE_FAULT);
            sm_ctx.prev_stuck_check_temp = -1.0f;
            sm_ctx.pan_temp_stuck_count = 0;
            return;
        }
    } else {
        sm_ctx.pan_temp_stuck_count = 0;
        sm_ctx.prev_stuck_check_temp = pan_temp;
    }
}

static void check_runaway_boundary(void) {
    /* If already latched, nothing to check */
    if (sm_ctx.runaway_latched) return;

    float temp = read_pan_temperature();
    uint32_t now = get_time_ms();

    /* NaN/infinite temperature → immediate breach */
    if (!isfinite(temp)) {
        sm_ctx.fault_code = FAULT_RUNAWAY_BOUNDARY;
        goto trigger_runaway;
    }

    /* Absolute temperature check */
    if (temp > g_config.runaway.max_absolute_temp_c) {
        sm_ctx.fault_code = FAULT_RUNAWAY_BOUNDARY;
        goto trigger_runaway;
    }

    /* Rate-of-rise check (requires at least one prior reading) */
    if (sm_ctx.last_pan_temp_time_ms > 0) {
        uint32_t dt_ms = now - sm_ctx.last_pan_temp_time_ms;
        if (dt_ms >= 10) {  /* Minimum 10ms to avoid noise amplification */
            float dt_s = dt_ms / 1000.0f;
            float rate = (temp - sm_ctx.last_pan_temp_c) / dt_s;
            if (rate > g_config.runaway.max_temp_rise_rate_c_per_s) {
                sm_ctx.fault_code = FAULT_RUNAWAY_BOUNDARY;
                goto trigger_runaway;
            }
        }
    }

    /* Store for next iteration */
    sm_ctx.last_pan_temp_c = temp;
    sm_ctx.last_pan_temp_time_ms = now;
    return;

trigger_runaway:
    /* Hardware-level cut: assert GPIO to OR gate */
#ifdef ESP_PLATFORM
    gpio_set_level(RUNAWAY_CUT_GPIO, 1);
#endif
    /* Software-level cut: disable PWM and power */
    trigger_hardware_shutdown();

    sm_ctx.runaway_latched = true;
    transition_to(STATE_RUNAWAY_FAULT);
}

void state_machine_reset_temp_baseline(void) {
    sm_ctx.last_pan_temp_c = read_pan_temperature();
    sm_ctx.last_pan_temp_time_ms = get_time_ms();
}

void state_machine_reset_stuck_tracking(void) {
    sm_ctx.prev_stuck_check_temp = -1.0f;
    sm_ctx.pan_temp_stuck_count = 0;
}

static bool fault_cleared(void) {
    float rtd_resistance;
    
    switch (sm_ctx.fault_code) {
        case FAULT_OVER_TEMP:
            return (read_heatsink_temperature() < 70.0f);

        case FAULT_FAN_FAILURE:
            return is_fan_running();

        case FAULT_PROBE_OPEN:
        case FAULT_PROBE_SHORT:
            rtd_resistance = read_rtd_resistance();
            return (rtd_resistance > 50.0f && rtd_resistance < 500.0f);

        case FAULT_SELF_TEST_FAILED:
            return run_self_test();

        case FAULT_RUNAWAY_BOUNDARY:
            return false;  /* Never clearable by software */

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
static void show_message_then_transition(const char *msg, system_state_t next_state) {
    display_show_message(msg);
    sm_ctx.message_pending = true;
    sm_ctx.message_next_state = next_state;
    sm_ctx.message_start_time = get_time_ms();
}
