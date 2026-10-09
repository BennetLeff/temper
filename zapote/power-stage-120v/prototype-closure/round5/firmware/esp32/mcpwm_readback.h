#ifndef R5_MCPWM_READBACK_H
#define R5_MCPWM_READBACK_H
#include "soc/mcpwm_struct.h"
#include "fullbridge_adapter.h"
/* S3's MCPWM source is fixed PLL160M in IDF5.2.3. This checks digital divider
 * programming, not oscillator accuracy or external gate-driver propagation. */
static inline bool r5_mcpwm_register_cycle(const volatile mcpwm_dev_t *m,bridge_cycle_t *c,uint32_t *hz)
{
    if(!m||!c||!hz||!m->update_cfg.global_up_en||!m->update_cfg.op0_up_en||!m->update_cfg.op1_up_en||
       m->operator_timersel.operator0_timersel||m->operator_timersel.operator1_timersel||
       m->timer[0].timer_cfg1.timer_start!=2||m->timer[0].timer_cfg1.timer_mod!=1||
       m->timer[0].timer_sync.timer_synci_en||m->timer[0].timer_cfg0.timer_period_upmethod) return false;
    *hz=160000000u/((m->clk_cfg.clk_prescale+1)*(m->timer[0].timer_cfg0.timer_prescale+1));
    c->period=m->timer[0].timer_cfg0.timer_period+1;
    c->dead_ticks=m->operators[0].dt_red_cfg.dt_red+1;
    if(*hz!=80000000u||c->period!=1600||c->dead_ticks!=10) return false;
    for(unsigned leg=0;leg<2;leg++) {
        const volatile mcpwm_operator_reg_t *o=&m->operators[leg];
        uint32_t rise=o->timestamp[0].gen,fall=o->timestamp[1].gen;
        if(o->gen_stmp_cfg.val!=0x11u||o->gen_cfg0.val!=1||o->generator[1].val||
           o->gen_force.val||o->carrier_cfg.carrier_en||o->fh_status.val||
           o->generator[0].val!=((rise?1u:2u)|(2u<<4)|(1u<<6))||
           o->dt_cfg.val!=0x24000u||o->dt_red_cfg.dt_red+1!=c->dead_ticks||
           o->dt_fed_cfg.dt_fed+1!=c->dead_ticks||rise>c->period/2||
           (leg==0&&rise)||fall!=(rise+c->period/2)%c->period) return false;
        c->pulse[2*leg]=(bridge_pulse_t){(rise+c->dead_ticks)%c->period,c->period/2-c->dead_ticks};
        c->pulse[2*leg+1]=(bridge_pulse_t){(fall+c->dead_ticks)%c->period,c->period/2-c->dead_ticks};
    }
    return true;
}
#endif
