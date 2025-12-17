/**
 * @file esp32_spi.c
 * @brief ESP32 SPI HAL Implementation
 * 
 * Wraps ESP-IDF SPI master driver for MAX31865 RTD communication.
 * Supports multiple devices on the same bus with DMA transfers.
 */

#include "../include/hal_spi.h"
#include "driver/spi_master.h"
#include "esp_log.h"
#include <string.h>

static const char *TAG = "hal_spi";

/* Maximum SPI buses and devices */
#define MAX_SPI_BUSES       2
#define MAX_SPI_DEVICES     4

/* SPI device handle wrapper */
typedef struct {
    spi_device_handle_t handle;
    hal_spi_bus_t bus;
    bool in_use;
} spi_device_entry_t;

/* Track bus and device state */
static bool s_bus_initialized[MAX_SPI_BUSES];
static spi_device_entry_t s_devices[MAX_SPI_DEVICES];

/* ============================================================================
 * HAL Implementation Functions
 * ============================================================================ */

static hal_status_t esp32_spi_bus_init(hal_spi_bus_t bus, const hal_spi_config_t *config)
{
    if (bus < 0 || bus >= MAX_SPI_BUSES || !config) {
        return HAL_ERROR_INVALID_ARG;
    }
    
    if (s_bus_initialized[bus]) {
        ESP_LOGW(TAG, "SPI bus %d already initialized", bus);
        return HAL_ERROR_BUSY;
    }
    
    /* Map to ESP-IDF SPI host */
    spi_host_device_t host = (bus == 0) ? SPI2_HOST : SPI3_HOST;
    
    /* Configure SPI bus */
    spi_bus_config_t bus_cfg = {
        .mosi_io_num = config->pin_mosi,
        .miso_io_num = config->pin_miso,
        .sclk_io_num = config->pin_sclk,
        .quadwp_io_num = -1,
        .quadhd_io_num = -1,
        .max_transfer_sz = 4096,
    };
    
    /* Initialize bus with DMA (channel auto-allocated in ESP-IDF v5) */
    esp_err_t err = spi_bus_initialize(host, &bus_cfg, SPI_DMA_CH_AUTO);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "Failed to initialize SPI bus %d: %s", bus, esp_err_to_name(err));
        return HAL_ERROR;
    }
    
    s_bus_initialized[bus] = true;
    ESP_LOGI(TAG, "SPI bus %d initialized (host=%d)", bus, host);
    return HAL_OK;
}

static hal_status_t esp32_spi_device_add(hal_spi_bus_t bus, const hal_spi_config_t *config,
                                         hal_spi_device_t *device)
{
    if (bus < 0 || bus >= MAX_SPI_BUSES || !config || !device) {
        return HAL_ERROR_INVALID_ARG;
    }
    
    if (!s_bus_initialized[bus]) {
        return HAL_ERROR_NOT_READY;
    }
    
    /* Find free device slot */
    int slot = -1;
    for (int i = 0; i < MAX_SPI_DEVICES; i++) {
        if (!s_devices[i].in_use) {
            slot = i;
            break;
        }
    }
    
    if (slot < 0) {
        ESP_LOGE(TAG, "No free SPI device slots");
        return HAL_ERROR_NO_MEM;
    }
    
    spi_host_device_t host = (bus == 0) ? SPI2_HOST : SPI3_HOST;
    
    /* Configure device */
    spi_device_interface_config_t dev_cfg = {
        .clock_speed_hz = config->clock_hz,
        .mode = config->mode,
        .spics_io_num = config->pin_cs,
        .queue_size = 4,
        .flags = config->cs_active_high ? SPI_DEVICE_POSITIVE_CS : 0,
    };
    
    esp_err_t err = spi_bus_add_device(host, &dev_cfg, &s_devices[slot].handle);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "Failed to add SPI device: %s", esp_err_to_name(err));
        return HAL_ERROR;
    }
    
    s_devices[slot].bus = bus;
    s_devices[slot].in_use = true;
    *device = (hal_spi_device_t)&s_devices[slot];
    
    ESP_LOGI(TAG, "SPI device added on bus %d, CS pin %d", bus, config->pin_cs);
    return HAL_OK;
}

static hal_status_t esp32_spi_transfer(hal_spi_device_t device, const hal_spi_transaction_t *transaction)
{
    if (!device || !transaction) {
        return HAL_ERROR_INVALID_ARG;
    }
    
    spi_device_entry_t *dev = (spi_device_entry_t *)device;
    if (!dev->in_use) {
        return HAL_ERROR_NOT_READY;
    }
    
    spi_transaction_t trans = {
        .length = transaction->length * 8,  /* Length in bits */
        .tx_buffer = transaction->tx_buffer,
        .rx_buffer = transaction->rx_buffer,
    };
    
    esp_err_t err = spi_device_polling_transmit(dev->handle, &trans);
    if (err != ESP_OK) {
        return HAL_ERROR;
    }
    
    return HAL_OK;
}

