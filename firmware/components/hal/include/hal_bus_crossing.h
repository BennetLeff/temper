#ifndef TEMPER_HAL_BUS_CROSSING_H
#define TEMPER_HAL_BUS_CROSSING_H
#include <stdbool.h>
#include <stdint.h>
/* Controller adapter. sampled_us is the acquisition timestamp, not the time
 * this record was read. zero_crossing is a one-shot LINE zero-crossing event
 * (centre of the native-21 LINE_ZC pulse on J4.16), never the tank-current
 * CT_ZC and never derived from VBUS: with the bridge idle the film bus
 * capacitors hold the line peak, and at burst power the bus valley sits tens
 * of volts above zero (DECISIONS 2026-10-06). An adapter must set
 * from_line_zc only when the event comes from LINE_ZC; the scheduler refuses
 * any other crossing source. bus_v (calibrated VBUS_P/N) is informational.
 */
typedef struct {
    uint64_t sampled_us;
    float bus_v;
    bool valid, zero_crossing, from_line_zc;
} hal_bus_crossing_t;
#endif
