# Main component CMakeLists.txt
# Lists source files for the main application component

idf_component_register(
    SRCS 
        "main.c"
        "state_machine.c"
        "state_handlers.c"
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
        hal
        nvs_flash
        esp_timer
)
