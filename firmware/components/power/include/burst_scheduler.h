#ifndef TEMPER_BURST_SCHEDULER_H
#define TEMPER_BURST_SCHEDULER_H
#include "../../hal/include/hal_bus_crossing.h"
#define BURST_DEFAULT_PERIOD_S 20.0
typedef struct {
    bool burst_enabled; /* Zero initialization keeps native-20 continuous-only. */
    double measured_burst_w, line_rms_v, power_factor, period_s;
} burst_config_t;
typedef struct {
    burst_config_t config;
    uint64_t last_crossing_us, last_sample_us;
    uint32_t half_cycles, on_half_cycles, index;
    bool configured, seen_crossing, seen_sample, on, fault;
} burst_scheduler_t;
double burst_min_period_s(double measured_w, double line_v, double pf);
bool burst_scheduler_init(burst_scheduler_t *, const burst_config_t *);
/* Single controller owner, call at the bus acquisition rate (20 ksample/s).
 * Normal transitions happen only on qualified crossings; an invalid/stale
 * sample latches off immediately. Fault shutdown never waits for a crossing.
 */
bool burst_scheduler_step(burst_scheduler_t *, uint64_t now_us,
                          const hal_bus_crossing_t *, double requested_w);
#endif
