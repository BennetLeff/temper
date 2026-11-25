/* C51 food-probe RTD service (U50 on the shared RTD SPI bus, CS# = TCA9555 P06): the bus discipline and
 * the unplug / open-lead / stale-config behaviour, against a register model of the MAX31865 and a link
 * that checks every hold. Assertions are the oracle (built with -UNDEBUG). */
#include "rtd_food_service.h"
#include "max31865.h"
#include <assert.h>
#include <math.h>
#include <stdio.h>
#include <string.h>

#define NEAR(a, b, tol) (fabs((double)(a) - (double)(b)) <= (tol))
#define TICK_US 100000ull

typedef struct {
    /* link */
    bool locked, selected;
    int locks_this_tick, select_fail, deselect_fail, xfer_fail;
    unsigned violations, xfers, locks;
    /* MAX31865 model */
    uint8_t config, fault_status;
    bool stepped1, plugged, input_fault, converting;
    uint16_t code;
    uint64_t now, step_t[3]; /* times of BIAS_CLEAR, STEP1, STEP2 writes */
} fake_t;

static fake_t F;

static bool f_lock(void *c) { (void)c; if (F.locked) F.violations++; F.locked = true; F.locks++; F.locks_this_tick++; return true; }
static void f_unlock(void *c)
{
    (void)c;
    if (!F.locked) F.violations++;
    if (F.selected) F.violations++; /* released the bus with U50 selected */
    F.locked = false;
}
static bool f_select(void *c, bool sel)
{
    (void)c;
    if (!F.locked) F.violations++;
    if (sel && F.select_fail) { F.select_fail--; return false; }
    if (!sel && F.deselect_fail) { F.deselect_fail--; return false; }
    F.selected = sel;
    return true;
}

static void model_write(uint8_t reg, uint8_t v)
{
    if (reg != MAX31865_REG_CONFIG) return;
    if (v == MAX31865_CONFIG_BIAS_CLEAR) { F.fault_status = 0; F.config = MAX31865_CONFIG_BIAS_ON; F.converting = false; F.step_t[0] = F.now; return; }
    if (v == MAX31865_CONFIG_MANUAL_STEP1) { F.stepped1 = true; F.config = v; F.step_t[1] = F.now; return; }
    if (v == MAX31865_CONFIG_MANUAL_STEP2) {
        F.step_t[2] = F.now;
        if (F.stepped1) F.fault_status = F.plugged ? (F.input_fault ? MAX31865_FAULT_RTDIN_LOW : 0) : MAX31865_FAULT_REFIN_HIGH;
        F.stepped1 = false;
        F.config = MAX31865_CONFIG_BIAS_ON; /* D3:D2 read 00: cycle done */
        return;
    }
    F.config = v;
    F.converting = v == MAX31865_CONFIG_CONVERTING;
}

static uint8_t model_read(uint8_t reg)
{
    uint16_t word = (uint16_t)((F.plugged ? F.code : 32767u) << 1);
    switch (reg) {
    case MAX31865_REG_CONFIG: return F.config;
    case MAX31865_REG_RTD_MSB: return (uint8_t)(word >> 8);
    case MAX31865_REG_RTD_MSB + 1: return (uint8_t)word;
    case MAX31865_REG_FAULT_STATUS: return F.fault_status;
    default: return 0;
    }
}

static bool f_xfer(void *c, const uint8_t *tx, uint8_t *rx, size_t n)
{
    (void)c;
    if (!F.locked || !F.selected) F.violations++;
    F.xfers++;
    if (F.xfer_fail) { F.xfer_fail--; return false; }
    uint8_t a = tx[0];
    if (a & 0x80u) {
        for (size_t i = 1; i < n; i++) model_write((uint8_t)((a & 0x7Fu) + i - 1), tx[i]);
    } else {
        rx[0] = 0;
        for (size_t i = 1; i < n; i++) rx[i] = model_read((uint8_t)(a + i - 1));
    }
    return true;
}

static rtd_food_service_t S;

static void reset(void)
{
    memset(&F, 0, sizeof F);
    F.plugged = true;
    F.code = (uint16_t)lround(0.28784 * 32768.0); /* 60 C, from the controller's rtd_food() */
    rtd_food_link_t link = {.bus_lock = f_lock, .bus_unlock = f_unlock, .select = f_select, .xfer = f_xfer, .ctx = NULL};
    rtd_food_params_t p;
    rtd_food_default_params(&p);
    rtd_food_service_init(&S, &link, &p);
}

static void run_ms(unsigned ms)
{
    for (unsigned t = 0; t < ms; t += 100) {
        F.now += TICK_US;
        F.locks_this_tick = 0;
        rtd_food_service_tick(&S, F.now);
        assert(F.locks_this_tick <= 1); /* one short hold per tick: never a wait inside it */
        assert(!F.locked);
    }
}

