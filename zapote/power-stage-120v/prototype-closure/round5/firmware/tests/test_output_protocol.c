#include "supervisor_outputs.h"
#include <assert.h>
#include <stdio.h>
typedef struct {bool cmd,closed;uint32_t changed;} contact;
static void move(contact *c,bool cmd,uint32_t us){if(cmd!=c->cmd){c->cmd=cmd;c->changed=us;}if(us-c->changed>=(cmd?72450u:24000u))c->closed=cmd;}
int main(void){
 r5_supervisor_t s;energy_config_t cfg=energy_study_config();cfg.commissioned=true;r5_supervisor_init(&s,&cfg,0);
 r5_supervisor_inputs_t i={.mirror_valid=true,.feedback_static=true};
 i.energy=(energy_inputs_t){.stop_ok=true,.aux_ok=true,.sensors_valid=true,.hardware_ok=true,
 .k1_released=true,.k2_released=true,.kb_released=true,.manual_post_ok=true,.manual_post_serial=12,
 .resistor_cool=true,.receiver_ok=true,.line_rms_v=120,.valid_line_cycles=2};
 r5_supervisor_signals_t wire={0};contact a={0},b={0};
 bool latch=false,token=false,attempt=false,old_reset=false,old_start=false,old_admit=false;
 pc_state previous=PC_FAULT;unsigned reset_edges=0,start_edges=0,admit_edges=0;
 puts("us,pc,reset_ok,stop_done,start_released,admit,k1,kpa,kpb,latch,token,attempt");
 for(uint32_t us=60000000;us<62000000;us+=1000){
  bool reset=us==61001000,start=us==61003000;
  /* Native active-low asynchronous clear dominates edge clocks. These ideal
     gate truth tables test digital protocol, not propagation/hold times. */
  if(wire.stop_done){latch=false;token=false;attempt=false;}
  if(reset&&!old_reset&&wire.reset_ok&&!wire.stop_done){latch=true;reset_edges++;}
  if(start&&!old_start&&wire.start_released&&wire.post_ok&&latch&&!wire.admit){token=true;start_edges++;}
  if(wire.admit&&!old_admit){attempt=attempt||(token&&latch);if(attempt)token=false;admit_edges++;}
  old_reset=reset;old_start=start;old_admit=wire.admit;
  move(&a,wire.kpa,us);move(&b,wire.kpb,us);
  i.now_us=i.mirror_us=us;i.energy.now_ms=i.energy.sampled_ms=us/1000;
  i.energy.reset=reset;i.energy.start=start;i.energy.hardware_latch_ok=latch;
  i.kpa_nc=!a.closed;i.kpb_nc=!b.closed;i.hardware_attempt=attempt;i.hardware_total_window=attempt;
  r5_supervisor_step(&s,&i);if(s.consume_post)i.energy.manual_post_ok=false;
  wire=r5_supervisor_signals(&s,true,false,i.energy.manual_post_ok);
  if(s.isolation.state>=PC_TEST_A_CLOSE&&s.isolation.state<=PC_RUN)assert(!wire.reset_ok);
  assert(s.energy.state!=ENERGY_FAULT&&s.isolation.state!=PC_FAULT);
  if(s.isolation.state!=previous||reset||start||wire.admit){
   printf("%u,%u,%u,%u,%u,%u,%u,%u,%u,%u,%u,%u\n",us,s.isolation.state,wire.reset_ok,wire.stop_done,wire.start_released,wire.admit,wire.k1,wire.kpa,wire.kpb,latch,token,attempt);
   previous=s.isolation.state;
  }
  if(wire.k1){
   assert(attempt&&latch&&!token&&!wire.stop_done&&reset_edges==1&&start_edges==1&&admit_edges==1);
   i.energy.off_request=true;i.now_us+=1000;i.mirror_us+=1000;i.energy.now_ms++;i.energy.sampled_ms++;
   r5_supervisor_step(&s,&i);wire=r5_supervisor_signals(&s,true,false,false);
   assert(wire.stop_done&&!wire.k1&&!wire.k2&&!wire.kb&&!wire.kpa&&!wire.kpb&&!wire.admit);
   puts("PASS: exact target wire projection preserves cold RESET/START token through selftest; ADMIT ACK precedes K1; end clears hardware attempt");return 0;
  }
 }
 assert(!"source not admitted");
}
