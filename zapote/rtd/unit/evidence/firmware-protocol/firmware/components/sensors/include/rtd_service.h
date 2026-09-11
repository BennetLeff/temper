/**
 * @file rtd_service.h
 * @brief Board-owned MAX31865 SPI2/DRDY service.
 *
 * The DRDY ISR records completion only. `rtd_service_control_tick()` is called
 * by the control task and is the sole owner of MAX31865 SPI transfers and
 * state-machine fault delivery.
 */

#ifndef RTD_SERVICE_H
#define RTD_SERVICE_H

#include <stdbool.h>

#include "hal_types.h"

#ifdef __cplusplus
extern "C" {
#endif

/* The control task runs every 10 ms. Two ticks cover MAX31865's 10 ms maximum
 * BIAS startup, one tick covers the 600 us automatic-fault-cycle maximum, and
 * seven ticks provide a 70 ms first-conversion timeout. After the one-time
 * diagnostic, automatic conversion remains enabled so each DRDY is serviced
 * within the 100 ms missing-DRDY safety bound. */
#define RTD_DRDY_TIMEOUT_CONTROL_TICKS 7u
#define RTD_BIAS_STARTUP_CONTROL_TICKS 2u
#define RTD_FAULT_CYCLE_SETTLE_CONTROL_TICKS 1u

/** Configure SPI2, MAX31865 chip-select, DRDY, and start the first cycle. */
hal_status_t rtd_service_bootstrap(void);

/**
 * Consume a DRDY completion from the control-task context. This is the only
 * function that performs RTD SPI traffic or calls the state machine.
 */
void rtd_service_control_tick(void);

/** True only after bootstrap and one fresh RTD conversion/status read. */
bool rtd_service_is_ready(void);

/** True only after a fresh RTD conversion has been read from MAX31865. */
bool rtd_service_has_sample(void);

/** Return newest resistance, or an open sentinel before the first sample. */
float rtd_service_get_resistance(void);

#ifdef __cplusplus
}
#endif

#endif /* RTD_SERVICE_H */
