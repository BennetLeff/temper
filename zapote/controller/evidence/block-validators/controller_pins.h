/* Controller RTD pin facts, transcribed from zapote/controller (the repo's
 * firmware/ tree still carries the pre-controller pin map).
 *   RTD_CS_N : ESP32-S3 GPIO10   (controller.ato: mcu.IO10 ~ rtd_cs_n; DECISIONS C2)
 *   RTD_DRDY : not a GPIO. TCA9555 expander P07 (controller.ato u_io.P07 ~ rtd_drdy;
 *              DECISIONS C23). The validator's drdy field is a u16 GPIO number, so
 *              the out-of-range sentinel 65535 means "no direct GPIO".
 */
#define PIN_SPI_CS_RTD1         10
#define PIN_RTD_DRDY            65535
