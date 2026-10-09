#include "power_target.h"
#include "mcpwm_target.h"
#include "pins.h"
#include "driver/gpio.h"
#include "esp_timer.h"
#include <math.h>
static bool sample(void *ctx,uint32_t *now,bridge_feedback_t *f,bool *line,float *v,float *a,float *pan)
{
    r5_power_context_t *s=ctx;
    if(!r5_pwm_readback(f)) return false;
    *now=(uint32_t)esp_timer_get_time(); /* Readback timestamps must not be in this sample's future. */
    if(s->line.fault||!s->line.seen||
       (uint32_t)(*now-s->line.received_us)>25000) return false;
    f->rails_ok=s->rails_qualified;f->interlock_ok=s->interlock_qualified;
    f->bus_fault=s->bus_fault;f->sup_run_ok=gpio_get_level(R5_SUP_RUN_OK)!=0;
    *line=s->line.serial!=s->used_line;s->used_line=s->line.serial;
    *v=s->line.volts;*a=s->line.amps;*pan=s->pan_budget_w;return true;
}
static bool phase(void *ctx,float g,float *out)
{
    r5_power_context_t *s=ctx;
    if(!s->map||s->map_size<2||!isfinite(g)||g<0) return false;
    for(unsigned i=0;i<s->map_size;++i) {
        const r5_phase_point_t p=s->map[i];
        if(!isfinite(p.conductance_s)||!isfinite(p.phase_fraction)||p.conductance_s<0||
           p.phase_fraction<0||p.phase_fraction>1||(i&&
           (p.conductance_s<=s->map[i-1].conductance_s||p.phase_fraction<s->map[i-1].phase_fraction))) return false;
    }
    if(s->map[0].conductance_s!=0||s->map[0].phase_fraction!=0||g>s->map[s->map_size-1].conductance_s) return false;
    for(unsigned i=1;i<s->map_size;++i) if(g<=s->map[i].conductance_s) {
        r5_phase_point_t a=s->map[i-1],b=s->map[i];
        *out=a.phase_fraction+(g-a.conductance_s)*(b.phase_fraction-a.phase_fraction)/(b.conductance_s-a.conductance_s);return true;
    }
    return false;
}
bool r5_power_bind(r5_power_context_t *ctx,const bridge_backend_t *backend)
{
    if(!ctx||!backend) return false;
    power_binding_t binding={.config={.timer_hz=80000000,.frequency_hz=50000,.input_deadtime_ns=125,.capture_age_us=1000,.max_power_w=1500,.inlet_target_a=13.5,.auxiliary_reserve_w=50,.commissioned=ctx->commissioned,.feedback_kind=BRIDGE_FEEDBACK_ONCHIP_REGISTER,.scope_record_id=ctx->scope_record_id},
      .backend=*backend,.sample=sample,.phase_from_conductance=phase,.context=ctx};
    return power_service_bind(&binding);
}
