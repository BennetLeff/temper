# Main component CMakeLists.txt
# Lists source files for the main application component
#
# The control/, safety/ and sensors/ directories are plain source directories
# (no component of their own); their sources are compiled into main, the same
# set of files the host test build compiles directly.
# testing/ (test_macros.h) is host-test-only and is deliberately not part of
# the application image.

idf_component_register(
    SRCS
        "main.c"
        "state_machine.c"
        "state_handlers.c"
        "../config.c"
        "../components/control/cascade_pid.c"
        "../components/control/low_temp_control.c"
        "../components/control/pan_detect.c"
        "../components/control/pid_control.c"
        "../components/control/pll_control.c"
        "../components/control/profiles.c"
        "../components/control/thermal_mass.c"
        "../components/control/zvs_monitor.c"
        "../components/safety/safety.c"
        "../components/safety/adc_guard.c"
        "../components/safety/coil_guard.c"
        "../components/safety/fan_guard.c"
        "../components/safety/ntc_guard.c"
        "../components/safety/pwm_guard.c"
        "../components/sensors/max31865.c"
        "../components/sensors/rtd_service.c"
    INCLUDE_DIRS
        "."
        ".."
        "../components/sensors/include"
        "../components/safety/include"
    REQUIRES
        driver
        temper_hal
        power
        nvs_flash
        esp_timer
)
