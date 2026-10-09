#ifndef R5_POWER_TARGET_H
#define R5_POWER_TARGET_H
#include "power_service.h"
#include "line_telemetry.h"
typedef struct { float conductance_s,phase_fraction; } r5_phase_point_t;
typedef struct {
    r5_line_receiver_t line;
    const r5_phase_point_t *map;unsigned map_size;
    float pan_budget_w;
    uint32_t used_line,scope_record_id;
    bool commissioned,boot_inhibit_verified;
    bool rails_qualified,interlock_qualified,bus_fault;
} r5_power_context_t;
/* Populate phase map ONLY from characterized hardware, and physical qualifier
 * fields ONLY from reviewed sensor paths. Empty context fails closed. */
bool r5_power_bind(r5_power_context_t *,const bridge_backend_t *);
#endif
