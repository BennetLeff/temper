/**
 * @file ui.c
 * @brief Implementation of the multi-mode encoder UI
 */

#include "ui.h"
#include "hal_encoder.h"
#include "hal_led.h"
#include "state_machine.h"
#include <string.h>

#define LONG_PRESS_MS 2000
#define DEBOUNCE_MS 50

typedef struct {
    ui_state_t state;
    setting_item_t selected_setting;
    int32_t last_encoder_count;
    uint32_t button_press_start_ms;
    bool button_was_pressed;
    float current_temp_setpoint;
    uint8_t current_intensity;
} ui_ctx_t;

static ui_ctx_t ui;

extern uint32_t hal_get_tick_ms(void);

void ui_init(void) {
    memset(&ui, 0, sizeof(ui_ctx_t));
    ui.state = UI_STATE_NORMAL;
    ui.selected_setting = SETTING_TEMP;
    ui.current_temp_setpoint = 100.0f; // Default
    ui.current_intensity = 5;
    
    if (hal_encoder) {
        hal_encoder->reset_count();
        ui.last_encoder_count = hal_encoder->get_count();
    }

    if (hal_led) {
        for (int i = 0; i < HAL_LED_COUNT; i++) {
            hal_led->init(i, HAL_PIN_INVALID); // Pin assignment handled by HAL
        }
    }
}

static void ui_update_leds(void) {
    if (!hal_led) return;

    system_state_t sys_state = state_machine_get_state();
    fault_code_t fault = state_machine_get_fault();

    // Reset all LEDs to OFF initially (or dim)
    for (int i = 0; i < HAL_LED_MASTER; i++) {
        hal_led->set_pattern(i, HAL_LED_PATTERN_OFF);
    }

    // 1. Handle Faults (Highest Priority)
    if (sys_state == STATE_FAULT || fault != FAULT_NONE) {
        hal_led->set_pattern(HAL_LED_MASTER, HAL_LED_PATTERN_BLINK_FAST);
        
        // Indicate specific fault
        switch (fault) {
            case FAULT_OVER_CURRENT: hal_led->set_pattern(HAL_LED_OCP, HAL_LED_PATTERN_ON); break;
            case FAULT_OVER_TEMP:    hal_led->set_pattern(HAL_LED_THERMAL, HAL_LED_PATTERN_ON); break;
            case FAULT_FAN_FAILURE:  hal_led->set_pattern(HAL_LED_WDT, HAL_LED_PATTERN_ON); break; // Reusing WDT for fan
            case FAULT_WATCHDOG_RESET: hal_led->set_pattern(HAL_LED_WDT, HAL_LED_PATTERN_ON); break;
            default: break;
        }
        return;
    }

    // 2. Handle System States
    switch (sys_state) {
        case STATE_IDLE:
            hal_led->set_pattern(HAL_LED_MASTER, HAL_LED_PATTERN_OFF);
            break;
        case STATE_PAN_DET:
            hal_led->set_pattern(HAL_LED_MASTER, HAL_LED_PATTERN_BLINK_SLOW);
            break;
        case STATE_PREHEAT:
            hal_led->set_pattern(HAL_LED_MASTER, HAL_LED_PATTERN_BLINK_FAST);
            break;
        case STATE_HEATING:
            hal_led->set_pattern(HAL_LED_MASTER, HAL_LED_PATTERN_ON);
            break;
        case STATE_COOLDOWN:
            hal_led->set_pattern(HAL_LED_MASTER, HAL_LED_PATTERN_DOUBLE_BLINK);
            break;
        default:
            hal_led->set_pattern(HAL_LED_MASTER, HAL_LED_PATTERN_OFF);
            break;
    }
}

