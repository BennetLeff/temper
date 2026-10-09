#include "bypass.h"
#include <assert.h>
#include <math.h>
#include <stdio.h>
int main(void)
{
    for(unsigned open=0;open<2;open++) {
        r5_measurement_t s;double e[8]={0};assert(r5_measurement_init(&s,e));
        for(uint32_t us=0;us<100000;us+=256) {
            double line=169.705627*sin(6.283185307179586*60*us/1e6);
            double current=line/(220+(open?12.5:0));
            double p[8]={line,open?12.5*current:0,220*current,170,168,0,current,current};
            assert(r5_measurement_add(&s,us,p,true,true));
        }
        assert(s.proof_ok); /* Current ratio alone passes even withKBopen. */
        assert(r5_bypass_loaded(&s)==!open);
    }
    puts("PASS: KT full-cycle current through12.5ohm falsely passes ratio; loadedVPRErejects openKB, acceptsclosedKB");
}
