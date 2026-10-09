#include "acquisition.h"
#include "qualification.h"
#include "measurement.h"
#include <assert.h>
#include <math.h>
#include <stdio.h>
int main(void) {
    post_record_t p={0};
    post_branch_t b[2]={{12.5f,.1f,true},{12.5f,.1f,true}};
    assert(!post_record_accept(&p,1,1,0,b,true,true,true,true));
    b[0].ohm=25;b[1].ohm=25;
    assert(!post_record_accept(&p,1,1,0,b,true,true,true,true));
    assert(post_record_accept(&p,1,2,0,b,true,true,true,true));
    assert(post_record_fresh(&p,1,60000));assert(!post_record_fresh(&p,1,60001));
    post_record_consume(&p);assert(!post_record_fresh(&p,1,0));
    b[1].ohm=26.2f;assert(!post_record_accept(&p,1,3,0,b,true,true,true,true));
    b[1].ohm=25;b[1].isolated_four_wire=false;
    assert(!post_record_accept(&p,1,4,0,b,true,true,true,true));
    b[1].isolated_four_wire=true;
    assert(!post_record_accept(&p,1,5,0,b,true,true,true,false));
    assert(!post_record_accept(&p,2,6,0,b,true,true,true,true));
    r5_heartbeat_t h={0};assert(!r5_heartbeat_step(&h,0,0));
    assert(!r5_heartbeat_step(&h,1,5));assert(!r5_heartbeat_step(&h,0,10));
    assert(r5_heartbeat_step(&h,1,15));assert(!r5_heartbeat_step(&h,1,31));
    assert(!r5_heartbeat_step(&h,0,35));
    r5_calibration_t c;float v,e;
    assert(!r5_calibrate(&c,100,100,100,.1,100,50,1));
    assert(!r5_calibrate(&c,100,10100,100,.1,5100,60,1));
    assert(r5_calibrate(&c,100,10100,100,.1,5100,50,1));
    assert(r5_scale(&c,2600,&v,&e)&&fabsf(v-25)<.001&&e>=1);
    r5_ntc_config_t ntc={10000,10000,3950,5,true};float t;
    assert(!r5_ntc_temperature(&ntc,0,&t));assert(!r5_ntc_temperature(&ntc,4095,&t));
    assert(r5_ntc_temperature(&ntc,2048,&t)&&fabsf(t-25)<.02);
    assert(!r5_ntc_cold(&ntc,2048,&t));assert(r5_ntc_cold(&ntc,2600,&t));
    r5_measurement_t s;double errors[8]={0};assert(r5_measurement_init(&s,errors));unsigned cycles=0;
    for(uint32_t us=0;us<100000;us+=256) {
        double wave=sin(2*3.14159265358979323846*60*us/1000000.);
        double p[8]={169.705627*wave,0,169.705627*wave,170,168,0,169.705627*wave/220,14.142136*wave};
        assert(r5_measurement_add(&s,us,p,true,true));
        if(s.complete) { ++cycles;assert(fabs(s.rms[0]-120)<.2);assert(fabs(s.rms[7]-10)<.02);assert(s.source_ok&&s.proof_ok); }
    }
    assert(cycles>=4&&!s.fault&&r5_measurement_fresh(&s,100000));
    assert(!s.catch_ok); /* Already charged at startup is not charge history. */
    double zero[8]={0};assert(!r5_measurement_add(&s,100000,zero,0,0)&&s.fault);
    puts("PASS: two-branch POST, replay, uncertainty, heartbeat DC/glitch, calibration, NTC, exact completed cycles");
}
