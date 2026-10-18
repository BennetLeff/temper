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
#define MAX31865_REG_HIGH_THRESHOLD_MSB 0x03u
#define MAX31865_REG_LOW_THRESHOLD_MSB  0x05u
#define MAX31865_REG_FAULT_STATUS       0x07u
#define MAX31865_REG_RTD_MSB            0x01u  /* MSB, then LSB (bit 0 = fault) */

/* Config register values. The automatic fault cycle (D3:D2 = 01) is the legacy
 * board's; the C1 board (zapote C37, CR-1 filter) uses the manual cycle only
 * (D3:D2 = 10, then 11; data sheet "Fault Detection Cycle (D3:D2)", Table 3). */
#define MAX31865_CONFIG_VBIAS                 0x80u
#define MAX31865_CONFIG_FAULT_CYCLE_AUTOMATIC 0x04u
#define MAX31865_CONFIG_FAULT_CYCLE_MANUAL_1  0x08u   /* 100X100Xb: run, manual delay      */
#define MAX31865_CONFIG_FAULT_CYCLE_MANUAL_2  0x0Cu   /* 100X110Xb: finish, manual delay   */
#define MAX31865_CONFIG_AUTO_CONVERT          0x40u
#define MAX31865_CONFIG_ONE_SHOT              0x20u
#define MAX31865_CONFIG_FAULT_CLEAR           0x02u
#define MAX31865_CONFIG_FAULT_CYCLE_MASK      0x0Cu

/* Fault-status bits from register 07h. */
#define MAX31865_FAULT_HIGH_THRESHOLD 0x80u
#define MAX31865_FAULT_LOW_THRESHOLD  0x40u
#define MAX31865_FAULT_REFIN_HIGH     0x20u   /* D5: REFIN- > 0.85 VBIAS, FORCE- closed */
#define MAX31865_FAULT_REFIN_LOW      0x10u   /* D4: REFIN- < 0.85 VBIAS, FORCE- open   */
#define MAX31865_FAULT_RTDIN_LOW      0x08u   /* D3: RTDIN- < 0.85 VBIAS, FORCE- open   */
#define MAX31865_FAULT_OVUV           0x04u   /* D2: over/undervoltage                  */

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
 * Write the configured threshold words and start an asynchronous automatic
 * fault-detection cycle. Does not claim that a conversion has completed.
 */
hal_status_t max31865_initialize(max31865_device_t *device,
                                 hal_spi_device_t spi_device);

/** Start an asynchronous automatic fault-detection cycle. */
hal_status_t max31865_start_fault_detection(const max31865_device_t *device);

/** Read the raw latched value of MAX31865 fault-status register 07h. */
hal_status_t max31865_read_fault_status(const max31865_device_t *device,
                                        uint8_t *fault_status);

/**
 * Service a completed fault-detection cycle and immediately start the next
 * one. The caller must invoke this only after DRDY or a verified completion
 * delay. A status-read failure, or failure to arm the next cycle after a
 * clean status, is reported as open/out-of-range before the error is
 * returned, so the safety path fails closed.
 */
hal_status_t max31865_service_fault_cycle(const max31865_device_t *device,
                                          max31865_fault_sink_t fault_sink,
                                          void *context);

/* ---- Continuous conversion (sensor-r3 C1, pcb/CHANGE-REQUEST.md CR-7) ---- */

/** Write the low/high fault-threshold register words. */
hal_status_t max31865_set_thresholds(const max31865_device_t *device,
                                     uint16_t low_word, uint16_t high_word);

/** CONFIG 0xC0: VBIAS on, automatic conversion, 4-wire, 60 Hz notch. */
hal_status_t max31865_start_conversions(const max31865_device_t *device);

/**
 * CONFIG 0xC2: as max31865_start_conversions, with the fault-status clear bit
 * (D1) set, so register 07h and the RTD LSB fault bit return to 0 and the
 * next conversion reports only its own condition. Called only by the safety
 * reset policy (rtd_service_request_fault_clear, DECISIONS.md D-OPEN).
 */
hal_status_t max31865_clear_fault_status(const max31865_device_t *device);

/* ---- Manual fault-detection cycle (sensor-r3 C1 on the CR-1 board) -------
 *
 * Data sheet (19-6478 Rev 3), "Fault Detection Cycle (D3:D2)": with an input
 * filter time constant above 100 us the cycle must be timed manually. The
 * caller owns the waits (rtd_service.c: RTD_C1_FAULT_CYCLE_STEP_US from
 * output/temper-sensor-r3/firmware/fault_cycle.py) and calls, in order:
 *   max31865_attach              handle only, no register write;
 *   max31865_bias_on             CONFIG 0x80: VBIAS on, conversions off
 *                                ("Normally Off"), wait >= 5 tau;
 *   max31865_bias_on_clear       CONFIG 0x82: the same with D1 (fault-status
 *                                clear; D5/D3/D2 written 0, as D1 requires);
 *   max31865_manual_fault_step1  CONFIG 0x88: checks REFIN- with FORCE-
 *                                closed (D5), then opens FORCE-; D3:D2 stay 10;
 *                                wait >= 5 tau;
 *   max31865_manual_fault_step2  CONFIG 0x8C: checks REFIN- and RTDIN- with
 *                                FORCE- open (D4, D3), closes FORCE-, D3:D2
 *                                self-clear to 00;
 *   max31865_fault_cycle_busy    until D3:D2 = 00, then
 *   max31865_read_fault_status   register 07h.
 * Writing step 2 without step 1 runs the automatic cycle instead (data sheet),
 * so a failed step-1 write must abort the sequence. */

/** Store the SPI handle; no register access. */
hal_status_t max31865_attach(max31865_device_t *device, hal_spi_device_t spi_device);

/** CONFIG 0x80: VBIAS on, automatic conversion off, 4-wire, 60 Hz notch. */
hal_status_t max31865_bias_on(const max31865_device_t *device);

/** CONFIG 0x82: as max31865_bias_on, with the fault-status clear bit (D1). */
hal_status_t max31865_bias_on_clear(const max31865_device_t *device);

/** CONFIG 0x88: manual fault detection, first step (FORCE- closed check). */
hal_status_t max31865_manual_fault_step1(const max31865_device_t *device);

/** CONFIG 0x8C: manual fault detection, second step (FORCE- open check). */
hal_status_t max31865_manual_fault_step2(const max31865_device_t *device);

/** True while a fault-detection cycle is still running (CONFIG D3:D2 != 0). */
hal_status_t max31865_fault_cycle_busy(const max31865_device_t *device,
                                       bool *busy);

/** Read the RTD register pair (01h MSB, 02h LSB; LSB bit 0 = fault flag). */
hal_status_t max31865_read_rtd(const max31865_device_t *device,
                               uint8_t *msb, uint8_t *lsb);

#ifdef __cplusplus
}
#endif

#endif /* MAX31865_H */
