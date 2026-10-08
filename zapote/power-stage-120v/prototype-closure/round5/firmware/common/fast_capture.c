#include "fast_capture.h"
#include <string.h>
uint32_t fast_crc32(const uint8_t *b,size_t n)
{
    uint32_t crc=0xffffffff;
    while(n--) { crc^=*b++; for(unsigned i=0;i<8;++i) crc=(crc>>1)^((crc&1)?0xedb88320:0); }
    return ~crc;
}
static uint32_t be32(const uint8_t *p)
{ return ((uint32_t)p[0]<<24)|((uint32_t)p[1]<<16)|((uint32_t)p[2]<<8)|p[3]; }
bool fast_capture_accept(fast_capture_receiver_t *r,const uint8_t *b,size_t n,
                         uint32_t began,uint32_t now,bridge_feedback_t *out)
{
    if(!r || !out) return false;
    memset(out,0,sizeof *out); /* Any failure invalidates every capture. */
    if(!b || n!=FAST_CAPTURE_BYTES || r->fault) goto fail;
    uint32_t seq=be32(b+8), age=be32(b+20), dt=now-began;
    if(be32(b)!=0x54464331 || b[4]!=1 || b[5]!=0x0f || b[6]!=0 || b[7]!=92 ||
       be32(b+12)!=80000000 || be32(b+88)!=fast_crc32(b,88) ||
       age>40000 || dt>200 || (r->seen && (uint32_t)(seq-r->sequence)!=1)) goto fail;
    for(unsigned i=0;i<4;++i) {
        out->period[i]=be32(b+24+4*i); out->high_ticks[i]=be32(b+40+4*i);
        out->rise_ticks[i]=be32(b+56+4*i); out->nonoverlap_ticks[i]=be32(b+72+4*i);
        if(out->period[i]<1332 || out->period[i]>2286 || !out->high_ticks[i] ||
           out->high_ticks[i]>=out->period[i] || out->rise_ticks[i]>=out->period[i] ||
           !out->nonoverlap_ticks[i] || out->nonoverlap_ticks[i]>=out->period[i]/4) goto fail;
        out->valid[i]=true;
    }
    r->seen=true; r->sequence=seq;
    out->serial=seq; out->sampled_us=began-(age+79)/80;
    return true;
fail: r->fault=true; memset(out,0,sizeof *out); return false;
}
