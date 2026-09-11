#include "unity.h"
#include "ui.h"
#include "hal_encoder.h"
#include "hal_led.h"
#include "state_machine.h"

// Mock functions
extern void hal_encoder_mock_set_count(int32_t count);
extern void hal_encoder_mock_set_button(bool pressed);
extern hal_led_pattern_t hal_led_mock_get_pattern(hal_led_id_t led);

static uint32_t mock_tick_ms = 0;
uint32_t hal_get_tick_ms(void) { return mock_tick_ms; }

static float last_target_temp = 0;
void state_machine_set_target_temp(float temp) { last_target_temp = temp; }

static system_state_t current_system_state = STATE_IDLE;
system_state_t state_machine_get_state(void) { return current_system_state; }

static fault_code_t current_fault = FAULT_NONE;
fault_code_t state_machine_get_fault(void) { return current_fault; }

static system_state_t last_forced_state = STATE_INIT;
void state_machine_force_state(system_state_t s) { last_forced_state = s; }

void state_machine_set_intensity(uint8_t level) {}

void setUp(void) {
    mock_tick_ms = 0;
    current_system_state = STATE_IDLE;
    current_fault = FAULT_NONE;
    ui_init();
    hal_encoder_mock_set_count(0);
    hal_encoder_mock_set_button(false);
}

void tearDown(void) {}

void test_ui_init(void) {
    TEST_ASSERT_EQUAL(UI_STATE_NORMAL, ui_get_state());
}

void test_ui_led_state_indication(void) {
    // 1. Idle
    current_system_state = STATE_IDLE;
    ui_update();
    TEST_ASSERT_EQUAL(HAL_LED_PATTERN_OFF, hal_led_mock_get_pattern(HAL_LED_MASTER));
    
    // 2. Pan Detection
    current_system_state = STATE_PAN_DET;
    ui_update();
    TEST_ASSERT_EQUAL(HAL_LED_PATTERN_BLINK_SLOW, hal_led_mock_get_pattern(HAL_LED_MASTER));
    
    // 3. Heating
    current_system_state = STATE_HEATING;
    ui_update();
    TEST_ASSERT_EQUAL(HAL_LED_PATTERN_ON, hal_led_mock_get_pattern(HAL_LED_MASTER));
}

void test_ui_led_fault_indication(void) {
    // Over-current fault
    current_system_state = STATE_FAULT;
    current_fault = FAULT_OVER_CURRENT;
    ui_update();
    
    TEST_ASSERT_EQUAL(HAL_LED_PATTERN_BLINK_FAST, hal_led_mock_get_pattern(HAL_LED_MASTER));
    TEST_ASSERT_EQUAL(HAL_LED_PATTERN_ON, hal_led_mock_get_pattern(HAL_LED_OCP));
}

void test_ui_temperature_adjustment(void) {
    // Start at 100C
    hal_encoder_mock_set_count(5); // +5 clicks
    ui_update();
    
    TEST_ASSERT_EQUAL_FLOAT(105.0f, last_target_temp);
    
    hal_encoder_mock_set_count(3); // -2 delta from last 5
    ui_update();
    TEST_ASSERT_EQUAL_FLOAT(103.0f, last_target_temp);
}

void test_ui_settings_transition(void) {
    // Simulate long press
    hal_encoder_mock_set_button(true);
    ui_update();
    
    mock_tick_ms += 2100; // > 2000ms
    hal_encoder_mock_set_button(false);
    ui_update();
    
    TEST_ASSERT_EQUAL(UI_STATE_SETTINGS, ui_get_state());
}

void test_ui_menu_cycling(void) {
    // Go to settings
    test_ui_settings_transition();
    
    TEST_ASSERT_EQUAL(SETTING_TEMP, ui_get_selected_setting());
    
    hal_encoder_mock_set_count(1); // +1 click
    ui_update();
    TEST_ASSERT_EQUAL(SETTING_INTENSITY, ui_get_selected_setting());
    
    hal_encoder_mock_set_count(2); // +1 click
    ui_update();
    TEST_ASSERT_EQUAL(SETTING_TIMER, ui_get_selected_setting());
}
