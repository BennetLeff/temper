/**
 * @file test_emc2301.c
 * @brief EMC2301 face-fan driver against a register model of the part's watchdog (DS20006532A 4.11).
 */
#include <stdio.h>
#include <string.h>

#include "unity/unity.h"

#include "../components/hal/include/emc2301.h"

/* ------------------------------------------------------------------ part model */
static struct {
    uint8_t reg[256];
    bool pu_wd;          /* power-up one-shot watchdog still armed (4.11.1) */
    bool expired;        /* fan held at 100 % until Fan Setting is written */
    uint32_t now_ms, last_access_ms;
    bool fail_reads, fail_writes;
    uint8_t stuck_reg;   /* writes to this register are ignored (0 = none) */
    uint8_t writes[64];  /* register of every write, in order */
    unsigned n_writes;
    uint8_t reads[64];
    unsigned n_reads;
} m;

static void model_por(void)
{
    memset(m.reg, 0, sizeof m.reg);
    m.reg[EMC2301_REG_CONFIG] = 0x40;
    m.reg[EMC2301_REG_FAN_CONFIG1] = 0x2B;
    m.reg[EMC2301_REG_TACH_HIGH] = 0xFF;
    m.reg[EMC2301_REG_TACH_LOW] = 0xF8;
    m.reg[EMC2301_REG_PRODUCT_ID] = EMC2301_PRODUCT_ID;
    m.reg[EMC2301_REG_MFR_ID] = EMC2301_MFR_ID;
    m.pu_wd = true;
    m.expired = false;
    m.last_access_ms = m.now_ms;
}

static void model_reset(void)
{
    memset(&m, 0, sizeof m);
    model_por();
}

static void advance(uint32_t ms)
{
    m.now_ms += ms;
    bool armed = m.pu_wd || (m.reg[EMC2301_REG_CONFIG] & EMC2301_CONFIG_WD_EN);
    if (armed && !m.expired && m.now_ms - m.last_access_ms >= 4000u) {
        m.expired = true;
        m.pu_wd = false;
        m.reg[EMC2301_REG_FAN_STATUS] |= EMC2301_STATUS_WATCH;
    }
}

/* The duty the fan actually sees, 0..255. */
static uint8_t fan_duty(void)
{
    return m.expired ? 0xFF : m.reg[EMC2301_REG_FAN_SETTING];
}

static bool rd(void *ctx, uint8_t reg, uint8_t *v)
{
    (void)ctx;
    if (m.fail_reads) return false;
    m.last_access_ms = m.now_ms;
    if (m.n_reads < sizeof m.reads) m.reads[m.n_reads++] = reg;
    *v = m.reg[reg];
    if (reg == EMC2301_REG_FAN_STATUS) m.reg[reg] = 0; /* read-then-clear */
    return true;
}

static bool wr(void *ctx, uint8_t reg, uint8_t v)
{
    (void)ctx;
    if (m.fail_writes) return false;
    m.last_access_ms = m.now_ms;
    if (m.n_writes < sizeof m.writes) m.writes[m.n_writes++] = reg;
    if (reg == m.stuck_reg) return true;
    m.reg[reg] = v;
    if (reg == EMC2301_REG_FAN_SETTING) {
        m.pu_wd = false;
        m.expired = false;
    }
    return true;
}

static const emc2301_ops_t ops = {.read = rd, .write = wr, .ctx = NULL};

static int first_write(uint8_t reg)
{
    for (unsigned i = 0; i < m.n_writes; i++)
        if (m.writes[i] == reg) return (int)i;
    return -1;
}

void setUp(void) { model_reset(); }
void tearDown(void) {}

/* ------------------------------------------------------------------ tests */
static void test_init_arms_watchdog_before_the_first_drive_write(void)
{
    model_reset();
    TEST_ASSERT_EQUAL(EMC2301_OK, emc2301_init(&ops, 0x80));
    TEST_ASSERT_TRUE(m.reg[EMC2301_REG_CONFIG] & EMC2301_CONFIG_WD_EN);
    TEST_ASSERT_TRUE(first_write(EMC2301_REG_CONFIG) >= 0);
    TEST_ASSERT_TRUE(first_write(EMC2301_REG_CONFIG) < first_write(EMC2301_REG_FAN_SETTING));
    TEST_ASSERT_EQUAL_HEX8(0x80, fan_duty());
    TEST_ASSERT_EQUAL_HEX8(0, m.reg[EMC2301_REG_CONFIG] & EMC2301_CONFIG_MASK); /* ALERT# reaches P17 */
}

