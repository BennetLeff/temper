#ifndef TEMPER_POWER_ENTRY_PROTOCOL_H
#define TEMPER_POWER_ENTRY_PROTOCOL_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

/* All multibyte integers are little endian. The 20-byte frame has no padding. */
#define PE_FRAME_SIZE 20u
#define PE_FRAME_MAGIC 0xA5u
#define PE_FRAME_VERSION 1u

typedef enum {
    PE_PREPARE_CHALLENGE = 1,
    PE_DISARM_ACK = 2,
    PE_READY = 3,
    PE_REQUEST = 4,
    PE_ACK = 5,
    PE_START = 6,
    PE_STOP = 7,
    PE_PING = 8,
    PE_PONG = 9,
    PE_ABORT = 10,
} pe_frame_type_t;

typedef struct {
    pe_frame_type_t type;
    uint64_t session;
    uint32_t value;
} pe_frame_t;

/* CRC-32/ISO-HDLC over bytes 0..15: reflected poly 0xEDB88320,
 * initial/final XOR 0xFFFFFFFF. Bytes 16..19 carry the CRC little endian. */
uint32_t pe_crc32(const uint8_t *data, size_t length);
void pe_frame_encode(const pe_frame_t *frame, uint8_t out[PE_FRAME_SIZE]);
bool pe_frame_decode(const uint8_t *data, size_t length, pe_frame_t *frame);

typedef struct {
    uint8_t bytes[PE_FRAME_SIZE];
    uint8_t count;
    uint64_t last_byte_ms;
    uint32_t max_gap_ms;
} pe_stream_t;

void pe_stream_init(pe_stream_t *stream, uint32_t max_gap_ms);
/* Returns true only for a complete valid frame. Malformed frames cannot
 * count as link progress. The caller must supply monotonic time. */
bool pe_stream_push(pe_stream_t *stream, uint8_t byte, uint64_t now_ms,
                    pe_frame_t *frame);

#endif
