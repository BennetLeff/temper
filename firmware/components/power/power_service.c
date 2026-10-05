#include "power_service.h"
#include <string.h>
static fullbridge_adapter_t bridge;
static power_binding_t owner;
static bool bound;
void power_service_bootstrap(void)
{
    fullbridge_stop(&bridge);
    memset(&owner, 0, sizeof(owner));
    memset(&bridge, 0, sizeof(bridge));
    bound = false;
}
bool power_service_bind(const power_binding_t *b)
{
    /* No live rebinding or clearing a fault by calling bind again. */
    if (bound || bridge.tripped || !b || !b->sample || !b->phase_from_conductance)
        return false;
    owner = *b;
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
    float v = 0, current = 0, pan = 0, phase = 0;
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
    if (!owner.phase_from_conductance(owner.context, bridge.conductance_s, &phase)) {
        pwm_disable_all();
        bridge.tripped = true;
        return;
    }
    (void)fullbridge_apply(&bridge, now, &f, phase);
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
    (void)fullbridge_request(&bridge, owner.config.max_power_w * percent / 100.0f);
}
void power_enable(void)
{                               /* No permission is granted by application state entry. */
}
void pwm_set_duty_cycle(uint8_t percent){
    power_set_level(percent);
}
void pwm_disable_all(void){
    fullbridge_stop(&bridge);
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
