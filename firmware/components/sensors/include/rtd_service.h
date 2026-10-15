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

/* ---- sensor-r3 C1 continuous conversion (TEMPER_PAN_CONTROL_C1) -----------
 *
 * With TEMPER_PAN_CONTROL_C1 the service runs the CR-7 sequence instead of the
 * legacy back-to-back fault-detection cycles:
 *   bootstrap: C1 threshold words (84.27 / 233.214 ohm), one automatic
 *              fault-detection cycle at power-up (coil off), completion by
 *              polling CONFIG D3:D2 (DRDY does not mark fault-cycle completion);
 *   then:      CONFIG 0xC0 (VBIAS, automatic conversion, 60 Hz notch); each
 *              DRDY reads RTD MSB:LSB. A set fault flag reads register 07h and
 *              reports it through state_machine_report_rtd_device_fault (the
 *              same fail-closed sink as the legacy path) and in the sample.
 *   stale:     no DRDY for RTD_C1_STALE_CONTROL_TICKS (60 ms, CR-7: 3 x 20 ms)
 *              reports an open fault, as the legacy 100 ms timeout does.
 *   frozen:    RTD_C1_FROZEN_CONVERSIONS identical codes in a row (5 s at
 *              50 Hz) report FAULT_ADC_STUCK through
 *              state_machine_report_rtd_frozen.
 * A few identical codes are NOT treated as stale: at 15-bit resolution and
 * sub-LSB noise they are normal (CR-7's "unchanged for 3 reads" would
 * false-fault; the r3 runaway check saw runs of up to 88 identical codes at
 * 0.3 LSB noise, so the frozen threshold is 250).
 * (output/temper-sensor-r3/firmware/DECISIONS.md D-STALE, runaway_checks.py)
 */
#define RTD_C1_STALE_CONTROL_TICKS 6u
#define RTD_C1_FROZEN_CONVERSIONS 250u

typedef struct {
    uint16_t code;         /**< 15-bit ratiometric code                    */
    float r_ohm;           /**< resistance, loading-corrected if CR-1 fitted */
    float t_c;             /**< Pt100 temperature, self-heating removed     */
    uint8_t fault_status;  /**< register 07h when the fault flag was set    */
    bool spi_ok;           /**< the RTD (and 07h) reads succeeded           */
    uint32_t seq;          /**< increments on every completed conversion    */
} rtd_sample_t;

/** Latest conversion. Returns false until the first conversion completes. */
bool rtd_service_latest_sample(rtd_sample_t *out);

#ifdef __cplusplus
}
#endif

#endif /* RTD_SERVICE_H */
