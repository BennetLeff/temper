#ifndef TEMPER_PLATFORM_ESP32_H
#define TEMPER_PLATFORM_ESP32_H
/*
 * ESP32-S3 platform layer for the integrated SELV controller (zapote/controller): the production
 * implementations of the platform functions state_machine.c / state_handlers.c declare extern
 * (host doubles: firmware/test/state_machine_stubs.c). ESP-IDF only. Decisions live in
 * components/platform/platform_logic.c (host-tested); see firmware/build-evidence/esp-idf/PLATFORM.md.
 *
 *   platform_esp32.c : time, peripherals_*, sensors (RTD, DC bus current), blower request, NVS
 *                      fault log, POST self-tests.
 *   ui_esp32.c       : UI board on J7 / SPI3 (DECISIONS C26): SSD1322 OLED, MCP23S08 buttons,
 *                      encoder and buzzer; led_set_pattern.
 */
#include <stdbool.h>

/* Blower full-speed floor requested by the state machine (fan_set_speed(FAN_SPEED_MAX)), read by
 * thermal_blower_tick() (thermal_io.c) and applied on top of the fan law (never below it). */
bool platform_fan_full_speed_requested(void);

/* UI board (ui_esp32.c). platform_ui_init(): SPI3 devices, MCP23S08 configuration and presence
 * check, SSD1322 init, UI I/O task; idempotent. platform_ui_present(): the MCP23S08 answered its
 * last configuration read-back. */
bool platform_ui_init(void);
bool platform_ui_present(void);

#endif
