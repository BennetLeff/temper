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
#include "sampled_measurement.h"
#include "fast_capture.h"
#define PI 3.14159265358979323846
#define ADC_DT .000256
#define PWM_DT .00002
#define OFFSET_MS 61000u
#define MAX_NODES 32
static struct {
    FILE *log,*samples,*cycles,*events; bool error,study,inject_stale,inject_capture,averaged,proof_open,bypass_open,bad_post;
    double next_adc,next_control,next_supervisor,guard_delay,end,vrms,rt,last_t,last_v[MAX_NODES];
    double physical[8];bool sampled_valid;uint32_t sampled_us,capture_serial;
    sampled_measurement_t measurement;fast_capture_receiver_t capture;
    double v[MAX_NODES],line_v,line_i,cycle_v2,cycle_i2,cycle_duration;
    double ktime,btime,ptime,contacts,bypass,proof,trip_time;
    double peak_bus,peak_catch,peak_tank,peak_i,catch_i2t,rect_i2t,pre1_j,pre2_j,pre1_pk,pre2_pk;
    double rp1,rp2,first_run,stop_at;
    uint64_t adc_serial,steps;int name_index[MAX_NODES];
    bool old_k,old_b,old_p,request,hw_latch,charge_seen,precharge_ok;
    bool bypass_electrical,catch_proven;
    bridge_cycle_t applied,pending;bool have_pending;
    fullbridge_adapter_t bridge; energy_supervisor_t energy; ads_receiver_t ads;
    energy_state_t old_state;
} s;
enum {TIME,SRC,MAINS,PRE,LI,BUS,CATCH,TANK,VPRE,IPROOF,ILINE,ITANK,ICATCH,IRECT,MID,DA,MOD,ALLOW,BYPASS,CONTACTS,NV};
static const char *names[NV]={"time","src","mains","pre","li","bp","catch","ct","vpre","iproof","lsrc#branch","lcoil#branch","lcatch#branch","vsense#branch","mid","da","m","allow","bypass","contacts"};
static bool apply(void*x,const bridge_cycle_t*c){(void)x;s.pending=*c;s.have_pending=true;return true;}
static bool request(void*x,bool on){(void)x;s.request=on;return true;}
static void inhibit(void*x){(void)x;s.request=false;}
static double clip(double x,double lo,double hi){return fmax(lo,fmin(hi,x));}
static int logfn(char *text,int id,void*x){(void)id;(void)x;fprintf(s.log,"%s\n",text);if(strstr(text,"timestep too small")||strstr(text,"Error:"))s.error=true;return 0;}
static int statfn(char*x,int id,void*c){(void)x;(void)id;(void)c;return 0;}
static int exitfn(int code,bool immediate,bool quit,int id,void*x){(void)immediate;(void)quit;(void)id;(void)x;if(code)s.error=true;return 0;}
static int bgfn(bool running,int id,void*x){(void)running;(void)id;(void)x;return 0;}
static int initfn(pvecinfoall a,int id,void*x){(void)id;(void)x;for(int n=0;n<NV;n++){s.name_index[n]=-1;for(int j=0;j<a->veccount;j++)if(!strcmp(a->vecs[j]->vecname,names[n]))s.name_index[n]=j;if(s.name_index[n]<0){fprintf(s.log,"MISSING %s\n",names[n]);s.error=true;}}return 0;}
static void trace_state(double t){if(s.energy.state!=s.old_state){fprintf(s.events,"%.9f,state,%d,%d\n",t,s.energy.state,s.energy.fault);s.old_state=s.energy.state;}}
static void cold_history(void){
    energy_config_t cfg=energy_study_config();cfg.commissioned=s.study;cfg.bus_max_v=230;cfg.catch_max_v=250;cfg.tank_max_v=1000;
    energy_supervisor_init(&s.energy,&cfg,0);
    /* Explicit simulated unpowered prehistory; does not erase analog stored energy. */
    for(uint32_t ms=0;ms<=OFFSET_MS;ms++){
        energy_inputs_t i={.now_ms=ms,.sampled_ms=ms,.stop_ok=true,.aux_ok=true,.sensors_valid=true,.hardware_ok=true,
        .k1_released=true,.k2_released=true,.kb_released=true,.resistor_cool=true,.receiver_ok=true};
        energy_supervisor_step(&s.energy,&i);
    }
    bridge_config_t bc={.timer_hz=80000000,.frequency_hz=50000,.input_deadtime_ns=125,.capture_age_us=1000,
    .max_power_w=1500,.inlet_target_a=13.5,.auxiliary_reserve_w=25,.commissioned=s.study};
    bridge_backend_t ops={apply,request,inhibit,0};
    fullbridge_init(&s.bridge,&bc,&ops);s.applied=s.bridge.cycle;
    if(s.study)fullbridge_request(&s.bridge,1500);
}
static void adc_event(double t){
    uint32_t us=(uint32_t)llround(t*1e6);
    bool stale=s.inject_stale && t>.4;
    /* The ADC serial/parser is exercised with explicit ideal calibrated sensor
       stimulus; no analog scale/noise/reference calibration is thereby proven. */
    uint8_t frame[ADS_FRAME_BYTES]={1,255};double physical[8]={s.v[SRC]/250,s.v[VPRE]/250,s.v[LI]/250,s.v[BUS]/1000,s.v[CATCH]/1000,s.v[TANK]/2000,s.v[IPROOF]/10,s.v[ILINE]/300};
    for(unsigned ch=0;ch<8;ch++){int32_t code=(int32_t)llround(clip(physical[ch],-.999,.999)*8388607);uint32_t u=(uint32_t)code&0xffffff;frame[3+3*ch]=u>>16;frame[4+3*ch]=u>>8;frame[5+3*ch]=u;}
    uint16_t crc=ads_crc16(frame,27);frame[27]=crc>>8;frame[28]=crc;ads_sample_t decoded={0};
    bool valid=!stale&&ads_accept(&s.ads,frame,us,us,&decoded);
    s.adc_serial++;
    static const double scale[8]={250,250,250,1000,1000,2000,10,300};
    if(valid){
        for(unsigned n=0;n<8;n++)s.physical[n]=decoded.code[n]/8388607.*scale[n];
        valid=sampled_measurement_add(&s.measurement,us,s.physical,s.proof>.999,s.contacts>.999);
        if(s.measurement.complete){
            s.line_v=s.measurement.rms[0];s.line_i=s.measurement.rms[7];
            fprintf(s.cycles,"%u,%.9f,%.9g,%.9g,%.9g,%.9g\n",s.measurement.serial,t,sqrt(s.cycle_v2/s.cycle_duration),sqrt(s.cycle_i2/s.cycle_duration),s.line_v,s.line_i);
            s.cycle_v2=s.cycle_i2=s.cycle_duration=0;
            if(s.study&&s.energy.state>=ENERGY_RAIL_QUALIFY&&s.energy.state<=ENERGY_RUN&&!s.bridge.tripped)
                fullbridge_line_cycle(&s.bridge,us,s.line_v,s.line_i,1500);
        }
    }
    s.sampled_valid=valid;s.sampled_us=us;s.precharge_ok=s.measurement.precharge_ok;
}
static void be32(uint8_t *p,uint32_t v){p[0]=v>>24;p[1]=v>>16;p[2]=v>>8;p[3]=v;}
static void controller_event(double t){
    uint32_t us=(uint32_t)llround(t*1e6),ms=OFFSET_MS+us/1000;
    bool valid=s.sampled_valid&&ads_fresh(&s.ads,us);
    if(s.physical[3]>100&&s.physical[4]>90)s.charge_seen=true;
    bool correlated=catch_correlates((float)s.physical[3],(float)s.physical[4],5,3,s.study,s.charge_seen);
    if(s.energy.state==ENERGY_PRECHARGE&&correlated&&s.precharge_ok)s.catch_proven=true;
    s.bypass_electrical=s.bypass>.999&&!s.bypass_open&&fabs(s.physical[1])<1.;
    bool proof_valid=s.proof>.999&&s.measurement.proof_ok&&s.bypass_electrical;
    if(us>=56000 && us<57000 && s.energy.out.reset_ok)s.hw_latch=true;
    if(s.v[BUS]>=230||s.v[CATCH]>=250||fabs(s.v[TANK])>=1000||fabs(s.v[ITANK])>=85){if(s.trip_time<0)s.trip_time=t;}
    bool hardware_ok=s.trip_time<0;
    bool capture_ok=!(s.inject_capture&&t>.4);
    energy_inputs_t in={.now_ms=ms,.sampled_ms=OFFSET_MS+s.sampled_us/1000,.manual_post_serial=1,.start=us>=60000&&us<61000,.reset=us>=56000&&us<57000,
    .off_request=t>=s.stop_at,.stop_ok=true,.aux_ok=true,.sensors_valid=valid,.hardware_ok=hardware_ok,.hardware_latch_ok=s.hw_latch,
    .catch_charge_proven=s.catch_proven,.k1_released=s.contacts<.001,.k2_released=s.contacts<.001,.kb_released=s.bypass<.001,
    .manual_post_ok=!s.bad_post,.resistor_cool=true,.receiver_ok=true,.precharge_complete=s.precharge_ok,
    .bypass_closed_electrically=s.bypass_electrical,.proof_current_valid=proof_valid,.rails_ok=s.bypass_electrical,
    .bus_fault=!hardware_ok,.interlock_ok=hardware_ok,.controller_alive=true,.pwm_qualified=capture_ok,
    .heat_request=s.request,.valid_line_cycles=(uint8_t)(s.measurement.serial>255?255:s.measurement.serial),.bus_v=fmax(0,s.physical[3]),
    .catch_v=fmax(0,s.physical[4]),.tank_abs_v=fabs(s.physical[5]),.line_rms_v=s.line_v,.inlet_rms_a=s.line_i};
    energy_supervisor_step(&s.energy,&in);trace_state(t);
    uint8_t capture[FAST_CAPTURE_BYTES]={0};be32(capture,0x54464331);capture[4]=1;capture[5]=15;capture[7]=92;
    be32(capture+8,++s.capture_serial);be32(capture+12,80000000);
    for(unsigned n=0;n<4;n++){be32(capture+24+4*n,s.applied.period);be32(capture+40+4*n,s.applied.pulse[n].width);be32(capture+56+4*n,s.applied.pulse[n].rise);be32(capture+72+4*n,s.applied.dead_ticks);}
    be32(capture+88,fast_crc32(capture,88));if(!capture_ok)capture[10]^=1;
    bridge_feedback_t fb={0};capture_ok=fast_capture_accept(&s.capture,capture,sizeof capture,us,us,&fb);
    fb.rails_ok=s.bypass_electrical;fb.sup_run_ok=s.energy.out.sup_run_ok;fb.interlock_ok=hardware_ok;fb.bus_fault=!hardware_ok;
    double reactance=2*PI*50000*20e-6-1/(2*PI*50000*540e-9);
    double phase=2*asin(fmin(.98,sqrt(fmax(0,s.bridge.conductance_s)*(s.rt*s.rt+reactance*reactance)/s.rt*PI*PI/8)))/PI;
    if(s.study&&s.bypass_electrical&&s.measurement.serial>=2&&s.bridge.have_line&&!s.bridge.tripped)fullbridge_apply(&s.bridge,us,&fb,(float)phase);
    if(s.energy.state==ENERGY_FAULT||s.energy.state==ENERGY_DISCHARGE)fullbridge_stop(&s.bridge);
    if(s.energy.out.k1!=s.old_k){s.ktime=t;s.old_k=s.energy.out.k1;}
    if(s.energy.out.kb!=s.old_b){s.btime=t;s.old_b=s.energy.out.kb;}
    if(s.energy.out.kt!=s.old_p){s.ptime=t;s.old_p=s.energy.out.kt;}
    if(s.energy.state==ENERGY_RUN&&s.first_run<0)s.first_run=t;
    fprintf(s.samples,"%.9f,%d,%u,%u,%.9g,%.9g,%.9g,%.9g,%.9g,%.9g,%.9g,%d,%d,%d,%d\n",t,s.energy.state,s.measurement.serial,(unsigned)s.adc_serial,s.v[BUS],s.v[CATCH],s.v[TANK],s.v[ITANK],s.line_v,s.line_i,s.bridge.conductance_s,s.request,s.energy.out.sup_run_ok,s.bridge.tripped,valid);
}
static int datafn(pvecvaluesall a,int count,int id,void*x){
    (void)count;(void)id;(void)x;if(s.error)return 0;
    for(int n=0;n<NV;n++){if(s.name_index[n]<0)return 0;s.v[n]=a->vecsa[s.name_index[n]]->creal;if(!isfinite(s.v[n])){s.error=true;return 0;}}
    double t=s.v[TIME],dt=t-s.last_t;
    if(s.trip_time<0&&(s.v[BUS]>=230||s.v[CATCH]>=250||fabs(s.v[TANK])>=1000||fabs(s.v[ITANK])>=85))s.trip_time=t;if(dt<0){s.error=true;return 0;}s.steps++;if(s.steps>5000000){s.error=true;ngSpice_Command("stop");return 0;}
    if(dt>0){s.cycle_v2+=.5*(s.last_v[SRC]*s.last_v[SRC]+s.v[SRC]*s.v[SRC])*dt;s.cycle_i2+=.5*(s.last_v[ILINE]*s.last_v[ILINE]+s.v[ILINE]*s.v[ILINE])*dt;s.cycle_duration+=dt;
    double pp=.5*(s.last_v[VPRE]*s.last_v[VPRE]+s.v[VPRE]*s.v[VPRE]);s.pre1_j+=pp/s.rp1*dt;s.pre2_j+=pp/s.rp2*dt;
    s.catch_i2t+=.5*(s.last_v[ICATCH]*s.last_v[ICATCH]+s.v[ICATCH]*s.v[ICATCH])*dt;s.rect_i2t+=.5*(s.last_v[IRECT]*s.last_v[IRECT]+s.v[IRECT]*s.v[IRECT])*dt;}
    s.peak_bus=fmax(s.peak_bus,s.v[BUS]);s.peak_catch=fmax(s.peak_catch,s.v[CATCH]);s.peak_tank=fmax(s.peak_tank,fabs(s.v[TANK]));s.peak_i=fmax(s.peak_i,fabs(s.v[ITANK]));s.pre1_pk=fmax(s.pre1_pk,s.v[VPRE]*s.v[VPRE]/s.rp1);s.pre2_pk=fmax(s.pre2_pk,s.v[VPRE]*s.v[VPRE]/s.rp2);
    if(t>=s.next_control-1e-12){if(s.have_pending){s.applied=s.pending;s.have_pending=false;}s.next_control=(floor(t/PWM_DT+1e-7)+1)*PWM_DT;}
    if(t>=s.next_adc-1e-12){adc_event(t);s.next_adc=(s.adc_serial+1)*ADC_DT;}
    if(t>=s.next_supervisor-1e-12){controller_event(t);s.next_supervisor=(floor(t/.001+1e-7)+1)*.001;}
    memcpy(s.last_v,s.v,sizeof(s.v));s.last_t=t;return 0;
}
static double transition(double t,double since,bool on,double delay){double z=clip((t-since-delay)/100e-6,0,1);return on?z:1-z;}
static int vsrcfn(double *v,double t,char*name,int id,void*x){(void)id;(void)x;
    s.contacts=s.old_k?transition(t,s.ktime,true,.020):(s.ktime>0?transition(t,s.ktime,false,.024):0);
    s.bypass=s.old_b?transition(t,s.btime,true,.020):(s.btime>0?transition(t,s.btime,false,.020):0);
    s.proof=s.old_p?transition(t,s.ptime,true,.001):(s.ptime>0?transition(t,s.ptime,false,.001):0);
    if(!strcmp(name,"vcontacts"))*v=s.contacts;
    else if(!strcmp(name,"vbypass"))*v=s.bypass_open?0:s.bypass;
    else if(!strcmp(name,"vproof"))*v=s.proof_open?0:s.proof;
    else if(!strcmp(name,"vhwfault"))*v=s.trip_time>=0;
    else if(!strcmp(name,"vallow"))*v=s.energy.out.sup_run_ok&&s.request&&(s.trip_time<0||t<s.trip_time+s.guard_delay);
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
int main(int argc,char**argv){if(argc!=10){fprintf(stderr,"usage: cosim DECK OUTPUT_DIR study|inhibited|stale|capture RT VRMS RP1 RP2 GUARD_US END\n");return 2;}memset(&s,0,sizeof(s));
    s.proof_open=!strcmp(argv[3],"proof-open");s.bypass_open=!strcmp(argv[3],"bypass-open");s.bad_post=!strcmp(argv[3],"bad-post");s.averaged=true;s.study=strcmp(argv[3],"inhibited")!=0;s.inject_stale=!strcmp(argv[3],"stale");s.inject_capture=!strcmp(argv[3],"capture");s.rt=strtod(argv[4],0);s.vrms=strtod(argv[5],0);s.rp1=strtod(argv[6],0);s.rp2=strtod(argv[7],0);s.guard_delay=strtod(argv[8],0)*1e-6;s.end=strtod(argv[9],0);s.stop_at=s.end-.03;s.first_run=s.trip_time=-1;s.next_adc=ADC_DT;s.next_control=PWM_DT;s.next_supervisor=.001;s.old_state=ENERGY_OFF;
    if(mkdir(argv[2],0700)){perror("fresh output");return 2;}char p[4096];snprintf(p,sizeof p,"%s/STATUS",argv[2]);FILE*f=fopen(p,"w");fprintf(f,"INCOMPLETE\n");fclose(f);
#define OPEN(member,file) snprintf(p,sizeof p,"%s/" file,argv[2]);s.member=fopen(p,"w");if(!s.member)return 2
    OPEN(log,"ngspice.log");OPEN(samples,"samples.csv");OPEN(cycles,"cycles.csv");OPEN(events,"events.csv");
    fprintf(s.samples,"time_s,state,line_serial,adc_serial,bus_v,catch_v,tank_v,tank_a,line_rms_v,inlet_rms_a,conductance_s,request,run_ok,bridge_tripped,adc_valid\n");fprintf(s.cycles,"serial,time_s,solver_line_v,solver_inlet_a,sampled_line_v,sampled_inlet_a\n");fprintf(s.events,"time_s,event,state,fault\n");
    alarm(180);cold_history();ngSpice_Init(logfn,statfn,exitfn,datafn,initfn,bgfn,0);int ident=0;ngSpice_Init_Sync(vsrcfn,0,syncfn,&ident,0);
    char cmd[4096];snprintf(cmd,sizeof cmd,"source %s",argv[1]);ngSpice_Command(cmd);ngSpice_Command("run");
    snprintf(p,sizeof p,"%s/result.json",argv[2]);f=fopen(p,"w");fprintf(f,"{\"completed_time_s\":%.12g,\"accepted_steps\":%llu,\"adc_frames\":%llu,\"line_cycles\":%u,\"first_run_s\":%.9g,\"final_state\":%d,\"final_fault\":%d,\"bus_peak_v\":%.9g,\"catch_peak_v\":%.9g,\"tank_peak_v\":%.9g,\"tank_peak_a\":%.9g,\"catch_i2t\":%.9g,\"rect_i2t\":%.9g,\"pre1_j\":%.9g,\"pre2_j\":%.9g,\"pre1_peak_w\":%.9g,\"pre2_peak_w\":%.9g,\"error\":%s}\n",s.last_t,(unsigned long long)s.steps,(unsigned long long)s.adc_serial,s.measurement.serial,s.first_run,s.energy.state,s.energy.fault,s.peak_bus,s.peak_catch,s.peak_tank,s.peak_i,s.catch_i2t,s.rect_i2t,s.pre1_j,s.pre2_j,s.pre1_pk,s.pre2_pk,s.error?"true":"false");fclose(f);
    bool complete=!s.error&&s.last_t>=s.end-1e-9;snprintf(p,sizeof p,"%s/STATUS",argv[2]);f=fopen(p,"w");fprintf(f,complete?"SIMULATED_DIAGNOSTIC_ONLY\n":"INCOMPLETE\n");fclose(f);fclose(s.log);fclose(s.samples);fclose(s.cycles);fclose(s.events);return complete?0:1;
}
