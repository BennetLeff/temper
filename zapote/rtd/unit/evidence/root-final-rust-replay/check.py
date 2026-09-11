from pathlib import Path
import copy, hashlib, json, shutil, subprocess
root=Path('/Users/bennet/Desktop/temper/.worktrees/codex/buck-harness-experiment-plan')
base=root/'zapote/rtd/unit/evidence/acceptance-final'; out=root/'zapote/rtd/unit/evidence/root-final-rust-replay'
hashfile=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
binary=out/'zapote-rtd'; shutil.copy2(base/'zapote-rtd',binary)
data=json.loads((base/'input.json').read_text())
assert data['identity']['binary_sha256']==hashfile(binary)
assert data['identity']['board_sha256']==hashfile(root/'zapote/rtd/unit/candidate/section.kicad_pcb')
def run(name, data):
 ip=out/(name+'-input.json'); rp=out/(name+'-report.json'); ip.write_text(json.dumps(data,indent=2)+'\n')
 r=subprocess.run([str(binary),'--unit-input',str(ip),'--output',str(rp),'--no-telemetry'],capture_output=True,text=True)
 report=json.loads(rp.read_text())
 return report,{'input_sha256':hashfile(ip),'report_sha256':hashfile(rp),'exit_code':r.returncode,'stderr':r.stderr}
report, info=run('baseline',data)
assert report==json.loads((base/'report.json').read_text())
assert not [f for f in report['findings'] if f['status']=='fail']
variants={}
v=copy.deepcopy(data); v['model']['observed_faults']=[r for r in v['model']['observed_faults'] if r['name']!='sense_plus_open']; variants['missing_sense_plus']=v
v=copy.deepcopy(data); next(r for r in v['model']['observed_faults'] if r['name']=='sense_plus_open')['observed_detected']=False; variants['sense_plus_not_detected']=v
v=copy.deepcopy(data); row=next(r for r in v['model']['observed_faults'] if r['name']=='sense_plus_open'); row['observed_latency_ms']=200.0; row['observed_detect_ms']=200.0; variants['late_sense_plus']=v
v=copy.deepcopy(data); v['native']['vias']=[r for r in v['native']['vias'] if r['net']!='gnd']; variants['missing_ground_vias']=v
results={}
for name,v in variants.items():
 r,receipt=run(name,v); failures=[f for f in r['findings'] if f['status']=='fail']
 receipt['status']=r['status']; receipt['failures']=failures; results[name]=receipt
 if name == 'missing_sense_plus':
  assert r['status']=='indeterminate' and any(f['object']=='SENSE+' and f['status']=='indeterminate' for f in r['findings']), (name,r)
  receipt['required_missing_input_findings']=[f for f in r['findings'] if f['object']=='SENSE+']
 else:
  assert r['status']=='fail' and failures,(name,r)
summary={'scope':'Independent frozen final Rust replay and four input-level defect controls; no physical acceptance claimed','binary_sha256':hashfile(binary),'baseline_identical':True,'baseline':info,'baseline_status':report['status'],'baseline_indeterminate':[f for f in report['findings'] if f['status']=='indeterminate'],'mutation_results':results}
(out/'receipt.json').write_text(json.dumps(summary,indent=2)+'\n'); shutil.copy2(__file__,out/'check.py')
print(json.dumps({**summary,'mutation_results':{k:{'status':v['status'],'failures':[(f['rule'],f['object']) for f in v['failures']]} for k,v in results.items()}},indent=2))
