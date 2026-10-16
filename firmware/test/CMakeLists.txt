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
    ${CMAKE_CURRENT_SOURCE_DIR}/../components/temper_hal/mock/hal_init_mock.c
    ${CMAKE_CURRENT_SOURCE_DIR}/../components/temper_hal/mock/mock_gpio.c
    ${CMAKE_CURRENT_SOURCE_DIR}/../components/temper_hal/mock/mock_adc.c
    ${CMAKE_CURRENT_SOURCE_DIR}/../components/temper_hal/mock/mock_pwm.c
    ${CMAKE_CURRENT_SOURCE_DIR}/../components/temper_hal/mock/mock_spi.c
    ${CMAKE_CURRENT_SOURCE_DIR}/../components/temper_hal/mock/mock_timer.c
)

# Firmware components to test (the actual production code)
# Note: state_machine.c has unique stub requirements and is tested separately
set(FIRMWARE_SOURCES
    ${CMAKE_CURRENT_SOURCE_DIR}/../components/control/pid_control.c
    ${CMAKE_CURRENT_SOURCE_DIR}/../components/control/low_temp_control.c
    ${CMAKE_CURRENT_SOURCE_DIR}/../components/control/pll_control.c
    ${CMAKE_CURRENT_SOURCE_DIR}/../components/control/zvs_monitor.c
    ${CMAKE_CURRENT_SOURCE_DIR}/../components/safety/safety.c
)

# Test source files (excluding state_machine which is tested separately)
set(TEST_SOURCES
    ${CMAKE_CURRENT_SOURCE_DIR}/test_main.c
    ${CMAKE_CURRENT_SOURCE_DIR}/test_pid_control.c
    ${CMAKE_CURRENT_SOURCE_DIR}/test_low_temp_control.c
    ${CMAKE_CURRENT_SOURCE_DIR}/test_safety.c
)

# ============================================================================
# Include directories
# ============================================================================

set(INCLUDE_DIRS
    ${CMAKE_CURRENT_SOURCE_DIR}
    ${CMAKE_CURRENT_SOURCE_DIR}/..
    ${CMAKE_CURRENT_SOURCE_DIR}/unity
    ${CMAKE_CURRENT_SOURCE_DIR}/../components/temper_hal/include
    ${CMAKE_CURRENT_SOURCE_DIR}/../components/temper_hal/mock
    ${CMAKE_CURRENT_SOURCE_DIR}/../components/control
    ${CMAKE_CURRENT_SOURCE_DIR}/../components/safety
    ${CMAKE_CURRENT_SOURCE_DIR}/../main
)

# ============================================================================
# Codegen: regenerate firmware/config.h from config.yaml
# ============================================================================

add_custom_command(
    OUTPUT ${CMAKE_CURRENT_SOURCE_DIR}/../config.h
    MAIN_DEPENDENCY ${CMAKE_CURRENT_SOURCE_DIR}/../config.yaml
    COMMAND python3 ${CMAKE_CURRENT_SOURCE_DIR}/../tools/gen_config.py
    WORKING_DIRECTORY ${CMAKE_CURRENT_SOURCE_DIR}/..
    COMMENT "Regenerating firmware/config.h from config.yaml"
    VERBATIM
)
add_custom_target(gen_config DEPENDS ${CMAKE_CURRENT_SOURCE_DIR}/../config.h)

# ============================================================================
# Codegen: regenerate firmware/main/fault_list_generated.h from
#          firmware/test/traces/manifest.json + fault_list_supplemental.yaml
# ============================================================================

add_custom_command(
    OUTPUT ${CMAKE_CURRENT_SOURCE_DIR}/../main/fault_list_generated.h
    MAIN_DEPENDENCY ${CMAKE_CURRENT_SOURCE_DIR}/traces/manifest.json
    DEPENDS ${CMAKE_CURRENT_SOURCE_DIR}/../tools/fault_list_supplemental.yaml
    COMMAND python3 ${CMAKE_CURRENT_SOURCE_DIR}/../tools/gen_fault_list.py
    WORKING_DIRECTORY ${CMAKE_CURRENT_SOURCE_DIR}/..
    COMMENT "Regenerating firmware/main/fault_list_generated.h from manifest.json"
    VERBATIM
)
add_custom_target(gen_fault_list DEPENDS ${CMAKE_CURRENT_SOURCE_DIR}/../main/fault_list_generated.h)

