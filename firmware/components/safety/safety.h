/**
 * @file safety.h
 * @brief Safety and watchdog module for induction cooker
 * 
 * Implements:
 * - Task Watchdog Timer (TWDT) monitoring
 * - Logical watchdog (safety check before reset)
 * - Boot reason detection and safe mode
 * - Hardware interlock checking
 */

#ifndef SAFETY_H
#define SAFETY_H

#include <stdint.h>
#include <stdbool.h>

#ifdef __cplusplus
extern "C" {
#endif

/**
 * @brief Watchdog timeout configuration (milliseconds)
 */
#define WDT_TIMEOUT_MS          1000    /**< 1 second timeout (strict) */
#define WDT_TIMEOUT_IDLE_MS     10000   /**< 10 second timeout in idle */
#define WDT_TIMEOUT_INIT_MS     5000    /**< 5 second timeout for POST */

/**
 * @brief Safety fault codes
 */
typedef enum {
    SAFETY_OK = 0,
    SAFETY_OVER_TEMP,
    SAFETY_OVER_CURRENT,
    SAFETY_FAN_FAILURE,
    SAFETY_SENSOR_FAULT,
    SAFETY_INTERLOCK_TRIP,
    SAFETY_PLL_UNLOCK,           /**< PLL lost lock - frequency unstable */
    SAFETY_FREQ_OUT_OF_BOUNDS,   /**< Frequency outside safe operating range */
    SAFETY_ZVS_LOSS              /**< Zero voltage switching failure */
} safety_status_t;

/**
 * @brief Initialize safety watchdog system
 * 
 * Configures ESP32 Task Watchdog Timer to monitor
 * both CPU cores and trigger panic on timeout.
 */
void safety_wdt_init(void);

/**
 * @brief Set watchdog timeout
 * 
 * @param timeout_ms Timeout in milliseconds
 */
void watchdog_set_timeout(uint32_t timeout_ms);

/**
 * @brief Feed (reset) the watchdog timer
 * 
 * Must be called periodically to prevent system reset.
 */
void watchdog_feed(void);

/**
 * @brief Secure watchdog reset with safety check
 * 
 * Only resets watchdog if safety conditions are met.
 * If unsafe, allows watchdog to timeout and reboot.
 */
void secure_wdt_reset(void);

/**
 * @brief Check boot reason and enter safe mode if needed
 * 
 * Call at startup to detect watchdog reset and
 * enter safe mode (PWM disabled) if crash occurred.
 */
void check_boot_reason(void);

/**
 * @brief Enter safe mode
 * 
 * Disables all PWM outputs and requires manual reset.
 */
void enter_safe_mode(void);

/**
 * @brief Check hardware safety interlocks
 * 
 * @return true if all interlocks OK
 */
bool check_hardware_interlocks(void);

/**
 * @brief Check all sensors for valid readings
 * 
 * @return true if all sensors reporting valid data
 */
bool check_sensors_valid(void);

/**
 * @brief Run comprehensive safety check
 *
 * @return SAFETY_OK if all checks pass, fault code otherwise
 */
safety_status_t run_safety_check(void);

/**
 * @brief Check PLL lock status and frequency bounds
 *
 * Per ticket temper-1lj.3: Monitors PLL for:
 * - Lock status (must maintain lock during operation)
 * - Frequency within safe bounds (f_res ± margins)
 *
 * @return SAFETY_OK, SAFETY_PLL_UNLOCK, or SAFETY_FREQ_OUT_OF_BOUNDS
 */
safety_status_t check_pll_safety(void);

/**
 * @brief Check ZVS operation status
 *
 * Per ticket temper-1lj.3: Monitors for hard switching events
 * that indicate ZVS failure and can cause IGBT thermal runaway.
 *
 * @return SAFETY_OK, SAFETY_ZVS_LOSS, or SAFETY_OK with power reduction
 */
safety_status_t check_zvs_safety(void);

/**
 * @brief Trigger emergency hardware shutdown
 * 
 * Immediately disables all power outputs.
 */
void trigger_hardware_shutdown(void);

/**
 * @brief Check if system is in safe mode
 * 
 * @return true if in safe mode
 */
bool is_safe_mode_active(void);

/**
 * @brief Initialize the external hardware watchdog's heartbeat output
 *
 * zapote/controller: TPS3823-33 (U21) WDI on GPIO18 (PIN_IL_WDI, 1 k
 * pull-down). Configures it as an output, low. Call during system
 * initialization, before the WDI supervisor task starts.
 *
 * The legacy board's GPIO map (WDI on GPIO7, RESET_N read on GPIO6, a
 * runaway-cut output on GPIO15) does not exist on zapote: GPIO6/7 are the
 * heatsink and coil ADCs and GPIO15 is the leg-B high-side gate command. The
 * MCU cannot drive the interlock's trip (C4); its stop is RUN_EN low and the
 * gate commands low (pwm_disable_all()). The TPS3823 RESET_N read-back is
 * SUP_RUN_OK_RB on the TCA9555 (EXP_SUP_RUN_OK_RB), which has no driver yet.
 */
void watchdog_hardware_init(void);

/**
 * @brief Drive the TPS3823 WDI pin
 *
 * Only the WDI supervisor task calls this (zapote C42: never an ISR, timer,
 * LEDC or RMT, and never the control loop itself), with the level
 * wdi_sup_step() returns after checking control-loop progress.
 * firmware/tools/check_board_pin_map.py fails if any other file calls it or
 * names PIN_IL_WDI.
 */
void watchdog_hardware_write_wdi(bool level);

/* ============================================================================
 * Simulation API (Non-ESP builds only)
 * 
 * These functions allow test code to inject sensor values and faults
 * for testing safety logic without hardware.
 * ============================================================================ */
#ifndef ESP_PLATFORM
void safety_sim_set_temp(float temp);
void safety_sim_set_current(float current);
void safety_sim_set_rtd(float resistance);
void safety_sim_set_fan(bool running);
void safety_sim_set_strict_mode(bool strict);
void safety_sim_set_wdt_reset(bool active);
void safety_sim_inject_fault(safety_status_t fault);
void safety_sim_reset(void);
uint32_t safety_sim_get_wdt_feeds(void);
uint32_t safety_sim_get_wdi_writes(void);
bool safety_sim_get_wdi_level(void);
#endif

#ifdef __cplusplus
}
#endif

#endif /* SAFETY_H */
