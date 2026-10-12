# HAL Component CMakeLists.txt
# Hardware Abstraction Layer for Temper Induction Cooker
#
# This component is registered as "temper_hal" and its sources live in ../hal. The directory
# components/hal must NOT contain a CMakeLists.txt: ESP-IDF names a component after its directory,
# so a project component called "hal" silently replaces ESP-IDF's own "hal" component and breaks
# every IDF component that includes hal/*.h (e.g. mbedtls: hal/sha_types.h not found).
set(TEMPER_HAL_DIR "${CMAKE_CURRENT_SOURCE_DIR}/../hal")

# Determine which implementation to use based on build target
# ESP_PLATFORM (set by idf.py) rather than CONFIG_IDF_TARGET: sdkconfig variables are not yet
# defined during ESP-IDF's early requirement-expansion pass, which is where REQUIRES is read.
if(ESP_PLATFORM)
    # Building for ESP32 - use ESP32 HAL implementations
    set(HAL_IMPL_DIR "${TEMPER_HAL_DIR}/esp32")
    set(HAL_SOURCES
        "${HAL_IMPL_DIR}/hal_init.c"
        "${HAL_IMPL_DIR}/hal_gpio_esp32.c"
        "${HAL_IMPL_DIR}/hal_adc_esp32.c"
        "${HAL_IMPL_DIR}/hal_pwm_esp32.c"
        "${HAL_IMPL_DIR}/hal_spi_esp32.c"
        "${HAL_IMPL_DIR}/hal_timer_esp32.c"
        "${HAL_IMPL_DIR}/controller_board_esp32.c"
        "${TEMPER_HAL_DIR}/controller_board.c"
    )
    set(HAL_REQUIRES driver esp_timer esp_adc)
else()
    # Building for host (testing) - use mock implementations
    set(HAL_IMPL_DIR "${TEMPER_HAL_DIR}/mock")
    set(HAL_SOURCES
        "${HAL_IMPL_DIR}/hal_init_mock.c"
        "${HAL_IMPL_DIR}/mock_gpio.c"
        "${HAL_IMPL_DIR}/mock_adc.c"
        "${HAL_IMPL_DIR}/mock_pwm.c"
        "${HAL_IMPL_DIR}/mock_spi.c"
        "${HAL_IMPL_DIR}/mock_timer.c"
        "${TEMPER_HAL_DIR}/controller_board.c"
    )
    set(HAL_REQUIRES "")
endif()

idf_component_register(
    SRCS ${HAL_SOURCES}
    INCLUDE_DIRS "${TEMPER_HAL_DIR}/include"
    REQUIRES ${HAL_REQUIRES}
)

# For non-IDF builds (native host testing)
if(NOT ESP_PLATFORM)
    # Enable mock mode define
    target_compile_definitions(${COMPONENT_LIB} PUBLIC HAL_MOCK_MODE=1)
endif()
