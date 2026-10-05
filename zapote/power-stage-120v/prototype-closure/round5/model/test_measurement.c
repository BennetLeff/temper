#include "sampled_measurement.h"
#include <assert.h>
#include <math.h>
#include <stdio.h>
int main(void){
 sampled_measurement_t s={0};double p[8]={0};
 for(uint32_t us=256;us<200000;us+=256){double t=us*1e-6,w=2*3.141592653589793*60*t;
  p[0]=120*sqrt(2)*sin(w);p[1]=0;p[2]=p[0];p[3]=170;p[4]=170;p[5]=0;p[6]=p[2]/220;p[7]=4*sin(w)+3*sin(3*w);
  assert(sampled_measurement_add(&s,us,p,true,true));}
 assert(s.serial>=10);assert(fabs(s.rms[0]-120)<.02);assert(fabs(s.rms[7]-sqrt(12.5))<.002);assert(s.precharge_ok);assert(s.proof_ok);
 assert(!sampled_measurement_add(&s,s.previous_us,p,true,true));
 s=(sampled_measurement_t){0};
 for(uint32_t us=256;us<200000;us+=256){double w=2*3.141592653589793*60*us*1e-6;p[0]=120*sqrt(2)*sin(w);p[2]=p[0];p[6]=0;assert(sampled_measurement_add(&s,us,p,true,true));}
 assert(!s.proof_ok);puts("PASS: analytic sine/harmonic true RMS, two-polarity crest admission, missing-proof rejection, duplicate timestamp rejection");return 0;
}
