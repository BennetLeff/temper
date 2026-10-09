/* Independent analytic waveform checks of the exact STM32/shared estimator.
 * No plant outputs or estimator-computed values supply the expected answers. */
#include "measurement.h"
#include "bypass.h"
#include <assert.h>
#include <math.h>
#include <stdio.h>

static r5_measurement_t waveform(double line, double third, bool proof,
                                 bool contacts, double drop, double error)
{
    r5_measurement_t s;
    double uncertainty[8]={error,error,error,error,error,error,error/220,error};
    assert(r5_measurement_init(&s,uncertainty));
    for(uint32_t us=256;us<=200000;us+=256) {
        double phase=2*3.14159265358979323846*60*us*1e-6;
        double v=sqrt(2.)*(line*sin(phase)+third*sin(3*phase));
        double p[8]={v,drop,v,175,175,0,proof?v/220:0,3*sin(phase)};
        assert(r5_measurement_add(&s,us,p,proof,contacts));
    }
    return s;
}
int main(void)
{
    /* 256us linear interpolation attenuates a sampled sine slightly. Analytic
       RMS is120V; the independent tolerance includes interpolation error. */
    r5_measurement_t s=waveform(120,0,true,true,0,0);
    assert(s.serial>=10 && fabs(s.rms[0]-120)<.11);
    assert(s.precharge_ok && s.proof_ok && s.source_ok);
    assert(r5_bypass_loaded(&s));
    assert(!s.catch_ok); /* An initially charged capacitor is not charge proof. */
    double withdrawn[8]={1,0,1,175,175,0,0,0};
    assert(r5_measurement_add(&s,s.previous_us+256,withdrawn,false,false));
    assert(!s.precharge_ok&&!s.proof_ok);
    s=waveform(120,12,true,true,0,0);
    assert(fabs(s.rms[0]-sqrt(120.*120+12.*12))<.15);
    s=waveform(120,0,false,true,0,0);assert(!s.proof_ok);
    s=waveform(120,0,true,false,0,0);assert(!s.precharge_ok);
    s=waveform(240,0,true,true,0,0);assert(!s.source_ok&&!s.precharge_ok);
    s=waveform(120,0,true,true,4.9,.2);assert(!s.precharge_ok);
    s=waveform(120,0,true,true,6.8,0);
    assert(s.proof_ok&&!r5_bypass_loaded(&s));
    double p[8]={0};
    assert(!r5_measurement_add(&s,s.previous_us,p,true,true));
    assert(!s.precharge_ok&&!s.proof_ok&&!s.source_ok&&!s.catch_ok);
    double invalid[8]={0};invalid[3]=NAN;
    assert(!r5_measurement_init(&s,invalid));
    puts("PASS: exact shared estimator, analytic RMS/harmonic and admission negative controls");
    return 0;
}
