/**
 * @file temper_pins.h
 * @brief Temper PCB Pin Assignments for ESP32-S3
 * 
 * Defines all GPIO pin mappings between the ESP32-S3-WROOM-1 module
 * and the Temper induction cooker PCB peripherals.
 * 
 * NOTE: Pin numbers are provisional until PCB layout is finalized.
 * Update these values after routing is complete.
 */

#ifndef TEMPER_PINS_H
#define TEMPER_PINS_H

#ifdef __cplusplus
extern "C" {
#endif

/* ============================================================================
 * Gate Driver PWM Pins (UCC21550)
 * 
 * These pins connect to the isolated gate driver for half-bridge control.
 * Uses MCPWM peripheral for hardware dead-time insertion.
 * ============================================================================ */

/** High-side gate driver input (UCC21550 INA) */
#define PIN_PWM_HI              4

/** Low-side gate driver input (UCC21550 INB) */
#define PIN_PWM_LO              5

/* ============================================================================
 * ADC Pins
 * 
 * Analog inputs for current and voltage sensing.
 * ESP32-S3 ADC1 channels used (ADC2 unavailable when WiFi active).
 * ============================================================================ */

/** Current transformer burden voltage (ADC1_CH0 = GPIO1) */
#define PIN_ADC_CURRENT         1
#define ADC_CHANNEL_CURRENT     ADC_CHANNEL_0

/** Bus voltage divider output (ADC1_CH1 = GPIO2) */
#define PIN_ADC_VOLTAGE         2
#define ADC_CHANNEL_VOLTAGE     ADC_CHANNEL_1

/** NTC thermistor for IGBT temperature (ADC1_CH2 = GPIO3) */
#define PIN_ADC_NTC             3
#define ADC_CHANNEL_NTC         ADC_CHANNEL_2

/* ============================================================================
 * SPI Pins (MAX31865 RTD Interface)
 * 
 * SPI bus for precision temperature measurement via MAX31865.
 * Using SPI2 (HSPI) host on ESP32-S3.
 * ============================================================================ */

/** SPI Clock */
#define PIN_SPI_CLK             12

/** SPI Master Out Slave In */
#define PIN_SPI_MOSI            11

/** SPI Master In Slave Out */
#define PIN_SPI_MISO            13

/** Chip Select for RTD sensor 1 (coil temperature) */
#define PIN_SPI_CS_RTD1         10

/** Chip Select for RTD sensor 2 (ambient temperature) */
#define PIN_SPI_CS_RTD2         9

/* ============================================================================
 * Control and Status Pins
 * ============================================================================ */

/** Zero-crossing detector input (from comparator output) */
#define PIN_ZCD_INPUT           6

/** Hardware watchdog kick output (to TPS3823) */
#define PIN_WDT_KICK            7

/** Fault output to hardware safety latch (active low) */
#define PIN_FAULT_OUT           8

/** Inrush limiter bypass relay control */
#define PIN_RELAY_BYPASS        15

/** Master reset input from hardware safety system */
#define PIN_RESET_INPUT         16

/* ============================================================================
 * User Interface Pins
 * ============================================================================ */

/** Fault indicator LED (active high) */
#define PIN_LED_FAULT           17

/** Power indicator LED (active high) */
#define PIN_LED_POWER           18

/** User reset button (active low with pull-up) */
#define PIN_BUTTON_RESET        0   /* GPIO0 - boot button, use with care */

/* ============================================================================
 * I2C Pins (Optional - for future expansion)
 * ============================================================================ */

/** I2C Data (isolated via ADUM1250) */
#define PIN_I2C_SDA             38

/** I2C Clock (isolated via ADUM1250) */
#define PIN_I2C_SCL             39

/* ============================================================================
 * Debug/Programming Pins
 * 
 * Reserved for JTAG and UART, do not use for general I/O.
 * ============================================================================ */

/** UART TX for debug console */
#define PIN_UART_TX             43

/** UART RX for debug console */
#define PIN_UART_RX             44

/* ============================================================================
 * MCPWM Configuration
 * ============================================================================ */

/** MCPWM unit for gate driver (0 or 1) */
#define MCPWM_UNIT_GATE_DRIVER  0

/** MCPWM timer for gate driver (0, 1, or 2) */
#define MCPWM_TIMER_GATE_DRIVER 0

#ifdef __cplusplus
}
#endif

#endif /* TEMPER_PINS_H */
