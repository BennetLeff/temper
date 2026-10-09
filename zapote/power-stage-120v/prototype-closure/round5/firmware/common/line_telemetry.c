#include "line_telemetry.h"
#include "crc32.h"
#include <math.h>
#include <string.h>
static void put(uint8_t *p,uint32_t n) { p[0]=n>>24;p[1]=n>>16;p[2]=n>>8;p[3]=n; }
static uint32_t get(const uint8_t *p) { return (uint32_t)p[0]<<24|(uint32_t)p[1]<<16|(uint32_t)p[2]<<8|p[3]; }
bool r5_line_encode(const r5_measurement_t *s,uint8_t p[R5_LINE_BYTES])
{
    if(!s||!p||s->fault||!s->complete||!s->source_ok) return false;
    memcpy(p,"TLM1",4);put(p+4,s->serial);put(p+8,(uint32_t)llround(s->period*1e6));
    put(p+12,(uint32_t)llround(s->rms[0]*1000));put(p+16,(uint32_t)llround(s->rms[7]*1000));
    put(p+20,1);put(p+24,r5_crc32(p,24));return true;
}
bool r5_line_receive(r5_line_receiver_t *r,const uint8_t p[R5_LINE_BYTES],uint32_t now)
{
    if(!r||!p||r->fault) return false;
    uint32_t serial=get(p+4),duration=get(p+8),mv=get(p+12),ma=get(p+16);
    bool ok=!memcmp(p,"TLM1",4)&&get(p+24)==r5_crc32(p,24)&&get(p+20)==1&&
      duration>=15384&&duration<=22223&&mv>=100000&&mv<=140000&&ma<=15000&&
      (!r->seen||(serial-r->serial==1&&(uint32_t)(now-r->received_us)>=14000&&
                  (uint32_t)(now-r->received_us)<=25000));
    if(!ok) { r->fault=true;return false; }
    *r=(r5_line_receiver_t){serial,now,duration,mv*.001f,ma*.001f,true,false};return true;
}
