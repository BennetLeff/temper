#ifndef TEMPER_R5_PINS_H
#define TEMPER_R5_PINS_H
/* ECO R5-CTRL-01: NEW dedicated ESP32-S3-WROOM-1-N8 carrier; NOT the legacy
 * controller and NOT an in-place pin assignment. No PSRAM, no fan/RTD/UI loads.
 * Native USB 19/20, console 43/44, boot straps 0/3/45/46 left reserved. */
#define R5_PWM_AH 4
#define R5_PWM_AL 5
#define R5_PWM_BH 15
#define R5_PWM_BL 16
#define R5_REQUEST 17
#define R5_HEARTBEAT 18
#define R5_FAULT_HIGH 21
#define R5_RAIL_OK 35
#define R5_INTERLOCK_OK 36
#define R5_SUP_RUN_OK 37
#define R5_UART_TX 8
#define R5_UART_RX 9
#endif
