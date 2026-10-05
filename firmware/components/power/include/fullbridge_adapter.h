#ifndef TEMPER_FULLBRIDGE_ADAPTER_H
#define TEMPER_FULLBRIDGE_ADAPTER_H
#include <stdbool.h>
#include <stdint.h>
/* Fixed-frequency phase-shifted bridge, one common timer. Indices A_H,A_L,B_H,B_L.
 * Each pulse wraps modulo period. Deadtime is MCU input non-overlap, NOT the
 * UCC21550's separate 396.6..488 ns output deadtime allocation. */
typedef struct { uint32_t rise, width; } bridge_pulse_t;
typedef struct { uint32_t period, dead_ticks; bridge_pulse_t pulse[4]; } bridge_cycle_t;
typedef struct {
    uint32_t timer_hz, frequency_hz, input_deadtime_ns, capture_age_us;
    float max_power_w, inlet_target_a, auxiliary_reserve_w;
    /* Disabled until commissioning map and exact controller wiring reviewed. */
    bool commissioned;
} bridge_config_t;
typedef struct {
    uint32_t sampled_us, serial;
    uint32_t period[4], high_ticks[4], rise_ticks[4], nonoverlap_ticks[4];
    bool valid[4], rails_ok, sup_run_ok, interlock_ok, bus_fault;
} bridge_feedback_t;
typedef struct {
    bool (*apply_cycle)(void *context, const bridge_cycle_t *cycle);
    bool (*set_request)(void *context, bool request);
    void (*inhibit)(void *context); /* Always deassert request BEFORE forcing PWM low. */
    void *context;
} bridge_backend_t;
typedef struct {
    bridge_config_t cfg;
    bridge_backend_t backend;
    bridge_cycle_t cycle;
    float conductance_s, requested_w;
    uint32_t last_line_us, last_capture_serial;
    bool initialized, armed, tripped, have_line, have_capture;
} fullbridge_adapter_t;
bool bridge_plan_cycle(uint32_t timer_hz, uint32_t frequency_hz,
                       uint32_t deadtime_ns, float phase_fraction, bridge_cycle_t *);
bool bridge_output_at(const bridge_cycle_t *, unsigned output, uint32_t tick);
bool fullbridge_init(fullbridge_adapter_t *, const bridge_config_t *, const bridge_backend_t *);
void fullbridge_stop(fullbridge_adapter_t *);
/* Request changes do not touch GPIO. Caller is sole task owner; no ISR calls. */
bool fullbridge_request(fullbridge_adapter_t *, float watts);
/* Call on each COMPLETE line-cycle estimate. Counter/timing prevents stale RMS
 * data re-use. Return false inhibits on invalid/repeated/out-of-range data. */
bool fullbridge_line_cycle(fullbridge_adapter_t *, uint32_t now_us,
                           float line_rms_v, float inlet_rms_a, float pan_budget_w);
/* Calibrated phase is supplied by characterized pan/current controller. It is
 * not guessed from watts. Feedback covers ALL four outputs and both deadtimes. */
bool fullbridge_apply(fullbridge_adapter_t *, uint32_t now_us,
                      const bridge_feedback_t *, float characterized_phase_fraction);
#endif
