#include "acquisition.h"
#include <assert.h>
#include <math.h>
#include <stdio.h>
#include <string.h>
static void seal(uint8_t f[30]) { uint16_t c=ads_crc16(f,27);f[27]=c>>8;f[28]=c; }
static void frame(uint8_t f[30]) { memset(f,0,30); f[0]=1; f[1]=255; uint16_t c=ads_crc16(f,27); f[27]=c>>8; f[28]=c; }
int main(void)
{
    assert(ads_crc16((const uint8_t *)"123456789",9)==0x29b1);
    uint8_t f[30];
    ads_command(0,0,f); assert(f[3]==0xcc && f[4]==0x9c && f[27]==0);
    ads_command(0x6100,0x3110,f); assert(f[3]==0x31 && f[4]==0x10);
    assert(((f[6]<<8)|f[7])==ads_crc16(f,6));
    frame(f); ads_receiver_t r={0}; ads_sample_t s;
    assert(ads_accept(&r,f,1000,1060,&s)); assert(s.serial==1); assert(ads_fresh(&r,2000)); assert(!ads_fresh(&r,2001));
    assert(ads_accept(&r,f,1256,1316,&s)); assert(!ads_accept(&r,f,1256,1316,&s));
    assert(!ads_accept(&r,f,1512,1572,&s));
    for (unsigned byte=0; byte<30; ++byte) for (unsigned bit=0; bit<8; ++bit) {
        frame(f); r=(ads_receiver_t){0}; f[byte]^=(uint8_t)(1u<<bit);
        assert(!ads_accept(&r,f,1000,1060,&s));
    }
    for(unsigned fault=2;fault<=6;++fault) {
        frame(f);f[0]|=1u<<fault;seal(f);r=(ads_receiver_t){0};
        assert(!ads_accept(&r,f,1000,1060,&s));
    }
    frame(f);f[3]=0x7f;f[4]=0xff;f[5]=0xff;seal(f);r=(ads_receiver_t){0};
    assert(!ads_accept(&r,f,1000,1060,&s));
    frame(f);f[3]=0xff;f[4]=0xff;f[5]=0xff;seal(f);r=(ads_receiver_t){0};
    assert(ads_accept(&r,f,1000,1060,&s));assert(s.code[0]==-1);
    assert(!ads_accept(&r,f,1400,1460,&s));
    frame(f); r=(ads_receiver_t){0}; assert(!ads_accept(&r,f,1000,1201,&s));
    frame(f); r=(ads_receiver_t){0}; assert(ads_accept(&r,f,0xffffff00u,0xffffff40u,&s));
    assert(ads_accept(&r,f,0,60,&s));
    post_record_t p={0}; assert(!post_record_accept(&p,1,1,0,NAN,10,12,1,1,1));
    assert(post_record_accept(&p,1,1,0,11,10,12,1,1,1)); assert(post_record_fresh(&p,1,60000));
    assert(!post_record_fresh(&p,2,100)); post_record_consume(&p); assert(!post_record_fresh(&p,1,100));
    assert(!post_record_accept(&p,1,1,100,11,10,12,1,1,1));
    assert(post_record_accept(&p,1,2,100,11,10,12,1,1,1));
    assert(!catch_correlates(170,0,5,2,1,1)); assert(catch_correlates(170,168,5,2,1,1));
    assert(!catch_correlates(170,168,5,2,0,1)); assert(!catch_correlates(170,168,5,2,1,0));
    puts("PASS: CRC known vector, 240 bit corruptions, duplicate/gap/latency/wrap, POST lifetime, catch correlation");
}