# ============================================================================
# Codegen: regenerate firmware/main/transition_table.h from transition_table.yaml
# ============================================================================

add_custom_command(
    OUTPUT ${CMAKE_CURRENT_SOURCE_DIR}/../main/transition_table.h
    MAIN_DEPENDENCY ${CMAKE_CURRENT_SOURCE_DIR}/../transition_table.yaml
    DEPENDS ${CMAKE_CURRENT_SOURCE_DIR}/../main/state_machine.h
    COMMAND python3 ${CMAKE_CURRENT_SOURCE_DIR}/../tools/gen_transition_table.py
    WORKING_DIRECTORY ${CMAKE_CURRENT_SOURCE_DIR}/..
    COMMENT "Regenerating firmware/main/transition_table.h from transition_table.yaml"
    VERBATIM
)
add_custom_target(gen_transition_table DEPENDS ${CMAKE_CURRENT_SOURCE_DIR}/../main/transition_table.h)

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
    ${CMAKE_CURRENT_SOURCE_DIR}/../main/state_handlers.c
    ${CMAKE_CURRENT_SOURCE_DIR}/../components/control/low_temp_control.c
    ${CMAKE_CURRENT_SOURCE_DIR}/../components/control/pid_control.c
    ${CMAKE_CURRENT_SOURCE_DIR}/../components/control/thermal_mass.c
    ${CMAKE_CURRENT_SOURCE_DIR}/../components/control/profiles.c
    ${CMAKE_CURRENT_SOURCE_DIR}/state_machine_stubs.c
    ${CMAKE_CURRENT_SOURCE_DIR}/test_state_machine.c
    ${CMAKE_CURRENT_SOURCE_DIR}/test_transition_table_generated.c
    ${CMAKE_CURRENT_SOURCE_DIR}/test_main_state_machine.c
)
target_include_directories(test_state_machine_only PRIVATE ${INCLUDE_DIRS})
target_link_libraries(test_state_machine_only m)
add_dependencies(test_state_machine_only gen_config gen_fault_list gen_transition_table)

# MAX31865 register and terminal-fault-path contract. This target intentionally
# combines the real driver and state machine through the SPI mock so threshold
# programming and decoded fault delivery are exercised together.
add_executable(test_max31865_only
    ${UNITY_SOURCES}
    ${MOCK_HAL_SOURCES}
    ${CMAKE_CURRENT_SOURCE_DIR}/../components/sensors/max31865.c
    ${CMAKE_CURRENT_SOURCE_DIR}/../components/sensors/rtd_service.c
    ${CMAKE_CURRENT_SOURCE_DIR}/../main/state_machine.c
    ${CMAKE_CURRENT_SOURCE_DIR}/../main/state_handlers.c
    ${CMAKE_CURRENT_SOURCE_DIR}/../components/control/low_temp_control.c
    ${CMAKE_CURRENT_SOURCE_DIR}/../components/control/pid_control.c
    ${CMAKE_CURRENT_SOURCE_DIR}/../components/control/thermal_mass.c
    ${CMAKE_CURRENT_SOURCE_DIR}/../components/control/profiles.c
    ${CMAKE_CURRENT_SOURCE_DIR}/state_machine_stubs.c
    ${CMAKE_CURRENT_SOURCE_DIR}/test_max31865.c
    ${CMAKE_CURRENT_SOURCE_DIR}/test_main_max31865.c
)
target_include_directories(test_max31865_only PRIVATE ${INCLUDE_DIRS}
    ${CMAKE_CURRENT_SOURCE_DIR}/../components/sensors/include)
target_link_libraries(test_max31865_only m)
add_dependencies(test_max31865_only gen_config gen_fault_list gen_transition_table)

