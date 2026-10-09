#ifndef TEMPER_R5_ACQUISITION_H
#define TEMPER_R5_ACQUISITION_H
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#define ADS_FRAME_BYTES 30u
/* Status + eight signed 24-bit samples + 16-bit CRC padded to 24 bits. */
typedef struct { int32_t code[8]; uint32_t captured_us, serial; } ads_sample_t;
typedef struct { uint32_t serial, captured_us; bool seen, fault; } ads_receiver_t;
uint16_t ads_crc16(const uint8_t *, size_t);
void ads_command(uint16_t command, uint16_t data, uint8_t out[ADS_FRAME_BYTES]);
bool ads_accept(ads_receiver_t *, const uint8_t frame[ADS_FRAME_BYTES], uint32_t drdy_us,
                uint32_t read_us, ads_sample_t *);
/* Clears only during cold boot/startup; runtime failure is latched. */
bool ads_fresh(const ads_receiver_t *, uint32_t now_us);
typedef struct { float ohm, uncertainty_ohm; bool isolated_four_wire; } post_branch_t;
typedef struct {
    uint32_t boot_nonce, serial, issued_ms;
    post_branch_t branch[2];
    bool valid;
} post_record_t;
bool post_record_accept(post_record_t *, uint32_t boot_nonce, uint32_t serial,
                        uint32_t now_ms, const post_branch_t branch[2],
                        bool contacts_released, bool discharged, bool operator_confirmed,
                        bool cold_equilibrium_documented);
bool post_record_fresh(const post_record_t *, uint32_t boot_nonce, uint32_t now_ms);
void post_record_consume(post_record_t *);
/* Synchronous ADC channels; tolerance is explicit and not factory calibrated. */
bool catch_correlates(float bus_v, float catch_v, float error_v, float diode_max_v,
                      bool qualified_gain, bool charging_observed);
#endif
