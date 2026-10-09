#include "measurement.h"
#include "line_telemetry.h"
#include "sensor_frontend.h"
#include <assert.h>
#include <math.h>
#include <stdio.h>
#include <string.h>
static r5_measurement_t run(unsigned fault)
{
    r5_measurement_t s;double error[8]={0};assert(r5_measurement_init(&s,error));
    for(uint32_t us=0;us<120000;us+=256) {
        double v=169.705627* sin(6.283185307179586*60*us/1e6);
        double cap=us<16667?0:168;
        double p[8]={v,0,v,170,cap,0,v/220,0};
        if(fault==1&&v<0) p[1]=10; /* bad negative crest only */
        if(fault==2) p[6]=0;
        if(fault==3) p[0]*=1.25;
        if(fault==4) p[4]=168; /* charged at boot */
        if(fault==5) p[3]=120; /* precharge incomplete */
        if(fault==6) p[7]=16;
        assert(r5_measurement_add(&s,us,p,fault!=7,true));
    }
    return s;
}
int main(void)
{
    r5_measurement_t s=run(0);assert(s.precharge_ok&&s.proof_ok&&s.source_ok&&s.catch_ok);
    r5_measurement_t disabled=s;
    double p[8];memcpy(p,disabled.previous,sizeof p);
    assert(r5_measurement_add(&disabled,disabled.previous_us+256,p,false,false));
    assert(!disabled.proof_ok&&!disabled.precharge_ok);
    assert(!run(1).precharge_ok);assert(!run(2).proof_ok);assert(!run(3).source_ok);
    assert(!run(4).catch_ok);assert(!run(5).precharge_ok);assert(!run(6).source_ok);assert(!run(7).proof_ok);
    uint8_t frame[R5_LINE_BYTES];s.complete=true;assert(r5_line_encode(&s,frame));
    r5_line_receiver_t r={0};assert(r5_line_receive(&r,frame,100000));
    assert(!r5_line_receive(&r,frame,116667));
    for(unsigned bit=0;bit<R5_LINE_BYTES*8;bit++) {
        r=(r5_line_receiver_t){0};frame[bit/8]^=1u<<(bit%8);
        assert(!r5_line_receive(&r,frame,100000));frame[bit/8]^=1u<<(bit%8);
    }
    r5_sensor_frontend_t f={0};assert(!r5_sensors_configure(&f));
    for(unsigned ch=0;ch<8;ch++) assert(r5_calibrate(&f.channel[ch],0,1000000,100,.01,500000,50,.01));
    assert(r5_sensors_configure(&f));ads_sample_t a={.captured_us=1000};assert(r5_sensors_sample(&f,&a,false,false));
    assert(!r5_sensors_sample(&f,&a,false,false));
    puts("PASS: polarity-specific crest, proof open/disabled, source overvoltage/overcurrent, catch initial-state, 224 UART bit corruptions, duplicate, target frontend calibration");
}
