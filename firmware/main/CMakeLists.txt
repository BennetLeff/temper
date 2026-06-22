# Main component CMakeLists.txt
# Lists source files for the main application component

idf_component_register(
    SRCS 
        "main.c"
        "state_machine.c"
    INCLUDE_DIRS 
        "."
        ".."
    REQUIRES
        driver
        nvs_flash
        esp_timer
)
