/**
 * @file max31865.c
 * @brief Register-level MAX31865 RTD fault-detection driver.
 */

#include "max31865.h"

#include "config.h"

static bool device_ready(const max31865_device_t *device)
{
    /* Mock SPI represents its first device by handle zero. Production HAL
     * rejects a null handle itself, while accepting it here keeps the driver
     * interface testable without weakening the production failure path. */
    return device != NULL;
}

static void report_fault(max31865_fault_sink_t fault_sink, uint8_t status,
                         void *context)
{
    if (fault_sink == NULL || status == 0u) {
        return;
    }

    /* The low threshold is the explicit short detector. Any remaining
     * MAX31865 status is an unsafe open/out-of-range or analogue-path fault.
     * When both thresholds are present, preserve the low-threshold diagnosis
     * while still causing the same terminal hardware shutdown. */
    fault_sink((status & MAX31865_FAULT_LOW_THRESHOLD) != 0u,
               (status & (uint8_t)~MAX31865_FAULT_LOW_THRESHOLD) != 0u,
               context);
}

hal_status_t max31865_start_fault_detection(const max31865_device_t *device)
{
    const uint8_t config = MAX31865_CONFIG_VBIAS |
                           MAX31865_CONFIG_FAULT_CYCLE_AUTOMATIC |
                           MAX31865_CONFIG_FILTER_60HZ;

    if (!device_ready(device)) {
        return HAL_ERROR_INVALID_ARG;
    }

    /* Do not set CONFIG.D1 here: fault status is deliberately latched until
     * the safety-reset policy explicitly clears it. */
    return HAL_SPI_WRITE_REG(device->spi_device, MAX31865_REG_CONFIG,
                             &config, 1u);
}

hal_status_t max31865_start_continuous(const max31865_device_t *device)
{
    const uint8_t config = MAX31865_CONFIG_VBIAS |
                           MAX31865_CONFIG_CONVERSION_AUTOMATIC |
                           MAX31865_CONFIG_FILTER_60HZ;

    if (!device_ready(device)) {
        return HAL_ERROR_INVALID_ARG;
    }

    /* D6 selects automatic conversion. After the startup diagnostic, this
     * leaves the ADC producing a DRDY for every conversion period. */
    return HAL_SPI_WRITE_REG(device->spi_device, MAX31865_REG_CONFIG,
                             &config, 1u);
}

hal_status_t max31865_read_rtd_code(const max31865_device_t *device,
                                    uint16_t *rtd_code)
{
    uint8_t data[2];
    hal_status_t status;

    if (!device_ready(device) || rtd_code == NULL) {
        return HAL_ERROR_INVALID_ARG;
    }

    /* Reading RTD MSB/LSB is the conversion-data read that releases DRDY.
     * The low bit is the MAX31865 fault flag, not part of the 15-bit code. */
    status = HAL_SPI_READ_REG(device->spi_device, MAX31865_REG_RTD_MSB,
                              data, sizeof(data));
    if (status != HAL_OK) {
        return status;
    }
    *rtd_code = (uint16_t)(((uint16_t)data[0] << 7) |
                           ((uint16_t)data[1] >> 1));
    return HAL_OK;
}

hal_status_t max31865_initialize(max31865_device_t *device,
                                 hal_spi_device_t spi_device)
{
    const uint8_t config = MAX31865_CONFIG_VBIAS;
    const uint8_t high_threshold[] = {
        (uint8_t)(MAX31865_HIGH_THRESHOLD_WORD >> 8),
        (uint8_t)MAX31865_HIGH_THRESHOLD_WORD,
    };
    const uint8_t low_threshold[] = {
        (uint8_t)(MAX31865_LOW_THRESHOLD_WORD >> 8),
        (uint8_t)MAX31865_LOW_THRESHOLD_WORD,
    };
    hal_status_t status;

    if (device == NULL) {
        return HAL_ERROR_INVALID_ARG;
    }

    device->spi_device = spi_device;

    status = HAL_SPI_WRITE_REG(device->spi_device,
                               MAX31865_REG_HIGH_THRESHOLD_MSB,
                               high_threshold, sizeof(high_threshold));
    if (status != HAL_OK) {
        return status;
    }

    status = HAL_SPI_WRITE_REG(device->spi_device,
                               MAX31865_REG_LOW_THRESHOLD_MSB,
                               low_threshold, sizeof(low_threshold));
    if (status != HAL_OK) {
        return status;
    }

    /* Enable BIAS only. The service starts the automatic fault cycle after
     * the MAX31865 10 ms maximum BIAS startup interval. */
    return HAL_SPI_WRITE_REG(device->spi_device, MAX31865_REG_CONFIG,
                             &config, 1u);
}

hal_status_t max31865_read_fault_status(const max31865_device_t *device,
                                        uint8_t *fault_status)
{
    if (!device_ready(device) || fault_status == NULL) {
        return HAL_ERROR_INVALID_ARG;
    }

    return HAL_SPI_READ_REG(device->spi_device, MAX31865_REG_FAULT_STATUS,
                            fault_status, 1u);
}

hal_status_t max31865_service_fault_cycle(const max31865_device_t *device,
                                          uint16_t *rtd_code,
                                          max31865_fault_sink_t fault_sink,
                                          void *context)
{
    uint16_t sample_code = 0u;
    uint8_t fault_status = 0u;
    hal_status_t status = max31865_read_rtd_code(device, &sample_code);

    if (rtd_code != NULL) {
        *rtd_code = sample_code;
    }
    if (status != HAL_OK) {
        if (fault_sink != NULL) {
            fault_sink(false, true, context);
        }
        return status;
    }

    status = max31865_read_fault_status(device, &fault_status);

    if (status != HAL_OK) {
        /* The MCU cannot distinguish a missing/open RTD path from an SPI
         * transport failure safely, so surface it through the same terminal
         * open/out-of-range path. */
        if (fault_sink != NULL) {
            fault_sink(false, true, context);
        }
        return status;
    }

    report_fault(fault_sink, fault_status, context);
    return HAL_OK;
}
