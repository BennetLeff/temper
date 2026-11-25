/**
 * @file rtd_service.h
 * @brief Board-owned MAX31865 SPI2/DRDY service.
 *
 * Sequence (controller C37 / C46; sensor-r3 firmware DECISIONS D-FCYC):
 *   bootstrap: thresholds, VBIAS on with conversions off;
 *   manual fault cycle, once, at power-up: wait STEP, step 1, wait STEP, step 2, poll D3:D2 = 00,
 *     read and report 07h, wait RESTART from step 2, release DRDY, start continuous conversions
 *     (4-wire, 60 Hz notch). Waits are measured on the HAL microsecond clock, not counted in ticks;
 *   CONVERTING: DRDY (TCA9555 P07, DECISIONS C23) sampled once per control tick; each low
 *     DRDY is one conversion: the data word is read (which releases DRDY) and DRDY is
 *     re-sampled to confirm the release before the next low is accepted.
 * No cycle runs while converting. At one step per 10 ms tick a manual cycle plus the first
 * conversion after a restart (52-55 ms) leaves no margin inside the 100 ms word age below. Each
 * conversion still checks the input against the thresholds: open element, shorted element and open
 * RTDIN- are caught within a conversion (D-FCYC). RTDIN- shorted to ground in service can convert
 * inside the window and is seen only by the power-up cycle.
 * Faults. A flagged conversion is reported and the converter keeps running, so a reset can verify the
 * probe (rtd_service_fault_status_clean()). Terminal until a power cycle: a flagged power-up cycle, a
 * cycle that does not finish, no conversion for RTD_DRDY_TIMEOUT_CONTROL_TICKS, a frozen code, a
 * flagged word with no readable status, an SPI failure in a cycle.
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

/* Manual-cycle waits (sensor-r3 fault_cycle.py / fault-cycle.json, 1536 corners of the CR-1 input
 * network: tau_max 1009.9 us, worst 15-bit settle 5.533 ms). STEP >= 5 tau_max before each step;
 * RESTART from step 2 = max(5 tau_max + 1 ms, 10.5 tau_max, 2 x 5.533 ms) -> 11.5 ms, plus 1 ms for
 * the chip's own step-2 check. */
#define RTD_FAULT_CYCLE_STEP_US    5500u
#define RTD_FAULT_CYCLE_RESTART_US 12500u

/* rtd_service_startup() bound, in 10 ms steps: every phase is bounded by
 * RTD_DRDY_TIMEOUT_CONTROL_TICKS on its own; well inside the TPS3823's watchdog time. */
#define RTD_STARTUP_MAX_TICKS 60u

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

/* Identical codes in a row that count as a frozen converter: 5 s at 50 Hz (sensor-r3 D-STALE). A few
 * are normal at 15 bits. */
#define RTD_FROZEN_CONVERSIONS 250u

typedef struct {
    uint16_t code;         /* 15-bit ratiometric code */
    float r_ohm;           /* CR-7 loading-corrected */
    float t_c;             /* self-heating removed */
    uint8_t fault_status;  /* register 07h when the word carried the fault bit, else 0 */
    bool spi_ok;
    uint32_t seq;          /* increments on every conversion */
} rtd_sample_t;

/** Latest conversion, flagged or not (rtd_convert_classify_failure() judges it). False before the
 * first one, once it is older than RTD_DRDY_TIMEOUT_CONTROL_TICKS, or when the service has stopped. */
bool rtd_service_latest_sample(rtd_sample_t *out);

/**
 * Safety-reset hook for a probe fault (sensor-r3 D-RESET). The first call asks for a verification and
 * returns false: 07h clear, manual fault cycle, restart (about 0.1 s). True, once, after that cycle
 * read 07h = 0 and a later conversion came back unflagged. A flagged cycle or conversion cancels it.
 * Always false when the service has stopped (power-up cycle fault, no conversions, stuck cycle, SPI
 * on the cycle, frozen code): those need a power cycle.
 */
bool rtd_service_fault_status_clean(void);

/** Configure SPI2 and the MAX31865 chip-select, write the thresholds and switch VBIAS on.
 * Fails (and the control task then fails closed) without a DRDY source. */
hal_status_t rtd_service_bootstrap(void);

/**
 * Consume a DRDY completion from the control-task context. This is the only
 * function that performs RTD SPI traffic or calls the state machine.
 */
void rtd_service_control_tick(void);

/**
 * Run the service to its first data word before the control task exists, so the state machine never
 * runs without a pan reading (its runaway check latches on one). step() must wait one control period
 * and refresh the DRDY source. Faults are reported to the state machine as usual, so call it after
 * state_machine_init(). False: no reading (a fault was reported, or the bound ran out and was
 * reported as open).
 */
bool rtd_service_startup(void (*step)(void *context), void *context);

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
