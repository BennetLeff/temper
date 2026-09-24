#include "avr64da32_boot_contract.h"

bool pe_avr_boot_fuses_ok(pe_avr_fuses_t actual, pe_avr_fuses_t expected) {
    /* AVR64DA32 FUSE.SYSCFG0 has RSTPINCFG[3:2]=0b10 for external RESET
     * on PF6 and EESAVE[0]=1. Bits 4 and 1 are reserved. PF7 UPDI is a
     * dedicated package pin, not a SYSCFG0 bit on this device. */
    if ((expected.syscfg0 & 0x1fu) != 0x09u) return false;

    /* FUSE.BODCFG: LVL[7:5] is 0..3; ACTIVE[3:2] selects continuous
     * mode and SLEEP[1:0]=1 keeps BOD continuous during sleep. The
     * threshold remains an electrical review input. */
    uint8_t active = (expected.bodcfg >> 2) & 0x03u;
    if ((expected.bodcfg >> 5) > 3u || (active != 1u && active != 3u) ||
        (expected.bodcfg & 0x03u) != 0x01u)
        return false;

    /* FUSE.OSCCFG selects OSCHF=0. FUSE.WDTCFG is deliberately restricted
     * to a non-windowed period 1..11; the actual period needs timing review. */
    if (expected.osccfg != 0u || expected.wdtcfg < 1u ||
        expected.wdtcfg > 11u) return false;

    return actual.wdtcfg == expected.wdtcfg &&
           actual.bodcfg == expected.bodcfg &&
           actual.osccfg == expected.osccfg &&
           actual.syscfg0 == expected.syscfg0;
}
