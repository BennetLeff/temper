#include "qualification.h"
#include <math.h>
#include <stddef.h>
#include <stdlib.h>

#include <string.h>
bool r5_heartbeat_step(r5_heartbeat_t *h, bool level, uint32_t now)
{
    if(!h || h->fault) return false;
    if(!h->seen) { h->seen=true; h->level=level; h->edge_ms=now; return false; }
    uint32_t elapsed=now-h->edge_ms;
    if(level!=h->level) {
        /* Controller toggles every 5ms; tolerate task jitter, never DC. */
        if(elapsed<2 || elapsed>15) { h->fault=true; return false; }
        h->edge_ms=now; h->level=level; if(h->edges<3) ++h->edges;
    } else if(elapsed>15) { h->fault=true; return false; }
    return h->edges>=3;
}
bool r5_calibrate(r5_calibration_t *c, int32_t zero, int32_t injected,
                   float reference, float reference_error, int32_t check,
                   float check_reference, float limit)
{
    if(!c) return false;
    memset(c,0,sizeof *c);
    if(!isfinite(reference)||!isfinite(reference_error)||!isfinite(check_reference)||
       !isfinite(limit)||reference==0||reference_error<0||limit<=0||
       zero<=-8380000||zero>=8380000||injected<=-8380000||injected>=8380000||
       check<=-8380000||check>=8380000||abs(injected-zero)<1000||
       abs(check-zero)<500||abs(check-injected)<500) return false;
    float gain=reference/(float)(injected-zero);
    float residual=fabsf((check-zero)*gain-check_reference);
    if(!isfinite(gain)||residual>limit) return false;
    *c=(r5_calibration_t){gain,(float)zero,limit,reference_error+limit,true};
    return true;
}
bool r5_scale(const r5_calibration_t *c,int32_t code,float *v,float *error)
{
    if(!c||!v||!error||!c->valid||code<=-8380000||code>=8380000) return false;
    *v=((float)code-c->offset_code)*c->units_per_code; *error=c->error;
    return isfinite(*v)&&isfinite(*error)&&*error>=0;
}
bool r5_ntc_temperature(const r5_ntc_config_t *c,uint16_t code,float *t)
{
    if(!c||!t||code<16||code>4079||!isfinite(c->pullup_ohm)||!isfinite(c->r25_ohm)||
       !isfinite(c->beta_k)||!isfinite(c->error_c)||c->pullup_ohm<=0||c->r25_ohm<=0||
       c->beta_k<1000||c->error_c<0||c->error_c>5) return false;
    float r=c->pullup_ohm*(float)code/(4095-code);
    *t=1.0f/(1.0f/298.15f+logf(r/c->r25_ohm)/c->beta_k)-273.15f;
    return isfinite(*t)&&*t>=-40&&*t<=200;
}
bool r5_ntc_cold(const r5_ntc_config_t *c,uint16_t code,float *t)
{ return r5_ntc_temperature(c,code,t)&&c->lag_qualified&&*t<=20&&*t+c->error_c<=25; }
