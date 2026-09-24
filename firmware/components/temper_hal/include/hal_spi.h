/**
 * @file hal_spi.h
 * @brief SPI Hardware Abstraction Layer
 * 
 * Provides platform-independent SPI operations for:
 * - Master mode communication
 * - Full-duplex transfers
 * - Register read/write helpers
 * 
 * Used by:
 * - MAX31865 RTD temperature sensor
 * - Any future SPI peripherals
 */

#ifndef HAL_SPI_H
#define HAL_SPI_H

#include "hal_types.h"

#ifdef __cplusplus
extern "C" {
#endif

/**
 * @brief SPI operations interface
 */
typedef struct {
    /**
     * @brief Initialize SPI bus
     * 
     * @param bus SPI bus identifier
     * @param config SPI configuration
     * @return HAL_OK on success
     */
    hal_status_t (*bus_init)(hal_spi_bus_t bus, const hal_spi_config_t *config);
    
    /**
     * @brief Add device to SPI bus
     * 
     * @param bus SPI bus identifier
     * @param config Device configuration
     * @param device Pointer to store device handle
     * @return HAL_OK on success
     */
    hal_status_t (*device_add)(hal_spi_bus_t bus, const hal_spi_config_t *config,
                               hal_spi_device_t *device);
    
    /**
     * @brief Perform SPI transfer
     * 
     * Full-duplex transfer: transmits tx_buffer while receiving into rx_buffer.
     * Either buffer can be NULL for transmit-only or receive-only.
     * 
     * @param device SPI device handle
     * @param transaction Transaction descriptor
     * @return HAL_OK on success
     */
    hal_status_t (*transfer)(hal_spi_device_t device, const hal_spi_transaction_t *transaction);
    
    /**
     * @brief Read register from SPI device
     * 
     * Convenience function for register-based devices.
     * 
     * @param device SPI device handle
     * @param reg Register address
     * @param data Pointer to store read data
     * @param len Number of bytes to read
     * @return HAL_OK on success
     */
    hal_status_t (*read_reg)(hal_spi_device_t device, uint8_t reg, uint8_t *data, size_t len);
    
    /**
     * @brief Write register to SPI device
     * 
     * @param device SPI device handle
     * @param reg Register address
     * @param data Data to write
     * @param len Number of bytes to write
     * @return HAL_OK on success
     */
    hal_status_t (*write_reg)(hal_spi_device_t device, uint8_t reg, const uint8_t *data, size_t len);
    
    /**
     * @brief Remove device from SPI bus
     * 
     * @param device SPI device handle
     * @return HAL_OK on success
     */
    hal_status_t (*device_remove)(hal_spi_device_t device);
    
    /**
     * @brief Deinitialize SPI bus
     * 
     * @param bus SPI bus identifier
     * @return HAL_OK on success
     */
    hal_status_t (*bus_deinit)(hal_spi_bus_t bus);
} hal_spi_ops_t;

/**
 * @brief Global SPI operations pointer
 */
extern const hal_spi_ops_t *hal_spi;

/**
 * @brief Set SPI operations implementation
 */
void hal_spi_set_ops(const hal_spi_ops_t *ops);

/* ============================================================================
 * Convenience Macros
 * ============================================================================ */

/**
 * @brief Read SPI register (convenience wrapper)
 */
#define HAL_SPI_READ_REG(device, reg, data, len) \
    (hal_spi ? hal_spi->read_reg((device), (reg), (data), (len)) : HAL_ERROR_NOT_READY)

/**
 * @brief Write SPI register (convenience wrapper)
 */
#define HAL_SPI_WRITE_REG(device, reg, data, len) \
    (hal_spi ? hal_spi->write_reg((device), (reg), (data), (len)) : HAL_ERROR_NOT_READY)

#ifdef __cplusplus
}
#endif

#endif /* HAL_SPI_H */
