/**
 * @file rtd_service.h
 * @brief Board-owned MAX31865 SPI2/DRDY service.
 *
 * DRDY is TCA9555 P07 on the integrated controller (layout L2, DECISIONS C23),
 * sampled once per control tick through rtd_service_set_drdy_source(); a
 * high-to-low transition records completion. `rtd_service_control_tick()` is
 * called by the control task and is the sole owner of MAX31865 SPI transfers
 * and state-machine fault delivery.
 */

#ifndef RTD_SERVICE_H
#define RTD_SERVICE_H

#include <stdbool.h>
#include <stdint.h>

#include "hal_types.h"

#ifdef __cplusplus
extern "C" {
#endif

/* The control task runs every 10 ms. MAX31865 automatic fault detection and
 * the specified 21 ms maximum conversion complete well inside this 100 ms
 * fail-silent bound. */
#define RTD_DRDY_TIMEOUT_CONTROL_TICKS 10u

/**
 * DRDY level source: returns false when no fresh sample is available, else
 * true with *drdy_low = the pin is low (asserted). Called from the control
 * task only. On the controller this reads the expander snapshot.
 */
typedef bool (*rtd_drdy_level_fn)(void *context, bool *drdy_low);

/** Install the DRDY source; required before rtd_service_bootstrap(). */
void rtd_service_set_drdy_source(rtd_drdy_level_fn level, void *context);

/** Configure SPI2 and the MAX31865 chip-select, and start the first cycle.
 * Fails (and the control task then fails closed) without a DRDY source. */
hal_status_t rtd_service_bootstrap(void);

/**
 * Consume a DRDY completion from the control-task context. This is the only
 * function that performs RTD SPI traffic or calls the state machine.
 */
void rtd_service_control_tick(void);

/** True only after successful board-owned SPI/MAX31865 bootstrap. */
bool rtd_service_is_ready(void);

/**
 * Latest RTD data word (MAX31865 registers 01h/02h), read by rtd_service_control_tick() on each
 * DRDY completion, before the fault cycle is serviced (the read also releases DRDY). Returns
 * false - no usable sample - unless the service is ready, a word has been read since bootstrap,
 * the last data read succeeded and it is at most RTD_DRDY_TIMEOUT_CONTROL_TICKS control ticks
 * old (the same fail-silent bound as DRDY). *age_ticks: control ticks since the read (0 = this
 * tick). Control-task context only, like every other rtd_service call.
 */
bool rtd_service_latest_word(uint16_t *rtd_word, uint8_t *age_ticks);

#ifdef __cplusplus
}
#endif

#endif /* RTD_SERVICE_H */
