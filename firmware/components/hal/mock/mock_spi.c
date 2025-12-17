/**
 * @file mock_spi.c
 * @brief Mock SPI implementation for testing
 * 
 * Provides simulated SPI with:
 * - Transaction recording
 * - Response injection for register reads
 * - Device simulation (e.g., MAX31865)
 */

#include "../include/hal_spi.h"
#include <string.h>
#include <stdbool.h>
#include <stddef.h>

/* Maximum buses and devices */
#define MOCK_SPI_MAX_BUSES 4
#define MOCK_SPI_MAX_DEVICES 8
#define MOCK_SPI_REG_SIZE 256

/* Device state (simulated register file) */
typedef struct {
    bool in_use;
    hal_spi_bus_t bus;
    hal_spi_config_t config;
    uint8_t registers[MOCK_SPI_REG_SIZE];
} mock_spi_device_t;

/* Bus state */
typedef struct {
    bool initialized;
    hal_spi_config_t config;
} mock_spi_bus_t;

static mock_spi_bus_t s_buses[MOCK_SPI_MAX_BUSES];
static mock_spi_device_t s_devices[MOCK_SPI_MAX_DEVICES];
static uint32_t s_call_count_transfer = 0;

/* ============================================================================
 * Mock Control Functions
 * ============================================================================ */

void mock_spi_reset(void)
{
    memset(s_buses, 0, sizeof(s_buses));
    memset(s_devices, 0, sizeof(s_devices));
    s_call_count_transfer = 0;
}

void mock_spi_set_register(hal_spi_device_t device, uint8_t reg, uint8_t value)
{
    intptr_t idx = (intptr_t)device;
    if (idx >= 0 && idx < MOCK_SPI_MAX_DEVICES && s_devices[idx].in_use) {
        s_devices[idx].registers[reg] = value;
    }
}

uint8_t mock_spi_get_register(hal_spi_device_t device, uint8_t reg)
{
    intptr_t idx = (intptr_t)device;
    if (idx >= 0 && idx < MOCK_SPI_MAX_DEVICES && s_devices[idx].in_use) {
        return s_devices[idx].registers[reg];
    }
    return 0;
}

void mock_spi_set_register_block(hal_spi_device_t device, uint8_t start_reg, 
                                  const uint8_t *data, size_t len)
{
    intptr_t idx = (intptr_t)device;
    if (idx >= 0 && idx < MOCK_SPI_MAX_DEVICES && s_devices[idx].in_use) {
        for (size_t i = 0; i < len && (start_reg + i) < MOCK_SPI_REG_SIZE; i++) {
            s_devices[idx].registers[start_reg + i] = data[i];
        }
    }
}

uint32_t mock_spi_get_transfer_count(void) { return s_call_count_transfer; }

/* ============================================================================
 * HAL Implementation
 * ============================================================================ */

static hal_status_t mock_spi_bus_init(hal_spi_bus_t bus, const hal_spi_config_t *config)
{
    if (bus < 0 || bus >= MOCK_SPI_MAX_BUSES || !config) {
        return HAL_ERROR_INVALID_ARG;
    }
    
    s_buses[bus].initialized = true;
    s_buses[bus].config = *config;
    return HAL_OK;
}

static hal_status_t mock_spi_device_add(hal_spi_bus_t bus, const hal_spi_config_t *config,
                                        hal_spi_device_t *device)
{
    if (bus < 0 || bus >= MOCK_SPI_MAX_BUSES || !config || !device) {
        return HAL_ERROR_INVALID_ARG;
    }
    
    if (!s_buses[bus].initialized) {
        return HAL_ERROR_NOT_READY;
    }
    
    /* Find free device slot */
    for (int i = 0; i < MOCK_SPI_MAX_DEVICES; i++) {
        if (!s_devices[i].in_use) {
            s_devices[i].in_use = true;
            s_devices[i].bus = bus;
            s_devices[i].config = *config;
            memset(s_devices[i].registers, 0, MOCK_SPI_REG_SIZE);
            *device = (hal_spi_device_t)(intptr_t)i;
            return HAL_OK;
        }
    }
    
    return HAL_ERROR_NO_MEM;
}

static hal_status_t mock_spi_transfer(hal_spi_device_t device, 
                                      const hal_spi_transaction_t *transaction)
{
    s_call_count_transfer++;
    
    intptr_t idx = (intptr_t)device;
    if (idx < 0 || idx >= MOCK_SPI_MAX_DEVICES || !transaction) {
        return HAL_ERROR_INVALID_ARG;
    }
    
    if (!s_devices[idx].in_use) {
        return HAL_ERROR_NOT_READY;
    }
    
    /* Simple loopback/echo for testing */
    if (transaction->tx_buffer && transaction->rx_buffer) {
        memcpy(transaction->rx_buffer, transaction->tx_buffer, transaction->length);
    }
    
    return HAL_OK;
}

static hal_status_t mock_spi_read_reg(hal_spi_device_t device, uint8_t reg, 
                                      uint8_t *data, size_t len)
{
    s_call_count_transfer++;
    
    intptr_t idx = (intptr_t)device;
    if (idx < 0 || idx >= MOCK_SPI_MAX_DEVICES || !data) {
        return HAL_ERROR_INVALID_ARG;
    }
    
    if (!s_devices[idx].in_use) {
        return HAL_ERROR_NOT_READY;
    }
    
    /* Read from simulated register file */
    for (size_t i = 0; i < len && (reg + i) < MOCK_SPI_REG_SIZE; i++) {
        data[i] = s_devices[idx].registers[reg + i];
    }
    
    return HAL_OK;
}

static hal_status_t mock_spi_write_reg(hal_spi_device_t device, uint8_t reg,
                                       const uint8_t *data, size_t len)
{
    s_call_count_transfer++;
    
    intptr_t idx = (intptr_t)device;
    if (idx < 0 || idx >= MOCK_SPI_MAX_DEVICES || !data) {
        return HAL_ERROR_INVALID_ARG;
    }
    
    if (!s_devices[idx].in_use) {
        return HAL_ERROR_NOT_READY;
    }
    
    /* Write to simulated register file */
    for (size_t i = 0; i < len && (reg + i) < MOCK_SPI_REG_SIZE; i++) {
        s_devices[idx].registers[reg + i] = data[i];
    }
    
    return HAL_OK;
}

static hal_status_t mock_spi_device_remove(hal_spi_device_t device)
{
    intptr_t idx = (intptr_t)device;
    if (idx < 0 || idx >= MOCK_SPI_MAX_DEVICES) {
        return HAL_ERROR_INVALID_ARG;
    }
    
    memset(&s_devices[idx], 0, sizeof(mock_spi_device_t));
    return HAL_OK;
}

static hal_status_t mock_spi_bus_deinit(hal_spi_bus_t bus)
{
    if (bus < 0 || bus >= MOCK_SPI_MAX_BUSES) {
        return HAL_ERROR_INVALID_ARG;
    }
    
    s_buses[bus].initialized = false;
    return HAL_OK;
}

/* ============================================================================
 * Export Operations Struct
 * ============================================================================ */

const hal_spi_ops_t hal_spi_mock_ops = {
    .bus_init = mock_spi_bus_init,
    .device_add = mock_spi_device_add,
    .transfer = mock_spi_transfer,
    .read_reg = mock_spi_read_reg,
    .write_reg = mock_spi_write_reg,
    .device_remove = mock_spi_device_remove,
    .bus_deinit = mock_spi_bus_deinit
};
