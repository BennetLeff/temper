/* Accepted-step co-simulation: links the actual portable production C core.
 * Electrical plant and injected calibrated sensors remain diagnostic models.
 */
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>
#include <errno.h>
#include <unistd.h>
#include <sys/stat.h>
#include <ngspice/sharedspice.h>
#include "fullbridge_adapter.h"
#include "energy_supervisor.h"
#include "acquisition.h"
#include "measurement.h"
#include "bypass.h"
#include "supervisor_binding.h"
#include "supervisor_outputs.h"
#include "contact_model.h"
#define PI 3.14159265358979323846
#define ADC_DT .000256
#define PWM_DT .00002
#define OFFSET_MS 61000u
#define MAX_NODES 32
static struct {
    FILE *log,*samples,*cycles,*events; bool error,study,inject_stale,inject_readback,averaged,proof_open,bypass_open,bad_post;
    bool demand_pause,never_demand,paused,resumed;
    double next_adc,next_control,next_supervisor,guard_delay,end,vrms,rt,last_t,last_v[MAX_NODES];
    double physical[8];bool sampled_valid;uint32_t sampled_us,feedback_serial;
    r5_measurement_t measurement;post_record_t post;
    double v[MAX_NODES],line_v,line_i,cycle_v2,cycle_i2,cycle_duration;
    double ktime,btime,ptime,contacts,bypass,proof,trip_time;
    double pa_time,pb_time,pa,pb,proof_until,admission_time;
    double k_initial,b_initial,p_initial,pa_initial,pb_initial;
    double peak_bus,peak_catch,peak_tank,peak_i,catch_i2t,rect_i2t,pre1_j,pre2_j,pre1_pk,pre2_pk;
    double rp1,rp2,first_run,stop_at,joined_run_s,load_j,unsafe_run_s;
    uint64_t adc_serial,steps;int name_index[MAX_NODES];
    bool old_k,old_b,old_p,request,hw_latch,precharge_ok;
    bool old_pa,old_pb,hardware_attempt,start_token;
    bool bypass_electrical;
    bridge_cycle_t applied,pending;bool have_pending;
    fullbridge_adapter_t bridge; r5_supervisor_t supervisor; ads_receiver_t ads;
    energy_state_t old_state;pc_state old_isolation;
    r5_supervisor_signals_t wires;
} s;
enum {TIME,SRC,MAINS,PRE,LI,BUS,CATCH,TANK,VPRE,IPROOF,ILINE,ITANK,ICATCH,IRECT,MID,DA,MOD,ALLOW,BYPASS,CONTACTS,VRES,NV};
static const char *names[NV]={"time","src","mains","pre","li","bp","catch","ct","vpre","iproof","lsrc#branch","lcoil#branch","lcatch#branch","vsense#branch","mid","da","m","allow","bypass","contacts","vres"};
/* Explicit ideal SI ranges. VPRE follows the revised nominal801:1 divider,
 * AMC gain2, output attenuator0.5 and ADC1.2V reference. Other channels retain
 * the historical diagnostic gains; none are installed calibration records. */
