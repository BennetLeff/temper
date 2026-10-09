#ifndef TEMPER_PRECHARGE_ISOLATION_H
#define TEMPER_PRECHARGE_ISOLATION_H
#include <stdbool.h>
#include <stdint.h>

/* Additive executable ECO contract; not linked into the production target. */
typedef enum {
    PC_OFF, PC_TEST_A_CLOSE, PC_TEST_A_OPEN, PC_TEST_B_CLOSE, PC_TEST_B_OPEN,
    PC_CONNECT, PC_PRECHARGE, PC_BYPASS, PC_ISOLATE, PC_REARM, PC_REPROVE, PC_READY, PC_RUN, PC_FAULT
} pc_state;
typedef struct {
    uint32_t now_us, mirror_us, post_token;
    bool start, reset, healthy, source_released, bypass_released, discharged;
    bool post_valid, cold, a_nc, b_nc, mirror_valid;
    bool feedback_static, proof_timer_ready;
    bool precharge_complete, bypass_proven, post_isolation_proven, run_qualified;
} pc_inputs;
typedef struct { bool a, b, main, bypass, run; } pc_outputs;
typedef struct {
    pc_state state;
    uint32_t entered_us, stable_us, previous_us, source_us, used_post;
    bool stable, initialized, previous_start, previous_reset, reset_armed, proof_low_seen;
    pc_outputs out;
} pc_controller;
void pc_step(pc_controller *s, const pc_inputs *i);
/* Slots: all off, K1 only, K2 only, KB only, KPA only, KPB only.
 * Each mask contains the five sampled receiver levels after settling. */
bool pc_decode_mirrors(const uint8_t slots[6], uint8_t *closed_mask);
#endif
