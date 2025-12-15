# ============================================================================
# Temper Firmware Test Build
# ============================================================================
# Host-based unit testing using Unity test framework
# 
# Build:   cmake -B build && cmake --build build
# Run:     ./build/test_runner
# Clean:   rm -rf build
# ============================================================================

cmake_minimum_required(VERSION 3.16)
project(temper_tests C)

set(CMAKE_C_STANDARD 99)
set(CMAKE_C_STANDARD_REQUIRED ON)

# Enable warnings
add_compile_options(-Wall -Wextra -Wpedantic)

# Debug build for tests
set(CMAKE_BUILD_TYPE Debug)

# ============================================================================
# Configuration
# ============================================================================

# Define that we're building for host (not ESP32)
add_definitions(-DHOST_BUILD)

# Induction cooker specifications (from design docs)
add_definitions(
    -DOCP_THRESHOLD_AMPS=50.0f
    -DOVP_THRESHOLD_VOLTS=390.0f
    -DTHERMAL_SHUTDOWN_C=85.0f
    -DWATCHDOG_TIMEOUT_MS=1600
    -DTEMP_PRECISION_C=0.5f
    -DFREQ_MIN_KHZ=38.0f
    -DFREQ_MAX_KHZ=50.0f
    -DDEAD_TIME_NS=500
    -DPAN_VALID_MIN_AMPS=3.0f
    -DPAN_VALID_MAX_AMPS=15.0f
    -DPAN_NO_LOAD_AMPS=20.0f
)

# ============================================================================
# Source files
# ============================================================================

# Unity test framework
set(UNITY_SOURCES
    ${CMAKE_CURRENT_SOURCE_DIR}/unity/unity.c
)

# HAL mock implementations
set(MOCK_HAL_SOURCES
    ${CMAKE_CURRENT_SOURCE_DIR}/../components/hal/mock/hal_init_mock.c
    ${CMAKE_CURRENT_SOURCE_DIR}/../components/hal/mock/mock_gpio.c
    ${CMAKE_CURRENT_SOURCE_DIR}/../components/hal/mock/mock_adc.c
    ${CMAKE_CURRENT_SOURCE_DIR}/../components/hal/mock/mock_pwm.c
    ${CMAKE_CURRENT_SOURCE_DIR}/../components/hal/mock/mock_spi.c
    ${CMAKE_CURRENT_SOURCE_DIR}/../components/hal/mock/mock_timer.c
)

# Firmware components to test (the actual production code)
# Note: state_machine.c has unique stub requirements and is tested separately
set(FIRMWARE_SOURCES
    ${CMAKE_CURRENT_SOURCE_DIR}/../components/control/pid_control.c
    ${CMAKE_CURRENT_SOURCE_DIR}/../components/safety/safety.c
)

# Test source files (excluding state_machine which is tested separately)
set(TEST_SOURCES
    ${CMAKE_CURRENT_SOURCE_DIR}/test_main.c
    ${CMAKE_CURRENT_SOURCE_DIR}/test_pid_control.c
    ${CMAKE_CURRENT_SOURCE_DIR}/test_safety.c
)

# ============================================================================
# Include directories
# ============================================================================

set(INCLUDE_DIRS
    ${CMAKE_CURRENT_SOURCE_DIR}
    ${CMAKE_CURRENT_SOURCE_DIR}/unity
    ${CMAKE_CURRENT_SOURCE_DIR}/../components/hal/include
    ${CMAKE_CURRENT_SOURCE_DIR}/../components/hal/mock
    ${CMAKE_CURRENT_SOURCE_DIR}/../components/control
    ${CMAKE_CURRENT_SOURCE_DIR}/../components/safety
    ${CMAKE_CURRENT_SOURCE_DIR}/../main
)

# ============================================================================
# Test executable
# ============================================================================

add_executable(test_runner
    ${UNITY_SOURCES}
    ${MOCK_HAL_SOURCES}
    ${FIRMWARE_SOURCES}
    ${TEST_SOURCES}
)