static const double adc_scale[8]={250,961.2,250,1000,1000,2000,10,300};
static bool apply(void*x,const bridge_cycle_t*c){(void)x;s.pending=*c;s.have_pending=true;return true;}
static bool request(void*x,bool on){(void)x;s.request=on;return true;}
static void inhibit(void*x){(void)x;s.request=false;}
static double clip(double x,double lo,double hi){return fmax(lo,fmin(hi,x));}
static int logfn(char *text,int id,void*x){(void)id;(void)x;fprintf(s.log,"%s\n",text);if(strstr(text,"timestep too small")||strstr(text,"Error:"))s.error=true;return 0;}
static int statfn(char*x,int id,void*c){(void)x;(void)id;(void)c;return 0;}
static int exitfn(int code,bool immediate,bool quit,int id,void*x){(void)immediate;(void)quit;(void)id;(void)x;if(code)s.error=true;return 0;}
static int bgfn(bool running,int id,void*x){(void)running;(void)id;(void)x;return 0;}
static int initfn(pvecinfoall a,int id,void*x){(void)id;(void)x;for(int n=0;n<NV;n++){s.name_index[n]=-1;for(int j=0;j<a->veccount;j++)if(!strcmp(a->vecs[j]->vecname,names[n]))s.name_index[n]=j;if(s.name_index[n]<0){fprintf(s.log,"MISSING %s\n",names[n]);s.error=true;}}return 0;}
static void trace_state(double t){if(s.supervisor.energy.state!=s.old_state){fprintf(s.events,"%.9f,state,%d,%d\n",t,s.supervisor.energy.state,s.supervisor.energy.fault);s.old_state=s.supervisor.energy.state;}if(s.supervisor.isolation.state!=s.old_isolation){fprintf(s.events,"%.9f,isolation,%d,0\n",t,s.supervisor.isolation.state);s.old_isolation=s.supervisor.isolation.state;}}
static void cold_history(void){
    /* Model-only uncertainty: one ADC LSB per ideal SI channel. This is not
       a calibration allowance for physical sensors or their analog front end. */
    double error[8];for(unsigned n=0;n<8;n++)error[n]=adc_scale[n]/8388607;
    if(!r5_measurement_init(&s.measurement,error)){s.error=true;return;}
    const post_branch_t branch[2]={{(float)s.rp1,0,true},{(float)s.rp2,0,true}};
    /* Exact simulated resistances and explicit cold, discharged prehistory;
       physical POST still requires two isolated measurements with uncertainty. */
    post_record_accept(&s.post,1,1,OFFSET_MS,branch,true,true,!s.bad_post,true);
    energy_config_t cfg=energy_study_config();cfg.commissioned=s.study;cfg.bus_max_v=230;cfg.catch_max_v=250;cfg.tank_max_v=1000;
    r5_supervisor_init(&s.supervisor,&cfg,0);
    /* Explicit simulated unpowered prehistory; does not erase analog stored energy. */
    for(uint32_t ms=0;ms<=OFFSET_MS;ms++){
        energy_inputs_t i={.now_ms=ms,.sampled_ms=ms,.stop_ok=true,.aux_ok=true,.sensors_valid=true,.hardware_ok=true,
        .k1_released=true,.k2_released=true,.kb_released=true,.resistor_cool=true,.receiver_ok=true};
        r5_supervisor_inputs_t boot={.energy=i,.now_us=ms*1000,.mirror_us=ms*1000,
            .mirror_valid=true,.feedback_static=true,.kpa_nc=true,.kpb_nc=true};
        r5_supervisor_step(&s.supervisor,&boot);
    }
    s.wires=r5_supervisor_signals(&s.supervisor,true,true,true);
    bridge_config_t bc={.timer_hz=80000000,.frequency_hz=50000,.input_deadtime_ns=125,.capture_age_us=1000,
    .max_power_w=1500,.inlet_target_a=13.5,.auxiliary_reserve_w=25,.commissioned=s.study,
    .feedback_kind=BRIDGE_FEEDBACK_ONCHIP_REGISTER,.scope_record_id=UINT32_MAX};
    bridge_backend_t ops={apply,request,inhibit,0};
    fullbridge_init(&s.bridge,&bc,&ops);s.applied=s.bridge.cycle;
    if(s.study&&!s.never_demand)fullbridge_request(&s.bridge,1500);
}
static void adc_event(double t){
    uint32_t us=(uint32_t)llround(t*1e6);
    bool stale=s.inject_stale && t>1.0;
    /* The ADC serial/parser is exercised with explicit ideal calibrated sensor
       stimulus; no analog scale/noise/reference calibration is thereby proven. */
    uint8_t frame[ADS_FRAME_BYTES]={1,255};double physical[8]={s.v[SRC],s.v[VPRE],s.v[LI],s.v[BUS],s.v[CATCH],s.v[TANK],s.v[IPROOF],s.v[ILINE]};
    for(unsigned n=0;n<8;n++)physical[n]/=adc_scale[n];
    /* An amplifier outside its nominal linear range cannot supply ideal data. */
    if(fabs(s.v[VPRE])>=801)s.ads.fault=true;
    for(unsigned ch=0;ch<8;ch++){int32_t code=(int32_t)llround(clip(physical[ch],-.999,.999)*8388607);uint32_t u=(uint32_t)code&0xffffff;frame[3+3*ch]=u>>16;frame[4+3*ch]=u>>8;frame[5+3*ch]=u;}
    uint16_t crc=ads_crc16(frame,27);frame[27]=crc>>8;frame[28]=crc;ads_sample_t decoded={0};
    bool valid=!stale&&ads_accept(&s.ads,frame,us,us,&decoded);
    if(!valid&&s.sampled_valid) {
        fprintf(s.log,"ADC_INVALID us=%u ads_fault=%d normalized_channels",us,s.ads.fault);
        for(unsigned n=0;n<8;n++)fprintf(s.log," %.9g",physical[n]);
        fprintf(s.log,"\n");
    }
    s.adc_serial++;
    if(valid){
        for(unsigned n=0;n<8;n++)s.physical[n]=decoded.code[n]/8388607.*adc_scale[n];
        valid=r5_measurement_add(&s.measurement,us,s.physical,s.proof>.999,s.contacts>.999);
        if(s.measurement.complete){
            s.line_v=s.measurement.rms[0];s.line_i=s.measurement.rms[7];
            fprintf(s.cycles,"%u,%.9f,%.9g,%.9g,%.9g,%.9g\n",s.measurement.serial,t,sqrt(s.cycle_v2/s.cycle_duration),sqrt(s.cycle_i2/s.cycle_duration),s.line_v,s.line_i);
            s.cycle_v2=s.cycle_i2=s.cycle_duration=0;
            if(s.study&&s.supervisor.energy.state>=ENERGY_RAIL_QUALIFY&&s.supervisor.energy.state<=ENERGY_RUN&&!s.bridge.tripped)
                fullbridge_line_cycle(&s.bridge,us,s.line_v,s.line_i,1500);
        }
    }
    s.sampled_valid=valid;s.sampled_us=us;s.precharge_ok=s.measurement.precharge_ok;
}
static void controller_event(double t){
    uint32_t us=(uint32_t)llround(t*1e6),ms=OFFSET_MS+us/1000;
    if(s.demand_pause&&us>=950000&&!s.paused){fullbridge_request(&s.bridge,0);s.paused=true;}
    if(s.demand_pause&&us>=1050000&&!s.resumed){fullbridge_request(&s.bridge,1500);s.resumed=true;}
    bool valid=s.sampled_valid&&ads_fresh(&s.ads,us)&&r5_measurement_fresh(&s.measurement,us);
    if(!s.wires.kb||s.bypass<.001)s.bypass_electrical=false;
    else if(r5_bypass_loaded(&s.measurement))s.bypass_electrical=true;
    bool proof_valid=s.proof>.999&&s.measurement.proof_ok;
    if(us>=56000 && us<57000 && s.wires.reset_ok)s.hw_latch=true;
    if(s.v[BUS]>=230||s.v[CATCH]>=250||fabs(s.v[TANK])>=1000||fabs(s.v[ITANK])>=85){if(s.trip_time<0)s.trip_time=t;}
    bool hardware_ok=s.trip_time<0;
    bool source_off=s.contacts<.001&&s.bypass<.001&&fabs(s.v[BUS])<30&&fabs(s.v[CATCH])<30;
    if(s.wires.stop_done||!hardware_ok){s.hw_latch=false;s.hardware_attempt=false;s.start_token=false;}
    if(us>=60000&&us<61000&&s.hw_latch&&source_off&&!s.wires.admit&&s.wires.post_ok&&s.wires.start_released)s.start_token=true;
    bool capture_ok=!(s.inject_readback&&t>1.0);
    energy_inputs_t in={.now_ms=ms,.sampled_ms=OFFSET_MS+s.sampled_us/1000,.manual_post_serial=1,.start=us>=60000&&us<61000,.reset=us>=56000&&us<57000,
    .off_request=us>=(uint32_t)llround(s.stop_at*1e6),.stop_ok=true,.aux_ok=true,.sensors_valid=valid,.hardware_ok=hardware_ok,.hardware_latch_ok=s.hw_latch,
    .catch_charge_proven=s.measurement.catch_ok,.k1_released=s.contacts<.001,.k2_released=s.contacts<.001,.kb_released=s.bypass<.001,
    .manual_post_ok=post_record_fresh(&s.post,1,ms),.resistor_cool=true,.receiver_ok=true,.precharge_complete=s.precharge_ok,
    .bypass_closed_electrically=s.bypass_electrical,.proof_current_valid=proof_valid,.rails_ok=s.bypass_electrical,
    .bus_fault=!hardware_ok,.interlock_ok=hardware_ok,.controller_alive=true,.pwm_qualified=capture_ok,
    .heat_request=s.request,.valid_line_cycles=(uint8_t)(s.measurement.serial>255?255:s.measurement.serial),.bus_v=s.physical[3],
    .catch_v=s.physical[4],.tank_abs_v=fabs(s.physical[5]),.line_rms_v=s.line_v,.inlet_rms_a=s.line_i};
    r5_supervisor_inputs_t joined={.energy=in,.now_us=ms*1000,.mirror_us=ms*1000,
        .measurement_serial=s.measurement.serial,.mirror_valid=true,.feedback_static=true,
        .kpa_nc=s.pa<.001,.kpb_nc=s.pb<.001,
        .loaded_bypass_proof=r5_bypass_loaded(&s.measurement),
        .proof_window_high=t<s.proof_until,
        .hardware_attempt=s.hardware_attempt,
        .hardware_total_window=s.hardware_attempt&&t<s.admission_time+.446458};
    r5_supervisor_step(&s.supervisor,&joined);trace_state(t);
    s.wires=r5_supervisor_signals(&s.supervisor,valid,true,post_record_fresh(&s.post,1,ms));
    /* Ideal one-token admission latch: one controller tick ACK latency, never
       restart an existing attempt. Native gate propagation is not simulated. */
    if(s.wires.stop_done){s.hw_latch=false;s.hardware_attempt=false;s.start_token=false;}
    if(s.wires.admit&&!s.hardware_attempt&&s.start_token&&source_off&&s.hw_latch){
        s.hardware_attempt=true;s.admission_time=t;s.start_token=false;
    }
    if(s.supervisor.consume_post)post_record_consume(&s.post);
    /* Simulated register state, never physical pad capture. UINT32_MAX is a
       diagnostic-only commissioning sentinel, not a real scope record. */
    bridge_feedback_t fb={.kind=BRIDGE_FEEDBACK_ONCHIP_REGISTER,
        .sampled_us=us,.serial=++s.feedback_serial,
        .onchip={.programmed_cycle=s.applied,.timer_hz=80000000,
        .coherent=capture_ok,.timer_advancing=true,.outputs_connected=true}};
    fb.rails_ok=s.bypass_electrical;fb.sup_run_ok=s.wires.run;fb.interlock_ok=hardware_ok;fb.bus_fault=!hardware_ok;
    double reactance=2*PI*50000*20e-6-1/(2*PI*50000*540e-9);
    double phase=2*asin(fmin(.98,sqrt(fmax(0,s.bridge.conductance_s)*(s.rt*s.rt+reactance*reactance)/s.rt*PI*PI/8)))/PI;
    if(s.study&&s.bypass_electrical&&s.measurement.serial>=2&&s.bridge.have_line&&!s.bridge.tripped)fullbridge_apply(&s.bridge,us,&fb,(float)phase);
    if(s.supervisor.energy.state==ENERGY_FAULT||s.supervisor.energy.state==ENERGY_DISCHARGE)fullbridge_stop(&s.bridge);
    if(s.wires.k1!=s.old_k){s.k_initial=contact_position(t,s.ktime,s.k_initial,s.old_k,s.old_k?.07245:.024);s.ktime=t;s.old_k=s.wires.k1;}
    if(s.wires.kb!=s.old_b){s.b_initial=contact_position(t,s.btime,s.b_initial,s.old_b,s.old_b?.07245:.016);s.btime=t;s.old_b=s.wires.kb;}
    if(s.wires.kt!=s.old_p){
        s.p_initial=s.proof;s.ptime=t;s.old_p=s.wires.kt;
        /* Diagnostic model of the qualified non-retriggerable proof timer.
           Low request alone never rearms a still-active hardware window. */
        if(s.old_p&&t>=s.proof_until)s.proof_until=t+.131433;
    }
    if(s.wires.kpa!=s.old_pa){s.pa_initial=contact_position(t,s.pa_time,s.pa_initial,s.old_pa,s.old_pa?.07245:.024);s.pa_time=t;s.old_pa=s.wires.kpa;}
    if(s.wires.kpb!=s.old_pb){s.pb_initial=contact_position(t,s.pb_time,s.pb_initial,s.old_pb,s.old_pb?.07245:.024);s.pb_time=t;s.old_pb=s.wires.kpb;}
    if(s.wires.run&&s.request&&s.first_run<0)s.first_run=t;
    fprintf(s.samples,"%.9f,%d,%u,%u,%.9g,%.9g,%.9g,%.9g,%.9g,%.9g,%.9g,%d,%d,%d,%d\n",t,s.supervisor.energy.state,s.measurement.serial,(unsigned)s.adc_serial,s.v[BUS],s.v[CATCH],s.v[TANK],s.v[ITANK],s.line_v,s.line_i,s.bridge.conductance_s,s.request,s.wires.run,s.bridge.tripped,valid);
}
static int datafn(pvecvaluesall a,int count,int id,void*x){
    (void)count;(void)id;(void)x;if(s.error)return 0;
    for(int n=0;n<NV;n++){if(s.name_index[n]<0)return 0;s.v[n]=a->vecsa[s.name_index[n]]->creal;if(!isfinite(s.v[n])){s.error=true;return 0;}}
    double t=s.v[TIME],dt=t-s.last_t;
    if(s.trip_time<0&&(s.v[BUS]>=230||s.v[CATCH]>=250||fabs(s.v[TANK])>=1000||fabs(s.v[ITANK])>=85))s.trip_time=t;if(dt<0){s.error=true;return 0;}s.steps++;if(s.steps>5000000){s.error=true;ngSpice_Command("stop");return 0;}
    if(dt>0){
    if(s.v[ALLOW]>.999){s.joined_run_s+=dt;if(s.pa>.001||s.pb>.001)s.unsafe_run_s+=dt;}
    s.load_j+=.5*(s.last_v[ALLOW]*s.last_v[MOD]*s.last_v[BUS]*s.last_v[BUS]+s.v[ALLOW]*s.v[MOD]*s.v[BUS]*s.v[BUS])*dt;
    s.cycle_v2+=.5*(s.last_v[SRC]*s.last_v[SRC]+s.v[SRC]*s.v[SRC])*dt;s.cycle_i2+=.5*(s.last_v[ILINE]*s.last_v[ILINE]+s.v[ILINE]*s.v[ILINE])*dt;s.cycle_duration+=dt;
    double pp=.5*(s.last_v[VRES]*s.last_v[VRES]+s.v[VRES]*s.v[VRES]);s.pre1_j+=pp/s.rp1*dt;s.pre2_j+=pp/s.rp2*dt;
    s.catch_i2t+=.5*(s.last_v[ICATCH]*s.last_v[ICATCH]+s.v[ICATCH]*s.v[ICATCH])*dt;s.rect_i2t+=.5*(s.last_v[IRECT]*s.last_v[IRECT]+s.v[IRECT]*s.v[IRECT])*dt;}
    s.peak_bus=fmax(s.peak_bus,s.v[BUS]);s.peak_catch=fmax(s.peak_catch,s.v[CATCH]);s.peak_tank=fmax(s.peak_tank,fabs(s.v[TANK]));s.peak_i=fmax(s.peak_i,fabs(s.v[ITANK]));s.pre1_pk=fmax(s.pre1_pk,s.v[VRES]*s.v[VRES]/s.rp1);s.pre2_pk=fmax(s.pre2_pk,s.v[VRES]*s.v[VRES]/s.rp2);
    if(t>=s.next_control-1e-12){if(s.have_pending){s.applied=s.pending;s.have_pending=false;}s.next_control=(floor(t/PWM_DT+1e-7)+1)*PWM_DT;}
    if(t>=s.next_adc-1e-12){adc_event(t);s.next_adc=(s.adc_serial+1)*ADC_DT;}
    if(t>=s.next_supervisor-1e-12){controller_event(t);s.next_supervisor=(floor(t/.001+1e-7)+1)*.001;}
    memcpy(s.last_v,s.v,sizeof(s.v));s.last_t=t;return 0;
}
static int vsrcfn(double *v,double t,char*name,int id,void*x){(void)id;(void)x;
    /* LC1D18BD published closing maximum72.45ms replaces the former20ms
       sensitivity. Opening16/24ms bounds still omit installed arc dynamics. */
    s.contacts=contact_position(t,s.ktime,s.k_initial,s.old_k,s.old_k?.07245:.024);
    s.bypass=contact_position(t,s.btime,s.b_initial,s.old_b,s.old_b?.07245:.016);
    s.pa=contact_position(t,s.pa_time,s.pa_initial,s.old_pa,s.old_pa?.07245:.024);
    s.pb=contact_position(t,s.pb_time,s.pb_initial,s.old_pb,s.old_pb?.07245:.024);
    s.proof=contact_position(t,s.ptime,s.p_initial,s.old_p,.005);
    if(s.old_p&&t>=s.proof_until)
        s.proof=contact_position(t,s.proof_until,contact_position(s.proof_until,s.ptime,s.p_initial,true,.005),false,.005);
    if(!strcmp(name,"vcontacts"))*v=s.contacts;
    else if(!strcmp(name,"vbypass"))*v=s.bypass_open?0:s.bypass;
    else if(!strcmp(name,"vproof"))*v=s.proof_open?0:s.proof;
    else if(!strcmp(name,"vpa"))*v=s.pa;
    else if(!strcmp(name,"vpb"))*v=s.pb;
    else if(!strcmp(name,"vhwfault"))*v=s.trip_time>=0;
    else if(!strcmp(name,"vallow"))*v=s.wires.run&&s.request&&(s.trip_time<0||t<s.trip_time+s.guard_delay);
    else if(!strcmp(name,"vm")&&!s.applied.period){*v=0;}
 else if(!strcmp(name,"vm")&&s.averaged){
 double phase=((s.applied.pulse[2].rise+s.applied.period-s.applied.pulse[0].rise)%s.applied.period)/(s.applied.period/2.);
 double x=2*PI*50000*20e-6-1/(2*PI*50000*540e-9);
 *v=8/(PI*PI)*pow(sin(PI*phase/2),2)*s.rt/(s.rt*s.rt+x*x);
 }
 else if(!strcmp(name,"vm")){
        /* Smooth command edges preserve applied cycle widths; 50ns ramp is an
           explicit reduced-port assumption, not a gate-driver timing model. */
        double phase=fmod(t, PWM_DT), value[4]={0};
        for(unsigned n=0;n<4;n++) if(s.applied.pulse[n].width){
            double rise=s.applied.pulse[n].rise/80e6;
            double age=fmod(phase-rise+PWM_DT,PWM_DT);
            double width=s.applied.pulse[n].width/80e6;
            value[n]=clip(age/50e-9,0,1)*clip((width-age)/50e-9,0,1);
        }
        *v=.5*(value[0]-value[1]-value[2]+value[3]);
    }
    else {s.error=true;*v=0;}return 0;
}
static int syncfn(double t,double*d,double old,int redo,int id,int loc,void*x){(void)old;(void)redo;(void)id;(void)loc;(void)x;
    double deadline=fmin(s.next_adc,fmin(s.next_control,s.next_supervisor));
    if(s.trip_time>=0&&s.trip_time+s.guard_delay>t+1e-14)deadline=fmin(deadline,s.trip_time+s.guard_delay);

    if(t<deadline-1e-14&&t+*d>deadline)*d=deadline-t;return 0;
}
int main(int argc,char**argv){if(argc!=10){fprintf(stderr,"usage: cosim DECK OUTPUT_DIR study|inhibited|stale|readback RT VRMS RP1 RP2 GUARD_US END\n");return 2;}memset(&s,0,sizeof(s));
    s.proof_open=!strcmp(argv[3],"proof-open");s.bypass_open=!strcmp(argv[3],"bypass-open");s.bad_post=!strcmp(argv[3],"bad-post");s.averaged=true;s.study=strcmp(argv[3],"inhibited")!=0;s.inject_stale=!strcmp(argv[3],"stale");s.inject_readback=!strcmp(argv[3],"readback");s.rt=strtod(argv[4],0);s.vrms=strtod(argv[5],0);s.rp1=strtod(argv[6],0);s.rp2=strtod(argv[7],0);s.guard_delay=strtod(argv[8],0)*1e-6;s.end=strtod(argv[9],0);s.stop_at=s.end-.03;s.first_run=s.trip_time=-1;s.next_adc=ADC_DT;s.next_control=PWM_DT;s.next_supervisor=.001;s.old_state=ENERGY_OFF;
    if(mkdir(argv[2],0700)){perror("fresh output");return 2;}char p[4096];snprintf(p,sizeof p,"%s/STATUS",argv[2]);FILE*f=fopen(p,"w");fprintf(f,"INCOMPLETE\n");fclose(f);
#define OPEN(member,file) snprintf(p,sizeof p,"%s/" file,argv[2]);s.member=fopen(p,"w");if(!s.member)return 2
    s.demand_pause=!strcmp(argv[3],"demand-pause");
    s.never_demand=!strcmp(argv[3],"no-demand");
    OPEN(log,"ngspice.log");OPEN(samples,"samples.csv");OPEN(cycles,"cycles.csv");OPEN(events,"events.csv");
    fprintf(s.samples,"time_s,state,line_serial,adc_serial,bus_v,catch_v,tank_v,tank_a,line_rms_v,inlet_rms_a,conductance_s,request,run_ok,bridge_tripped,adc_valid\n");fprintf(s.cycles,"serial,time_s,solver_line_v,solver_inlet_a,sampled_line_v,sampled_inlet_a\n");fprintf(s.events,"time_s,event,state,fault\n");
    alarm(180);cold_history();ngSpice_Init(logfn,statfn,exitfn,datafn,initfn,bgfn,0);int ident=0;ngSpice_Init_Sync(vsrcfn,0,syncfn,&ident,0);
    char cmd[4096];snprintf(cmd,sizeof cmd,"source %s",argv[1]);ngSpice_Command(cmd);ngSpice_Command("run");
    snprintf(p,sizeof p,"%s/result.json",argv[2]);f=fopen(p,"w");fprintf(f,"{\"completed_time_s\":%.12g,\"accepted_steps\":%llu,\"adc_frames\":%llu,\"line_cycles\":%u,\"first_run_s\":%.9g,\"joined_run_s\":%.9g,\"load_j\":%.9g,\"unsafe_run_s\":%.9g,\"final_state\":%d,\"final_fault\":%d,\"bus_peak_v\":%.9g,\"catch_peak_v\":%.9g,\"tank_peak_v\":%.9g,\"tank_peak_a\":%.9g,\"catch_i2t\":%.9g,\"rect_i2t\":%.9g,\"pre1_j\":%.9g,\"pre2_j\":%.9g,\"pre1_peak_w\":%.9g,\"pre2_peak_w\":%.9g,\"error\":%s}\n",s.last_t,(unsigned long long)s.steps,(unsigned long long)s.adc_serial,s.measurement.serial,s.first_run,s.joined_run_s,s.load_j,s.unsafe_run_s,s.supervisor.energy.state,s.supervisor.energy.fault,s.peak_bus,s.peak_catch,s.peak_tank,s.peak_i,s.catch_i2t,s.rect_i2t,s.pre1_j,s.pre2_j,s.pre1_pk,s.pre2_pk,s.error?"true":"false");fclose(f);
    bool complete=!s.error&&s.last_t>=s.end-1e-9;snprintf(p,sizeof p,"%s/STATUS",argv[2]);f=fopen(p,"w");fprintf(f,complete?"SIMULATED_DIAGNOSTIC_ONLY\n":"INCOMPLETE\n");fclose(f);fclose(s.log);fclose(s.samples);fclose(s.cycles);fclose(s.events);return complete?0:1;
}
