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
                           MAX31865_CONFIG_FAULT_CYCLE_AUTOMATIC;

    if (!device_ready(device)) {
        return HAL_ERROR_INVALID_ARG;
    }

    /* Do not set CONFIG.D1 here: fault status is deliberately latched until
     * the safety-reset policy explicitly clears it. */
    return HAL_SPI_WRITE_REG(device->spi_device, MAX31865_REG_CONFIG,
                             &config, 1u);
}

hal_status_t max31865_initialize(max31865_device_t *device,
                                 hal_spi_device_t spi_device)
{
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

    return max31865_start_fault_detection(device);
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
                                          max31865_fault_sink_t fault_sink,
                                          void *context)
{
    uint8_t fault_status = 0u;
    hal_status_t status = max31865_read_fault_status(device, &fault_status);

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
    status = max31865_start_fault_detection(device);
    if (status != HAL_OK && fault_status == 0u && fault_sink != NULL) {
        /* A good completed cycle is not enough if the next cycle cannot be
         * armed: continuing operation would leave the RTD path unmonitored. */
        fault_sink(false, true, context);
    }
    return status;
}

hal_status_t max31865_set_thresholds(const max31865_device_t *device,
                                     uint16_t low_word, uint16_t high_word)
{
    const uint8_t high_threshold[] = {(uint8_t)(high_word >> 8), (uint8_t)high_word};
    const uint8_t low_threshold[] = {(uint8_t)(low_word >> 8), (uint8_t)low_word};
    hal_status_t status;

    if (!device_ready(device)) {
        return HAL_ERROR_INVALID_ARG;
    }
    status = HAL_SPI_WRITE_REG(device->spi_device, MAX31865_REG_HIGH_THRESHOLD_MSB,
                               high_threshold, sizeof(high_threshold));
    if (status != HAL_OK) {
        return status;
    }
    return HAL_SPI_WRITE_REG(device->spi_device, MAX31865_REG_LOW_THRESHOLD_MSB,
                             low_threshold, sizeof(low_threshold));
}

hal_status_t max31865_start_conversions(const max31865_device_t *device)
{
    const uint8_t config = MAX31865_CONFIG_VBIAS | MAX31865_CONFIG_AUTO_CONVERT;

    if (!device_ready(device)) {
        return HAL_ERROR_INVALID_ARG;
    }
    return HAL_SPI_WRITE_REG(device->spi_device, MAX31865_REG_CONFIG, &config, 1u);
}

hal_status_t max31865_clear_fault_status(const max31865_device_t *device)
{
    const uint8_t config = MAX31865_CONFIG_VBIAS | MAX31865_CONFIG_AUTO_CONVERT |
                           MAX31865_CONFIG_FAULT_CLEAR;

    if (!device_ready(device)) {
        return HAL_ERROR_INVALID_ARG;
    }
    return HAL_SPI_WRITE_REG(device->spi_device, MAX31865_REG_CONFIG, &config, 1u);
}

static hal_status_t write_config(const max31865_device_t *device, uint8_t config)
{
    if (!device_ready(device)) {
        return HAL_ERROR_INVALID_ARG;
    }
    return HAL_SPI_WRITE_REG(device->spi_device, MAX31865_REG_CONFIG, &config, 1u);
}

hal_status_t max31865_attach(max31865_device_t *device, hal_spi_device_t spi_device)
{
    if (device == NULL) {
        return HAL_ERROR_INVALID_ARG;
    }
    device->spi_device = spi_device;
    return HAL_OK;
}

hal_status_t max31865_bias_on(const max31865_device_t *device)
{
    return write_config(device, MAX31865_CONFIG_VBIAS);
}

hal_status_t max31865_bias_on_clear(const max31865_device_t *device)
{
    return write_config(device, MAX31865_CONFIG_VBIAS | MAX31865_CONFIG_FAULT_CLEAR);
}

hal_status_t max31865_manual_fault_step1(const max31865_device_t *device)
{
    return write_config(device, MAX31865_CONFIG_VBIAS | MAX31865_CONFIG_FAULT_CYCLE_MANUAL_1);
}

hal_status_t max31865_manual_fault_step2(const max31865_device_t *device)
{
    return write_config(device, MAX31865_CONFIG_VBIAS | MAX31865_CONFIG_FAULT_CYCLE_MANUAL_2);
}

hal_status_t max31865_fault_cycle_busy(const max31865_device_t *device,
                                       bool *busy)
{
    uint8_t config = 0u;
    hal_status_t status;

    if (!device_ready(device) || busy == NULL) {
        return HAL_ERROR_INVALID_ARG;
    }
    status = HAL_SPI_READ_REG(device->spi_device, MAX31865_REG_CONFIG, &config, 1u);
    *busy = (status == HAL_OK) && ((config & MAX31865_CONFIG_FAULT_CYCLE_MASK) != 0u);
    return status;
}

hal_status_t max31865_read_rtd(const max31865_device_t *device,
                               uint8_t *msb, uint8_t *lsb)
{
    uint8_t buf[2] = {0u, 0u};
    hal_status_t status;

    if (!device_ready(device) || msb == NULL || lsb == NULL) {
        return HAL_ERROR_INVALID_ARG;
    }
    status = HAL_SPI_READ_REG(device->spi_device, MAX31865_REG_RTD_MSB, buf, 2u);
    *msb = buf[0];
    *lsb = buf[1];
    return status;
}
