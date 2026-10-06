#ifndef TEMPER_HAL_BUS_CROSSING_H
#define TEMPER_HAL_BUS_CROSSING_H
#include <stdbool.h>
#include <stdint.h>
/* Controller adapter: calibrated VBUS_P/N via AMC1311/OPA2388 on ADC1.
 * sampled_us is the acquisition timestamp, not the time this record was read.
 * zero_crossing is a one-shot event from the controller's line-zero logic,
 * never the tank-current CT_ZC. The scheduler checks freshness and bus voltage.
 */
typedef struct {
    uint64_t sampled_us;
    float bus_v;
    bool valid, zero_crossing;
} hal_bus_crossing_t;
#endif
