#include "fast_capture.h"
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
static void be32(uint8_t *p,uint32_t x) {
 p[0]=(uint8_t)(x>>24);p[1]=(uint8_t)(x>>16);p[2]=(uint8_t)(x>>8);p[3]=(uint8_t)x;
}
static void seal(uint8_t *p) {be32(p+88,fast_crc32(p,88));}
static void reject(const uint8_t *p,uint32_t began,uint32_t now) {
 fast_capture_receiver_t r={0}; bridge_feedback_t f;
 assert(!fast_capture_accept(&r,p,92,began,now,&f)); assert(r.fault);
 for(unsigned i=0;i<4;i++) assert(!f.valid[i]);
}
int main(int argc,char **argv) {
 assert(argc==2); FILE *fp=fopen(argv[1],"r"); assert(fp);
 fast_capture_receiver_t r={0}; bridge_feedback_t f;
 uint8_t p[92],last[92]; unsigned count=0; char line[200];
 assert(fast_crc32((const uint8_t*)"123456789",9)==0xcbf43926u);
 while(fgets(line,sizeof line,fp)) {
  assert(strlen(line)==185);
  for(unsigned i=0;i<92;i++) {char hex[3]={line[i*2],line[i*2+1],0};p[i]=(uint8_t)strtoul(hex,NULL,16);}
  uint32_t now=1000000u+count*250u;
  assert(fast_capture_accept(&r,p,92,now,now+75,&f));
  assert(f.sampled_us==now-500);
  unsigned shift=count<14?400:(count==14?0:(count==15?800:799));
  bridge_cycle_t c;
  assert(bridge_plan_cycle(80000000,50000,400,(float)shift/800,&c));
  for(unsigned i=0;i<4;i++) {
   assert(f.valid[i]);assert(f.period[i]==c.period);
   assert(f.high_ticks[i]==c.pulse[i].width);
   assert(f.rise_ticks[i]==c.pulse[i].rise);
   assert(f.nonoverlap_ticks[i]==c.dead_ticks);
  }
  memcpy(last,p,92); count++;
 }
 fclose(fp); assert(count==18);
 // Every single-byte payload/CRC corruption must reject and latch.
 for(unsigned i=0;i<92;i++) {memcpy(p,last,92);p[i]^=1;reject(p,1000,1075);}
 memcpy(p,last,92);p[5]=0;seal(p);reject(p,1000,1075);
 memcpy(p,last,92);be32(p+20,40001);seal(p);reject(p,1000,1075);
 memcpy(p,last,92);be32(p+12,79999999);seal(p);reject(p,1000,1075);
 memcpy(p,last,92);be32(p+24,2287);seal(p);reject(p,1000,1075);
 memcpy(p,last,92);be32(p+40,0);seal(p);reject(p,1000,1075);
 memcpy(p,last,92);be32(p+56,1600);seal(p);reject(p,1000,1075);
 memcpy(p,last,92);be32(p+72,0);seal(p);reject(p,1000,1075);
 reject(last,1000,1201);
 assert(!fast_capture_accept(&r,last,92,1000,1075,&f));assert(r.fault);
 // Persistent receiver fault cannot be cleared by a subsequent good packet.
 be32(last+8,r.sequence+1);seal(last);
 assert(!fast_capture_accept(&r,last,92,1000,1075,&f));
 r=(fast_capture_receiver_t){0};be32(last+8,UINT32_MAX);seal(last);
 assert(fast_capture_accept(&r,last,92,UINT32_MAX-20,54,&f));
 be32(last+8,0);seal(last);assert(fast_capture_accept(&r,last,92,1000,1075,&f));
 puts("PASS C oracle: 18 real RTL frames match receiver and bridge planner; 92 corruption positions, invalid fields, time/sequence wrap, repeated sequence and fault latch");
}
