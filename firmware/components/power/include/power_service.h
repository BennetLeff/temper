#ifndef TEMPER_POWER_SERVICE_H
#define TEMPER_POWER_SERVICE_H
#include "fullbridge_adapter.h"
/* A board owner must implement and review this binding, including actual four
 * GPIOs, synchronous atomic cycle commit, independent captures and JCTRL
 * isolated transport. There is deliberately no legacy-pin fallback. */
typedef struct {
    bridge_config_t config;
    bridge_backend_t backend;
    bool (*sample)(void *, uint32_t *now_us, bridge_feedback_t *, bool *new_line_cycle,
                   float *line_v, float *inlet_a, float *pan_budget_w);
    bool (*phase_from_conductance)(void *, float conductance_s, float *phase);
    void *context;
} power_binding_t;
void power_service_bootstrap(void);
bool power_service_bind(const power_binding_t *binding);
void power_service_tick(void);
bool power_service_frequency(uint32_t hz);
bool power_service_pan_pulse(uint32_t duration_us);
void power_set_level(uint8_t percent);
void power_enable(void);
void pwm_set_duty_cycle(uint8_t percent);
void pwm_disable_all(void);
bool test_pwm_generation(void);
#endif
