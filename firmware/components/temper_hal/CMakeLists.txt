# temper_hal: Hardware Abstraction Layer for the Temper induction cooker.
#
# Named temper_hal, not hal: a project component named `hal` replaces
# ESP-IDF's own `hal` component, after which driver/gpio.h, mbedtls, etc.
# cannot find hal/*_types.h and the target does not build.
#
# This file is only read by the ESP-IDF build, so it registers the ESP32
# implementations unconditionally. The host tests compile the mock/
# sources directly (firmware/test/CMakeLists.txt) and never load this file.
# (An earlier `if(CONFIG_IDF_TARGET)` switch here was evaluated without
# sdkconfig during IDF's requirement-expansion pass, so the ESP32 sources
# were registered with the mock branch's empty REQUIRES.)

idf_component_register(
    SRCS
        "esp32/hal_init.c"
        "esp32/hal_gpio_esp32.c"
        "esp32/hal_adc_esp32.c"
        "esp32/hal_pwm_esp32.c"
        "esp32/hal_spi_esp32.c"
        "esp32/hal_timer_esp32.c"
    INCLUDE_DIRS "include"
    REQUIRES
        esp_driver_gpio
        esp_driver_gptimer
        esp_driver_mcpwm
        esp_driver_spi
        esp_adc
        esp_timer
)
