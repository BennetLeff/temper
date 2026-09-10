# Main component CMakeLists.txt
# Lists source files for the main application component
#
# The two ../components/sensors/*.c entries below are deliberate and are NOT a
# missing component: sensors/rtd_service.c includes "state_machine.h", which
# lives in this directory. Registering sensors as its own component would make
# main and sensors mutually dependent, which ESP-IDF cannot resolve, so the
# sensors sources are compiled into main instead. They are in the build exactly
# once; components/sensors/ has no CMakeLists.txt for that reason.
#
# ui.c is intentionally absent: main.c defines its own local ui_task() and
# never calls into ui.c, whose only consumer is firmware/test/test_ui.c.

idf_component_register(
    SRCS
        "main.c"
        "state_machine.c"
        "state_handlers.c"
        "../components/sensors/max31865.c"
        "../components/sensors/rtd_service.c"
    INCLUDE_DIRS
        "."
        ".."
        "../components/sensors/include"
    REQUIRES
        driver
        # `temper_hal`, not `hal`: ESP-IDF has its own core component named
        # `hal`, and a project component of the same name replaces it for the
        # entire build. See components/temper_hal/CMakeLists.txt.
        temper_hal
        nvs_flash
        esp_timer
        # main/state_machine.c and main.c include ../components/safety/safety.h
        # and ../components/control/*.h and call into both layers.
        safety
        control
)
