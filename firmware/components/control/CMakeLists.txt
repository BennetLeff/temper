# Control component (ESP-IDF).
#
# - sensor-r3 C1 pan-temperature loop and runaway supervisor
#   (output/temper-sensor-r3/firmware/DECISIONS.md D-MODE);
# - the legacy modules the state machine still calls in a C1 build:
#   thermal_mass (PAN_DET classification), pid_control (pid_set_tuning),
#   profiles (HEATING profile steps), pll_control (PREHEAT/HEATING/COOLDOWN
#   enable/disable/update), pan_detect (detect_pan_presence), and zvs_monitor
#   (safety.c's ZVS check). The host suites link the same set
#   (firmware/test/CMakeLists.txt C1_RUNTIME_SOURCES).
#
# Not registered: cascade_pid.c and low_temp_control.c (host-test-only; the
# target state machine does not call them).

idf_component_register(
    SRCS
        "pan_temp_estimator.c"
        "plant_gain.c"
        "pan_rate_pid.c"
        "contact_check.c"
        "pan_sensor_guard.c"
        "pan_temp_loop.c"
        "pan_supervisor.c"
        "thermal_mass.c"
        "pid_control.c"
        "profiles.c"
        "pll_control.c"
        "pan_detect.c"
        "zvs_monitor.c"
    INCLUDE_DIRS
        "."
    REQUIRES
        esp_driver_mcpwm
        esp_timer
)
