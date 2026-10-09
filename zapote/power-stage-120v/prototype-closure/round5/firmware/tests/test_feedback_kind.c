#include "fullbridge_adapter.h"
#include <assert.h>
#include <stdio.h>
static bool apply(void *p,const bridge_cycle_t *c){(void)p;(void)c;return true;}
static bool request(void *p,bool v){(void)p;(void)v;return true;}
static void inhibit(void *p){(void)p;}
static bridge_config_t config(void){return (bridge_config_t){.timer_hz=80000000,.frequency_hz=50000,.input_deadtime_ns=125,
 .capture_age_us=1000,.max_power_w=1200,.inlet_target_a=13.5,.auxiliary_reserve_w=50,.commissioned=true};}
int main(void){
 bridge_backend_t ops={apply,request,inhibit,0};bridge_config_t c=config();fullbridge_adapter_t b;
 assert(!fullbridge_init(&b,&c,&ops));
 c.feedback_kind=BRIDGE_FEEDBACK_ONCHIP_REGISTER;assert(!fullbridge_init(&b,&c,&ops));
 c.scope_record_id=1;c.commissioned=false;assert(!fullbridge_init(&b,&c,&ops));c.commissioned=true;
 for(unsigned fault=0;fault<7;fault++){
  assert(fullbridge_init(&b,&c,&ops));assert(fullbridge_line_cycle(&b,1000,120,0,1200));
  bridge_feedback_t f={.kind=BRIDGE_FEEDBACK_ONCHIP_REGISTER,.sampled_us=1000,.serial=1,
    .rails_ok=true,.interlock_ok=true,.sup_run_ok=true,
    .onchip={.programmed_cycle=b.cycle,.timer_hz=80000000,.coherent=true,.timer_advancing=true,.outputs_connected=true}};
  if(fault==1)f.kind=BRIDGE_FEEDBACK_BENCH_CAPTURE;
  if(fault==2)f.onchip.coherent=false;
  if(fault==3)f.onchip.timer_advancing=false;
  if(fault==4)f.onchip.outputs_connected=false;
  if(fault==5)f.onchip.programmed_cycle.pulse[2].rise++;
  if(fault==6)f.rails_ok=false;
  assert(fullbridge_apply(&b,1000,&f,0)==(fault==0));
 }
 puts("unknown source, missing scope/commissioning, capture substitution, incoherent/stuck/disconnected/incorrect registers and missing physical rail guard rejected; explicit onchip feedback accepted without edge arrays");
}