# Fault list codegen verification tests
add_executable(test_fault_list_only
    ${UNITY_SOURCES}
    ${CMAKE_CURRENT_SOURCE_DIR}/test_fault_list_generated.c
)
target_include_directories(test_fault_list_only PRIVATE ${INCLUDE_DIRS})
target_link_libraries(test_fault_list_only m)
add_dependencies(test_fault_list_only gen_fault_list)

# PID controller tests only
add_executable(test_pid_only
    ${UNITY_SOURCES}
    ${CMAKE_CURRENT_SOURCE_DIR}/../components/control/pid_control.c
    ${CMAKE_CURRENT_SOURCE_DIR}/test_pid_control.c
    ${CMAKE_CURRENT_SOURCE_DIR}/test_main_pid.c
)
target_include_directories(test_pid_only PRIVATE ${INCLUDE_DIRS})
target_link_libraries(test_pid_only m)

# Low temperature control tests only
add_executable(test_low_temp_only
    ${UNITY_SOURCES}
    ${CMAKE_CURRENT_SOURCE_DIR}/../components/control/low_temp_control.c
    ${CMAKE_CURRENT_SOURCE_DIR}/../components/control/pid_control.c
    ${CMAKE_CURRENT_SOURCE_DIR}/test_low_temp_control.c
    ${CMAKE_CURRENT_SOURCE_DIR}/test_main_low_temp.c
)
target_include_directories(test_low_temp_only PRIVATE ${INCLUDE_DIRS})
target_link_libraries(test_low_temp_only m)

