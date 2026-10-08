#ifndef TEMPER_R5_FAST_CAPTURE_H
#define TEMPER_R5_FAST_CAPTURE_H
#include "fullbridge_adapter.h"
#include <stddef.h>
#define FAST_CAPTURE_BYTES 92u
/* FPGA data contract v1. All edge counters on ONE 80 MHz clock; not two MCPWM
   capture groups. Logic-level measurements do not certify physical Vgs/ZVS. */
typedef struct { uint32_t sequence; bool seen, fault; } fast_capture_receiver_t;
uint32_t fast_crc32(const uint8_t *, size_t);
bool fast_capture_accept(fast_capture_receiver_t *, const uint8_t *, size_t,
                         uint32_t transaction_start_us, uint32_t now_us, bridge_feedback_t *);
#endif
