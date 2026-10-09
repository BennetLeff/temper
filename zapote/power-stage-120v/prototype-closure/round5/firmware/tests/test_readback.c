#include "mcpwm_readback.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>
static mcpwm_dev_t m;
static void setup(unsigned shift){
 memset(&m,0,sizeof m);m.update_cfg.global_up_en=1;m.update_cfg.op0_up_en=1;m.update_cfg.op1_up_en=1;m.clk_cfg.clk_prescale=1;
 m.timer[0].timer_cfg0.timer_period=1599;m.timer[0].timer_cfg1.timer_start=2;m.timer[0].timer_cfg1.timer_mod=1;
 for(unsigned l=0;l<2;l++) {unsigned r=l?shift:0;
 m.operators[l].timestamp[0].gen=r;m.operators[l].timestamp[1].gen=(r+800)%1600;
 m.operators[l].gen_stmp_cfg.val=0x11;m.operators[l].gen_cfg0.gen_cfg_upmethod=1;
 m.operators[l].generator[0].val=(r?1:2)|(2<<4)|(1<<6);
 m.operators[l].dt_cfg.val=0x24000;m.operators[l].dt_red_cfg.dt_red=9;m.operators[l].dt_fed_cfg.dt_fed=9;
 }
}
int main(void){bridge_cycle_t c,p;uint32_t hz;
 for(unsigned n=0;n<=800;n++){setup(n);assert(r5_mcpwm_register_cycle(&m,&c,&hz));assert(bridge_plan_cycle(80000000,50000,125,n/800.f,&p));assert(!memcmp(&c,&p,sizeof c));}
 setup(100);m.operators[1].gen_stmp_cfg.val|=0x100;assert(!r5_mcpwm_register_cycle(&m,&c,&hz));
 setup(100);m.update_cfg.global_up_en=0;assert(!r5_mcpwm_register_cycle(&m,&c,&hz));
 setup(100);m.clk_cfg.clk_prescale=2;assert(!r5_mcpwm_register_cycle(&m,&c,&hz));
 setup(100);m.operators[1].dt_cfg.dt_fed_outinvert=0;assert(!r5_mcpwm_register_cycle(&m,&c,&hz));
 setup(100);m.operators[1].generator[0].gen_uteb=2;assert(!r5_mcpwm_register_cycle(&m,&c,&hz));
 setup(100);m.operator_timersel.operator1_timersel=1;assert(!r5_mcpwm_register_cycle(&m,&c,&hz));
 puts("801 actual SDK register decodes match waveform oracle; pending/clock/inversion/action/timer faults rejected");}
