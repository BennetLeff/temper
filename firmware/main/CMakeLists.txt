# Main component CMakeLists.txt
# Lists source files for the main application component

idf_component_register(
    SRCS 
        "main.c"
        "state_machine.c"
        "state_handlers.c"
        "thermal_io.c"
        "../config.c"
        "../components/control/thermal_mgmt.c"
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
        # Platform layer (ESP-IDF only; host doubles in test/state_machine_stubs.c)
        "platform/platform_esp32.c"
        "platform/ui_esp32.c"
        "../components/platform/platform_logic.c"
    INCLUDE_DIRS 
        "."
        ".."
        "../components/sensors/include"
        "../components/safety/include"
        "../components/platform/include"
        "platform"
    REQUIRES
        driver
        temper_hal
        power
        nvs_flash
        esp_timer
)
