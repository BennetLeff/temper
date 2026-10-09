#include "supervisor_outputs.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>
typedef struct { bool command,closed;uint32_t changed; } contact;
static void contact_step(contact *c,bool cmd,uint32_t us){
 if(c->command!=cmd){c->command=cmd;c->changed=us;}
 if(us-c->changed>=(cmd?72450u:24000u)) c->closed=cmd;
}
static unsigned scenario(unsigned fault){
 r5_supervisor_t s;energy_config_t cfg=energy_study_config();cfg.commissioned=true;r5_supervisor_init(&s,&cfg,0);
 contact a={0},b={0},k1={0},k2={0},kb={0};bool kt=false,ran=false,proof_seen=false;uint32_t edge=0,source=0;unsigned pulses=0,consumed=0;
 r5_supervisor_inputs_t i={0};i.energy=(energy_inputs_t){.stop_ok=true,.aux_ok=true,.sensors_valid=true,
 .hardware_ok=true,.hardware_latch_ok=true,.catch_charge_proven=true,.manual_post_ok=true,.manual_post_serial=42,
 .resistor_cool=true,.receiver_ok=true,.rails_ok=true,.interlock_ok=true,.controller_alive=true,.pwm_qualified=true,
 .heat_request=true,.valid_line_cycles=2,.line_rms_v=120};
 i.mirror_valid=true;i.feedback_static=true;
 for(uint32_t us=60000000;us<63000000;us+=1000){
  contact_step(&a,s.kpa,us);contact_step(&b,s.kpb,us);contact_step(&k1,s.out.k1,us);contact_step(&k2,s.out.k2,us);contact_step(&kb,s.out.kb,us);
  r5_supervisor_signals_t wires=r5_supervisor_signals(&s,true,true,i.energy.manual_post_ok);
  if(s.isolation.state>=PC_TEST_A_CLOSE&&s.isolation.state<=PC_RUN)assert(!wires.stop_done);
  if(wires.admit&&fault!=5){i.hardware_attempt=true;i.hardware_total_window=true;}
  if(fault==6)i.hardware_total_window=true;
  if(s.out.kt&&!kt){edge=us;pulses++;}kt=s.out.kt;
  if(s.out.k1&&!source)source=us;
  if(source&&us-source>=446000)i.hardware_total_window=false;
  if((!fault||fault>=8)&&source){
   i.energy.heat_request=!(us-source>=1000000&&us-source<1100000);
   i.energy.off_request=us-source>=1150000;
  }
  i.now_us=i.mirror_us=us;i.energy.now_ms=i.energy.sampled_ms=us/1000;
  i.energy.start=us>=61000000&&us<61001000;
  i.energy.k1_released=!k1.closed;i.energy.k2_released=!k2.closed;i.energy.kb_released=!kb.closed;
  i.kpa_nc=!a.closed;i.kpb_nc=!b.closed;
  i.energy.bus_v=k1.closed&&k2.closed?170:0;i.energy.catch_v=i.energy.bus_v;
  i.energy.precharge_complete=source&&us-source>=110000;
  i.energy.proof_current_valid=kt&&us-edge>=34000;
  i.loaded_bypass_proof=i.energy.proof_current_valid&&fault!=1;
  if(i.loaded_bypass_proof)i.energy.bypass_closed_electrically=true;
  i.measurement_serial=us/16667;
  i.proof_window_high=edge&&us-edge<131433;
  if(fault==2&&pulses)i.proof_window_high=true;
  if(fault==3&&s.isolation.state>=PC_ISOLATE)i.feedback_static=false;
  if(fault==4&&s.isolation.state==PC_REPROVE)i.measurement_serial=s.reproof_serial;
  if(fault==7)i.energy.heat_request=false;
  if(fault==8&&source&&us-source>=1001000)i.energy.pwm_qualified=false;
  if(fault==9&&source&&us-source>=1001000)i.kpa_nc=false;
  r5_supervisor_step(&s,&i);
  if(s.isolation.state==PC_READY||s.isolation.state==PC_RUN)proof_seen=true;
  if(s.consume_post&&i.energy.manual_post_ok){i.energy.manual_post_ok=false;consumed++;}
  if(s.out.sup_run_ok){assert(!fault||fault>=8);assert(pulses==2&&consumed==1);assert(!s.kpa&&!s.kpb&&i.kpa_nc&&i.kpb_nc);assert(s.run_session_qualified);if(!ran){assert(us-source<446000);ran=true;}}
  if(!fault&&source&&us-source>=1000000&&us-source<1100000)assert(s.energy.state==ENERGY_READY&&s.isolation.state==PC_RUN&&!s.out.sup_run_ok&&!s.stop_done);
  if(!fault&&source&&us-source>=1100000&&us-source<1150000)assert(s.out.sup_run_ok);
  if(!fault&&i.energy.off_request){assert(s.energy.state==ENERGY_DISCHARGE&&s.isolation.state==PC_OFF&&s.stop_done&&!s.run_session_qualified);return pulses;}
  if(s.energy.state==ENERGY_FAULT||s.isolation.state==PC_FAULT){
   if(!fault)fprintf(stderr,"unexpected fault energy=%d reason=%d pc=%d at%u sourceage%u pulses%u\n",s.energy.state,s.energy.fault,s.isolation.state,us,us-source,pulses);
   assert(fault);if(fault==7){assert(proof_seen&&!ran);assert(us-s.isolation.source_us>=446000);}assert(!s.run_session_qualified);assert(!s.out.k1&&!s.out.k2&&!s.out.kb&&!s.out.kt&&!s.kpa&&!s.kpb);return 0;
  }
 }
 assert(!"neither run nor fail");return 0;
}
static void fault_reset(void){
 r5_supervisor_t s;energy_config_t c=energy_study_config();c.commissioned=true;r5_supervisor_init(&s,&c,0);
 r5_supervisor_inputs_t i={.mirror_valid=true,.feedback_static=true,.kpa_nc=true,.kpb_nc=true};
 i.energy=(energy_inputs_t){.stop_ok=true,.aux_ok=true,.sensors_valid=true,.hardware_ok=true,
 .hardware_latch_ok=true,.k1_released=true,.k2_released=true,.kb_released=true,.resistor_cool=true,
 .receiver_ok=true,.line_rms_v=120,.valid_line_cycles=2};
 for(unsigned ms=0;ms<=121010;ms++){
  i.energy.now_ms=i.energy.sampled_ms=ms;i.now_us=i.mirror_us=ms*1000;
  if(ms>=60002)i.energy.hardware_latch_ok=false;
  i.energy.start=ms==60001; /* Missing POST faults both controllers. */
  r5_supervisor_step(&s,&i);
 }
 assert(s.energy.state==ENERGY_FAULT&&s.isolation.state==PC_FAULT);
 assert(s.energy.out.reset_ok&&s.isolation.reset_armed);
 r5_supervisor_signals_t pins=r5_supervisor_signals(&s,true,false,false);
 assert(pins.reset_ok&&!pins.stop_done&&!pins.k1&&!pins.kpa&&!pins.admit);
 /* Native asynchronous clear is released before RESET clocks the latch. */
 i.energy.reset=true;i.energy.now_ms++;i.energy.sampled_ms++;i.now_us+=1000;i.mirror_us+=1000;
 r5_supervisor_step(&s,&i);assert(s.energy.state==ENERGY_OFF&&s.isolation.state==PC_OFF);
 i.energy.hardware_latch_ok=true; /* Physical RESET rearms hardware latch. */
 i.energy.reset=false;i.energy.now_ms++;i.energy.sampled_ms++;i.now_us+=1000;i.mirror_us+=1000;
 r5_supervisor_step(&s,&i);
 i.energy.start=true;i.energy.manual_post_ok=true;i.energy.manual_post_serial=99;
 i.energy.now_ms++;i.energy.sampled_ms++;i.now_us+=1000;i.mirror_us+=1000;
 r5_supervisor_step(&s,&i);assert(s.isolation.state==PC_TEST_A_CLOSE&&s.consume_post&&s.kpa&&!s.out.k1&&!s.run_session_qualified);
}
static void catch_valley(void){
 r5_supervisor_t s;energy_config_t c=energy_study_config();c.commissioned=true;r5_supervisor_init(&s,&c,0);
 s.energy.state=ENERGY_RUN;s.isolation.state=PC_RUN;s.out.sup_run_ok=true;s.admitted=true;
 r5_supervisor_inputs_t i={.now_us=1000,.mirror_us=1000,.mirror_valid=true,.feedback_static=true,
 .kpa_nc=true,.kpb_nc=true,.hardware_attempt=true,.hardware_total_window=true};
 i.energy=(energy_inputs_t){.now_ms=1,.sampled_ms=1,.stop_ok=true,.aux_ok=true,.sensors_valid=true,.hardware_ok=true,
 .hardware_latch_ok=true,.resistor_cool=true,.receiver_ok=true,.line_rms_v=120,.catch_v=170,.bus_v=170,
 .catch_charge_proven=true,.bypass_closed_electrically=true,.rails_ok=true,.interlock_ok=true,.controller_alive=true,
 .pwm_qualified=true,.heat_request=true};
 r5_supervisor_step(&s,&i);assert(s.out.sup_run_ok);
 i.energy.now_ms=i.energy.sampled_ms=2;i.now_us=i.mirror_us=2000;
 i.energy.catch_charge_proven=false;i.energy.bus_v=40;
 r5_supervisor_step(&s,&i);assert(s.out.sup_run_ok&&s.energy.state==ENERGY_RUN);
 i.energy.off_request=true;i.energy.now_ms=i.energy.sampled_ms=3;i.now_us=i.mirror_us=3000;
 r5_supervisor_step(&s,&i);assert(!s.catch_history&&s.stop_done&&!s.out.sup_run_ok);
 r5_supervisor_signals_t pins=r5_supervisor_signals(&s,true,true,false);assert(pins.stop_done&&!pins.run&&!pins.k1);
}
int main(void){catch_valley();fault_reset();

assert(scenario(0)==2);for(unsigned f=1;f<=9;f++)assert(scenario(f)==0);puts("shared wrapper: delayed consumed POST, two loaded proof pulses, physical131433us+2ms rearm, RUN<446ms; zero-demand100ms after expiredTOTAL resumes RUN; session clears onOFF/fault/newSTART; no proof/stuck window/static loss/cached proof fail closed");}