static void test_wrong_id_writes_nothing_and_the_part_goes_full(void)
{
    model_reset();
    m.reg[EMC2301_REG_PRODUCT_ID] = 0x36; /* EMC2302 */
    TEST_ASSERT_EQUAL(EMC2301_ERR_ID, emc2301_init(&ops, 0x40));
    TEST_ASSERT_EQUAL_UINT(0, m.n_writes);
    advance(4000);
    TEST_ASSERT_EQUAL_HEX8(0xFF, fan_duty());
}

static void test_bus_failure_is_reported(void)
{
    model_reset();
    m.fail_reads = true;
    TEST_ASSERT_EQUAL(EMC2301_ERR_BUS, emc2301_init(&ops, 0x40));
    model_reset();
    m.fail_writes = true;
    TEST_ASSERT_EQUAL(EMC2301_ERR_BUS, emc2301_init(&ops, 0x40));
}

static void test_config_that_does_not_hold_is_a_readback_error(void)
{
    model_reset();
    m.stuck_reg = EMC2301_REG_CONFIG;
    TEST_ASSERT_EQUAL(EMC2301_ERR_READBACK, emc2301_init(&ops, 0x40));
    TEST_ASSERT_EQUAL(-1, first_write(EMC2301_REG_FAN_SETTING)); /* no drive without the watchdog */
}

static void test_push_pull_inverted_or_rpm_mode_is_corrected(void)
{
    model_reset();
    m.reg[EMC2301_REG_PWM_OUTPUT] = EMC2301_FAN1_BIT;
    m.reg[EMC2301_REG_PWM_POL] = EMC2301_FAN1_BIT;
    m.reg[EMC2301_REG_FAN_CONFIG1] |= EMC2301_FANCFG1_ENAG;
    TEST_ASSERT_EQUAL(EMC2301_OK, emc2301_init(&ops, 0x40));
    TEST_ASSERT_EQUAL_HEX8(0, m.reg[EMC2301_REG_PWM_OUTPUT] & EMC2301_FAN1_BIT);
    TEST_ASSERT_EQUAL_HEX8(0, m.reg[EMC2301_REG_PWM_POL] & EMC2301_FAN1_BIT);
    TEST_ASSERT_EQUAL_HEX8(0, m.reg[EMC2301_REG_FAN_CONFIG1] & EMC2301_FANCFG1_ENAG);
    model_reset();
    m.reg[EMC2301_REG_PWM_OUTPUT] = EMC2301_FAN1_BIT;
    m.stuck_reg = EMC2301_REG_PWM_OUTPUT;
    TEST_ASSERT_EQUAL(EMC2301_ERR_READBACK, emc2301_init(&ops, 0x40));
}

static void test_serviced_part_holds_its_drive(void)
{
    model_reset();
    TEST_ASSERT_EQUAL(EMC2301_OK, emc2301_init(&ops, 0x60));
    emc2301_poll_t p;
    for (int i = 0; i < 20; i++) {
        advance(EMC2301_SERVICE_PERIOD_MS);
        TEST_ASSERT_EQUAL(EMC2301_OK, emc2301_service(&ops, 0x60, &p));
        TEST_ASSERT_FALSE(p.watchdog_expired);
        TEST_ASSERT_EQUAL_HEX8(0x60, fan_duty());
    }
}

static void test_missed_service_goes_full_then_is_reprogrammed(void)
{
    model_reset();
    TEST_ASSERT_EQUAL(EMC2301_OK, emc2301_init(&ops, 0x60));
    advance(4000); /* MCU hang */
    TEST_ASSERT_EQUAL_HEX8(0xFF, fan_duty());
    emc2301_poll_t p;
    TEST_ASSERT_EQUAL(EMC2301_OK, emc2301_service(&ops, 0x60, &p));
    TEST_ASSERT_TRUE(p.watchdog_expired);
    TEST_ASSERT_EQUAL_HEX8(0x60, fan_duty());
}

