get_filename_component(REPO "${CMAKE_CURRENT_LIST_DIR}/../../../../../../.." ABSOLUTE)
idf_component_register(SRCS "main.c" "../mcpwm_target.c" "../power_target.c"
    "../../common/line_telemetry.c"
    "${REPO}/firmware/components/power/fullbridge_adapter.c"
    "${REPO}/firmware/components/power/power_service.c"
    "${REPO}/firmware/components/power/energy_link.c"
    INCLUDE_DIRS ".." "../../common" "${REPO}/firmware/components/power/include"
    REQUIRES driver esp_timer)
