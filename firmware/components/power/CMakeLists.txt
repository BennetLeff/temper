set(POWER_SRCS "energy_supervisor.c" "fullbridge_adapter.c" "power_service.c" "energy_link.c"
    "burst_scheduler.c" "line_zc.c" "input_limits.c" "n21_signal.c" "n21_binding.c" "tank_freq.c")
set(POWER_REQUIRES driver esp_timer)
# The ESP32 binding is opt-in (Kconfig TEMPER_POWER_HW_BINDING, default n): it has not been
# compiled against ESP-IDF yet, so it must not break the default image.
if(CONFIG_TEMPER_POWER_HW_BINDING)
    list(APPEND POWER_SRCS "n21_hw_esp32.c")
    list(APPEND POWER_REQUIRES esp_adc esp_rom freertos)
endif()
idf_component_register(SRCS ${POWER_SRCS} INCLUDE_DIRS "include" REQUIRES ${POWER_REQUIRES})
