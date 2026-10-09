#include "measurement.h"
#include <math.h>
#include <string.h>
bool r5_measurement_init(r5_measurement_t *s,const double error[8])
{
    if(!s) return false;
    memset(s,0,sizeof *s);s->fault=true;
    if(!error) return false;
    for(unsigned n=0;n<8;n++) if(!isfinite(error[n])||error[n]<0) return false;
    memcpy(s->error,error,sizeof s->error);s->fault=false;return true;
}
static void area(r5_measurement_t *s,const double *a,const double *b,double dt)
{
    for(unsigned n=0;n<8;n++) s->integral[n]+=(a[n]*a[n]+a[n]*b[n]+b[n]*b[n])*dt/3;
    s->duration+=dt;
}
static bool fail(r5_measurement_t *s)
{ s->fault=true;s->complete=s->precharge_ok=s->proof_ok=s->source_ok=s->catch_ok=false;return false; }
bool r5_measurement_add(r5_measurement_t *s,uint32_t us,const double p[8],bool proof,bool contacts)
{
    if(!s||!p||s->fault) return false;
    s->complete=false;
    /* A completed-cycle result never preserves permission after withdrawal of
       its physical excitation/contact qualifier during the next cycle. */
    if(!proof) s->proof_ok=false;
    if(!contacts) { s->precharge_ok=false;s->good_pre=0; }
    for(unsigned n=0;n<8;n++) if(!isfinite(p[n])) return fail(s);
    if(!s->seen) {
        s->seen=true;s->previous_us=us;memcpy(s->previous,p,sizeof s->previous);
        s->catch_discharged=fabs(p[4])+s->error[4]<5;
        s->initial_catch=s->previous_catch=p[4];return true;
    }
    uint32_t dus=us-s->previous_us;if(dus<200||dus>350) return fail(s);
    double dt=dus*1e-6;
    if(s->previous[0]<0&&p[0]>=0) {
        double f=-s->previous[0]/(p[0]-s->previous[0]),cross[8];
        for(unsigned n=0;n<8;n++) cross[n]=s->previous[n]+f*(p[n]-s->previous[n]);
        if(s->started) {
            area(s,s->previous,cross,dt*f);
            if(s->duration<1./65||s->duration>1./45) return fail(s);
            for(unsigned n=0;n<8;n++) s->rms[n]=sqrt(s->integral[n]/s->duration);
            s->period=s->duration;s->serial++;s->complete=true;s->completed_us=us;
            double crest=fmax(s->peak[0],s->peak[1]);
            s->source_ok=s->rms[0]-s->error[0]>=100&&s->rms[0]+s->error[0]<=140&&
                s->rms[7]+s->error[7]<=15&&crest+s->error[0]<=230&&
                crest<=1.8*s->rms[0]&&s->peak[0]>=s->rms[0]&&s->peak[1]>=s->rms[0];
            bool good=contacts&&s->contacts_entire&&s->source_ok;
            for(unsigned k=0;k<2;k++) good=good&&s->drop_at_peak[k]<5&&
                s->drop_at_peak[k]/11.875<.5&&s->ratio_at_peak[k]>=.95;
            s->good_pre=good?(s->good_pre<2?s->good_pre+1:2):0;
            s->precharge_ok=s->good_pre>=2;
            /* Full cycle excitation plus uncertainty-contained 220R proof load. */
            s->proof_ok=proof&&s->proof_entire&&s->rms[2]-s->error[2]>=100&&
                s->rms[6]-s->error[6]>=.9*(s->rms[2]+s->error[2])/220&&
                s->rms[6]+s->error[6]<=1.1*(s->rms[2]-s->error[2])/220;
        }
        memset(s->integral,0,sizeof s->integral);s->duration=0;s->started=true;
        memset(s->peak,0,sizeof s->peak);memset(s->drop_at_peak,0,sizeof s->drop_at_peak);
        memset(s->ratio_at_peak,0,sizeof s->ratio_at_peak);
        s->proof_entire=proof;s->contacts_entire=contacts;area(s,cross,p,dt*(1-f));
    } else if(s->started) area(s,s->previous,p,dt);
    if(s->started&&s->duration>1./45) return fail(s);
    s->proof_entire=s->proof_entire&&proof;s->contacts_entire=s->contacts_entire&&contacts;
    unsigned k=p[0]>=0?0:1;
    if(s->started&&fabs(p[0])>=s->peak[k]) {
        s->peak[k]=fabs(p[0]);s->drop_at_peak[k]=fabs(p[1])+s->error[1];
        s->ratio_at_peak[k]=(p[3]-s->error[3])/(fabs(p[0])+s->error[0]+1e-12);
    }
    if(s->catch_discharged&&p[4]-s->initial_catch>20+2*s->error[4]&&p[4]>s->previous_catch)
        s->catch_rose=true;
    s->catch_ok=s->catch_rose&&p[3]-s->error[3]>=100&&
        p[4]-s->error[4]>=p[3]+s->error[3]-5&&p[4]+s->error[4]<=p[3]-s->error[3]+5;
    s->previous_catch=p[4];s->previous_us=us;memcpy(s->previous,p,sizeof s->previous);return true;
}
bool r5_measurement_fresh(const r5_measurement_t *s,uint32_t us)
{ return s&&s->seen&&!s->fault&&(uint32_t)(us-s->previous_us)<=1000; }
