/* Register-SEMANTICS test, NOT execution of ESP silicon. Uses the actual SDK
 * register layout. Counter interleavings are exhausted at every shadow write.
 * The semantics are independently specified in Espressif mcpwm_struct.h. */
#include "soc/mcpwm_struct.h"
#include "fullbridge_adapter.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>
static void tez(const mcpwm_dev_t *regs,uint32_t active[4])
{
    if(!regs->update_cfg.global_up_en) return;
    for(unsigned op=0;op<2;op++) {
        if(regs->operators[op].gen_stmp_cfg.gen_a_upmethod&1) active[op*2]=regs->operators[op].timestamp[0].gen;
        if(regs->operators[op].gen_stmp_cfg.gen_b_upmethod&1) active[op*2+1]=regs->operators[op].timestamp[1].gen;
    }
}
int main(void)
{
    unsigned naive_mixes=0;
    for(unsigned gate=0;gate<2;gate++) for(unsigned events=0;events<32;events++) {
        mcpwm_dev_t regs={0};uint32_t active[4]={0,800,0,800};
        uint32_t old[4]={0,800,0,800},next[4]={0,800,400,1200};
        regs.update_cfg.global_up_en=!gate;
        for(unsigned i=0;i<2;i++) {
            regs.operators[i].gen_stmp_cfg.gen_a_upmethod=1;
            regs.operators[i].gen_stmp_cfg.gen_b_upmethod=1;
            regs.operators[i].timestamp[0].gen=old[2*i];regs.operators[i].timestamp[1].gen=old[2*i+1];
        }
        for(unsigned i=0;i<4;i++) {
            regs.operators[i/2].timestamp[i%2].gen=next[i];
            if(events&(1u<<i)) tez(&regs,active);
            bool mixed=memcmp(active,old,sizeof old)&&memcmp(active,next,sizeof next);
            if(gate) assert(!mixed);else naive_mixes+=mixed;
        }
        regs.update_cfg.global_up_en=1;tez(&regs,active);assert(!memcmp(active,next,sizeof next));
    }
    assert(naive_mixes>0);
    for(unsigned phase=0;phase<=800;phase++) {
        bridge_cycle_t c;assert(bridge_plan_cycle(80000000,50000,125,phase/800.f,&c));
        unsigned high[4]={0};
        for(unsigned tick=0;tick<c.period;tick++) {
            assert(!(bridge_output_at(&c,0,tick)&&bridge_output_at(&c,1,tick)));
            assert(!(bridge_output_at(&c,2,tick)&&bridge_output_at(&c,3,tick)));
            for(unsigned p=0;p<4;p++) high[p]+=bridge_output_at(&c,p,tick);
        }
        for(unsigned p=0;p<4;p++) assert(high[p]==790);
        if(phase==800) { assert(c.pulse[2].rise==810);assert(c.pulse[3].rise==10); }
    }
    printf("PASS: ungated interleavings expose %u mixed states; global-gated transactions never mix; all801 phases incl endpoints have790ticks each and no overlap\n",naive_mixes);
}