static void handle_rotation(int32_t delta) {
    if (delta == 0) return;

    // TODO: Implement acceleration based on delta magnitude or timing
    // For now, simple 1:1 or fixed boost
    int32_t effective_delta = delta;
    if (delta > 5 || delta < -5) effective_delta *= 5;
    if (delta > 10 || delta < -10) effective_delta *= 10;

    switch (ui.state) {
        case UI_STATE_NORMAL:
            ui.current_temp_setpoint += (float)effective_delta;
            if (ui.current_temp_setpoint < 30.0f) ui.current_temp_setpoint = 30.0f;
            if (ui.current_temp_setpoint > 250.0f) ui.current_temp_setpoint = 250.0f;
            state_machine_set_target_temp(ui.current_temp_setpoint);
            break;

        case UI_STATE_SETTINGS:
            // Cycle through menu items
            if (delta > 0) {
                ui.selected_setting = (ui.selected_setting + 1) % SETTING_COUNT;
            } else {
                ui.selected_setting = (ui.selected_setting + SETTING_COUNT - 1) % SETTING_COUNT;
            }
            break;

        case UI_STATE_EDIT:
            if (ui.selected_setting == SETTING_TEMP) {
                ui.current_temp_setpoint += (float)effective_delta;
                if (ui.current_temp_setpoint < 30.0f) ui.current_temp_setpoint = 30.0f;
                if (ui.current_temp_setpoint > 250.0f) ui.current_temp_setpoint = 250.0f;
                state_machine_set_target_temp(ui.current_temp_setpoint);
            } else if (ui.selected_setting == SETTING_INTENSITY) {
                int32_t new_intensity = (int32_t)ui.current_intensity + delta;
                if (new_intensity < 1) new_intensity = 1;
                if (new_intensity > 10) new_intensity = 10;
                ui.current_intensity = (uint8_t)new_intensity;
                state_machine_set_intensity(ui.current_intensity);
            }
            break;
    }
}

static void handle_button_press(bool long_press) {
    switch (ui.state) {
        case UI_STATE_NORMAL:
            if (long_press) {
                ui.state = UI_STATE_SETTINGS;
            } else {
                // Toggle start/stop
                if (state_machine_get_state() == STATE_IDLE) {
                    state_machine_force_state(STATE_PAN_DET);
                } else {
                    state_machine_force_state(STATE_COOLDOWN);
                }
            }
            break;

        case UI_STATE_SETTINGS:
            if (long_press) {
                ui.state = UI_STATE_NORMAL;
            } else {
                ui.state = UI_STATE_EDIT;
            }
            break;

        case UI_STATE_EDIT:
            if (long_press) {
                ui.state = UI_STATE_NORMAL;
            } else {
                ui.state = UI_STATE_SETTINGS;
            }
            break;
    }
}

void ui_update(void) {
    if (!hal_encoder) return;

    // 1. Handle Rotation
    int32_t current_count = hal_encoder->get_count();
    int32_t delta = current_count - ui.last_encoder_count;
    if (delta != 0) {
        handle_rotation(delta);
        ui.last_encoder_count = current_count;
    }

    // 2. Handle Button
    bool pressed = hal_encoder->get_button_state();
    uint32_t now = hal_get_tick_ms();

    if (pressed && !ui.button_was_pressed) {
        // Just pressed
        ui.button_press_start_ms = now;
        ui.button_was_pressed = true;
    } else if (!pressed && ui.button_was_pressed) {
        // Just released
        uint32_t duration = now - ui.button_press_start_ms;
        if (duration > DEBOUNCE_MS) {
            handle_button_press(duration >= LONG_PRESS_MS);
        }
        ui.button_was_pressed = false;
    } else if (pressed && ui.button_was_pressed) {
        // Still pressed, check for long press while held
        if (now - ui.button_press_start_ms >= LONG_PRESS_MS) {
            // Optional: trigger long press immediately when threshold reached
            // but we need to avoid re-triggering. 
            // For now, we only handle on release or simplify.
        }
    }

    // 3. Update LEDs
    ui_update_leds();
}

ui_state_t ui_get_state(void) {
    return ui.state;
}

setting_item_t ui_get_selected_setting(void) {
    return ui.selected_setting;
}
