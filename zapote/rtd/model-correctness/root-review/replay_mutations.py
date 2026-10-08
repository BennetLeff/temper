#!/usr/bin/env python3
"""Exercise the compiled validator on the real bound unit, including hostile receipts."""
from __future__ import annotations
import copy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile

HERE = Path(__file__).resolve().parent
RULE = 'ERC.RTD.MODEL_QUALIFICATION'
DEVICE = 'ERC.RTD.MODEL_DEVICE_APPLICABILITY'


def main(binary: Path) -> None:
    base = json.loads((HERE.parent / 'qualified-input/input.json').read_text())
    rows = []
    mutations = [('valid', (), None, 'pass')]
    for field in ['model_source_artifact_utf8', 'model_artifact_utf8', 'cases']:
        mutations.append(('missing_' + field, ('model_qualification',field), None,'fail'))
    mutations.extend([
        ('missing_receipt',('model_qualification',),None,'indeterminate'),
        ('wrong_schema',('model_qualification','schema'),'invented','fail'),
        ('raw_model_drift',('model_qualification','model_artifact_utf8'),'{}','fail'),
        ('raw_source_drift',('model_qualification','model_source_artifact_utf8'),'changed','fail'),
        ('forged_device_pass',('model_qualification','device_applicability','status'),'PASS','pass'),
        ('over_budget_observation',('model_qualification','cases',0,'observed','latency_ms'),3.0,'fail'),
        ('not_detected',('model_qualification','cases',0,'observed','detected'),False,'fail'),
        ('zero_bound',('model_qualification','cases',0,'derived','bound_ms'),0,'fail'),
        ('zero_energy',('model_qualification','cases',2,'derived','energy_max'),0,'fail'),
        ('zero_c_matrix',('model_qualification','cases',2,'derived','c_max'),[[0,0],[0,0]],'fail'),
        ('negative_budget',('model_qualification','allocations','max_detect_ms'),-1,'fail'),
        ('smaller_declared_budget',('model_qualification','allocations','max_detect_ms'),.001,'fail'),
        ('inconsistent_reference_voltage',('model_qualification','reference_envelope','vref_v'),[0,0],'fail'),
        ('larger_reference_drift',('model_qualification','reference_envelope','drift_ppm_per_c'),80,'fail'),
    ])
    for field,value in [('cdiff_f',[0,0]),('cdiff_f',[.94e-9,1e-9]),('cground_p_f',[0,0]),('cground_m_f',[0,0]),('i_max_p_a',0),('i_window_a',0),('offset_v',0),('rref_ohm',[-1,430.3440645]),('rref_ohm',[400,500]),('rtd_short_ohm',[1,10]),('lead_sp_ohm',[1,1]),('rref_ohm','malformed')]:
        mutations.append((f'envelope_{field}_{value}',('model_qualification','parameter_envelope',field),value,'fail'))
    with tempfile.TemporaryDirectory(prefix='rtd-qualification-replay-') as tmp:
        tmp=Path(tmp)
        for name,path,value,expected in mutations + [('missing_case',(),None,'fail'),('duplicate_case',(),None,'fail'),('coordinated_source_change',(),None,'fail'),('rehash_wrong_runtime_model',(),None,'fail')]:
            data=copy.deepcopy(base)
            if path:
                obj=data
                for p in path[:-1]:obj=obj[p]
                if value is None:del obj[path[-1]]
                else:obj[path[-1]]=value
            elif name=='missing_case':data['model_qualification']['cases'].pop()
            elif name=='duplicate_case':data['model_qualification']['cases'][4]=data['model_qualification']['cases'][0]
            elif name=='coordinated_source_change':
                data['identity']['source_manifest_sha256']='c'*64
                data['model_qualification']['source_hashes']['source_manifest_sha256']='c'*64
                data['model_qualification']['source_hashes']['topology_source_sha256']='c'*64
            elif name=='rehash_wrong_runtime_model':
                data['model']['observed_faults'][0]['bound_ms']=.000001
                raw=json.dumps(data['model'])
                digest=hashlib.sha256(raw.encode()).hexdigest()
                data['model_qualification']['model_artifact_utf8']=raw
                data['model_qualification']['model_sha256']=digest
                data['identity']['model_sha256']=digest
            (tmp/'input.json').write_text(json.dumps(data))
            result=subprocess.run([str(binary),'--unit-input',str(tmp/'input.json'),'--output',str(tmp/'report.json')],capture_output=True,text=True)
            assert result.returncode in (0,1),(name,result.returncode,result.stderr)
            report=json.loads((tmp/'report.json').read_text())
            findings=[f for f in report['findings'] if f['rule']==RULE]
            assert findings and all(f['status']==expected for f in findings),(name,expected,findings)
            if expected=='pass':assert any(f['rule']==DEVICE and f['status']=='indeterminate' for f in report['findings']),name
            rows.append({'case':name,'expected':expected,'observed':sorted({f['status'] for f in findings}),'exit_code':result.returncode})
    receipt={'binary_sha256':hashlib.sha256(binary.read_bytes()).hexdigest(),'input_sha256':hashlib.sha256((HERE.parent/'qualified-input/input.json').read_bytes()).hexdigest(),'cases':rows,'all_expectations_met':True}
    (HERE/'mutation-replay.json').write_text(json.dumps(receipt,indent=2)+'\n')
    print(f'{len(rows)} compiled-validator scenarios matched expected results')


if __name__=='__main__':main(Path(sys.argv[1]).resolve())
