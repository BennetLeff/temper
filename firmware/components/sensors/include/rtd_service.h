/**
 * @file rtd_service.h
 * @brief Board-owned MAX31865 SPI2/DRDY service.
 *
 * Sequence (datasheet procedure; design lead decision 2026-10-12, PLATFORM.md):
 *   bootstrap: thresholds, then an automatic fault-detection cycle (conversions off);
 *   FAULT_CYCLE: CONFIG polled once per control tick until D3:D2 read back 00, then the
 *     latched status is reported and continuous conversions start (4-wire, 60 Hz notch);
 *   CONVERTING: DRDY (TCA9555 P07, DECISIONS C23) sampled once per control tick; each low
 *     DRDY is one conversion: the data word is read (which releases DRDY) and DRDY is
 *     re-sampled to confirm the release before the next low is accepted;
 *   every RTD_FAULT_CYCLE_PERIOD_TICKS, right after a conversion has been read, conversions
 *     pause and a new fault-detection cycle runs.
 * Any reported fault ends the service (terminal; the state machine has latched the cut).
 * `rtd_service_control_tick()` is called by the control task and is the sole owner of MAX31865
 * SPI transfers and state-machine fault delivery.
 */

#ifndef RTD_SERVICE_H
#define RTD_SERVICE_H

#include <stdbool.h>
#include <stdint.h>

#include "hal_types.h"

#ifdef __cplusplus
extern "C" {
#endif

/* The control task runs every 10 ms. Fail-silent bound for every wait (a fault cycle to finish,
 * the next conversion) and the maximum age of a usable data word: 100 ms. The automatic fault
 * cycle is sub-millisecond; continuous conversions at the 60 Hz notch are 16.7 ms apart, and the
 * first after a restart takes about the single-conversion time (~52 ms at 60 Hz; bench item). */
#define RTD_DRDY_TIMEOUT_CONTROL_TICKS 10u

/* Periodic fault-detection cycle: every 100 control ticks = 1 s (design lead: <= 1 s). Open and
 * short of the element are already caught on every conversion by the threshold faults (the data
 * word's fault bit, below), so the periodic cycle adds the lead / force-path diagnoses; each costs
 * a pause of about one tick plus the first conversion. At 1 s that is < 7 % of conversions, and
 * the word never ages past RTD_DRDY_TIMEOUT_CONTROL_TICKS across a pause. */
#define RTD_FAULT_CYCLE_PERIOD_TICKS 100u

/**
 * DRDY level source: returns false when no fresh sample is available, else
 * true with *drdy_low = the pin is low (asserted). Called from the control
 * task only. refresh = false: the snapshot taken at the start of this tick;
 * refresh = true: read the pin again now (after a data read, to confirm DRDY
 * was released). On the controller this is the TCA9555 snapshot / a re-poll.
 */
typedef bool (*rtd_drdy_level_fn)(void *context, bool refresh, bool *drdy_low);

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

/** True after a successful bootstrap until a fault is reported (terminal). */
bool rtd_service_is_ready(void);

/** True while continuous conversions run (false during a fault-detection cycle). */
bool rtd_service_converting(void);

/**
 * Latest RTD data word (MAX31865 registers 01h/02h), read by rtd_service_control_tick() on each
 * conversion (the read also releases DRDY). Returns false - no usable sample - unless the
 * service is ready, a word has been read since bootstrap, the last data read succeeded and it is
 * at most RTD_DRDY_TIMEOUT_CONTROL_TICKS control ticks old (the same fail-silent bound as DRDY).
 * A word with the fault bit is returned as read; its readers turn it into +inf / NaN. *age_ticks: control ticks since the read (0 = this
 * tick). Control-task context only, like every other rtd_service call.
 */
bool rtd_service_latest_word(uint16_t *rtd_word, uint8_t *age_ticks);

#ifdef __cplusplus
}
#endif

#endif /* RTD_SERVICE_H */
