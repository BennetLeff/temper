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

/* ---- sensor-r3 C1 (TEMPER_PAN_CONTROL_C1) on the zapote CR-1 board ---------
 *
 * The service runs the CR-7 sequence with the MANUAL fault-detection cycle.
 * zapote/controller C37: the CR-1 sense filter puts the input time constant far
 * above the 100 us the automatic cycle allows, so the automatic cycle is invalid
 * on this board (MAX31865 19-6478 Rev 3, "Fault Detection Cycle (D3:D2)").
 * output/temper-sensor-r3/firmware/fault_cycle.py (fault-cycle.json, DECISIONS.md
 * D-FCYC) takes the slowest pole of the CR-1 network over its tolerance corners,
 * tau_max = 1.01 ms (FORCE- open, element at 360 degC, every capacitor high),
 * and gates the two waits below:
 *   STEP     max(5 ms (C37 / CR-7 floor), 5 tau_max, 2 x the worst healthy settle
 *            to the 85 % comparators) = 5.5 ms between VBIAS-on, step 1 and step 2;
 *   RESTART  max(STEP, 5 tau_max + 1 ms, 10.5 tau_max (15-bit settling, data
 *            sheet Note 4), 2 x the worst 15-bit settle) = 11.5 ms from step 2
 *            (plus CHECK, the chip's own step-2 check before FORCE- closes,
 *            bounded by the automatic cycle's 600 us max) to the restart.
 * Each wait is measured with the HAL microsecond clock, not counted in ticks.
 *
 *   power-up:  thresholds (84.27 / 233.214 ohm), CONFIG 0x82 (VBIAS on, normally
 *              off, 07h clear), STEP, 0x88 (manual step 1: D5 with FORCE- closed),
 *              STEP, 0x8C (step 2: D4/D3 with FORCE- open), poll D3:D2 = 00, read
 *              07h. A set bit is terminal (reported, the service stops: a power
 *              cycle is needed, D-RESET). Clean: RESTART, then CONFIG 0xC0.
 *              The coil is off: the state machine is in INIT until the service
 *              converts, and no power is commanded before PREHEAT.
 *   reset:     rtd_service_fault_status_clean() (fault_cleared() for a probe
 *              fault, in FAULT with the coil off) asks for a verification:
 *              0x82 (clears 07h, stops conversions), 0x88 (VBIAS has been on
 *              throughout), STEP, 0x8C, 07h, RESTART, 0xC0; the reset is clean
 *              only after that cycle read 07h = 0 AND a later conversion came
 *              back without the fault flag. A flagged cycle is reported (the
 *              latch absorbs it) and conversions resume; the next request
 *              runs another cycle.
 *   then:      each DRDY reads RTD MSB:LSB; a set fault flag reads 07h and reports
 *              it through state_machine_report_rtd_device_fault.
 *   stale:     no DRDY for RTD_C1_STALE_CONTROL_TICKS (60 ms, CR-7: 3 x 20 ms)
 *              reports an open fault; the first conversion after a (re)start may
 *              take the single-conversion time (data sheet Note 5: 52-55 ms, 60 Hz
 *              notch), so it gets RTD_C1_FIRST_DRDY_CONTROL_TICKS.
 *   frozen:    RTD_C1_FROZEN_CONVERSIONS identical codes in a row (5 s at 50 Hz)
 *              report FAULT_ADC_STUCK through state_machine_report_rtd_frozen.
 *   rail:      after its own work, each tick, the service takes the MCP3202
 *              rail reading when one is due (rail_adc.h): one task owns the bus.
 * A few identical codes are NOT treated as stale: at 15-bit resolution and
 * sub-LSB noise they are normal (D-STALE). No automatic fault cycle (CONFIG
 * D3:D2 = 01) is ever written in a C1 build.
 */
#define RTD_C1_STALE_CONTROL_TICKS 6u
#define RTD_C1_FIRST_DRDY_CONTROL_TICKS 8u
#define RTD_C1_FROZEN_CONVERSIONS 250u
#define RTD_C1_FAULT_CYCLE_STEP_US 5500u
#define RTD_C1_FAULT_CYCLE_RESTART_US 11500u
#define RTD_C1_FAULT_CYCLE_CHECK_US 1000u
/* A fault-cycle phase still unfinished this many ticks past its wait: open. */
#define RTD_C1_FAULT_CYCLE_TIMEOUT_TICKS 10u

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

/**
 * Safety-reset hook (fault_cleared() for FAULT_PROBE_OPEN/SHORT in C1 builds;
 * DECISIONS.md D-OPEN, D-FCYC). Register 07h latches until cleared, and the
 * manual fault-detection cycle checks the input wiring a conversion cannot
 * (an input shorted to ground can still convert inside the window). The first
 * call asks the service for a verification (07h clear + manual cycle +
 * restart, above) and returns false; it returns true once that cycle read
 * 07h = 0 and a conversion after it is unflagged, and that verdict is used
 * once (the reset it allows consumes it). A flagged conversion in between
 * cancels it. About 0.1 s from the request.
 */
bool rtd_service_fault_status_clean(void);

/** Manual fault-detection cycles completed since bootstrap (diagnostics). */
uint32_t rtd_service_fault_cycles(void);

/** Register 07h read by the last completed manual cycle. */
uint8_t rtd_service_last_fault_cycle_status(void);

#ifdef __cplusplus
}
#endif

#endif /* RTD_SERVICE_H */