static void test_part_reset_is_reinitialised(void)
{
    model_reset();
    TEST_ASSERT_EQUAL(EMC2301_OK, emc2301_init(&ops, 0x60));
    model_por(); /* v3v3 dip resets the part: WD_EN clear, setting 0 */
    emc2301_poll_t p;
    TEST_ASSERT_EQUAL(EMC2301_OK, emc2301_service(&ops, 0x60, &p));
    TEST_ASSERT_TRUE(m.reg[EMC2301_REG_CONFIG] & EMC2301_CONFIG_WD_EN);
    TEST_ASSERT_EQUAL_HEX8(0x60, fan_duty());
}

static void test_new_drive_is_written_and_tach_read_high_first(void)
{
    model_reset();
    TEST_ASSERT_EQUAL(EMC2301_OK, emc2301_init(&ops, 0x60));
    m.reg[EMC2301_REG_TACH_HIGH] = 0x12;
    m.reg[EMC2301_REG_TACH_LOW] = 0xA8;
    m.n_reads = 0;
    emc2301_poll_t p;
    TEST_ASSERT_EQUAL(EMC2301_OK, emc2301_service(&ops, EMC2301_DRIVE_FULL, &p));
    TEST_ASSERT_EQUAL_HEX8(0xFF, fan_duty());
    TEST_ASSERT_EQUAL_HEX8(0xFF, p.drive);
    TEST_ASSERT_EQUAL_UINT16((0x12u << 5) | (0xA8u >> 3), p.tach_count);
    int hi = -1, lo = -1;
    for (unsigned i = 0; i < m.n_reads; i++) {
        if (m.reads[i] == EMC2301_REG_TACH_HIGH && hi < 0) hi = (int)i;
        if (m.reads[i] == EMC2301_REG_TACH_LOW && lo < 0) lo = (int)i;
    }
    TEST_ASSERT_TRUE(hi >= 0 && hi < lo);
}

static void test_status_flags_are_reported(void)
{
    model_reset();
    TEST_ASSERT_EQUAL(EMC2301_OK, emc2301_init(&ops, 0x60));
    m.reg[EMC2301_REG_FAN_STATUS] = EMC2301_STATUS_DVFAIL | EMC2301_STATUS_FNSPIN | EMC2301_STATUS_FNSTL;
    emc2301_poll_t p;
    TEST_ASSERT_EQUAL(EMC2301_OK, emc2301_service(&ops, 0x60, &p));
    TEST_ASSERT_TRUE(p.drive_fail && p.spin_fail && p.stall_untrusted);
    TEST_ASSERT_FALSE(p.watchdog_expired);
}

static void test_service_bus_failure_leaves_the_part_to_its_watchdog(void)
{
    model_reset();
    TEST_ASSERT_EQUAL(EMC2301_OK, emc2301_init(&ops, 0x30));
    m.fail_reads = m.fail_writes = true;
    emc2301_poll_t p;
    for (int i = 0; i < 4; i++) {
        advance(EMC2301_SERVICE_PERIOD_MS);
        TEST_ASSERT_EQUAL(EMC2301_ERR_BUS, emc2301_service(&ops, 0x30, &p));
    }
    TEST_ASSERT_EQUAL_HEX8(0xFF, fan_duty());
}

int main(void)
{
    UnityBegin("test_emc2301.c");
    printf("\n=== EMC2301 face-fan driver ===\n\n");
    RUN_TEST(test_init_arms_watchdog_before_the_first_drive_write);
    RUN_TEST(test_wrong_id_writes_nothing_and_the_part_goes_full);
    RUN_TEST(test_bus_failure_is_reported);
    RUN_TEST(test_config_that_does_not_hold_is_a_readback_error);
    RUN_TEST(test_push_pull_inverted_or_rpm_mode_is_corrected);
    RUN_TEST(test_serviced_part_holds_its_drive);
    RUN_TEST(test_missed_service_goes_full_then_is_reprogrammed);
    RUN_TEST(test_part_reset_is_reinitialised);
    RUN_TEST(test_new_drive_is_written_and_tach_read_high_first);
    RUN_TEST(test_status_flags_are_reported);
    RUN_TEST(test_service_bus_failure_leaves_the_part_to_its_watchdog);
    return UnityEnd();
}
