/**
 * @file max31865.h
 * @brief MAX31865 RTD interface and fault-cycle contract.
 *
 * This driver deliberately does not wait for a fault-detection conversion.
 * MAX31865 automatic fault detection completes asynchronously; callers start
 * a cycle, wait for DRDY (or a platform-owned verified delay), then service
 * the completed status and start the next cycle.
 */

#ifndef MAX31865_H
#define MAX31865_H

#include <stdbool.h>
#include <stdint.h>

#include "hal_spi.h"

#ifdef __cplusplus
extern "C" {
#endif

/* MAX31865 register map. */
#define MAX31865_REG_CONFIG             0x00u
#define MAX31865_REG_RTD_MSB            0x01u /* RTD data, 01h MSB / 02h LSB; LSB bit 0 = fault */
#define MAX31865_REG_HIGH_THRESHOLD_MSB 0x03u
#define MAX31865_REG_LOW_THRESHOLD_MSB  0x05u
#define MAX31865_REG_FAULT_STATUS       0x07u

/* Config register bits (datasheet "Configuration Register Definition"). */
#define MAX31865_CONFIG_VBIAS                 0x80u /* D7 bias on */
#define MAX31865_CONFIG_CONVERSION_AUTO       0x40u /* D6 continuous conversions */
#define MAX31865_CONFIG_3WIRE                 0x10u /* D4: 1 = 3-wire, 0 = 2- or 4-wire */
#define MAX31865_CONFIG_FAULT_CYCLE_STEP1     0x08u /* D3:D2 = 10: manual cycle, first step */
#define MAX31865_CONFIG_FAULT_CYCLE_STEP2     0x0Cu /* D3:D2 = 11: manual cycle, second step */
#define MAX31865_CONFIG_FAULT_CYCLE_MASK      0x0Cu /* D3:D2 read back 00 once a cycle is done */
#define MAX31865_CONFIG_FILTER_50HZ           0x01u /* D0: 1 = 50 Hz notch, 0 = 60 Hz */

/* Wiring and mains filter of this board's pan RTD:
 *  - 4-wire (D4 = 0): RTDSensing uses the datasheet 4-wire topology, FORCE+/RTDIN+ and
 *    FORCE-/RTDIN- on separate conductors (zapote/controller/elec/src/modules.ato:2122-2128,
 *    controller-layout; DECISIONS C27 cartridge table: J3 force+/sense+/sense-/force-).
 *  - 60 Hz notch (D0 = 0): the product is 120-127 V~ 60 Hz, US/Canada and Mexico
 *    (zapote/power-stage-120v/DECISIONS.md:299). */
#define MAX31865_CONFIG_WIRING_FILTER 0x00u

/* Manual fault-detection cycle (data sheet "Fault Detection Cycle (D3:D2)"): bias on with conversions
 * off, 100X100Xb, then 100X110Xb, the caller timing the waits (rtd_service.h). The automatic cycle
 * (D3:D2 = 01, or 11 without a prior 10) is invalid on the controller: the CR-1 input filter is far
 * above the 100 us it allows and it flags a healthy probe (controller C37; sensor-r3 D-FCYC). */
#define MAX31865_CONFIG_BIAS_ON      (MAX31865_CONFIG_VBIAS | MAX31865_CONFIG_WIRING_FILTER)
#define MAX31865_CONFIG_MANUAL_STEP1 (MAX31865_CONFIG_BIAS_ON | MAX31865_CONFIG_FAULT_CYCLE_STEP1)
#define MAX31865_CONFIG_MANUAL_STEP2 (MAX31865_CONFIG_BIAS_ON | MAX31865_CONFIG_FAULT_CYCLE_STEP2)
#define MAX31865_CONFIG_CONVERTING   (MAX31865_CONFIG_BIAS_ON | MAX31865_CONFIG_CONVERSION_AUTO)

/* Fault-status bits from register 07h. */
#define MAX31865_FAULT_HIGH_THRESHOLD 0x80u
#define MAX31865_FAULT_LOW_THRESHOLD  0x40u

/* Reference resistor of the pan RTD channel: RTDSensing.r_ref = 430 ohm +/- 0.05 %
 * (zapote/controller/elec/src/modules.ato:1823 on branch controller-layout, 4-wire network,
 * datasheet Figure 4). The same value derives MAX31865_{LOW,HIGH}_THRESHOLD_WORD in config.yaml
 * (firmware/tools/board_derivations.yaml), so the conversion below and the hardware thresholds
 * cannot use different references (checked by test_max31865.c). */
#define MAX31865_RREF_OHM 430.0f

/* RTD data register fault flag (LSB bit 0): set while the code is outside the programmed
 * threshold window (or any other fault-status bit is latched). */
#define MAX31865_RTD_WORD_FAULT 0x0001u

typedef struct {
    hal_spi_device_t spi_device;
} max31865_device_t;

/**
 * Callback used by the driver to deliver a decoded, latched RTD fault.
 *
 * A low-threshold fault is a short. Any other MAX31865 fault status is
 * conservatively reported as open/out-of-range, including a failed SPI read.
 */
typedef void (*max31865_fault_sink_t)(bool short_fault, bool open_fault,
                                      void *context);

/**
 * Write the threshold words, then VBIAS on with conversions off (D1 not set: 07h stays latched).
 * Starts no fault cycle.
 */
hal_status_t max31865_initialize(max31865_device_t *device,
                                 hal_spi_device_t spi_device);

/** Manual fault cycle, step 1 (checks with FORCE- closed, then opens it). A failed write must abort
 * the cycle: step 2's code without step 1 runs the automatic cycle. */
hal_status_t max31865_manual_fault_step1(const max31865_device_t *device);

/** Manual fault cycle, step 2 (checks with FORCE- open, closes it; D3:D2 self-clear). */
hal_status_t max31865_manual_fault_step2(const max31865_device_t *device);

/** Read the raw latched value of MAX31865 fault-status register 07h. */
hal_status_t max31865_read_fault_status(const max31865_device_t *device,
                                        uint8_t *fault_status);

/** Start continuous conversions (CONFIG = MAX31865_CONFIG_CONVERTING). */
hal_status_t max31865_start_conversions(const max31865_device_t *device);

/** *done = the fault-detection cycle has finished (CONFIG D3:D2 read back 00). */
hal_status_t max31865_fault_cycle_done(const max31865_device_t *device, bool *done);

/**
 * Read the latched fault status after a completed cycle and report a set bit. A failed read is
 * reported as open/out-of-range. *fault_reported (may be NULL) is set when the sink was called.
 * Conversions are restarted by the caller, after the input has settled.
 */
hal_status_t max31865_check_fault_status(const max31865_device_t *device,
                                         max31865_fault_sink_t fault_sink,
                                         void *context, bool *fault_reported);

/**
 * A conversion's data word carried the fault bit: read the latched fault
 * status and report it. A failed read, or a clean status despite the bit, is
 * reported as open/out-of-range (fail closed). The sink is always called.
 */
hal_status_t max31865_report_conversion_fault(const max31865_device_t *device,
                                              max31865_fault_sink_t fault_sink,
                                              void *context);

/** Read the 16-bit RTD data word (registers 01h/02h, MSB first). Reading it also releases DRDY
 * (datasheet: DRDY returns high when the RTD data registers are read). */
hal_status_t max31865_read_rtd_word(const max31865_device_t *device,
                                    uint16_t *rtd_word);

/**
 * Pure conversion of an RTD data word to ohms: code = word >> 1 (15 bits),
 * R = code * rref_ohm / 32768. Fail-safe sentinel: +INFINITY when the word's
 * fault bit is set or rref_ohm is not a positive finite value. +INFINITY trips
 * every RTD consumer (state_machine.c "> RTD_GROSS_OPEN_DIAGNOSTIC_OHM" ->
 * FAULT_PROBE_OPEN; safety.c "!isfinite" -> sensor fault); NaN would pass the
 * state machine's ordered comparisons, so it is never returned.
 */
float max31865_rtd_word_to_ohm(uint16_t rtd_word, float rref_ohm);

#ifdef __cplusplus
}
#endif

#endif /* MAX31865_H */
