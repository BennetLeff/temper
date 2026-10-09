#include "mirror.h"
#include <string.h>
bool r5_mirror_init(r5_mirror_t *m,unsigned count)
{
    if(!m) return false;
    memset(m,0,sizeof *m);if(!count||count>R5_MIRROR_MAX) { m->fault=true;return false; }
    m->count=count;return true;
}
static bool fail(r5_mirror_t *m)
{
    m->fault=true;m->qualified=false;m->excite_mask=0;
    for(unsigned i=0;i<m->count;i++) m->released[i]=false;
    return false;
}
bool r5_mirror_step(r5_mirror_t *m,uint32_t now,const bool r[R5_MIRROR_MAX],bool off,bool discharged)
{
    if(!m||!r||m->fault||!m->count) return false;
    if(m->static_requested) {
        if(now-m->published_us>2000) return fail(m);
        if(now-m->slot_at<100) return false;
        for(unsigned i=0;i<m->count;i++) {
            if(!m->static_ready&&!r[i]) return fail(m);
            if(r[i]!=m->raw[i]) { m->raw[i]=r[i];m->changed_us[i]=now; }
            m->released[i]=r[i]&&now-m->changed_us[i]>=5000;
        }
        m->static_ready=true;m->published_us=now;return true;
    }
    if(!m->started) {

        if(!off||!discharged) return false;
        m->started=true;m->scan_at=m->slot_at=now;m->slot_deadline=now+150;return false;
    }
    if((uint32_t)(now-m->scan_at)>1000) return fail(m);
    if(m->qualified&&(uint32_t)(now-m->published_us)>2000) return fail(m);
    if(!m->qualified&&(!off||!discharged)) return fail(m);
    uint32_t elapsed=now-m->slot_at;
    if(!m->sampled&&elapsed>=100) {
        for(unsigned i=0;i<m->count;i++) {
            bool active=m->slot==i+1;
            if(!active&&r[i]) return fail(m); /* Cross-short / stuck-high. */
            if(active&&r[i]) m->pending_mask|=1u<<i;
        }
        m->sampled=true;
    }
    if((int32_t)(now-m->slot_deadline)<0||!m->sampled) return m->qualified;
    if(++m->slot>m->count) {
        if(!m->qualified&&m->pending_mask!=((1u<<m->count)-1)) return fail(m);
        for(unsigned i=0;i<m->count;i++) {
            bool level=(m->pending_mask&(1u<<i))!=0;
            if(!m->qualified||level!=m->raw[i]) { m->raw[i]=level;m->changed_us[i]=now; }
            m->released[i]=level&&(uint32_t)(now-m->changed_us[i])>=5000;
        }
        m->qualified=true;m->published_us=now;m->slot=0;m->scan_at=now;m->pending_mask=0;
    }
    m->slot_deadline+=150;m->slot_at=now;m->sampled=false;m->excite_mask=m->slot?1u<<(m->slot-1):0;
    return m->qualified;
}
bool r5_mirror_fresh(const r5_mirror_t *m,uint32_t us)
{ return m&&m->qualified&&!m->fault&&(uint32_t)(us-m->published_us)<=2000; }
bool r5_mirror_hold_static(r5_mirror_t *m,uint32_t now)
{
    if(!r5_mirror_fresh(m,now)||m->static_requested) return false;
    for(unsigned i=0;i<m->count;i++) if(!m->released[i]) return false;
    m->static_requested=true;m->static_ready=false;m->slot_at=now;
    m->excite_mask=(1u<<m->count)-1;return true;
}
