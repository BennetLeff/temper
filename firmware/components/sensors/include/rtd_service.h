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

/* The control task runs every 10 ms. MAX31865 automatic fault detection and
 * the specified 21 ms maximum conversion complete well inside this 100 ms
 * fail-silent bound. */
#define RTD_DRDY_TIMEOUT_CONTROL_TICKS 10u

/** Configure SPI2, MAX31865 chip-select, DRDY, and start the first cycle. */
hal_status_t rtd_service_bootstrap(void);

/**
 * Consume a DRDY completion from the control-task context. This is the only
 * function that performs RTD SPI traffic or calls the state machine.
 */
void rtd_service_control_tick(void);

/** True only after successful board-owned SPI/MAX31865 bootstrap. */
bool rtd_service_is_ready(void);

#ifdef __cplusplus
}
#endif

#endif /* RTD_SERVICE_H */