# Safety tests only
add_executable(test_safety_only
    ${UNITY_SOURCES}
    ${MOCK_HAL_SOURCES}
    ${CMAKE_CURRENT_SOURCE_DIR}/../components/control/pll_control.c
    ${CMAKE_CURRENT_SOURCE_DIR}/../components/control/zvs_monitor.c
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

# Cascade PID tests only
add_executable(test_cascade_pid_only
    ${UNITY_SOURCES}
    ${CMAKE_CURRENT_SOURCE_DIR}/../components/control/pid_control.c
    ${CMAKE_CURRENT_SOURCE_DIR}/../components/control/cascade_pid.c
    ${CMAKE_CURRENT_SOURCE_DIR}/test_cascade_pid.c
    ${CMAKE_CURRENT_SOURCE_DIR}/test_main_cascade_pid.c
)
target_include_directories(test_cascade_pid_only PRIVATE ${INCLUDE_DIRS})
target_link_libraries(test_cascade_pid_only m)

# Cascade PID integration tests
add_executable(test_cascade_pid_integration_only
    ${UNITY_SOURCES}
    ${CMAKE_CURRENT_SOURCE_DIR}/../components/control/pid_control.c
    ${CMAKE_CURRENT_SOURCE_DIR}/../components/control/cascade_pid.c
    ${CMAKE_CURRENT_SOURCE_DIR}/test_integration_cascade_pid.c
    ${CMAKE_CURRENT_SOURCE_DIR}/test_main_integration_cascade_pid.c
)
target_include_directories(test_cascade_pid_integration_only PRIVATE ${INCLUDE_DIRS})
target_link_libraries(test_cascade_pid_integration_only m)

# Full state-machine integration tests.  Keep this target explicit instead of
# relying on a stale binary left in the build directory: the test exercises the
# same production state-machine sources and host stubs as the focused state
# machine suite.
add_executable(test_integration_only
    ${UNITY_SOURCES}
    ${CMAKE_CURRENT_SOURCE_DIR}/../main/state_machine.c
    ${CMAKE_CURRENT_SOURCE_DIR}/../main/state_handlers.c
    ${CMAKE_CURRENT_SOURCE_DIR}/../components/control/low_temp_control.c
    ${CMAKE_CURRENT_SOURCE_DIR}/../components/control/pid_control.c
    ${CMAKE_CURRENT_SOURCE_DIR}/../components/control/thermal_mass.c
    ${CMAKE_CURRENT_SOURCE_DIR}/../components/control/profiles.c
    ${CMAKE_CURRENT_SOURCE_DIR}/state_machine_stubs.c
    ${CMAKE_CURRENT_SOURCE_DIR}/test_integration.c
    ${CMAKE_CURRENT_SOURCE_DIR}/test_main_integration.c
)
target_include_directories(test_integration_only PRIVATE ${INCLUDE_DIRS})
target_link_libraries(test_integration_only m)
add_dependencies(test_integration_only gen_config gen_fault_list gen_transition_table)

# Thermal mass estimation tests
add_executable(test_thermal_mass_only
    ${UNITY_SOURCES}
    ${CMAKE_CURRENT_SOURCE_DIR}/../components/control/pid_control.c
    ${CMAKE_CURRENT_SOURCE_DIR}/../components/control/thermal_mass.c
    ${CMAKE_CURRENT_SOURCE_DIR}/test_thermal_mass.c
    ${CMAKE_CURRENT_SOURCE_DIR}/test_main_thermal_mass.c
)
target_include_directories(test_thermal_mass_only PRIVATE ${INCLUDE_DIRS})
target_link_libraries(test_thermal_mass_only m)


# ADC Guard Tests
add_executable(test_adc_guard_only
    ${UNITY_SOURCES}
    test_main_adc_guard.c
    test_adc_guard.c
    ../components/safety/adc_guard.c
    ../components/temper_hal/mock/mock_adc.c
)
target_include_directories(test_adc_guard_only PRIVATE 
    ../components/temper_hal/include
    ../components/safety/include
    unity
)


# PWM Guard Tests
add_executable(test_pwm_guard_only
    ${UNITY_SOURCES}
    test_main_pwm_guard.c
    test_pwm_guard.c
    ../components/safety/pwm_guard.c
)
target_include_directories(test_pwm_guard_only PRIVATE 
    ../components/temper_hal/include
    ../components/safety/include
    unity
)


# NTC Guard Tests
add_executable(test_ntc_guard_only
    ${UNITY_SOURCES}
    test_main_ntc_guard.c
    test_ntc_guard.c
    ../components/safety/ntc_guard.c
)
target_include_directories(test_ntc_guard_only PRIVATE 
    ../components/temper_hal/include
    ../components/safety/include
    unity
)
target_link_libraries(test_ntc_guard_only m)

# Fan Guard Tests
add_executable(test_fan_guard_only
    ${UNITY_SOURCES}
    test_main_fan_guard.c
    test_fan_guard.c
    ../components/safety/fan_guard.c
)
target_include_directories(test_fan_guard_only PRIVATE 
    ../components/temper_hal/include
    ../components/safety/include
    unity
)

# Coil Guard Tests
add_executable(test_coil_guard_only
    ${UNITY_SOURCES}
    test_main_coil_guard.c
    test_coil_guard.c
    ../components/safety/coil_guard.c
)
target_include_directories(test_coil_guard_only PRIVATE 
    ../components/temper_hal/include
    ../components/safety/include
    unity
)
target_link_libraries(test_coil_guard_only m)


# ============================================================================
# CTest integration
# ============================================================================

enable_testing()
add_test(NAME all_tests COMMAND test_runner)
add_test(NAME state_machine_tests COMMAND test_state_machine_only)
add_test(NAME max31865_tests COMMAND test_max31865_only)
add_test(NAME pid_tests COMMAND test_pid_only)
add_test(NAME cascade_pid_tests COMMAND test_cascade_pid_only)
add_test(NAME cascade_pid_integration_tests COMMAND test_cascade_pid_integration_only)
add_test(NAME thermal_mass_tests COMMAND test_thermal_mass_only)
add_test(NAME low_temp_tests COMMAND test_low_temp_only)
add_test(NAME safety_tests COMMAND test_safety_only)
add_test(NAME pan_detection_tests COMMAND test_pan_detection_only)
add_test(NAME pll_tests COMMAND test_pll_only)
add_test(NAME integration_tests COMMAND test_integration_only)

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
    DEPENDS test_runner test_state_machine_only test_pid_only test_safety_only test_integration_only
    COMMENT "Running all tests with verbose output..."
)

