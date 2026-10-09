#include "controller_intent.h"
#include <assert.h>
#include <stdio.h>
int main(void){
 energy_link_receiver_t r={.seen=true,.received_ms=100};
 energy_link_packet_t p={.kind=ENERGY_LINK_COMMAND,.flags=ENERGY_LINK_REQUEST};
 assert(r5_controller_intent(&r,&p,110,true,true));
 assert(!r5_controller_intent(&r,&p,121,true,true));
 assert(!r5_controller_intent(&r,&p,110,false,true));
 assert(!r5_controller_intent(&r,&p,110,true,false));
 p.flags|=ENERGY_LINK_FAULT;assert(!r5_controller_intent(&r,&p,110,true,true));
 p.flags=0;assert(r5_controller_diagnostics(&r,&p,110,true));assert(!r5_controller_intent(&r,&p,110,true,true));
 puts("controller intent requires fresh fault-free command, physicalREQUEST and changingheartbeat; no external waveform claim");
}
