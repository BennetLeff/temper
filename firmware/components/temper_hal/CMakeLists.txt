# HAL Component CMakeLists.txt
# Hardware Abstraction Layer for Temper Induction Cooker
#
# COMPONENT NAME: this component is `temper_hal`, not `hal`.
# ESP-IDF ships a core component literally named `hal` (esp-idf/components/hal),
# which provides `hal/aes_types.h`, `hal/sha_types.h`, `hal/efuse_hal.h` and
# friends. A project component takes precedence over an IDF component of the
# same name, so while this directory was named `components/hal` it *replaced*
# IDF's core `hal` for the whole build -- mbedtls, esp_hw_support and esp_system
# then failed to compile because those headers had vanished. No IDF project may
# define a component named `hal`. Do not rename this directory back.
#
# BUILD SELECTION: the ESP32-vs-mock choice below is keyed on `ESP_PLATFORM`,
# NOT on `CONFIG_IDF_TARGET`. `idf.py` passes -DESP_PLATFORM=1 on the cmake
# command line, so it is set from the first configure step onward. `CONFIG_*`
# variables are NOT: they only exist after sdkconfig has been generated, which
# happens *after* IDF's early requirements-expansion pass has already read this
# file. Keying on CONFIG_IDF_TARGET therefore selected the mock branch during
# requirements expansion and set HAL_REQUIRES to the empty string, so the ESP32
# sources were later compiled with no `driver` / `esp_timer` include paths and
# every `driver/gpio.h`-style include failed.

if(ESP_PLATFORM)
    # Building for ESP32 - use ESP32 HAL implementations
    set(HAL_IMPL_DIR "${CMAKE_CURRENT_SOURCE_DIR}/esp32")
    set(HAL_SOURCES
        "${HAL_IMPL_DIR}/hal_init.c"
        "${HAL_IMPL_DIR}/hal_gpio_esp32.c"
        "${HAL_IMPL_DIR}/hal_adc_esp32.c"
        "${HAL_IMPL_DIR}/hal_pwm_esp32.c"
        "${HAL_IMPL_DIR}/hal_spi_esp32.c"
        "${HAL_IMPL_DIR}/hal_timer_esp32.c"
    )
    set(HAL_REQUIRES driver esp_timer esp_adc)
else()
    # Building for host (testing) - use mock implementations
    set(HAL_IMPL_DIR "${CMAKE_CURRENT_SOURCE_DIR}/mock")
    set(HAL_SOURCES
        "${HAL_IMPL_DIR}/hal_init_mock.c"
        "${HAL_IMPL_DIR}/mock_gpio.c"
        "${HAL_IMPL_DIR}/mock_adc.c"
        "${HAL_IMPL_DIR}/mock_pwm.c"
        "${HAL_IMPL_DIR}/mock_spi.c"
        "${HAL_IMPL_DIR}/mock_timer.c"
    )
    set(HAL_REQUIRES "")
endif()

idf_component_register(
    SRCS ${HAL_SOURCES}
    INCLUDE_DIRS "include"
    REQUIRES ${HAL_REQUIRES}
)

# For non-IDF builds (native host testing)
if(NOT ESP_PLATFORM)
    # Enable mock mode define
    target_compile_definitions(${COMPONENT_LIB} PUBLIC HAL_MOCK_MODE=1)
endif()
