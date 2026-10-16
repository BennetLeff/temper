/**
 * @file board_power.h
 * @brief zapote/controller power-stage bring-up on the ESP-IDF target
 */

#ifndef BOARD_POWER_H
#define BOARD_POWER_H

#ifdef __cplusplus
extern "C" {
#endif

/**
 * @brief Gate commands low, RUN_EN low, PLL and pan-detect capture on CT_ZC.
 *
 * Call after hal_init(). Every failure leaves the power stage off: the gate
 * commands stay low, RUN_EN stays low, the PLL reports no lock and
 * detect_pan_presence() reports no pan. See board_power.c.
 */
void board_power_init(void);

#ifdef __cplusplus
}
#endif

#endif /* BOARD_POWER_H */
