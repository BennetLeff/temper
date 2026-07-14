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

/* Config register values used by the non-blocking automatic fault cycle. */
#define MAX31865_CONFIG_VBIAS                 0x80u
#define MAX31865_CONFIG_FAULT_CYCLE_AUTOMATIC 0x04u

/* Fault-status bits from register 07h. */
#define MAX31865_FAULT_HIGH_THRESHOLD 0x80u
#define MAX31865_FAULT_LOW_THRESHOLD  0x40u

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

#ifdef __cplusplus
}
#endif

#endif /* MAX31865_H */
