#pragma once
/* Net names and physical ADC pins are locked to the Rev C schematic. */
#define HARDWARE_REVISION "C-local100p"
#define PIN_ADC_A 2u       /* ADS9224R pin 24, SDO-0A */
#define PIN_ADC_B 3u       /* ADS9224R pin 20, SDO-0B */
#define PIN_ADC_CS 4u      /* ADS9224R pin 14 */
#define PIN_ADC_SCLK 5u    /* ADS9224R pin 16 */
#define PIN_ADC_CONVST 6u  /* ADS9224R pin 13 */
#define PIN_ADC_SDI 7u     /* ADS9224R pin 15 */
#define PIN_ADC_RESET 8u   /* ADS9224R pin 26 */
#define PIN_DDS_FSYNC 9u   /* AD9833 pin 8 */
#define PIN_DDS_SCLK 10u   /* AD9833 pin 7 */
#define PIN_DDS_DATA 11u   /* AD9833 pin 6 */
#define PIN_ADC_READY 12u  /* ADS9224R pin 25 */
#define PIN_USB_VBUS 13u   /* VBUS divided by two; no connection to board 5 V */
#define PIN_UART_TX 28u    /* Optional UART0 header J6; RP2040 pin 40 */
#define PIN_UART_RX 29u    /* Optional UART0 header J6; RP2040 pin 41 */
#define PIN_DDS_MCLK 21u   /* CLK_GPOUT0: common 120 MHz system clock / 5 */
#define PIN_LED 25u
#define DDS_CLOCK_HZ 24000000u
#define SYSTEM_CLOCK_HZ 120000000u
#define CAPTURE_CYCLES 120u
#define MAX_SAMPLES 32768u
