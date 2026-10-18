/**
 * @file hal_led_mock.c
 * @brief Mock implementation of the LED HAL
 */

#include "hal_led.h"
#include <string.h>

typedef struct {
    bool initialized;
    hal_pin_t pin;
    float brightness;
    hal_led_pattern_t pattern;
} mock_led_t;

static mock_led_t s_leds[HAL_LED_COUNT];

static hal_status_t mock_led_init(hal_led_id_t led, hal_pin_t pin) {
    if (led >= HAL_LED_COUNT) return HAL_ERROR_INVALID_ARG;
    s_leds[led].initialized = true;
    s_leds[led].pin = pin;
    s_leds[led].brightness = 0.0f;
    s_leds[led].pattern = HAL_LED_PATTERN_OFF;
    return HAL_OK;
}

static hal_status_t mock_led_set_brightness(hal_led_id_t led, float brightness) {
    if (led >= HAL_LED_COUNT) return HAL_ERROR_INVALID_ARG;
    s_leds[led].brightness = brightness;
    return HAL_OK;
}

static hal_status_t mock_led_set_pattern(hal_led_id_t led, hal_led_pattern_t pattern) {
    if (led >= HAL_LED_COUNT) return HAL_ERROR_INVALID_ARG;
    s_leds[led].pattern = pattern;
    return HAL_OK;
}

static void mock_led_update(void) {}

static hal_status_t mock_led_deinit(hal_led_id_t led) {
    if (led >= HAL_LED_COUNT) return HAL_ERROR_INVALID_ARG;
    s_leds[led].initialized = false;
    return HAL_OK;
}

const hal_led_ops_t hal_led_mock_ops = {
    .init = mock_led_init,
    .set_brightness = mock_led_set_brightness,
    .set_pattern = mock_led_set_pattern,
    .update = mock_led_update,
    .deinit = mock_led_deinit
};

const hal_led_ops_t *hal_led = &hal_led_mock_ops;

void hal_led_set_ops(const hal_led_ops_t *ops) {
    hal_led = ops;
}

// Test helpers
hal_led_pattern_t hal_led_mock_get_pattern(hal_led_id_t led) {
    if (led >= HAL_LED_COUNT) return HAL_LED_PATTERN_OFF;
    return s_leds[led].pattern;
}
