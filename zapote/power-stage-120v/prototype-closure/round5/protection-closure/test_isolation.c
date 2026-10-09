#include "isolation.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>

typedef enum { NORMAL, WELD_A_INITIAL, WELD_B_INITIAL, WELD_A_RELEASE,
    WELD_B_RELEASE, DISCONNECT_A, DISCONNECT_B, SHORT_A_FEEDBACK,
    SHORT_B_FEEDBACK, LOST_FEEDBACK_RUN, UNEXPECTED_A_RUN,
    UNEXPECTED_B_RUN, BYPASS_NEVER, NO_POST, STALE_POST, NOT_COLD,
    LOST_POWER_RUN, RESTART_HELD } scenario;
typedef struct { bool cmd, closed; uint32_t changed; } contact;
static void move(contact *c, bool cmd, uint32_t now, uint32_t close_us, uint32_t open_us) {
    if (c->cmd!=cmd) { c->cmd=cmd; c->changed=now; }
    if(now-c->changed >= (cmd?close_us:open_us)) c->closed=cmd;
}
static void run_case(scenario which, uint32_t close_us, uint32_t open_us,
                     bool expect_run, bool expect_fault) {
    pc_controller s={0}; contact a={0},b={0},main={0},kb={0};
    bool ever_run=false, ever_main=false, late_fault=false;
    uint32_t first_run=0, first_source=0;
    for(uint32_t now=0;now<=850000;now+=1000) {
        move(&a,s.out.a,now,close_us,open_us);
        move(&b,s.out.b,now,close_us,open_us);
        move(&main,s.out.main,now,close_us,open_us);
        move(&kb,s.out.bypass,now,close_us,open_us);
        if(which==WELD_A_INITIAL || (which==WELD_A_RELEASE && s.state==PC_ISOLATE)) a.closed=true;
        if(which==WELD_B_INITIAL || (which==WELD_B_RELEASE && s.state==PC_ISOLATE)) b.closed=true;
        if(ever_run && now-first_run>=10000) {
            late_fault=true;
            if(which==UNEXPECTED_A_RUN) a.closed=true;
            if(which==UNEXPECTED_B_RUN) b.closed=true;
        }
        pc_inputs i={.now_us=now,.mirror_us=now,.post_token=1,
            .start=now==1000 || (which==RESTART_HELD && now>=1000),
            .healthy=!(which==LOST_POWER_RUN && late_fault),
            .source_released=!main.closed,.bypass_released=!kb.closed,
            .discharged=!main.closed,.post_valid=which!=NO_POST,
            .cold=which!=NOT_COLD,.a_nc=!a.closed,.b_nc=!b.closed,
            .mirror_valid=!(which==LOST_FEEDBACK_RUN && late_fault),
            .precharge_complete=main.closed&&a.closed&&b.closed&&now-main.changed>=90000,
            .bypass_proven=kb.closed&&now-kb.changed>=110000&&which!=BYPASS_NEVER,
            .post_isolation_proven=s.state==PC_REPROVE&&now-s.entered_us>=100000,
            .feedback_static=true,.proof_timer_ready=true,.run_qualified=true};
        if(which==STALE_POST) s.used_post=1;
        if(which==DISCONNECT_A) i.a_nc=false;
        if(which==DISCONNECT_B) i.b_nc=false;
        if(which==SHORT_A_FEEDBACK) i.a_nc=true;
        if(which==SHORT_B_FEEDBACK) i.b_nc=true;
        pc_step(&s,&i);
        if(s.out.main&&!ever_main) first_source=now;
        ever_main|=s.out.main;
        if(s.out.run) {
            assert(!s.out.a && !s.out.b && !a.closed && !b.closed);
            assert(s.out.main && s.out.bypass && i.bypass_proven);
            if(!ever_run) first_run=now;
            ever_run=true;
        }
        if(s.state==PC_FAULT) assert(!s.out.a&&!s.out.b&&!s.out.main&&!s.out.bypass&&!s.out.run);
    }
    assert(ever_run==expect_run);
    assert((s.state==PC_FAULT)==expect_fault);
    if(which==WELD_A_INITIAL || which==WELD_B_INITIAL || which==SHORT_A_FEEDBACK ||
       which==SHORT_B_FEEDBACK || which==NO_POST || which==STALE_POST || which==NOT_COLD)
        assert(!ever_main);
    printf("scenario,%u,close_us,%u,open_us,%u,run,%u,fault,%u,first_run_us,%u,first_source_us,%u,source_to_run_us,%u\n",
        which,close_us,open_us,ever_run,s.state==PC_FAULT,first_run,first_source,ever_run?first_run-first_source:0);
}
static void protocol_tests(void) {
    for(unsigned mask=0;mask<32;mask++) {
        uint8_t slots[6]={0},decoded=255;
        for(unsigned n=0;n<5;n++) slots[n+1]=(uint8_t)(mask&(1u<<n));
        assert(pc_decode_mirrors(slots,&decoded)&&decoded==mask);
        for(unsigned bit=0;bit<5;bit++) {
            uint8_t bad[6]; memcpy(bad,slots,sizeof bad);
            bad[0]|=(uint8_t)(1u<<bit); assert(!pc_decode_mirrors(bad,&decoded));
            for(unsigned slot=1;slot<6;slot++) if(slot!=bit+1) {
                memcpy(bad,slots,sizeof bad); bad[slot]|=(uint8_t)(1u<<bit);
                assert(!pc_decode_mirrors(bad,&decoded));
            }
        }
    }
    puts("protocol,32_valid_masks,800_static_high_or_cross_channel_mutations_rejected");
}
static void boundary_tests(void) {
    for(pc_state state=PC_TEST_A_CLOSE;state<=PC_RUN;state++) {
        pc_controller s={.state=state,.initialized=true,.previous_us=99000};
        pc_inputs i={.now_us=100000,.mirror_us=100000,.healthy=false,.mirror_valid=true};
        pc_step(&s,&i); assert(s.state==PC_FAULT);
        assert(!s.out.a&&!s.out.b&&!s.out.main&&!s.out.bypass&&!s.out.run);
    }
    for(unsigned age=2000;age<=2001;age++) {
        pc_controller s={.state=PC_RUN,.initialized=true,.previous_us=99000};
        pc_inputs i={.now_us=100000,.mirror_us=100000-age,.healthy=true,.mirror_valid=true,
            .a_nc=true,.b_nc=true,.bypass_proven=true,.feedback_static=true,.proof_timer_ready=true,.run_qualified=true};
        pc_step(&s,&i); assert(s.out.run==(age==2000));
    }
    for(unsigned now=446457;now<=446458;now++) {
        pc_controller s={.state=PC_ISOLATE,.initialized=true,.previous_us=now-1000,
            .entered_us=430000,.source_us=0};
        pc_inputs i={.now_us=now,.mirror_us=now,.healthy=true,.mirror_valid=true,
            .bypass_proven=true,.feedback_static=true};
        pc_step(&s,&i); assert((s.state==PC_FAULT)==(now==446458));
    }
    pc_controller s={.state=PC_RUN,.initialized=true,.previous_us=1000};
    pc_inputs i={.now_us=2001,.mirror_us=2001,.healthy=true,.mirror_valid=true,
        .a_nc=true,.b_nc=true,.bypass_proven=true,.feedback_static=true,.proof_timer_ready=true,.run_qualified=true};
    pc_step(&s,&i);assert(s.state==PC_FAULT);
    /* RESET alone does not arm, nor does held START reset a fault. */
    i.now_us=3001;i.mirror_us=3001;i.reset=true;i.start=true;
    i.source_released=i.bypass_released=i.discharged=true;
    pc_step(&s,&i);assert(s.state==PC_FAULT);
    i.now_us=4001;i.mirror_us=4001;i.start=false;
    pc_step(&s,&i);assert(s.state==PC_FAULT);
    i.now_us+=1000;i.mirror_us=i.now_us;i.reset=false;
    pc_step(&s,&i);assert(s.state==PC_FAULT);
    i.now_us+=1000;i.mirror_us=i.now_us;i.reset=true;
    pc_step(&s,&i);assert(s.state==PC_OFF&&!s.out.run);
    /* NC may open before the main NO contact closes. Dwell is independent. */
    const pc_state closing[]={PC_TEST_A_CLOSE,PC_TEST_B_CLOSE,PC_CONNECT};
    for(unsigned n=0;n<3;n++) {
        s=(pc_controller){.state=closing[n]};
        for(unsigned now=0;now<=73000;now+=1000) {
            i=(pc_inputs){.now_us=now,.mirror_us=now,.healthy=true,.mirror_valid=true,
                .source_released=true,.bypass_released=true,.discharged=true,
                .feedback_static=true,.a_nc=closing[n]==PC_TEST_B_CLOSE,.b_nc=closing[n]==PC_TEST_A_CLOSE};
            pc_step(&s,&i);
            if(now<73000) assert(s.state==closing[n]&&!s.out.main);
            else assert(s.state!=closing[n]);
        }
    }
    /* Cached proof cannot pass; a fresh false-to-true epoch is mandatory. */
    for(unsigned cached=0;cached<2;cached++) {
        s=(pc_controller){.state=PC_REPROVE};
        for(unsigned now=0;now<=110000;now+=1000) {
            i=(pc_inputs){.now_us=now,.mirror_us=now,.healthy=true,.mirror_valid=true,
                .a_nc=true,.b_nc=true,.bypass_proven=true,
                .post_isolation_proven=cached||now>=50000,.feedback_static=true};
            pc_step(&s,&i);
            if(now<50000) assert(s.state==PC_REPROVE);
        }
        assert(s.state==(cached?PC_FAULT:PC_READY));
    }
    /* Rearm cannot bypass the global timer; static-mode loss fails closed. */
    s=(pc_controller){.state=PC_REARM};
    for(unsigned now=0;now<=446000;now+=1000) {
        i=(pc_inputs){.now_us=now,.mirror_us=now,.healthy=true,.mirror_valid=true,
            .a_nc=true,.b_nc=true,.bypass_proven=true,.feedback_static=true};
        pc_step(&s,&i); assert(s.state==PC_REARM&&!s.out.run);
    }
    i.now_us=i.mirror_us=447000;pc_step(&s,&i);assert(s.state==PC_FAULT);
    s=(pc_controller){.state=PC_RUN};
    i=(pc_inputs){.healthy=true,.mirror_valid=true,.a_nc=true,.b_nc=true,
        .bypass_proven=true,.run_qualified=true,.feedback_static=false};
    pc_step(&s,&i);assert(s.state==PC_FAULT&&!s.out.run);
    s=(pc_controller){0};
    i=(pc_inputs){.healthy=true,.mirror_valid=true,.a_nc=true,.b_nc=true,
        .feedback_static=true,.post_valid=true,.post_token=1,.cold=true,
        .source_released=true,.bypass_released=true,.discharged=true,.start=true,.reset=true};
    pc_step(&s,&i);assert(s.state==PC_FAULT&&!s.out.a&&!s.out.b);
    puts("boundaries,stop_all_active_states,stale_scan,446458us_global,scheduler,reset_pass");
}
int main(void) {
    protocol_tests();boundary_tests();
    for(uint32_t close=54000;close<=73000;close+=19000)
        for(uint32_t open=16000;open<=24000;open+=8000)
            run_case(NORMAL,close,open,true,false);
    for(scenario f=WELD_A_INITIAL;f<=RESTART_HELD;f++) {
        bool ran=f==LOST_FEEDBACK_RUN||f==UNEXPECTED_A_RUN||f==UNEXPECTED_B_RUN||
                 f==LOST_POWER_RUN||f==RESTART_HELD;
        run_case(f,73000,24000,ran,f!=RESTART_HELD);
    }
    run_case(NORMAL,100000,24000,false,true);
    run_case(NORMAL,73000,40000,false,true);
    puts("PASS executable_candidate_sequence_NO_POWER_RELEASE");
}
