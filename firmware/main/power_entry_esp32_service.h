#ifndef TEMPER_POWER_ENTRY_ESP32_SERVICE_H
#define TEMPER_POWER_ENTRY_ESP32_SERVICE_H

#include <stdbool.h>

/* Start one serialized UART1/I2C0/expander owner. Returns true only if the
 * Rev38 source runtime was armed; false means direct STOP remains asserted. */
bool pe_esp32_source_service_start(void);

/* Report completed work from independent tasks. The present monitor task has
 * no safety work to report, so it must not call the monitor function yet. */
void pe_esp32_source_service_control_progress(void);
void pe_esp32_source_service_monitor_progress(void);

#endif
