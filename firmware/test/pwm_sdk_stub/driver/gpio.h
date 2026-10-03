#pragma once
#include "mcpwm_prelude.h"
#define GPIO_MODE_OUTPUT 1
#define GPIO_IS_VALID_OUTPUT_GPIO(pin) ((pin)>=0 && (pin)<40)
esp_err_t gpio_reset_pin(int);
esp_err_t gpio_set_level(int,int);
esp_err_t gpio_set_direction(int,int);
esp_err_t gpio_hold_en(int);
esp_err_t gpio_hold_dis(int);
