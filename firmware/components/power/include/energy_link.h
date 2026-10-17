#ifndef TEMPER_ENERGY_LINK_H
#define TEMPER_ENERGY_LINK_H
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#define ENERGY_LINK_SIZE 20u
#define ENERGY_LINK_COMMAND 1u
#define ENERGY_LINK_STATUS 2u
#define ENERGY_LINK_REQUEST 1u
#define ENERGY_LINK_RAIL_OK 2u
#define ENERGY_LINK_FAULT 4u
/* Transport carries intent/diagnostics only. Dedicated hardware RUN_OK, fault
 * and changing-heartbeat wires still qualify gates independently. */
typedef struct {
    uint8_t kind, state;
    uint16_t flags;
    uint32_t sequence, requested_mw;
} energy_link_packet_t;
typedef struct {
    bool seen;
    uint32_t sequence, received_ms;
} energy_link_receiver_t;
bool energy_link_encode(const energy_link_packet_t *, uint8_t out[ENERGY_LINK_SIZE]);
bool energy_link_receive(energy_link_receiver_t *, uint8_t expected_kind,
                         const uint8_t *bytes, size_t size, uint32_t now_ms,
                         energy_link_packet_t *out);
bool energy_link_fresh(const energy_link_receiver_t *, uint32_t now_ms);
#endif
