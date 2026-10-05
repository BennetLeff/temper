#include "fast_capture.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>
static void put(uint8_t *p,uint32_t u) { p[0]=u>>24;p[1]=u>>16;p[2]=u>>8;p[3]=u; }
static void make(uint8_t b[92],uint32_t seq)
{
    memset(b,0,92);put(b,0x54464331);b[4]=1;b[5]=15;b[7]=92;put(b+8,seq);put(b+12,80000000);
    put(b+20,16000);
    for(unsigned i=0;i<4;++i) { put(b+24+4*i,1600);put(b+40+4*i,790);put(b+56+4*i,10+(i%2)*800);put(b+72+4*i,10); }
    put(b+88,fast_crc32(b,88));
}
int main(void)
{
    assert(fast_crc32((const uint8_t *)"123456789",9)==0xcbf43926);
    uint8_t b[92];make(b,1); fast_capture_receiver_t r={0};bridge_feedback_t f;
    assert(fast_capture_accept(&r,b,92,1000,1100,&f)); assert(f.sampled_us==800 && f.valid[3]);
    assert(!fast_capture_accept(&r,b,92,1100,1200,&f)); assert(!f.valid[0]);
    for(unsigned byte=0;byte<92;++byte) for(unsigned bit=0;bit<8;++bit) {
        make(b,1);r=(fast_capture_receiver_t){0};b[byte]^=1u<<bit;
        assert(!fast_capture_accept(&r,b,92,1000,1100,&f));
    }
    make(b,1);put(b+12,40000000);put(b+88,fast_crc32(b,88));r=(fast_capture_receiver_t){0};
    assert(!fast_capture_accept(&r,b,92,1000,1100,&f));
    make(b,1);r=(fast_capture_receiver_t){0};assert(!fast_capture_accept(&r,b,92,1000,1201,&f));
    puts("PASS: capture CRC known vector, 736 corruptions, replay, wrong clock, read latency");
}
