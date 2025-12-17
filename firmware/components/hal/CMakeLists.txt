# HAL Component CMakeLists.txt
# Hardware Abstraction Layer for Temper Induction Cooker

# Determine which implementation to use based on build target
if(CONFIG_IDF_TARGET)
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
    set(HAL_REQUIRES driver esp_timer)
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
if(NOT CONFIG_IDF_TARGET)
    # Enable mock mode define
    target_compile_definitions(${COMPONENT_LIB} PUBLIC HAL_MOCK_MODE=1)
endif()
