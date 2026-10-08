#include "power_service.h"
#include <string.h>
static fullbridge_adapter_t bridge;
static power_binding_t owner;
static bool bound;
static burst_scheduler_t burst;
static float burst_demand_w;
void power_service_bootstrap(void)
{
    fullbridge_stop(&bridge);
    memset(&owner, 0, sizeof(owner));
    memset(&bridge, 0, sizeof(bridge));
    bound = false;
    memset(&burst, 0, sizeof burst);
    burst_demand_w = 0;
}
bool power_service_bind(const power_binding_t *b)
{
    /* No live rebinding or clearing a fault by calling bind again. */
    if (bound || bridge.tripped || !b || !b->sample || !b->backend.inhibit ||
        (b->burst.burst_enabled && (!b->sample_bus || !b->set_burst_gate)))
        return false;
    if (!burst_scheduler_init(&burst, &b->burst)) return false;
    owner = *b;
    if (owner.burst.burst_enabled && !owner.set_burst_gate(owner.context, false)) {
        owner.backend.inhibit(owner.backend.context);
        return false;
    }
    bound = fullbridge_init(&bridge, &owner.config, &owner.backend);
    return bound;
}
void power_service_tick(void)
{
    if (!bound || bridge.tripped)
        return;
    bridge_feedback_t f = {0};
    uint32_t now = 0;
    bool line = false;
    float v = 0, current = 0, pan = 0;
    if (!owner.sample(owner.context, &now, &f, &line, &v, &current, &pan)) {
        pwm_disable_all();
        bridge.tripped = true;
        return;
    }
    if (line && !fullbridge_line_cycle(&bridge, now, v, current, pan))
        return;
    /* Remain inhibited until at least one complete line estimate is available. */
    if (!bridge.have_line)
        return;
    uint64_t bus_now = now;
    hal_bus_crossing_t bus = {0};
    bool was_on = burst.on;
    /* The supervisor first grants independent permission while all PWM pads
     * remain blocked. Start counting whole half-cycles only after that grant. */
    if (owner.burst.burst_enabled && !bridge.armed) {
        if (!burst_scheduler_init(&burst, &owner.burst)) {
            pwm_disable_all(); bridge.tripped = true; return;
        }
    }
    if ((owner.burst.burst_enabled && !owner.sample_bus(owner.context, &bus_now, &bus)) ||
        !burst_scheduler_step(&burst, bus_now, &bus,
                              owner.burst.burst_enabled ? burst_demand_w : bridge.requested_w)) {
        pwm_disable_all();
        bridge.tripped = true;
        return;
    }
    if (owner.burst.burst_enabled && !bridge.armed) burst.on = false;
    if (!fullbridge_apply(&bridge, now, &f, 1.0f)) return;
    if (owner.burst.burst_enabled && was_on != burst.on &&
        !owner.set_burst_gate(owner.context, burst.on)) {
        pwm_disable_all(); bridge.tripped = true;
    }
}
void power_set_level(uint8_t percent)
{
    if (!bound)
        return;
    if (percent > 100) {
        pwm_disable_all();
        bridge.tripped = true;
        return;
    }
    if (owner.burst.burst_enabled) {
        burst_demand_w = owner.config.max_power_w * percent / 100.0f;
        /* Internal continuous waveform and PERMIT remain qualified at the
         * measured floor; the separate gate implements crossing-only idle. */
        (void)fullbridge_request(&bridge, owner.burst.measured_burst_w);
    } else (void)fullbridge_request(&bridge, owner.config.max_power_w * percent / 100.0f);
}
void power_enable(void)
{                               /* No permission is granted by application state entry. */
}
void pwm_set_duty_cycle(uint8_t percent){
    power_set_level(percent);
}
void pwm_disable_all(void){
    fullbridge_stop(&bridge);
    if (bound && owner.burst.burst_enabled && !owner.set_burst_gate(owner.context, false))
        bridge.tripped = true;
    burst.on = false;
}
bool test_pwm_generation(void)
{
    /* Initialization/readback alone is not measured PWM qualification. */
    return bound && !bridge.tripped && bridge.have_capture;
}
bool power_service_frequency(uint32_t hz)
{
    /* First prototype uses one reviewed fixed frequency; no raw PLL timer edits. */
    return bound && !bridge.tripped && hz == owner.config.frequency_hz;
}
bool power_service_pan_pulse(uint32_t duration_us)
{
    (void)duration_us;
    /*
     * First-prototype burst mode is disallowed. A bounded continuous probe and calibrated
     * detection map must replace the legacy open-loop 20us ping.
     */
    return false;
}
