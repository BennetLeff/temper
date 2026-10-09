#ifndef R5_LINE_TELEMETRY_H
#define R5_LINE_TELEMETRY_H
#include "measurement.h"
#define R5_LINE_BYTES 28u
/* TLM1, sequence, cycle duration us, RMS mV, RMS mA, validity flags, CRC32.
   uint32 fields are big-endian; flags must equal 1. No remote clock assumption. */
typedef struct { uint32_t serial,received_us,duration_us;float volts,amps;bool seen,fault; } r5_line_receiver_t;
bool r5_line_encode(const r5_measurement_t *,uint8_t out[R5_LINE_BYTES]);
bool r5_line_receive(r5_line_receiver_t *,const uint8_t in[R5_LINE_BYTES],uint32_t now_us);
#endif
