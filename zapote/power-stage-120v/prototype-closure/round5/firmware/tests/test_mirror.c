#include "mirror.h"
#include <assert.h>
#include <stdio.h>
static void scan(r5_mirror_t *m,uint32_t until,unsigned closed,int stuck_high,int stuck_low,int cross)
{
    for(uint32_t us=0;us<=until;us+=50) {
        bool r[R5_MIRROR_MAX]={0};
        for(unsigned i=0;i<m->count;i++) r[i]=(closed&(1u<<i))&&(m->excite_mask&(1u<<i));
        if(stuck_high>=0) r[stuck_high]=true;
        if(stuck_low>=0) r[stuck_low]=false;
        if(cross>=0) r[cross]=r[0];
        (void)r5_mirror_step(m,us,r,true,true);
    }
}
static void timer_jitter(void)
{
    /* Conditional target timing allocation: entry latency0..20us, GPIOwrites5us.
       ADC's60us transfer runs in main and cannot mask this timer interrupt. */
    for(unsigned phase=0;phase<256;phase++) {
        r5_mirror_t m;assert(r5_mirror_init(&m,5));uint32_t last_change=0;
        for(unsigned tick=0;tick<180;tick++) {
            uint32_t now=tick*50+(tick*37+phase)%21;
            bool raw[5];for(unsigned n=0;n<5;n++)raw[n]=(m.excite_mask&(1u<<n))!=0;
            unsigned old=m.excite_mask;bool sampled=m.sampled;
            (void)r5_mirror_step(&m,now,raw,true,true);
            if(!sampled&&m.sampled)assert(now-last_change>=100);
            assert(!m.fault);
            if(!m.static_requested)(void)r5_mirror_hold_static(&m,now);
            if(old!=m.excite_mask){last_change=now+5;m.slot_at=last_change;}
        }
        assert(m.static_ready&&r5_mirror_fresh(&m,9000));
    }
}
int main(void)
{
    timer_jitter();

    for(unsigned count=3;count<=5;count+=2) {
        r5_mirror_t m;assert(r5_mirror_init(&m,count));scan(&m,7000,(1u<<count)-1,-1,-1,-1);
        assert(m.qualified&&!m.fault&&r5_mirror_fresh(&m,7000));
        for(unsigned ch=0;ch<count;ch++) assert(m.released[ch]);
        assert(r5_mirror_hold_static(&m,7000));assert(m.excite_mask==((1u<<count)-1));
        bool high[R5_MIRROR_MAX]={true,true,true,true,true};
        assert(!r5_mirror_step(&m,7050,high,true,true));assert(!m.static_ready);
        assert(r5_mirror_step(&m,7100,high,true,true));assert(m.static_ready);
        high[0]=false;assert(r5_mirror_step(&m,7200,high,false,false));assert(!m.raw[0]&&!m.released[0]);
        assert(m.excite_mask==((1u<<count)-1));assert(!r5_mirror_fresh(&m,10000));

        for(unsigned ch=0;ch<count;ch++) {
            assert(r5_mirror_init(&m,count));scan(&m,1500,(1u<<count)-1,(int)ch,-1,-1);assert(m.fault);
            assert(r5_mirror_init(&m,count));scan(&m,1500,(1u<<count)-1,-1,(int)ch,-1);assert(m.fault);
        }
        assert(r5_mirror_init(&m,count));scan(&m,1500,(1u<<count)-1,-1,-1,1);assert(m.fault);
    }
    puts("PASS: 3/5-channel sequential100us settle150us slots; inactive-cross-short and all stuckhigh/low; fullscanpublication; 5msrelease; 2msstale");
}