/* The waits must hold whatever the caller's tick: run the cycle with a 1 ms tick. */
static void test_fault_cycle_waits_at_a_fast_tick(void)
{
    reset();
    for (unsigned i = 0; i < 400; i++) {
        F.now += 1000u;
        F.locks_this_tick = 0;
        rtd_food_service_tick(&S, F.now);
        assert(F.locks_this_tick <= 1 && !F.locked);
    }
    assert(F.step_t[0] && F.step_t[1] && F.step_t[2]);
    assert(F.step_t[1] - F.step_t[0] >= RTD_FOOD_STEP_US && F.step_t[2] - F.step_t[1] >= RTD_FOOD_STEP_US);
    assert(F.converting && F.violations == 0);
}

static rtd_food_state_t state(float *t)
{
    float x = -1.0f;
    rtd_food_state_t s = rtd_food_service_state(&S, &x);
    if (t) *t = x;
    return s;
}

static void test_startup_runs_the_manual_fault_cycle_then_reads(void)
{
    reset();
    float t;
    assert(state(&t) == RTD_FOOD_NO_READING && isnan(t));
    run_ms(1200);
    assert(F.step_t[1] - F.step_t[0] >= RTD_FOOD_STEP_US && F.step_t[2] - F.step_t[1] >= RTD_FOOD_STEP_US);
    assert(state(&t) == RTD_FOOD_OK && NEAR(t, 60.0, 0.05));
    assert(F.violations == 0);
    /* 5 Hz at most once converting */
    unsigned x0 = F.xfers;
    run_ms(10000);
    printf("  reads in 10 s: %u\n", F.xfers - x0);
    assert(F.xfers - x0 <= 10000u / (RTD_FOOD_READ_PERIOD_US / 1000u) + 1u && F.xfers - x0 >= 40u);
    assert(F.violations == 0);
}

static void test_unplug_and_replug(void)
{
    reset();
    run_ms(1200);
    F.plugged = false;
    run_ms(1500);
    float t;
    assert(state(&t) == RTD_FOOD_UNPLUGGED && isnan(t));
    F.plugged = true;
    run_ms(2500);
    assert(state(&t) == RTD_FOOD_OK && NEAR(t, 60.0, 0.05));
    assert(F.violations == 0);
}

static void test_open_lead_and_input_fault(void)
{
    reset();
    run_ms(1200);
    F.code = (uint16_t)lround(0.60 * 32768.0); /* one sense lead open: drifted out of the window */
    run_ms(1500);
    assert(state(NULL) == RTD_FOOD_OPEN_LEAD);
    F.code = (uint16_t)lround(0.28784 * 32768.0);
    F.input_fault = true;
    run_ms(2500);
    assert(state(NULL) == RTD_FOOD_INPUT_FAULT);
    F.input_fault = false;
    run_ms(2500);
    assert(state(NULL) == RTD_FOOD_OK);
}

static void test_stale_config_is_never_a_temperature(void)
{
    /* A reset or corrupted U50 stops converting; its data register keeps the last value. */
    reset();
    run_ms(1200);
    F.config = 0x00;
    F.converting = false;
    run_ms(300);
    assert(state(NULL) != RTD_FOOD_OK);
    run_ms(2500); /* the service re-runs the cycle and restarts conversions */
    assert(state(NULL) == RTD_FOOD_OK && F.converting);
}

static void test_link_failures_release_the_bus_deselected(void)
{
    reset();
    run_ms(1200);
    F.select_fail = 1;
    run_ms(300);
    F.xfer_fail = 1;
    run_ms(300);
    assert(F.violations == 0);
    run_ms(2500);
    assert(state(NULL) == RTD_FOOD_OK);
    /* One failed deselect: retried at once, inside the same hold. */
    F.deselect_fail = 1;
    run_ms(300);
    assert(F.violations == 0 && state(NULL) == RTD_FOOD_OK);
}

static void test_stuck_select_stops_the_channel(void)
{
    reset();
    run_ms(1200);
    F.deselect_fail = 2;
    unsigned v = F.violations;
    run_ms(300);
    /* The bus was released with U50 still selected (the model counts that once); the hardware's 1 k
     * series resistors keep the pan converter and the MCP3202 readable through it. */
    assert(F.violations == v + 1u);
    assert(state(NULL) == RTD_FOOD_LINK_STUCK);
    unsigned locks = F.locks;
    run_ms(5000);
    assert(F.locks == locks); /* never touches the bus again */
}

int main(void)
{
    test_startup_runs_the_manual_fault_cycle_then_reads();
    test_fault_cycle_waits_at_a_fast_tick();
    test_unplug_and_replug();
    test_open_lead_and_input_fault();
    test_stale_config_is_never_a_temperature();
    test_link_failures_release_the_bus_deselected();
    test_stuck_select_stops_the_channel();
    printf("rtd_food_service: all passed\n");
    return 0;
}
