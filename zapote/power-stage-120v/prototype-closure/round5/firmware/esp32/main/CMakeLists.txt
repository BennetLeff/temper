get_filename_component(REPO "${CMAKE_CURRENT_LIST_DIR}/../../../../../../.." ABSOLUTE)
idf_component_register(SRCS "main.c" "../mcpwm_target.c" "../fast_spi.c" "../../common/fast_capture.c"
    "${REPO}/firmware/components/power/fullbridge_adapter.c"
    "${REPO}/firmware/components/power/energy_link.c"
    INCLUDE_DIRS ".." "../../common" "${REPO}/firmware/components/power/include"
    REQUIRES driver esp_timer)