static hal_status_t esp32_spi_read_reg(hal_spi_device_t device, uint8_t reg, 
                                        uint8_t *data, size_t len)
{
    if (!device || !data || len == 0) {
        return HAL_ERROR_INVALID_ARG;
    }
    
    spi_device_entry_t *dev = (spi_device_entry_t *)device;
    if (!dev->in_use) {
        return HAL_ERROR_NOT_READY;
    }
    
    /* Prepare TX buffer: register address (MSB=0 for read) + dummy bytes */
    uint8_t tx_buf[17];  /* Max 16 data bytes + 1 address byte */
    uint8_t rx_buf[17];
    
    if (len > 16) {
        return HAL_ERROR_INVALID_ARG;
    }
    
    tx_buf[0] = reg & 0x7F;  /* Clear MSB for read operation */
    memset(&tx_buf[1], 0xFF, len);  /* Dummy bytes for clock cycles */
    
    spi_transaction_t trans = {
        .length = (1 + len) * 8,
        .tx_buffer = tx_buf,
        .rx_buffer = rx_buf,
    };
    
    esp_err_t err = spi_device_polling_transmit(dev->handle, &trans);
    if (err != ESP_OK) {
        return HAL_ERROR;
    }
    
    /* Copy received data (skip first byte which was during address transmission) */
    memcpy(data, &rx_buf[1], len);
    return HAL_OK;
}

static hal_status_t esp32_spi_write_reg(hal_spi_device_t device, uint8_t reg,
                                         const uint8_t *data, size_t len)
{
    if (!device || !data || len == 0) {
        return HAL_ERROR_INVALID_ARG;
    }
    
    spi_device_entry_t *dev = (spi_device_entry_t *)device;
    if (!dev->in_use) {
        return HAL_ERROR_NOT_READY;
    }
    
    /* Prepare TX buffer: register address (MSB=1 for write) + data */
    uint8_t tx_buf[17];
    
    if (len > 16) {
        return HAL_ERROR_INVALID_ARG;
    }
    
    tx_buf[0] = reg | 0x80;  /* Set MSB for write operation */
    memcpy(&tx_buf[1], data, len);
    
    spi_transaction_t trans = {
        .length = (1 + len) * 8,
        .tx_buffer = tx_buf,
        .rx_buffer = NULL,
    };
    
    esp_err_t err = spi_device_polling_transmit(dev->handle, &trans);
    if (err != ESP_OK) {
        return HAL_ERROR;
    }
    
    return HAL_OK;
}

static hal_status_t esp32_spi_device_remove(hal_spi_device_t device)
{
    if (!device) {
        return HAL_ERROR_INVALID_ARG;
    }
    
    spi_device_entry_t *dev = (spi_device_entry_t *)device;
    if (!dev->in_use) {
        return HAL_OK;
    }
    
    esp_err_t err = spi_bus_remove_device(dev->handle);
    if (err != ESP_OK) {
        return HAL_ERROR;
    }
    
    dev->handle = NULL;
    dev->in_use = false;
    
    ESP_LOGD(TAG, "SPI device removed");
    return HAL_OK;
}

static hal_status_t esp32_spi_bus_deinit(hal_spi_bus_t bus)
{
    if (bus < 0 || bus >= MAX_SPI_BUSES) {
        return HAL_ERROR_INVALID_ARG;
    }
    
    if (!s_bus_initialized[bus]) {
        return HAL_OK;
    }
    
    /* Remove all devices on this bus first */
    for (int i = 0; i < MAX_SPI_DEVICES; i++) {
        if (s_devices[i].in_use && s_devices[i].bus == bus) {
            esp32_spi_device_remove(&s_devices[i]);
        }
    }
    
    spi_host_device_t host = (bus == 0) ? SPI2_HOST : SPI3_HOST;
    
    esp_err_t err = spi_bus_free(host);
    if (err != ESP_OK) {
        return HAL_ERROR;
    }
    
    s_bus_initialized[bus] = false;
    ESP_LOGI(TAG, "SPI bus %d deinitialized", bus);
    return HAL_OK;
}

/* ============================================================================
 * Export Operations Struct
 * ============================================================================ */

const hal_spi_ops_t hal_spi_esp32_ops = {
    .bus_init = esp32_spi_bus_init,
    .device_add = esp32_spi_device_add,
    .transfer = esp32_spi_transfer,
    .read_reg = esp32_spi_read_reg,
    .write_reg = esp32_spi_write_reg,
    .device_remove = esp32_spi_device_remove,
    .bus_deinit = esp32_spi_bus_deinit
};
