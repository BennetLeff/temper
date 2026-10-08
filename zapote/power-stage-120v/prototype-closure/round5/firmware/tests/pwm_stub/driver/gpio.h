#pragma once
#include "mcpwm_prelude.h"
#define GPIO_MODE_DISABLE 0
#define GPIO_MODE_OUTPUT 1
#define GPIO_PULLDOWN_ENABLE 1
typedef struct { uint64_t pin_bit_mask; int mode,pull_up_en,pull_down_en; } gpio_config_t;
esp_err_t gpio_config(const gpio_config_t*);
esp_err_t gpio_reset_pin(int);
esp_err_t gpio_set_level(int,int);
esp_err_t gpio_set_direction(int,int);
esp_err_t gpio_pullup_dis(int);
esp_err_t gpio_pulldown_en(int);
