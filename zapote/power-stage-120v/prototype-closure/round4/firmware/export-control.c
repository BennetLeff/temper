/*
 * Conditional model stimulus: calls the REAL adapter control implementation. Whole-inlet feedback
 * held below target; no claim of closed-loop correlation.
 */
#include "fullbridge_adapter.h"
#include <assert.h>
#include <stdio.h>
static bool apply(void *p, const bridge_cycle_t *c)
{
    (void)p;
    (void)c;
    return true;
}
static bool request(void *p, bool on)
{
    (void)p;
    (void)on;
    return true;
}
static void inhibit(void *p)
{
    (void)p;
}
int main(void)
{
    puts("line_v,time_s,conductance_s,power_budget_w,assumed_feedback_a");
    for (unsigned volts = 100; volts <= 140; volts += 20) {
        fullbridge_adapter_t b;
        bridge_config_t c = {.timer_hz = 80000000,.frequency_hz = 50000,.input_deadtime_ns = 125,
        .capture_age_us = 1000,.max_power_w = 1500,.inlet_target_a = 13.5f,.auxiliary_reserve_w = 25,.commissioned = true};
        bridge_backend_t ops = {apply, request, inhibit, NULL};
        assert(fullbridge_init(&b, &c, &ops));
        assert(fullbridge_request(&b, 1500));
        for (unsigned k = 0; k <= 150; k++) {
            uint32_t us = 90000 + (uint32_t)((uint64_t)k * 1000000 / 60);
            assert(fullbridge_line_cycle(&b, us, (float)volts, 0, 1500));
            printf("%u,%.6f,%.9g,%.9g,0\n", volts, us / 1e6, b.conductance_s, b.conductance_s * volts * volts);
        }
    }
}
