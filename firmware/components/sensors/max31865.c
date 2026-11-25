/**
 * @file max31865.c
 * @brief Register-level MAX31865 RTD fault-detection driver.
 */

#include "max31865.h"

#include "config.h"

#include <math.h>

static bool device_ready(const max31865_device_t *device)
{
    /* Mock SPI represents its first device by handle zero. Production HAL
     * rejects a null handle itself, while accepting it here keeps the driver
     * interface testable without weakening the production failure path. */
    return device != NULL;
}

void max31865_report_status(max31865_fault_sink_t fault_sink, uint8_t status, void *context)
{
    bool is_short;

    if (fault_sink == NULL || status == 0u) {
        return;
    }
    /* Diagnosis only: both outcomes take the same hardware shutdown. RTD-low is a short. RTDIN- /
     * REFIN- low are a short to ground (07h 0x18) unless REFIN- is also high: an open element or
     * open FORCE+ reads 0x28 and an open FORCE- 0x20 (sensor-r3 fault-cycle.json). */
    is_short = (status & MAX31865_FAULT_LOW_THRESHOLD) != 0u ||
               ((status & (MAX31865_FAULT_REFIN_LOW | MAX31865_FAULT_RTDIN_LOW)) != 0u &&
                (status & MAX31865_FAULT_REFIN_HIGH) == 0u);
    fault_sink(is_short, !is_short, context);
}

static hal_status_t write_config(const max31865_device_t *device, uint8_t config)
{
    if (!device_ready(device)) {
        return HAL_ERROR_INVALID_ARG;
    }
    /* D1 (fault clear) is set only by max31865_bias_on_clear(), for a reset verification. */
    return HAL_SPI_WRITE_REG(device->spi_device, MAX31865_REG_CONFIG, &config, 1u);
}

hal_status_t max31865_bias_on_clear(const max31865_device_t *device)
{
    return write_config(device, MAX31865_CONFIG_BIAS_CLEAR);
}

hal_status_t max31865_manual_fault_step1(const max31865_device_t *device)
{
    return write_config(device, MAX31865_CONFIG_MANUAL_STEP1);
}

hal_status_t max31865_manual_fault_step2(const max31865_device_t *device)
{
    return write_config(device, MAX31865_CONFIG_MANUAL_STEP2);
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

    return write_config(device, MAX31865_CONFIG_BIAS_ON);
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

hal_status_t max31865_start_conversions(const max31865_device_t *device)
{
    return write_config(device, MAX31865_CONFIG_CONVERTING);
}

hal_status_t max31865_fault_cycle_done(const max31865_device_t *device, bool *done)
{
    uint8_t config = 0u;
    hal_status_t status;

    if (!device_ready(device) || done == NULL) {
        return HAL_ERROR_INVALID_ARG;
    }
    status = HAL_SPI_READ_REG(device->spi_device, MAX31865_REG_CONFIG, &config, 1u);
    if (status == HAL_OK) {
        *done = (config & MAX31865_CONFIG_FAULT_CYCLE_MASK) == 0u;
    }
    return status;
}

hal_status_t max31865_check_fault_status(const max31865_device_t *device,
                                         max31865_fault_sink_t fault_sink,
                                         void *context, bool *fault_reported)
{
    uint8_t fault_status = 0u;
    hal_status_t status = max31865_read_fault_status(device, &fault_status);

    if (fault_reported != NULL) {
        *fault_reported = false;
    }
    if (status == HAL_OK && fault_status == 0u) {
        return HAL_OK;
    }
    if (fault_sink != NULL) {
        if (status != HAL_OK) {
            /* A transport failure cannot be told from an open RTD path: same terminal path. */
            fault_sink(false, true, context);
        } else {
            max31865_report_status(fault_sink, fault_status, context);
        }
        if (fault_reported != NULL) {
            *fault_reported = true;
        }
    }
    return status;
}

hal_status_t max31865_read_rtd_word(const max31865_device_t *device,
                                    uint16_t *rtd_word)
{
    uint8_t raw[2] = {0u, 0u};
    hal_status_t status;

    if (!device_ready(device) || rtd_word == NULL) {
        return HAL_ERROR_INVALID_ARG;
    }

    status = HAL_SPI_READ_REG(device->spi_device, MAX31865_REG_RTD_MSB, raw,
                              sizeof(raw));
    if (status == HAL_OK) {
        *rtd_word = (uint16_t)(((uint16_t)raw[0] << 8) | raw[1]);
    }
    return status;
}

float max31865_rtd_word_to_ohm(uint16_t rtd_word, float rref_ohm)
{
    if ((rtd_word & MAX31865_RTD_WORD_FAULT) != 0u || !(rref_ohm > 0.0f) ||
        !isfinite(rref_ohm)) {
        return INFINITY;
    }
    return (float)(rtd_word >> 1) * rref_ohm / 32768.0f;
}
