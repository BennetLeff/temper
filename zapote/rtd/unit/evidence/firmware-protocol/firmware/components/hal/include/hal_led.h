/**
 * @file hal_led.h
 * @brief LED Hardware Abstraction Layer with PWM and Pattern Support
 */

#ifndef HAL_LED_H
#define HAL_LED_H

#include "hal_types.h"

#ifdef __cplusplus
extern "C" {
#endif

/**
 * @brief LED identifiers
 */
typedef enum {
    HAL_LED_OCP,
    HAL_LED_OVP,
    HAL_LED_THERMAL,
    HAL_LED_WDT,
    HAL_LED_MASTER,
    HAL_LED_COUNT
} hal_led_id_t;

/**
 * @brief LED patterns
 */
typedef enum {
    HAL_LED_PATTERN_OFF,
    HAL_LED_PATTERN_ON,
    HAL_LED_PATTERN_BLINK_SLOW,  /**< 1 Hz */
    HAL_LED_PATTERN_BLINK_FAST,  /**< 4 Hz */
    HAL_LED_PATTERN_PULSE,       /**< Breathing effect */
    HAL_LED_PATTERN_DOUBLE_BLINK /**< Cooldown pattern */
} hal_led_pattern_t;

/**
 * @brief LED operations interface
 */
typedef struct {
    hal_status_t (*init)(hal_led_id_t led, hal_pin_t pin);
    hal_status_t (*set_brightness)(hal_led_id_t led, float brightness_percent);
    hal_status_t (*set_pattern)(hal_led_id_t led, hal_led_pattern_t pattern);
    void (*update)(void); /**< Call periodically for animation */
    hal_status_t (*deinit)(hal_led_id_t led);
} hal_led_ops_t;

extern const hal_led_ops_t *hal_led;

void hal_led_set_ops(const hal_led_ops_t *ops);

#ifdef __cplusplus
}
#endif

#endif /* HAL_LED_H */
