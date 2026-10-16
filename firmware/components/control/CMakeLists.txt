# sensor-r3 C1 pan-temperature loop and runaway supervisor (ESP-IDF component).
# Only the C1 modules are registered: the legacy control sources in this
# directory are host-test-only (firmware/test/CMakeLists.txt).
# output/temper-sensor-r3/firmware/DECISIONS.md D-MODE.

idf_component_register(
    SRCS
        "pan_temp_estimator.c"
        "contact_shift.c"
        "plant_gain.c"
        "pan_rate_pid.c"
        "contact_check.c"
        "pan_sensor_guard.c"
        "pan_temp_loop.c"
        "pan_supervisor.c"
    INCLUDE_DIRS
        "."
)
