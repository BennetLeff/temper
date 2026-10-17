#include "sampled_measurement.h"
#include <math.h>
#include <string.h>
static void accumulate(sampled_measurement_t *s,const double *a,const double *b,double dt)
{for(unsigned n=0;n<8;n++)s->integral[n]+=.5*(a[n]*a[n]+b[n]*b[n])*dt;s->duration+=dt;}
bool sampled_measurement_add(sampled_measurement_t *s,uint32_t us,const double p[8],bool proof,bool contacts)
{
    if(!s||!p)return false;s->complete=false;
    for(unsigned n=0;n<8;n++)if(!isfinite(p[n]))return false;
    if(!s->seen){s->seen=true;s->previous_us=us;memcpy(s->previous,p,sizeof s->previous);return true;}
    uint32_t dus=us-s->previous_us;if(dus<200||dus>350)return false;
    double dt=dus*1e-6;
    if(s->previous[0]<=0&&p[0]>0){
        double f=-s->previous[0]/(p[0]-s->previous[0]);double cross[8];
        for(unsigned n=0;n<8;n++)cross[n]=s->previous[n]+f*(p[n]-s->previous[n]);
        if(s->started){
            accumulate(s,s->previous,cross,dt*f);
            if(s->duration<.014||s->duration>.022)return false;
            for(unsigned n=0;n<8;n++)s->rms[n]=sqrt(s->integral[n]/s->duration);
            s->period=s->duration;s->serial++;s->complete=true;
            bool good=contacts&&s->crest_polarities==3&&s->crest_drop<5&&s->crest_drop/11.875<.5&&s->crest_bus_ratio>=.95;
            s->good_pre=good?s->good_pre+1:0;
            if(s->good_pre>=2)s->precharge_ok=true;
            s->proof_ok=s->proof_entire&&s->rms[6]>=.9*s->rms[2]/220&&s->rms[6]<=1.1*s->rms[2]/220&&s->rms[2]>=100;
        }
        memset(s->integral,0,sizeof s->integral);s->duration=0;s->started=true;
        s->proof_entire=proof;s->crest_polarities=0;s->crest_drop=0;s->crest_bus_ratio=1e9;
        accumulate(s,cross,p,dt*(1-f));
    }else if(s->started)accumulate(s,s->previous,p,dt);
    s->proof_entire=s->proof_entire&&proof;
    double threshold=.98*sqrt(2)*s->rms[0];
    if(s->started&&s->serial&&fabs(p[0])>=threshold){
        s->crest_polarities|=p[0]>0?1:2;s->crest_drop=fmax(s->crest_drop,fabs(p[1]));
        s->crest_bus_ratio=fmin(s->crest_bus_ratio,p[3]/fabs(p[0]));
    }
    s->previous_us=us;memcpy(s->previous,p,sizeof s->previous);return true;
}
