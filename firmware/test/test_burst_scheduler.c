#include "burst_scheduler.h"
#include <assert.h>
#include <math.h>
#include <stdio.h>
int main(void)
{
    /* Independent committed burst_flicker.py output, rounded to 0.01 s. */
    const double power[] = {160, 200, 250, 300};
    const double expected[] = {2.48, 5.06, 10.34, 18.52};
    for (unsigned i=0; i<4; i++) {
        double actual = burst_min_period_s(power[i],120,.95);
        printf("%.0f W minimum %.9f s\n",power[i],actual);
        assert(fabs(actual-expected[i]) < .005);
    }
    burst_scheduler_t s;
    burst_config_t c={0};
    assert(burst_scheduler_init(&s,&c));
    assert(burst_scheduler_step(&s,0,NULL,80) && s.on); /* continuous default */
    c=(burst_config_t){.burst_enabled=true,.measured_burst_w=160,.line_rms_v=120,.power_factor=.95};
    assert(burst_scheduler_init(&s,&c) && s.half_cycles==2400);
    unsigned on=0, changes=0;
    for (unsigned n=0;n<4800;n++) {
        uint64_t now=(uint64_t)n*25000/3;
        hal_bus_crossing_t bus={.sampled_us=now,.valid=true,.zero_crossing=true,.from_line_zc=true,.bus_v=0};
        bool before=s.on;
        assert(burst_scheduler_step(&s,now,&bus,80));
        on+=s.on; changes+=s.on!=before;
        before=s.on;
        bus.zero_crossing=false; bus.sampled_us=now+50; bus.bus_v=2;
        assert(burst_scheduler_step(&s,now+50,&bus,80) && s.on==before);
    }
    assert(on==2400 && changes==4);
    assert(!burst_scheduler_step(&s,s.last_crossing_us+10000,NULL,80) && !s.on);
    assert(burst_scheduler_init(&s,&c));
    hal_bus_crossing_t bus={.valid=true,.zero_crossing=true,.from_line_zc=true,.bus_v=0};
    assert(burst_scheduler_step(&s,0,&bus,80) && s.on);
    assert(burst_scheduler_step(&s,0,&bus,80) && s.index==0); /* repeated sample */
    bus.sampled_us=50;
    assert(!burst_scheduler_step(&s,50,&bus,80) && !s.on); /* duplicate/noisy edge */
    assert(burst_scheduler_init(&s,&c));
    /* Idle bridge: film caps hold the line peak; a LINE_ZC crossing still starts the burst. */
    bus=(hal_bus_crossing_t){.valid=true,.zero_crossing=true,.from_line_zc=true,.bus_v=170};
    assert(burst_scheduler_step(&s,0,&bus,80) && s.on);
    /* A crossing not sourced from LINE_ZC (e.g. derived from VBUS) is refused. */
    assert(burst_scheduler_init(&s,&c));
    bus=(hal_bus_crossing_t){.valid=true,.zero_crossing=true,.from_line_zc=false,.bus_v=0};
    assert(!burst_scheduler_step(&s,0,&bus,80) && !s.on);
    bus.from_line_zc=true;
    assert(burst_scheduler_init(&s,&c)); bus.bus_v=0;
    assert(!burst_scheduler_step(&s,151,&bus,80));
    c.measured_burst_w=400;
    assert(burst_scheduler_init(&s,&c) && s.half_cycles>2400);
    c.power_factor=NAN; assert(!burst_scheduler_init(&s,&c));
    puts("burst scheduler: LINE_ZC-only crossings, half-cycle counts, default-off, timing and input checks PASS");
}
