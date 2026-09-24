# Main component CMakeLists.txt
# Lists source files for the main application component

option(TEMPER_DIAGNOSTIC_LOCKOUT
    "Build the non-energizing ESP32-S3 diagnostic image while cooker hooks are unimplemented"
    ON)

if(TEMPER_DIAGNOSTIC_LOCKOUT)
    set(TEMPER_ENTRY_SOURCES
        "diagnostic_lockout.c"
        "diagnostic_lockout_idf.c"
        "diagnostic_lockout_hooks.c")
else()
    # Keep this path honest: it currently fails to link until the actual
    # cooker peripheral and self-test implementations are registered.
    set(TEMPER_ENTRY_SOURCES "main.c")
endif()

idf_component_register(
    SRCS
        ${TEMPER_ENTRY_SOURCES}
        "state_machine.c"
        "state_handlers.c"
        "../config.c"
        "../components/control/pan_detect.c"
        "../components/control/pid_control.c"
        "../components/control/pll_control.c"
        "../components/control/profiles.c"
        "../components/control/thermal_mass.c"
        "../components/control/zvs_monitor.c"
        "../components/safety/safety.c"
        "power_entry_authorization.c"
        "power_entry_source_runtime.c"
        "power_entry_esp32_adapter.c"
        "power_entry_esp32_idf.c"
        "power_entry_esp32_service.c"
        "../../zapote/power-entry/passive-reva/protection/interface-integration-38/receiver-firmware/protocol.c"
        "../components/sensors/max31865.c"
        "../components/sensors/rtd_service.c"
    INCLUDE_DIRS 
        "."
        ".."
        "../components/sensors/include"
    REQUIRES
        driver
        temper_hal
        nvs_flash
        esp_timer
)

if(TEMPER_DIAGNOSTIC_LOCKOUT)
    target_compile_definitions(${COMPONENT_LIB} PRIVATE TEMPER_DIAGNOSTIC_LOCKOUT=1)
endif()
