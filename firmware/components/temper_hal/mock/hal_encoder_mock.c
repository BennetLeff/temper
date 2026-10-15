/**
 * @file hal_encoder_mock.c
 * @brief Mock implementation of the encoder HAL
 */

#include "hal_encoder.h"
#include <string.h>

static int32_t s_count = 0;
static bool s_button_pressed = false;
static bool s_initialized = false;

static hal_status_t mock_encoder_init(const hal_encoder_config_t *config) {
    s_initialized = true;
    s_count = 0;
    s_button_pressed = false;
    return HAL_OK;
}

static int32_t mock_encoder_get_count(void) {
    return s_count;
}

static void mock_encoder_reset_count(void) {
    s_count = 0;
}

static bool mock_encoder_get_button_state(void) {
    return s_button_pressed;
}

static hal_status_t mock_encoder_deinit(void) {
    s_initialized = false;
    return HAL_OK;
}

const hal_encoder_ops_t hal_encoder_mock_ops = {
    .init = mock_encoder_init,
    .get_count = mock_encoder_get_count,
    .reset_count = mock_encoder_reset_count,
    .get_button_state = mock_encoder_get_button_state,
    .deinit = mock_encoder_deinit
};

// Global pointer
const hal_encoder_ops_t *hal_encoder = &hal_encoder_mock_ops;

void hal_encoder_set_ops(const hal_encoder_ops_t *ops) {
    hal_encoder = ops;
}

// Test helpers
void hal_encoder_mock_set_count(int32_t count) {
    s_count = count;
}

void hal_encoder_mock_set_button(bool pressed) {
    s_button_pressed = pressed;
}
