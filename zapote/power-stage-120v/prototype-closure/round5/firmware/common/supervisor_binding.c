#include "supervisor_binding.h"
#include <string.h>
static void cancel_pc(r5_supervisor_t *s)
{
    s->isolation.state=PC_OFF;s->isolation.out=(pc_outputs){0};
    s->run_session_qualified=false;s->catch_history=false;s->attempt_post_valid=false;s->admit=false;s->admission_pending=false;s->admitted=false;
}
void r5_supervisor_init(r5_supervisor_t *s,const energy_config_t *cfg,uint32_t ms)
{
    memset(s,0,sizeof *s);energy_supervisor_init(&s->energy,cfg,ms);
}
void r5_supervisor_step(r5_supervisor_t *s,const r5_supervisor_inputs_t *in)
{
    energy_inputs_t e=in->energy;
    pc_state before=s->isolation.state;
    bool source=before>=PC_PRECHARGE&&before<=PC_RUN;
    s->consume_post=false;
    s->reset_contacts_released=in->mirror_valid&&in->feedback_static&&
        in->now_us-in->mirror_us<=2000&&in->kpa_nc&&in->kpb_nc;
    /* The real POST is consumed at the beginning of mechanical testing. Its
       immutable token authorizes exactly this delayed energy START, not retry. */
    e.start=false;
    /* Charge proof is attempt history, not equality with the rectified bus at
       every valley. Live sensor validity and absolute limits remain mandatory. */
    if(source&&e.catch_charge_proven) s->catch_history=true;
    e.catch_charge_proven=s->catch_history&&e.catch_v>=100;
    e.heat_request=e.heat_request&&(before==PC_READY||before==PC_RUN);
    if(s->attempt_post_valid) { e.manual_post_ok=true;e.manual_post_serial=s->attempt_post_serial; }
    /* Only the qualified merged RUN command completes software startup.
       Native hardware independently latches actual SUP_RUN_OK_LOCAL. */
    if(s->run_session_qualified&&(!s->reset_contacts_released||!e.pwm_qualified)) {
        s->run_session_qualified=false;e.hardware_ok=false;
    }
    if(source&&!s->run_session_qualified&&in->now_us-s->isolation.source_us>=s->energy.cfg.attempt_ms*1000u)
        e.hardware_ok=false;
    if(source&&s->admitted&&(!in->hardware_attempt||(!s->run_session_qualified&&!in->hardware_total_window))) e.hardware_ok=false;
    if(before==PC_FAULT&&s->energy.state!=ENERGY_FAULT) e.hardware_ok=false;
    energy_supervisor_step(&s->energy,&e);
    /* A latched operational fault must not erase physical RESET eligibility.
       The energy core independently proves cold/discharged/retry dwell and a
       released RESET before exposing reset_ok. Both controllers see that same
       safe-low interval, then the same fresh reset edge. */
    bool reset_eligible=before==PC_FAULT&&s->energy.out.reset_ok;
    bool healthy=s->energy.configured&&(s->energy.state!=ENERGY_FAULT||reset_eligible)&&e.stop_ok&&(e.hardware_latch_ok||reset_eligible)&&
        e.sensors_valid&&e.receiver_ok&&e.aux_ok&&e.hardware_ok;
    if(s->energy.state==ENERGY_DISCHARGE||e.off_request) { s->stop_done=true;cancel_pc(s); }
    if(!in->proof_window_high) {
        if(!s->window_low_seen) { s->window_low_seen=true;s->window_low_us=in->now_us; }
    } else s->window_low_seen=false;
    bool rearm=s->first_kt_seen&&in->now_us-s->first_kt_us>=131433u&&
        s->window_low_seen&&in->now_us-s->window_low_us>=2000u;
    if(before==PC_REPROVE) {
        bool fresh=in->measurement_serial!=s->reproof_serial&&in->loaded_bypass_proof;
        if(fresh&&!s->reproof_good) { s->reproof_good=true;s->reproof_good_us=in->now_us; }
        if(s->reproof_good&&!fresh) s->reproof_failed=true;
        if(s->reproof_failed) healthy=false;
    }
    bool cold=s->energy.safe_timing&&e.resistor_cool&&
        e.now_ms-s->energy.safe_since_ms>=s->energy.cfg.discharge_stable_ms&&
        e.now_ms-s->energy.lockout_ms>=s->energy.cfg.retry_ms;
    pc_inputs p={.now_us=in->now_us,.mirror_us=in->mirror_us,
      .post_token=in->energy.manual_post_serial,.start=in->energy.start,.reset=e.reset,
      .healthy=healthy,.source_released=e.k1_released&&e.k2_released,.bypass_released=e.kb_released,
      .discharged=e.bus_v<30&&e.catch_v<30&&e.tank_abs_v<30,
      .post_valid=in->energy.manual_post_ok,.cold=cold,.a_nc=in->kpa_nc,.b_nc=in->kpb_nc,
      .mirror_valid=in->mirror_valid,.feedback_static=in->feedback_static,.proof_timer_ready=rearm,
      .precharge_complete=s->energy.state>=ENERGY_BYPASS_CLOSE&&s->energy.state<=ENERGY_RUN,
      .bypass_proven=e.bypass_closed_electrically&&s->energy.state>=ENERGY_RAIL_QUALIFY&&s->energy.state<=ENERGY_RUN,
      .post_isolation_proven=s->reproof_good&&!s->reproof_failed&&in->now_us-s->reproof_good_us>=50000u,
      .run_qualified=s->energy.state==ENERGY_READY||s->energy.state==ENERGY_RUN};
    pc_step(&s->isolation,&p);
    if(before==PC_OFF&&s->isolation.state==PC_TEST_A_CLOSE) {
        s->run_session_qualified=false;s->catch_history=false;s->attempt_post_valid=true;s->attempt_post_serial=in->energy.manual_post_serial;
        s->consume_post=true;s->admitted=false;s->admission_pending=false;s->admit=false;s->first_kt_seen=false;s->reproof_good=false;s->reproof_failed=false;
    }
    if(before==PC_CONNECT&&s->isolation.state==PC_PRECHARGE) {
        /* A new physical START token must admit a fresh hardware attempt.
           Stale-high windows are not an acknowledgment of this edge. */
        if(in->hardware_attempt||in->hardware_total_window) {
            s->isolation.state=PC_FAULT;s->isolation.out=(pc_outputs){0};
        } else { s->admission_pending=true;s->admit=true; }
    } else if(s->admission_pending) {
        if(s->isolation.state!=PC_PRECHARGE||in->now_us-s->isolation.source_us>=5000u) {
            s->isolation.state=PC_FAULT;s->isolation.out=(pc_outputs){0};
        } else if(in->hardware_attempt&&in->hardware_total_window) {
            e.start=true;e.manual_post_ok=s->attempt_post_valid;e.manual_post_serial=s->attempt_post_serial;
            energy_supervisor_step(&s->energy,&e);
            if(s->energy.state!=ENERGY_PRECHARGE) { s->isolation.state=PC_FAULT;s->isolation.out=(pc_outputs){0}; }
            else { s->admission_pending=false;s->admitted=true;s->admit=false; }
        }
    }

    if(before!=PC_REPROVE&&s->isolation.state==PC_REPROVE) {
        s->reproof_serial=in->measurement_serial;s->reproof_good=false;s->reproof_failed=false;
    }
    s->out=s->energy.out;
    s->out.k1=s->out.k1&&s->isolation.out.main;s->out.k2=s->out.k2&&s->isolation.out.main;
    s->out.kb=s->out.kb&&s->isolation.out.bypass;
    s->out.kt=(s->out.kt&&s->isolation.state==PC_BYPASS)||s->isolation.state==PC_REPROVE||
        (before==PC_REPROVE&&s->isolation.state==PC_READY); /* Preserve proof-load setup/hold across PB13 edge. */
    s->out.sup_run_ok=s->out.sup_run_ok&&s->isolation.out.run;
    if(s->out.sup_run_ok) s->run_session_qualified=true;
    s->kpa=s->isolation.out.a;s->kpb=s->isolation.out.b;
    if(s->out.kt&&!s->first_kt_seen) { s->first_kt_seen=true;s->first_kt_us=in->now_us; }
    if(s->isolation.state==PC_FAULT||s->energy.state==ENERGY_FAULT) {
        s->stop_done=true;s->run_session_qualified=false;s->catch_history=false;
        s->out=(energy_outputs_t){.reset_ok=s->energy.out.reset_ok};s->kpa=false;s->kpb=false;
        s->attempt_post_valid=false;s->consume_post=true;s->admit=false;s->admission_pending=false;
    }
    /* Release asynchronous clear before the fresh physical RESET edge. OFF is
       not STOP_DONE: it includes all source-isolated mechanical tests. */
    if(r5_supervisor_reset_permitted(s)&&!e.reset) s->stop_done=false;
}
