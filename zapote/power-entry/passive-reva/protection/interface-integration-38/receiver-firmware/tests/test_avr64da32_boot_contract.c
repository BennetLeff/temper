#include "../avr64da32_boot_contract.h"

#include <assert.h>

int main(void) {
    /* Example bytes exercise bit decoding; they are not approved fuses. */
    pe_avr_fuses_t expected = {0x08, 0x65, 0x00, 0xC9};
    assert(pe_avr_boot_fuses_ok(expected, expected));
    assert(!pe_avr_boot_fuses_ok(expected, (pe_avr_fuses_t){0}));

    pe_avr_fuses_t changed = expected;
    changed.syscfg0 &= (uint8_t)~0x08; /* PF6 no longer RESET */
    assert(!pe_avr_boot_fuses_ok(changed, expected));
    changed = expected;
    changed.syscfg0 |= 0x10; /* reserved bit, not PF7 UPDI */
    assert(!pe_avr_boot_fuses_ok(changed, expected));
    changed = expected;
    changed.syscfg0 &= (uint8_t)~0x01; /* chip erase loses journal */
    assert(!pe_avr_boot_fuses_ok(changed, expected));
    changed = expected;
    changed.bodcfg &= (uint8_t)~0x0C; /* no continuous BOD */
    assert(!pe_avr_boot_fuses_ok(changed, expected));
    changed = expected;
    changed.osccfg = 0x01; /* wrong clock source */
    assert(!pe_avr_boot_fuses_ok(changed, expected));
    changed = expected;
    changed.wdtcfg = 0x00; /* internal WDT disabled */
    assert(!pe_avr_boot_fuses_ok(changed, expected));

    changed = expected;
    changed.bodcfg &= (uint8_t)~0x0C;
    assert(!pe_avr_boot_fuses_ok(changed, changed));
    changed = expected;
    changed.wdtcfg = 0x00;
    assert(!pe_avr_boot_fuses_ok(changed, changed));
    changed = expected;
    changed.wdtcfg = 0x0C; /* reserved WDT period */
    assert(!pe_avr_boot_fuses_ok(changed, changed));
    changed = expected;
    changed.bodcfg |= 0x03; /* reserved BOD sleep mode */
    assert(!pe_avr_boot_fuses_ok(changed, changed));
    changed = expected;
    changed.bodcfg &= (uint8_t)~0x03; /* sleep BOD disabled */
    assert(!pe_avr_boot_fuses_ok(changed, changed));
    changed = expected;
    changed.bodcfg = (uint8_t)((changed.bodcfg & ~0x03u) | 0x02u);
    assert(!pe_avr_boot_fuses_ok(changed, changed)); /* sampled in sleep */
    changed = expected;
    changed.syscfg0 &= (uint8_t)~0x08;
    assert(!pe_avr_boot_fuses_ok(changed, changed));
    changed = expected;
    changed.syscfg0 |= 0x02; /* reserved SYSCFG0 bit */
    assert(!pe_avr_boot_fuses_ok(changed, changed));
    changed = expected;
    changed.syscfg0 |= 0x04; /* reserved RSTPINCFG encoding 0b11 */
    assert(!pe_avr_boot_fuses_ok(changed, changed));
    return 0;
}