# UI Tests
add_executable(test_ui_only
    ${UNITY_SOURCES}
    test_main_ui.c
    test_ui.c
    ../main/ui.c
    ../components/temper_hal/mock/hal_encoder_mock.c
    ../components/temper_hal/mock/hal_led_mock.c
)
target_include_directories(test_ui_only PRIVATE ${INCLUDE_DIRS})
target_link_libraries(test_ui_only m)

# Probe Detection Tests
add_executable(test_probe_detection_only
    ${UNITY_SOURCES}
    test_main_probe_detection.c
    test_probe_detection.c
    ../components/control/cascade_pid.c
    ../components/control/pid_control.c
)
target_include_directories(test_probe_detection_only PRIVATE ${INCLUDE_DIRS})
target_link_libraries(test_probe_detection_only m)

# Profile Tests
add_executable(test_profiles_only
    ${UNITY_SOURCES}
    test_main_profiles.c
    test_profiles.c
    ../components/control/profiles.c
)
target_include_directories(test_profiles_only PRIVATE ${INCLUDE_DIRS})
target_link_libraries(test_profiles_only m)

# SIL Fault Injection Tests
add_executable(test_sil_fault_injection
    ${UNITY_SOURCES}
    ${CMAKE_CURRENT_SOURCE_DIR}/../main/state_machine.c
    ${CMAKE_CURRENT_SOURCE_DIR}/../main/state_handlers.c
    ${CMAKE_CURRENT_SOURCE_DIR}/../components/control/low_temp_control.c
    ${CMAKE_CURRENT_SOURCE_DIR}/../components/control/pid_control.c
    ${CMAKE_CURRENT_SOURCE_DIR}/../components/control/thermal_mass.c
    ${CMAKE_CURRENT_SOURCE_DIR}/../components/control/profiles.c
    ${CMAKE_CURRENT_SOURCE_DIR}/state_machine_stubs.c
    ${CMAKE_CURRENT_SOURCE_DIR}/test_sil_fault_injection.c
)
target_include_directories(test_sil_fault_injection PRIVATE ${INCLUDE_DIRS})
target_link_libraries(test_sil_fault_injection m)

# CTest registration. The C1 configuration of the same suite
# (test_sil_fault_injection_c1, sil_fault_tests_c1) is registered with the
# other TEMPER_PAN_CONTROL_C1 targets below.
add_test(NAME sil_fault_tests
    COMMAND test_sil_fault_injection
    WORKING_DIRECTORY ${CMAKE_CURRENT_SOURCE_DIR}
)

# ============================================================================
# sensor-r3 C1 pan-temperature loop (components/control/pan_temp_*.c,
# plant_gain.c, pan_rate_pid.c, contact_check.c, pan_sensor_guard.c).
# Golden vectors are generated by output/temper-sensor-r3/firmware/
# export_vectors.py; the C-in-the-loop co-simulation and its runner live in
# that folder too (run.sh).
# ============================================================================

set(PAN_TEMP_LOOP_SOURCES
    ${CMAKE_CURRENT_SOURCE_DIR}/../components/control/pan_temp_estimator.c
    ${CMAKE_CURRENT_SOURCE_DIR}/../components/control/plant_gain.c
    ${CMAKE_CURRENT_SOURCE_DIR}/../components/control/pan_rate_pid.c
    ${CMAKE_CURRENT_SOURCE_DIR}/../components/control/contact_check.c
    ${CMAKE_CURRENT_SOURCE_DIR}/../components/control/pan_sensor_guard.c
    ${CMAKE_CURRENT_SOURCE_DIR}/../components/control/pan_temp_loop.c
)

add_executable(test_pan_temp_estimator_only
    ${UNITY_SOURCES}
    ${CMAKE_CURRENT_SOURCE_DIR}/../components/control/pan_temp_estimator.c
    ${CMAKE_CURRENT_SOURCE_DIR}/test_pan_temp_estimator.c
    ${CMAKE_CURRENT_SOURCE_DIR}/test_main_pan_temp_estimator.c
)
target_include_directories(test_pan_temp_estimator_only PRIVATE ${INCLUDE_DIRS})
target_link_libraries(test_pan_temp_estimator_only m)

