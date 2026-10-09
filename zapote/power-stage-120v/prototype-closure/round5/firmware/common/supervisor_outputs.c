#include "supervisor_outputs.h"
r5_supervisor_signals_t r5_supervisor_signals(const r5_supervisor_t *s,bool health,bool heartbeat,bool post)
{
 r5_supervisor_signals_t o={.stop_done=true};
 if(!s||!s->energy.configured||!health)return o;
 o.reset_ok=r5_supervisor_reset_permitted(s);o.stop_done=s->stop_done;o.healthy=health;o.heartbeat_ok=heartbeat;
 /* Faulted owners may expose qualified RESET and release STOP_DONE; no coil,
    run, proof, admission, POST or START permission is allowed in this branch. */
 if(s->energy.state==ENERGY_FAULT||s->isolation.state==PC_FAULT)return o;
 o.k1=s->out.k1;o.k2=s->out.k2;o.kb=s->out.kb;o.kt=s->out.kt;
 o.kpa=s->kpa;o.kpb=s->kpb;o.run=s->out.sup_run_ok;o.admit=s->admit;
 o.post_ok=s->attempt_post_valid||post;o.start_released=s->energy.start_released&&post;
 o.precharge_done=s->energy.state>=ENERGY_BYPASS_CLOSE&&s->energy.state<=ENERGY_RUN;
 o.bypass_proven=s->isolation.state==PC_READY||s->isolation.state==PC_RUN;
 return o;
}
