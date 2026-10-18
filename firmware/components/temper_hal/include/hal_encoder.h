/**
 * @file hal_encoder.h
 * @brief Rotary Encoder Hardware Abstraction Layer
 */

#ifndef HAL_ENCODER_H
#define HAL_ENCODER_H

#include "hal_types.h"

#ifdef __cplusplus
extern "C" {
#endif

/**
 * @brief Encoder configuration
 */
typedef struct {
    hal_pin_t pin_a;
    hal_pin_t pin_b;
    hal_pin_t pin_btn;
} hal_encoder_config_t;

/**
 * @brief Encoder operations interface
 */
typedef struct {
    hal_status_t (*init)(const hal_encoder_config_t *config);
    int32_t (*get_count)(void);
    void (*reset_count)(void);
    bool (*get_button_state)(void);
    hal_status_t (*deinit)(void);
} hal_encoder_ops_t;

extern const hal_encoder_ops_t *hal_encoder;

void hal_encoder_set_ops(const hal_encoder_ops_t *ops);

#ifdef __cplusplus
}
#endif

#endif /* HAL_ENCODER_H */
