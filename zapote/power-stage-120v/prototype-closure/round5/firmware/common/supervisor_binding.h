#ifndef R5_SUPERVISOR_BINDING_H
#define R5_SUPERVISOR_BINDING_H
#include "energy_supervisor.h"
#include "isolation.h"
/* Shared STM32/model orchestrator. Energy enum/wire protocol remain unchanged.
 * Physical booleans are qualified inputs, never inferred from commanded coils. */
typedef struct {
    energy_inputs_t energy;
    uint32_t now_us,mirror_us,measurement_serial;
    bool mirror_valid,feedback_static,kpa_nc,kpb_nc;
    bool loaded_bypass_proof,proof_window_high;
    bool hardware_attempt,hardware_total_window;
} r5_supervisor_inputs_t;
typedef struct {
    energy_supervisor_t energy;
    pc_controller isolation;
    energy_outputs_t out;
    bool kpa,kpb,admit,consume_post,attempt_post_valid;
    bool admission_pending,admitted,run_session_qualified,stop_done,catch_history,reset_contacts_released;
    uint32_t attempt_post_serial,first_kt_us,window_low_us,reproof_serial,reproof_good_us;
    bool first_kt_seen,window_low_seen,reproof_good,reproof_failed;
} r5_supervisor_t;
static inline bool r5_supervisor_reset_permitted(const r5_supervisor_t *s)
{
    return s->out.reset_ok&&s->reset_contacts_released&&!s->kpa&&!s->kpb&&
        (s->isolation.state==PC_OFF||(s->isolation.state==PC_FAULT&&s->isolation.reset_armed));
}
void r5_supervisor_init(r5_supervisor_t *,const energy_config_t *,uint32_t now_ms);
void r5_supervisor_step(r5_supervisor_t *,const r5_supervisor_inputs_t *);
#endif