add_executable(test_contact_check_only
    ${UNITY_SOURCES}
    ${CMAKE_CURRENT_SOURCE_DIR}/../components/control/contact_check.c
    ${CMAKE_CURRENT_SOURCE_DIR}/test_contact_check.c
    ${CMAKE_CURRENT_SOURCE_DIR}/test_main_contact_check.c
)
target_include_directories(test_contact_check_only PRIVATE ${INCLUDE_DIRS})
target_link_libraries(test_contact_check_only m)

add_executable(test_pan_temp_loop_only
    ${UNITY_SOURCES}
    ${PAN_TEMP_LOOP_SOURCES}
    ${CMAKE_CURRENT_SOURCE_DIR}/test_pan_temp_loop.c
    ${CMAKE_CURRENT_SOURCE_DIR}/test_main_pan_temp_loop.c
)
target_include_directories(test_pan_temp_loop_only PRIVATE ${INCLUDE_DIRS})
target_link_libraries(test_pan_temp_loop_only m)

# EVENT_CONTACT_LOST in the state machine (self-loop + UI message).
add_executable(test_pan_contact_sm_only
    ${UNITY_SOURCES}
    ${CMAKE_CURRENT_SOURCE_DIR}/../main/state_machine.c
    ${CMAKE_CURRENT_SOURCE_DIR}/../main/state_handlers.c
    ${CMAKE_CURRENT_SOURCE_DIR}/../components/control/low_temp_control.c
    ${CMAKE_CURRENT_SOURCE_DIR}/../components/control/pid_control.c
    ${CMAKE_CURRENT_SOURCE_DIR}/../components/control/thermal_mass.c
    ${CMAKE_CURRENT_SOURCE_DIR}/../components/control/profiles.c
    ${CMAKE_CURRENT_SOURCE_DIR}/state_machine_stubs.c
    ${CMAKE_CURRENT_SOURCE_DIR}/test_pan_contact_sm.c
    ${CMAKE_CURRENT_SOURCE_DIR}/test_main_pan_contact_sm.c
)
target_include_directories(test_pan_contact_sm_only PRIVATE ${INCLUDE_DIRS})
target_link_libraries(test_pan_contact_sm_only m)
add_dependencies(test_pan_contact_sm_only gen_config gen_fault_list gen_transition_table)

add_test(NAME pan_temp_estimator_tests COMMAND test_pan_temp_estimator_only)
add_test(NAME contact_check_tests COMMAND test_contact_check_only)
add_test(NAME pan_temp_loop_tests COMMAND test_pan_temp_loop_only)
add_test(NAME pan_contact_sm_tests COMMAND test_pan_contact_sm_only)

# ============================================================================
# sensor-r3 C1 runtime (TEMPER_PAN_CONTROL_C1): runaway supervisor and RTD
# conversion units, the state machine driving the C1 loop through
# main/pan_control.c, and the C1 MAX31865 service path (CR-7) through the SPI
# mock. output/temper-sensor-r3/firmware/DECISIONS.md D-MODE, D-RUN, D-STALE.
# The legacy targets above build without TEMPER_PAN_CONTROL_C1.
# ============================================================================

set(C1_RUNTIME_SOURCES
    ${PAN_TEMP_LOOP_SOURCES}
    ${CMAKE_CURRENT_SOURCE_DIR}/../components/control/pan_supervisor.c
    ${CMAKE_CURRENT_SOURCE_DIR}/../components/control/current_sense_check.c
    ${CMAKE_CURRENT_SOURCE_DIR}/../components/control/pan_leak_check.c
    ${CMAKE_CURRENT_SOURCE_DIR}/../main/pan_control.c
    ${CMAKE_CURRENT_SOURCE_DIR}/../components/sensors/rim_ntc.c
    ${CMAKE_CURRENT_SOURCE_DIR}/../main/state_machine.c
    ${CMAKE_CURRENT_SOURCE_DIR}/../main/state_handlers.c
    ${CMAKE_CURRENT_SOURCE_DIR}/../components/control/low_temp_control.c
    ${CMAKE_CURRENT_SOURCE_DIR}/../components/control/pid_control.c
    ${CMAKE_CURRENT_SOURCE_DIR}/../components/control/thermal_mass.c
    ${CMAKE_CURRENT_SOURCE_DIR}/../components/control/profiles.c
    ${CMAKE_CURRENT_SOURCE_DIR}/state_machine_stubs.c
)

