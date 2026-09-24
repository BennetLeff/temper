#ifndef TEMPER_POWER_ENTRY_ESP32_SERVICE_H
#define TEMPER_POWER_ENTRY_ESP32_SERVICE_H

#include <stdbool.h>

/* Start one serialized UART1/I2C0/expander owner. Returns true only if the
 * Rev38 source runtime was armed; false means direct STOP remains asserted. */
bool pe_esp32_source_service_start(void);

/* Queue one deliberate restart for the sole source task. Acceptance means
 * queued, with STOP/disarm applied at its next scheduling boundary; a later
 * terminal I/O fault can still cancel it. The caller never writes GPIO14 or
 * UART. Reject while locked out, stopped, or already queued. */
bool pe_esp32_source_service_request_deliberate_restart(void);

/* A monitor producer latches a terminal fault without touching Rev38 GPIO,
 * UART, or the source runtime from its task. The sole source owner consumes
 * this request and asserts STOP. In-flight I/O and task response time remain
 * physical timing qualifications; this API does not synchronously stop a
 * frame already on the wire. A new boot is required to clear the latch. */
void pe_esp32_source_service_request_monitor_fault(void);

/* Report completed work from independent tasks. The present monitor task has
 * no safety work to report, so it must not call the monitor function yet. */
void pe_esp32_source_service_control_progress(void);
void pe_esp32_source_service_monitor_progress(void);

#endif
