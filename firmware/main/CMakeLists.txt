# Main component CMakeLists.txt
# Lists source files for the main application component

idf_component_register(
    SRCS 
        "main.c"
        "state_machine.c"
        "state_handlers.c"
        "pan_control.c"
        "../components/sensors/max31865.c"
        "../components/sensors/rtd_service.c"
        "../components/sensors/rtd_convert.c"
        "../components/sensors/rim_ntc.c"
        "../components/sensors/rim_ntc_board.c"
        "../components/sensors/hs_ntc.c"
        "../components/sensors/hs_ntc_board.c"
        "../components/safety/safety.c"
        "../components/safety/wdi_supervisor.c"
        "../components/safety/power_gate.c"
        "../config.c"
        "board_peripherals.c"
        "board_power.c"
    INCLUDE_DIRS 
        "."
        ".."
        "../components/sensors/include"
        "../components/safety"
    REQUIRES
        driver
        temper_hal
        control
        nvs_flash
        esp_timer
        esp_driver_gpio
)

# sensor-r3 C1 pan sensor: the C1 loop (components/control, main/pan_control.c)
# controls PREHEAT/HEATING, and the C1 runaway checks and MAX31865 sequence
# (CR-7) replace the legacy ones. The legacy host test suites build without it.
# output/temper-sensor-r3/firmware/DECISIONS.md D-MODE.
target_compile_definitions(${COMPONENT_LIB} PRIVATE TEMPER_PAN_CONTROL_C1=1)