add_executable(test_c1_units_only
    ${UNITY_SOURCES}
    ${CMAKE_CURRENT_SOURCE_DIR}/../components/control/pan_supervisor.c
    ${CMAKE_CURRENT_SOURCE_DIR}/../components/control/current_sense_check.c
    ${CMAKE_CURRENT_SOURCE_DIR}/../components/control/pan_leak_check.c
    ${CMAKE_CURRENT_SOURCE_DIR}/../components/sensors/rtd_convert.c
    ${CMAKE_CURRENT_SOURCE_DIR}/test_c1_units.c
    ${CMAKE_CURRENT_SOURCE_DIR}/test_main_c1_units.c
)
target_include_directories(test_c1_units_only PRIVATE ${INCLUDE_DIRS}
    ${CMAKE_CURRENT_SOURCE_DIR}/../components/sensors/include)
target_link_libraries(test_c1_units_only m)

add_executable(test_c1_runtime_only
    ${UNITY_SOURCES}
    ${C1_RUNTIME_SOURCES}
    ${CMAKE_CURRENT_SOURCE_DIR}/../components/sensors/rtd_convert.c
    ${CMAKE_CURRENT_SOURCE_DIR}/test_c1_runtime.c
    ${CMAKE_CURRENT_SOURCE_DIR}/test_main_c1_runtime.c
)
target_compile_definitions(test_c1_runtime_only PRIVATE TEMPER_PAN_CONTROL_C1=1)
target_include_directories(test_c1_runtime_only PRIVATE ${INCLUDE_DIRS}
    ${CMAKE_CURRENT_SOURCE_DIR}/../components/sensors/include)
target_link_libraries(test_c1_runtime_only m)
add_dependencies(test_c1_runtime_only gen_config gen_fault_list gen_transition_table)

# The same runtime tests with the input-current (AMC1301) cross-check compiled
# in (TEMPER_INPUT_CURRENT_SENSE, default 0 until the sense is on the board;
# DECISIONS.md D-ISENSE (c)). test_c1_runtime.c adds the cross-check tests in
# this build.
add_executable(test_c1_runtime_isense_only
    ${UNITY_SOURCES}
    ${C1_RUNTIME_SOURCES}
    ${CMAKE_CURRENT_SOURCE_DIR}/../components/sensors/rtd_convert.c
    ${CMAKE_CURRENT_SOURCE_DIR}/test_c1_runtime.c
    ${CMAKE_CURRENT_SOURCE_DIR}/test_main_c1_runtime.c
)
target_compile_definitions(test_c1_runtime_isense_only PRIVATE TEMPER_PAN_CONTROL_C1=1
    TEMPER_INPUT_CURRENT_SENSE=1)
target_include_directories(test_c1_runtime_isense_only PRIVATE ${INCLUDE_DIRS}
    ${CMAKE_CURRENT_SOURCE_DIR}/../components/sensors/include)
target_link_libraries(test_c1_runtime_isense_only m)
add_dependencies(test_c1_runtime_isense_only gen_config gen_fault_list gen_transition_table)

