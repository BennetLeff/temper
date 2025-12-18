/**
 * @file ui.h
 * @brief User Interface module for induction cooker
 */

#ifndef UI_H
#define UI_H

#include "hal_types.h"
#include <stdint.h>
#include <stdbool.h>

#ifdef __cplusplus
extern "C" {
#endif

/**
 * @brief UI States
 */
typedef enum {
    UI_STATE_NORMAL,    /**< Adjusting temperature / Start-Stop */
    UI_STATE_SETTINGS,  /**< Cycling through settings menu */
    UI_STATE_EDIT       /**< Editing a specific setting */
} ui_state_t;

/**
 * @brief Settings menu items
 */
typedef enum {
    SETTING_TEMP,
    SETTING_INTENSITY,
    SETTING_TIMER,
    SETTING_PROFILE,
    SETTING_COUNT
} setting_item_t;

/**
 * @brief Initialize UI module
 */
void ui_init(void);

/**
 * @brief Update UI module
 * 
 * Call periodically (e.g., 50Hz)
 */
void ui_update(void);

/**
 * @brief Get current UI state
 */
ui_state_t ui_get_state(void);

/**
 * @brief Get currently selected setting item
 */
setting_item_t ui_get_selected_setting(void);

#ifdef __cplusplus
}
#endif

#endif /* UI_H */
