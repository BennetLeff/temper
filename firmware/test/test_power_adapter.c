#include "energy_supervisor.h"
#include "fullbridge_adapter.h"
#include "power_service.h"
#include "energy_link.h"
#include <assert.h>
#include <math.h>
#include <stdio.h>
#include <string.h>
static unsigned tests;
static void step(energy_supervisor_t *s, energy_inputs_t *i, uint32_t dt){
    i->now_ms += dt;
    i->sampled_ms = i->now_ms;
    energy_supervisor_step(s, i);
}
static energy_inputs_t healthy(void)
{
    return (energy_inputs_t){
        .stop_ok = true,.aux_ok = true,.sensors_valid = true,.hardware_ok = true,
            .k1_released = true,.k2_released = true,.kb_released = true,.manual_post_ok = true,
            .manual_post_serial = 1,.resistor_cool = true,.receiver_ok = true,.valid_line_cycles = 2,.line_rms_v = 120
    };
}
static void start(energy_supervisor_t *s, energy_inputs_t *i)
{
    energy_config_t c = energy_study_config();
    c.commissioned = true;
    energy_supervisor_init(s, &c, 0);
    *i = healthy();
    step(s, i, 1);
    step(s, i, 60000);
    assert(s->out.reset_ok);
    i->reset = true;
    step(s, i, 1);
    i->hardware_latch_ok = true; /* Physical RESET clocked the separate latch. */
    i->reset = false;
    step(s, i, 1);
    i->start = true;
    step(s, i, 1);
    assert(s->state == ENERGY_PRECHARGE && s->out.k1 && s->out.k2 && !s->out.sup_run_ok);
    i->k1_released = i->k2_released = false;
}
static void ready(energy_supervisor_t *s, energy_inputs_t *i)
{
    start(s, i);
    i->precharge_complete = true;
    step(s, i, 100);
    assert(s->out.kb);
    i->bypass_closed_electrically = true;
    i->kb_released = false;
    step(s, i, 10);
    assert(s->out.kt);
    i->proof_current_valid = true;
    step(s, i, 1);
    step(s, i, 50);
    assert(s->state == ENERGY_RAIL_QUALIFY);
    i->rails_ok = i->interlock_ok = i->controller_alive = true;
    i->catch_charge_proven = true;
    step(s, i, 1);
    assert(s->state == ENERGY_READY);
}
static void test_start_reset(void)
{
    energy_supervisor_t s;
    energy_config_t c = energy_study_config();
    c.commissioned = true;
    energy_inputs_t i = healthy();
    energy_supervisor_init(&s, &c, 0);
    i.start = true;
    step(&s, &i, 1);
    step(&s, &i, 61000);
    assert(s.state == ENERGY_OFF);
    i.start = false;
    step(&s, &i, 1);
    i.reset = true;
    step(&s, &i, 1);
    assert(s.state == ENERGY_OFF);
    assert(s.out.reset_ok);
    i.hardware_latch_ok = true;
    i.reset = false;
    i.start = true;
    step(&s, &i, 1);
    assert(s.state == ENERGY_PRECHARGE);
    i.stop_ok = false;
    step(&s, &i, 1);
    assert(s.state == ENERGY_FAULT && !s.out.k1);
    i.stop_ok = true;
    i.start = false;
    i.reset = false;
    step(&s, &i, 1);
    step(&s, &i, 60000);
    i.reset = true;
    i.start = true;
    step(&s, &i, 1);
    assert(s.state == ENERGY_OFF && !s.out.k1);
    i.start = false;
    i.reset = false;
    step(&s, &i, 1);
    i.start = true;
    step(&s, &i, 1);
    assert(s.state == ENERGY_OFF);      /* POST consumed */
    i.start = false;
    i.manual_post_serial = 2;
    step(&s, &i, 1);
    i.start = true;
    step(&s, &i, 1);
    assert(s.state == ENERGY_PRECHARGE);
    tests++;
}
static void test_sequence_faults(void)
{
    energy_supervisor_t s;
    energy_inputs_t i;
    ready(&s, &i);
    i.heat_request = true;
    step(&s, &i, 1);
    assert(s.state == ENERGY_READY);
    i.pwm_qualified = true;
    step(&s, &i, 1);
    assert(s.state == ENERGY_RUN && s.out.sup_run_ok);
    i.rails_ok = false;
    step(&s, &i, 1);
    assert(s.state == ENERGY_FAULT && !s.out.sup_run_ok && !s.out.k1);
    start(&s, &i);
    step(&s, &i, 298);
    assert(s.fault == ENERGY_TIMEOUT);
    start(&s, &i);
    i.kb_released = false;
    step(&s, &i, 1);
    assert(s.fault == ENERGY_CONTACT);
    start(&s, &i);
    i.bus_v = NAN;
    step(&s, &i, 1);
    assert(s.fault == ENERGY_BAD_SAMPLE);
    start(&s, &i);
    i.now_ms += 21;
    energy_supervisor_step(&s, &i);
    assert(s.fault == ENERGY_BAD_SAMPLE);
    ready(&s, &i);
    i.bus_fault = true;
    step(&s, &i, 1);
    assert(s.fault == ENERGY_RAIL);
    ready(&s, &i);
    i.catch_v = 250;
    step(&s, &i, 1);
    assert(s.fault == ENERGY_LIMIT);
    ready(&s, &i);
    energy_supervisor_step(&s, NULL);
    assert(s.state == ENERGY_FAULT && !s.out.k1 && !s.out.sup_run_ok);
    ready(&s, &i);
    i.off_request = true;
    step(&s, &i, 1);
    assert(s.state == ENERGY_DISCHARGE && !s.out.k1 && !s.out.sup_run_ok);
    tests++;
}
static void test_no_late_proof(void)
{
    energy_supervisor_t s;
    energy_inputs_t i;
    start(&s, &i);
    i.precharge_complete = true;
    step(&s, &i, 100);
    i.bypass_closed_electrically = true;
    step(&s, &i, 10);
    i.proof_current_valid = true;
    step(&s, &i, 96);
    assert(s.state == ENERGY_FAULT);
    tests++;
}
static void test_all_async_gates(void)
{
    for (unsigned f = 0; f < 12; f++) {
        energy_supervisor_t s;
        energy_inputs_t i;
        ready(&s, &i);
        i.heat_request = i.pwm_qualified = true;
        step(&s, &i, 1);
        switch (f) {
        case 0:
            i.stop_ok = false;
            break;
        case 1:
            i.aux_ok = false;
            break;
        case 2:
            i.sensors_valid = false;
            break;
        case 3:
            i.hardware_ok = false;
            break;
        case 4:
            i.controller_alive = false;
            break;
        case 5:
            i.interlock_ok = false;
            break;
        case 6:
            i.bypass_closed_electrically = false;
            break;
        case 7:
            i.receiver_ok = false;
            break;
        case 8:
            i.pwm_qualified = false;
            break;
        case 9:
            i.line_rms_v = 99;
            break;
        case 10:
            i.hardware_latch_ok = false;
            break;
        case 11:
            i.catch_charge_proven = false;
            break;
        }
        step(&s, &i, 1);
        assert(s.state == ENERGY_FAULT && !s.out.k1 && !s.out.k2 && !s.out.kb && !s.out.kt && !s.out.sup_run_ok);
    } tests++;
}
static void test_waveforms(void)
{
    for (uint32_t freq = 35000; freq <= 60000; freq += 5000)
        for (unsigned phase = 0; phase <= 100; phase++) {
            bridge_cycle_t c;
            if (phase != 100) {
                assert(!bridge_plan_cycle(80000000, freq, 125, phase / 100.0f, &c));
                continue;
            }
            assert(bridge_plan_cycle(80000000, freq, 200, 1, &c));
            unsigned high[4] = {0}, positive = 0, negative = 0;
            for (uint32_t t = 0; t < c.period; t++) {
                bool a = bridge_output_at(&c, 0, t), al = bridge_output_at(&c, 1, t), b = bridge_output_at(&c, 2, t),
                 bl = bridge_output_at(&c, 3, t);
                assert(!(a && al) && !(b && bl));
                positive += a && bl;
                negative += al && b;
                for (unsigned n = 0; n < 4; n++)
                    high[n] += bridge_output_at(&c, n, t);
            }
            assert(positive == negative);
            for (unsigned n = 0; n < 4; n++)
                assert(high[n] == c.pulse[n].width);
            if (!phase)
                assert(!positive && !negative);
        }
    tests++;
}
static struct {
    unsigned inhibits, applies;
    bool request, fail_apply;
} fake;
static bridge_cycle_t captured_cycle;
static bool apply(void *c, const bridge_cycle_t *cycle)
{
    (void)c;
    captured_cycle = *cycle;
    fake.applies++;
    return !fake.fail_apply;
}
static bool request(void *c, bool on)
{
    (void)c;
    fake.request = on;
    return true;
}
static void inhibit(void *c)
{
    (void)c;
    fake.request = false;
    fake.inhibits++;
}
static bridge_config_t config(void)
{
    return (bridge_config_t){
        .timer_hz = 80000000,.frequency_hz = 50000,.input_deadtime_ns = 125,.capture_age_us = 1000,.max_power_w = 1200,.inlet_target_a = 13.5f,.auxiliary_reserve_w = 100,.commissioned = true
    };
}
static void init(fullbridge_adapter_t *b){
    memset(&fake, 0, sizeof(fake));
    bridge_config_t c = config();
    bridge_backend_t ops = {apply, request, inhibit, NULL};
    assert(fullbridge_init(b, &c, &ops));
}
static bridge_feedback_t feedback(fullbridge_adapter_t *b, uint32_t now)
{
    bridge_feedback_t f = {.sampled_us = now,.serial = 1,.rails_ok = true,.sup_run_ok = true,.interlock_ok = true};
    for (unsigned n = 0; n < 4; n++) {
        f.valid[n] = true;
        f.period[n] = b->cycle.period;
        f.high_ticks[n] = b->cycle.pulse[n].width;
        f.rise_ticks[n] = b->cycle.pulse[n].rise;
        f.nonoverlap_ticks[n] = b->cycle.dead_ticks;
    } return f;
}
static void run(fullbridge_adapter_t *b){
    init(b);
    assert(fullbridge_request(b, 1000));
    assert(fullbridge_line_cycle(b, 0, 120, 1, 1000));
    assert(fullbridge_line_cycle(b, 16667, 120, 1, 1000));
}
static void test_control_and_capture(void)
{
    fullbridge_adapter_t b;
    run(&b);
    assert(b.conductance_s * 14400 <= 33.335f);
    bridge_feedback_t f = feedback(&b, 16667);
    assert(fullbridge_apply(&b, 16667, &f, 1) && fake.request);
    float before = b.conductance_s;
    assert(fullbridge_line_cycle(&b, 33334, 120, 14, 1000));
    assert(b.conductance_s < before);
    f = feedback(&b, 33334);
    f.valid[3] = false;
    assert(!fullbridge_apply(&b, 33334, &f, 1) && !fake.request && b.tripped);
    for (unsigned n = 0; n < 4; n++) {
        run(&b);
        f = feedback(&b, 16667);
        f.nonoverlap_ticks[n] = 0;
        assert(!fullbridge_apply(&b, 16667, &f, 1));
    }
    run(&b);
    f = feedback(&b, 0);
    assert(!fullbridge_apply(&b, 16667, &f, 1));
    run(&b);
    f = feedback(&b, 16667);
    f.rise_ticks[2] += 20;
    assert(!fullbridge_apply(&b, 16667, &f, 1));
    run(&b);
    assert(!fullbridge_line_cycle(&b, 16667, 120, 1, 1000));
    run(&b);
    assert(!fullbridge_request(&b, NAN));
    run(&b);
    f = feedback(&b, 16667);
    fake.fail_apply = true;
    assert(!fullbridge_apply(&b, 16667, &f, 1) && !fake.request);
    tests++;
}
static void test_default_off(void)
{
    fullbridge_adapter_t b;
    bridge_config_t c = config();
    c.commissioned = false;
    bridge_backend_t ops = {apply, request, inhibit, NULL};
    assert(!fullbridge_init(&b, &c, &ops));
    power_service_bootstrap();
    power_enable();
    power_set_level(100);
    assert(!test_pwm_generation());
    assert(!power_service_pan_pulse(20));
    assert(!power_service_frequency(50000));
    tests++;
}
static uint64_t service_now;
static bool service_crossing, service_line, service_gate;
static unsigned service_gate_changes;
static bool sample_service(void *ctx, uint32_t *now, bridge_feedback_t *f,
                           bool *line, float *v, float *a, float *pan)
{
    (void)ctx;
    *now = (uint32_t)service_now; *line=service_line; *v=120; *a=1; *pan=160;
    *f=(bridge_feedback_t){.sampled_us=*now,.serial=*now,.rails_ok=true,.sup_run_ok=true,.interlock_ok=true};
    for (unsigned i=0;i<4;i++) {
        f->valid[i]=true; f->period[i]=captured_cycle.period;
        f->rise_ticks[i]=captured_cycle.pulse[i].rise;
        f->high_ticks[i]=captured_cycle.pulse[i].width;
        f->nonoverlap_ticks[i]=captured_cycle.dead_ticks;
    }
    return true;
}
static bool sample_bus(void *ctx,uint64_t *now,hal_bus_crossing_t *bus)
{
    (void)ctx; *now=service_now;
    *bus=(hal_bus_crossing_t){.sampled_us=*now,.bus_v=service_crossing?0:2,.valid=true,.zero_crossing=service_crossing,.from_line_zc=true};
    return true;
}
static bool gate(void *ctx,bool enabled)
{
    (void)ctx;
    if (enabled!=service_gate) { assert(service_crossing); service_gate_changes++; }
    service_gate=enabled; return true;
}
static void test_burst_binding(void)
{
    power_service_bootstrap(); memset(&fake,0,sizeof fake);
    power_binding_t b={.config=config(),.backend={apply,request,inhibit,NULL},
        .sample=sample_service,
        .burst={.burst_enabled=true,.measured_burst_w=160,.line_rms_v=120,.power_factor=.95},
        .sample_bus=sample_bus,.set_burst_gate=gate};
    b.config.max_power_w=160;
    service_gate=false; service_gate_changes=0; service_crossing=true;
    assert(power_service_bind(&b)); power_set_level(50);
    for (unsigned n=0;n<4804;n++) {
        service_now=(uint64_t)n*25000/3; service_crossing=true; service_line=n%2==0;
        power_service_tick();
        service_now+=50; service_crossing=false; service_line=false;
        power_service_tick();
    }
    assert(service_gate_changes>=4 && test_pwm_generation());
    /* A normal stop demand must not change the outputs between crossings. */
    bool before=service_gate; power_set_level(0); power_service_tick(); assert(service_gate==before);
    service_now=(uint64_t)4804*25000/3; service_crossing=service_line=true;
    power_service_tick(); assert(!service_gate);
    power_service_bootstrap(); tests++;
}
static void test_link(void)
{
    energy_link_packet_t p = {.kind = ENERGY_LINK_COMMAND,.sequence = UINT32_MAX,.requested_mw = 100000,.flags = ENERGY_LINK_REQUEST}, out = {0};
    uint8_t bytes[ENERGY_LINK_SIZE];
    energy_link_receiver_t r = {0};
    assert(energy_link_encode(&p, bytes));
    for (unsigned n = 0; n < ENERGY_LINK_SIZE; n++) {
        bytes[n] ^= 1;
        assert(!energy_link_receive(&r, ENERGY_LINK_COMMAND, bytes, sizeof(bytes), 0, &out));
        bytes[n] ^= 1;
    }
    assert(energy_link_receive(&r, ENERGY_LINK_COMMAND, bytes, sizeof(bytes), 1, &out));
    assert(!energy_link_receive(&r, ENERGY_LINK_COMMAND, bytes, sizeof(bytes), 2, &out));
    p.sequence = 0;
    assert(energy_link_encode(&p, bytes));
    assert(energy_link_receive(&r, ENERGY_LINK_COMMAND, bytes, sizeof(bytes), 2, &out));
    assert(energy_link_fresh(&r, 22));
    assert(!energy_link_fresh(&r, 23));
    assert(!energy_link_receive(&r, ENERGY_LINK_STATUS, bytes, sizeof(bytes), 3, &out));
    assert(!energy_link_receive(&r, ENERGY_LINK_COMMAND, bytes, sizeof(bytes) - 1, 3, &out));
    p.flags = ENERGY_LINK_REQUEST | ENERGY_LINK_FAULT;
    assert(!energy_link_encode(&p, bytes));
    tests++;
}
static void test_hardware_contract(void)
{
    energy_supervisor_t s;
    energy_inputs_t i = healthy();
    energy_config_t c = energy_study_config();
    c.commissioned = true;
    energy_supervisor_init(&s, &c, 0);
    i.reset = true;
    step(&s, &i, 1);
    step(&s, &i, 61000);
    assert(!s.out.reset_ok); /* Held at boot never clocks latch at eligibility. */
    i.reset = false;
    step(&s, &i, 1);
    assert(s.out.reset_ok);
    i.start = true;
    step(&s, &i, 1);
    assert(s.state == ENERGY_OFF && !s.out.k1); /* Actual LATCH_OK is still low. */
    i.start = false;
    step(&s, &i, 1);
    i.reset = true;
    step(&s, &i, 1);
    assert(s.out.reset_ok && !s.out.k1);
    i.hardware_latch_ok = true;
    i.reset = false;
    step(&s, &i, 1);
    i.start = true;
    step(&s, &i, 1);
    assert(s.state == ENERGY_PRECHARGE);
    i.k1_released = i.k2_released = false;
    i.precharge_complete = true;
    step(&s, &i, 100);
    i.bypass_closed_electrically = true;
    i.kb_released = false;
    step(&s, &i, 10);
    step(&s, &i, 20); /* Relay pickup does not count as loaded proof. */
    i.proof_current_valid = true;
    step(&s, &i, 1);
    step(&s, &i, 49);
    assert(s.state == ENERGY_BYPASS_PROVE && s.out.kt);
    step(&s, &i, 1);
    assert(s.state == ENERGY_RAIL_QUALIFY && !s.out.kt); /* 71 ms < 87 ms pulse corner. */
    i.rails_ok = i.interlock_ok = i.controller_alive = true;
    i.heat_request = i.pwm_qualified = true;
    i.bus_v = 170;
    i.catch_v = 0; /* Open catch path: DIAG/rails/upper-limit alone cannot pass. */
    step(&s, &i, 1);
    assert(s.state == ENERGY_RAIL_QUALIFY && !s.out.sup_run_ok);
    step(&s, &i, 1999);
    assert(s.state == ENERGY_FAULT && !s.out.k1);
    tests++;
}
static void test_completed_attempt_requires_reset_and_post(void)
{
    energy_supervisor_t s;
    energy_inputs_t i;
    ready(&s, &i);
    i.off_request = true;
    step(&s, &i, 1);
    assert(s.state == ENERGY_DISCHARGE);
    i.hardware_latch_ok = false; /* STOP_DONE deliberately clears the pod latch. */
    i.off_request = i.start = false;
    i.k1_released = i.k2_released = i.kb_released = true;
    step(&s, &i, 1);
    assert(s.state == ENERGY_DISCHARGE && s.fault == ENERGY_OK);
    step(&s, &i, 60000);
    assert(s.state == ENERGY_OFF);
    i.start = true;
    step(&s, &i, 1);
    assert(s.state == ENERGY_OFF && !s.out.k1);
    i.start = false;
    step(&s, &i, 1);
    assert(s.out.reset_ok);
    i.reset = true;
    step(&s, &i, 1);
    assert(s.out.reset_ok);
    i.hardware_latch_ok = true;
    i.reset = false;
    step(&s, &i, 1);
    i.start = true;
    step(&s, &i, 1);
    assert(s.state == ENERGY_OFF); /* Prior POST cannot authorize a sibling attempt. */
    i.start = false;
    i.manual_post_serial = 2;
    step(&s, &i, 1);
    i.start = true;
    step(&s, &i, 1);
    assert(s.state == ENERGY_PRECHARGE && s.out.k1 && s.out.k2);
    tests++;
}
int main(void){
    test_start_reset();
    test_sequence_faults();
    test_no_late_proof();
    test_all_async_gates();
    test_waveforms();
    test_control_and_capture();
    test_default_off();
    test_burst_binding();
    test_link();
    test_hardware_contract();
    test_completed_attempt_requires_reset_and_post();
    printf("%u power adapter test groups passed; 6 fixed-phase waveform sweeps and 600 rejected phase configurations\n", tests);
    return 0;
}