target_include_directories(test_runner PRIVATE ${INCLUDE_DIRS})

# Link math library
target_link_libraries(test_runner m)

# ============================================================================
# Individual test targets (for selective testing)
# ============================================================================

# State machine tests only (uses custom stubs, not mock HAL)
add_executable(test_state_machine_only
    ${UNITY_SOURCES}
    ${CMAKE_CURRENT_SOURCE_DIR}/../main/state_machine.c
    ${CMAKE_CURRENT_SOURCE_DIR}/state_machine_stubs.c
    ${CMAKE_CURRENT_SOURCE_DIR}/test_state_machine.c
    ${CMAKE_CURRENT_SOURCE_DIR}/test_main_state_machine.c
)
target_include_directories(test_state_machine_only PRIVATE ${INCLUDE_DIRS})
target_link_libraries(test_state_machine_only m)

# PID controller tests only
add_executable(test_pid_only
    ${UNITY_SOURCES}
    ${CMAKE_CURRENT_SOURCE_DIR}/../components/control/pid_control.c
    ${CMAKE_CURRENT_SOURCE_DIR}/test_pid_control.c
    ${CMAKE_CURRENT_SOURCE_DIR}/test_main_pid.c
)
target_include_directories(test_pid_only PRIVATE ${INCLUDE_DIRS})
target_link_libraries(test_pid_only m)

# Safety tests only
add_executable(test_safety_only
    ${UNITY_SOURCES}
    ${MOCK_HAL_SOURCES}
    ${CMAKE_CURRENT_SOURCE_DIR}/../components/safety/safety.c
    ${CMAKE_CURRENT_SOURCE_DIR}/test_safety.c
    ${CMAKE_CURRENT_SOURCE_DIR}/test_main_safety.c
)
target_include_directories(test_safety_only PRIVATE ${INCLUDE_DIRS})
target_link_libraries(test_safety_only m)

# Pan detection tests only
add_executable(test_pan_detection_only
    ${UNITY_SOURCES}
    ${CMAKE_CURRENT_SOURCE_DIR}/pan_detect_logic.c
    ${CMAKE_CURRENT_SOURCE_DIR}/test_pan_detection.c
    ${CMAKE_CURRENT_SOURCE_DIR}/test_main_pan_detection.c
)
target_include_directories(test_pan_detection_only PRIVATE ${INCLUDE_DIRS})
target_link_libraries(test_pan_detection_only m)

# PLL control tests only
add_executable(test_pll_only
    ${UNITY_SOURCES}
    ${CMAKE_CURRENT_SOURCE_DIR}/../components/control/pll_control.c
    ${CMAKE_CURRENT_SOURCE_DIR}/test_pll_control.c
    ${CMAKE_CURRENT_SOURCE_DIR}/test_main_pll.c
)
target_include_directories(test_pll_only PRIVATE ${INCLUDE_DIRS})
target_link_libraries(test_pll_only m)

# ============================================================================
# CTest integration
# ============================================================================

enable_testing()
add_test(NAME all_tests COMMAND test_runner)
add_test(NAME state_machine_tests COMMAND test_state_machine_only)
add_test(NAME pid_tests COMMAND test_pid_only)
add_test(NAME safety_tests COMMAND test_safety_only)
add_test(NAME pan_detection_tests COMMAND test_pan_detection_only)
add_test(NAME pll_tests COMMAND test_pll_only)

# ============================================================================
# Custom targets
# ============================================================================

# Run all tests
add_custom_target(run_tests
    COMMAND ${CMAKE_CURRENT_BINARY_DIR}/test_runner
    DEPENDS test_runner
    COMMENT "Running all tests..."
)

# Run tests with verbose output
add_custom_target(run_tests_verbose
    COMMAND ${CMAKE_CTEST_COMMAND} --verbose
    DEPENDS test_runner test_state_machine_only test_pid_only test_safety_only
    COMMENT "Running all tests with verbose output..."
)
