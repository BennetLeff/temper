#ifndef R5_CRC32_H
#define R5_CRC32_H
#include <stdint.h>
#include <stddef.h>
static inline uint32_t r5_crc32(const uint8_t *b,size_t n)
{
    uint32_t crc=0xffffffff;
    while(n--) { crc^=*b++;for(unsigned i=0;i<8;++i) crc=(crc>>1)^((crc&1)?0xedb88320:0); }
    return ~crc;
}
#endif
