#include <stdbool.h>
#include <stdio.h>
#include <math.h>
#include <string.h>
#include <stdlib.h>
#include <ngspice/sharedspice.h>
static double next=0.000256,last,max_error; static unsigned samples; static int bindex; static bool fault;
static int statfn(char*s,int i,void*x){return 0;}
static int exitfn(int a,bool b,bool c,int d,void*x){return 0;}
static int initfn(pvecinfoall a,int i,void*x){bindex=-1;for(int j=0;j<a->veccount;j++)if(!strcmp(a->vecs[j]->vecname,"b"))bindex=j;return 0;}
static int bgfn(bool b,int i,void*x){return 0;}

static int out(char *s,int id,void*x){(void)id;(void)x;puts(s);return 0;}
static int data(pvecvaluesall a,int n,int id,void*x){
 double t=0;for(int i=0;i<a->veccount;i++)if(a->vecsa[i]->is_scale)t=a->vecsa[i]->creal;
 if(t+1e-12>=next){if(fabs(t-next)>1e-10)fault=true;next+=.000256;samples++;}
 if(bindex<0)fault=true;else {if(!isfinite(a->vecsa[bindex]->creal))fault=true;double expected=1-exp(-t/.001);max_error=fmax(max_error,fabs(a->vecsa[bindex]->creal-expected));}last=t;return 0;}
static int ext(double*v,double t,char*name,int id,void*x){*v=1;return 0;}
static int syncfn(double t,double*d,double old,int redo,int id,int loc,void*x){(void)old;(void)redo;(void)id;(void)loc;(void)x;if(t<next-1e-14&&t+*d>next)*d=next-t;return 0;}
int main(){ngSpice_Init(out,statfn,exitfn,data,initfn,bgfn,0);int id=0;ngSpice_Init_Sync(ext,0,syncfn,&id,0);char *s[]={"shared test","V1 a 0 external","R1 a b 1000","C1 b 0 1u",".save v(a) v(b)",".options method=gear reltol=1e-6 abstol=1e-10",".tran 1u 2m 0 1u uic",".end",0};ngSpice_Circ(s);ngSpice_Command("run");printf("{\"last_s\":%.12g,\"max_rc_error_v\":%.12g,\"sample_deadlines\":%u,\"fault\":%s}\n",last,max_error,samples,fault?"true":"false");return fault||last<.002-1e-12||max_error>1e-5||samples!=7;}
