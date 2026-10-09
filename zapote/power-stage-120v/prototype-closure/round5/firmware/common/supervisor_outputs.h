#ifndef R5_SUPERVISOR_OUTPUTS_H
#define R5_SUPERVISOR_OUTPUTS_H
#include "supervisor_binding.h"
/* Exact target wire projection, also callable by native-gate/model fixtures. */
typedef struct {
 bool k1,k2,kb,kt,kpa,kpb,run,admit;
 bool reset_ok,stop_done,post_ok,start_released,precharge_done,bypass_proven;
 bool healthy,heartbeat_ok;
} r5_supervisor_signals_t;
r5_supervisor_signals_t r5_supervisor_signals(const r5_supervisor_t *,bool acquisition_healthy,
                                            bool heartbeat_ok,bool post_fresh);
#endif
