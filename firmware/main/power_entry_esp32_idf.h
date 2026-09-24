#ifndef TEMPER_POWER_ENTRY_ESP32_IDF_H
#define TEMPER_POWER_ENTRY_ESP32_IDF_H

#include "power_entry_esp32_adapter.h"

/* Candidate ESP-IDF v5.2+ binding. Caller owns a single serialized source
 * task and calls pe_source_runtime_boot only after this succeeds. The current
 * cooker app_main does not yet instantiate that task. */
bool pe_esp32_idf_boot(pe_esp32_adapter_t *adapter);

/* Poll one byte from the isolated receiver UART. A negative result is an
 * adapter/driver failure; zero means no byte, one means byte received. */
int pe_esp32_idf_poll_byte(uint8_t *byte);

#endif
