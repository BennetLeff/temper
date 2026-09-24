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
#include <stdint.h>

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
/* Missing-DRDY control fault bound; this is not an accepted Rev38 monitor age. */
#define RTD_MAX_CONTROL_SAMPLE_AGE_MS 100u

/** Configure SPI2, MAX31865 chip-select, DRDY, and start the first cycle. */
hal_status_t rtd_service_bootstrap(void);

/**
 * Consume a DRDY completion from the control-task context. This is the only
 * function that performs RTD SPI traffic or calls the state machine.
 */
void rtd_service_control_tick(void);

/** True only after bootstrap and one fresh RTD conversion/status read. */
bool rtd_service_is_ready(void);

/** Control-task only: true after any conversion; use sample status across tasks. */
bool rtd_service_has_sample(void);

typedef struct {
    bool ready;
    uint32_t generation;
    uint32_t age_ms;
} rtd_sample_status_t;

/**
 * Atomically read conversion readiness and generation across tasks. A new
 * generation is published only after a completed conversion/status transfer.
 * age_ms is elapsed monotonic HAL time since that transfer, or UINT32_MAX
 * when no usable sample or clock is available. A monitor must still apply
 * its state-specific maximum age and check every other required input.
 * Zero means no conversion has been published since bootstrap. Generations
 * wrap from 0x7fffffff to one; compare for change only within a bounded
 * maximum-age window, alongside cooker-state checks.
 */
rtd_sample_status_t rtd_service_sample_status(void);

#ifdef RTD_SERVICE_TESTING
/** Host-test seam for the generation wrap boundary. */
void rtd_service_test_seed_generation(uint32_t generation);
#endif

/** Control-task only: newest resistance, or an open sentinel if unready. */
float rtd_service_get_resistance(void);

/** IEC 751 PT100 resistance to temperature; NAN outside -200 to 850 C. */
float rtd_pt100_temperature_c(float resistance_ohm);

/** Control-task only: NAN until a valid, at-most-100-ms sample is available. */
float rtd_service_pan_temperature_c(void);

#ifdef __cplusplus
}
#endif

#endif /* RTD_SERVICE_H */
