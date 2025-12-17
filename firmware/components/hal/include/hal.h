/**
 * @file hal.h
 * @brief Master HAL include file
 * 
 * Include this single header to get access to all HAL interfaces.
 * 
 * Usage:
 * @code
 * #include "hal.h"
 * 
 * // In application init:
 * hal_init();  // Sets up all HAL implementations
 * 
 * // Or for testing:
 * hal_init_mock();  // Sets up mock implementations
 * @endcode
 */

#ifndef HAL_H
#define HAL_H

#include "hal_types.h"
#include "hal_gpio.h"
#include "hal_adc.h"
#include "hal_pwm.h"
#include "hal_spi.h"
#include "hal_timer.h"

#ifdef __cplusplus
extern "C" {
#endif

/**
 * @brief Initialize HAL with platform-specific implementations
 * 
 * Call this once at startup to configure all HAL interfaces
 * with the appropriate platform drivers.
 * 
 * @return HAL_OK on success
 */
hal_status_t hal_init(void);

/**
 * @brief Initialize HAL with mock implementations
 * 
 * Call this for unit testing to use mock drivers.
 * 
 * @return HAL_OK on success
 */
hal_status_t hal_init_mock(void);

/**
 * @brief Deinitialize HAL
 * 
 * Releases all HAL resources.
 * 
 * @return HAL_OK on success
 */
hal_status_t hal_deinit(void);

/**
 * @brief Check if HAL is initialized
 * 
 * @return true if HAL is ready
 */
bool hal_is_initialized(void);

#ifdef __cplusplus
}
#endif

#endif /* HAL_H */
