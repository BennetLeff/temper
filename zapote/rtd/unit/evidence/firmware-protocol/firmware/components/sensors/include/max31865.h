/**
 * @file max31865.h
 * @brief MAX31865 RTD interface and fault-cycle contract.
 *
 * MAX31865 automatic fault detection and ADC conversion are separate phases.
 * The service waits for BIAS startup, runs the automatic fault cycle once,
 * starts continuous conversion, then reads RTD data before servicing status.
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
#define MAX31865_REG_RTD_MSB            0x01u
#define MAX31865_REG_HIGH_THRESHOLD_MSB 0x03u
#define MAX31865_REG_LOW_THRESHOLD_MSB  0x05u
#define MAX31865_REG_FAULT_STATUS       0x07u

/* Config register values. Automatic fault detection does not start a
 * conversion; continuous conversion is enabled only after that cycle. */
#define MAX31865_CONFIG_VBIAS                 0x80u
#define MAX31865_CONFIG_CONVERSION_AUTOMATIC  0x40u
#define MAX31865_CONFIG_FAULT_CYCLE_AUTOMATIC 0x04u
#define MAX31865_CONFIG_FILTER_60HZ           0x00u

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

/** Start asynchronous automatic conversion; each completed conversion asserts DRDY. */
hal_status_t max31865_start_continuous(const max31865_device_t *device);

/** Read and right-align the 15-bit RTD conversion; this read releases DRDY. */
hal_status_t max31865_read_rtd_code(const max31865_device_t *device,
                                    uint16_t *rtd_code);

/** Read the raw latched value of MAX31865 fault-status register 07h. */
hal_status_t max31865_read_fault_status(const max31865_device_t *device,
                                        uint8_t *fault_status);

/**
 * Service a completed automatic conversion: read RTD data first to release
 * DRDY, then read the latched fault status. A read failure fails closed
 * through the open/out-of-range callback. Automatic fault detection is run
 * once during startup; it is not re-armed on every conversion.
 */
hal_status_t max31865_service_fault_cycle(const max31865_device_t *device,
                                          uint16_t *rtd_code,
                                          max31865_fault_sink_t fault_sink,
                                          void *context);

#ifdef __cplusplus
}
#endif

#endif /* MAX31865_H */