add_executable(test_c1_rtd_service_only
    ${UNITY_SOURCES}
    ${MOCK_HAL_SOURCES}
    ${C1_RUNTIME_SOURCES}
    ${CMAKE_CURRENT_SOURCE_DIR}/../components/sensors/max31865.c
    ${CMAKE_CURRENT_SOURCE_DIR}/../components/sensors/rtd_service.c
    ${CMAKE_CURRENT_SOURCE_DIR}/../components/sensors/rtd_convert.c
    ${CMAKE_CURRENT_SOURCE_DIR}/test_c1_rtd_service.c
    ${CMAKE_CURRENT_SOURCE_DIR}/test_main_c1_rtd_service.c
)
target_compile_definitions(test_c1_rtd_service_only PRIVATE TEMPER_PAN_CONTROL_C1=1)
target_include_directories(test_c1_rtd_service_only PRIVATE ${INCLUDE_DIRS}
    ${CMAKE_CURRENT_SOURCE_DIR}/../components/sensors/include)
target_link_libraries(test_c1_rtd_service_only m)
add_dependencies(test_c1_rtd_service_only gen_config gen_fault_list gen_transition_table)

# sensor-r3 C1 rim NTC driver (CR-7 rim channel; DECISIONS.md D-RIM): the
# driver through a mock HAL, and its board binding through the hal_adc mock.
add_executable(test_c1_rim_ntc_only
    ${UNITY_SOURCES}
    ${MOCK_HAL_SOURCES}
    ${CMAKE_CURRENT_SOURCE_DIR}/../components/sensors/rim_ntc.c
    ${CMAKE_CURRENT_SOURCE_DIR}/../components/sensors/rim_ntc_board.c
    ${CMAKE_CURRENT_SOURCE_DIR}/test_c1_rim_ntc.c
    ${CMAKE_CURRENT_SOURCE_DIR}/test_main_c1_rim_ntc.c
)
target_include_directories(test_c1_rim_ntc_only PRIVATE ${INCLUDE_DIRS}
    ${CMAKE_CURRENT_SOURCE_DIR}/../components/sensors/include)
target_link_libraries(test_c1_rim_ntc_only m)

add_test(NAME c1_units_tests COMMAND test_c1_units_only)
add_test(NAME c1_runtime_tests COMMAND test_c1_runtime_only)
add_test(NAME c1_runtime_isense_tests COMMAND test_c1_runtime_isense_only)
add_test(NAME c1_rtd_service_tests COMMAND test_c1_rtd_service_only)
add_test(NAME c1_rim_ntc_tests COMMAND test_c1_rim_ntc_only)

# SIL fault injection in the C1 configuration: the same runner and manifest
# (test_sil_fault_injection.c, traces/manifest.json "modes"), built with
# TEMPER_PAN_CONTROL_C1 as the ESP-IDF target is, with the C1 loop and
# supervisor and the real MAX31865 service driven through the SPI mock by a
# register-level converter model. output/temper-sensor-r3/firmware/
# DECISIONS.md D-SIL; coverage of both configurations is gated by
# test_sil_coverage.py (scripts/check_sil_coverage.py).
add_executable(test_sil_fault_injection_c1
    ${UNITY_SOURCES}
    ${MOCK_HAL_SOURCES}
    ${C1_RUNTIME_SOURCES}
    ${CMAKE_CURRENT_SOURCE_DIR}/../components/sensors/max31865.c
    ${CMAKE_CURRENT_SOURCE_DIR}/../components/sensors/rtd_service.c
    ${CMAKE_CURRENT_SOURCE_DIR}/../components/sensors/rtd_convert.c
    ${CMAKE_CURRENT_SOURCE_DIR}/test_sil_fault_injection.c
)
target_compile_definitions(test_sil_fault_injection_c1 PRIVATE TEMPER_PAN_CONTROL_C1=1)
target_include_directories(test_sil_fault_injection_c1 PRIVATE ${INCLUDE_DIRS}
    ${CMAKE_CURRENT_SOURCE_DIR}/../components/sensors/include)
target_link_libraries(test_sil_fault_injection_c1 m)
add_dependencies(test_sil_fault_injection_c1 gen_config gen_fault_list gen_transition_table)

add_test(NAME sil_fault_tests_c1
    COMMAND test_sil_fault_injection_c1
    WORKING_DIRECTORY ${CMAKE_CURRENT_SOURCE_DIR}
)
