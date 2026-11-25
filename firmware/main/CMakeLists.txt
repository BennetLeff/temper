# Main component CMakeLists.txt
# Lists source files for the main application component

idf_component_register(
    SRCS 
        "main.c"
        "state_machine.c"
        "state_handlers.c"
        "thermal_io.c"
        "pan_control.c"
        "pan_io.c"
        "soak_store_nvs.c"
        "../config.c"
        "../components/control/thermal_mgmt.c"
        "../components/control/cascade_pid.c"
        "../components/control/low_temp_control.c"
        "../components/control/pan_detect.c"
        "../components/control/pid_control.c"
        "../components/control/pll_control.c"
        "../components/control/profiles.c"
        "../components/control/contact_check.c"
        "../components/control/contact_shift.c"
        "../components/control/current_sense_check.c"
        "../components/control/pan_cold_soak.c"
        "../components/control/pan_leak_check.c"
        "../components/control/pan_rate_pid.c"
        "../components/control/pan_rim_limit.c"
        "../components/control/pan_sensor_guard.c"
        "../components/control/pan_soak_store.c"
        "../components/control/pan_supervisor.c"
        "../components/control/pan_temp_estimator.c"
        "../components/control/pan_temp_loop.c"
        "../components/control/plant_gain.c"
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
        "../components/sensors/rtd_convert.c"
        "../components/sensors/rtd_food.c"
        "../components/sensors/rim_ntc.c"
        "../components/sensors/hs_ntc.c"
        # Platform layer (ESP-IDF only; host doubles in test/state_machine_stubs.c)
        "platform/platform_esp32.c"
        "platform/ui_esp32.c"
        "../components/platform/platform_logic.c"
    INCLUDE_DIRS 
        "."
        ".."
        "../components/control"
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

# The sensor-r3 C1 pan loop controls PREHEAT / HEATING on the target (sensor-r3 D-MODE). The legacy host
# suites build without it; test_c1_runtime builds with it.
target_compile_definitions(${COMPONENT_LIB} PRIVATE TEMPER_PAN_CONTROL_C1=1)
