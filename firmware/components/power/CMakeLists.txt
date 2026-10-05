idf_component_register(SRCS "energy_supervisor.c" "fullbridge_adapter.c" "power_service.c" "energy_link.c"
    INCLUDE_DIRS "include" REQUIRES driver esp_timer)
