"""Negative checks for reported fixture verdicts, not model self-consistency."""
from __future__ import annotations
from report import extra_fixture_outcome
from run import HERE, dump

base={'status':'COMPLETED','what':'dis','corner':0,'disable_ns':48.0,'reenable_ns':48.0}
cases={
 'valid':(base,'PASS'),
 'aborted':(dict(base,status='INDETERMINATE'),'INDETERMINATE'),
 'missing_measurement':({k:v for k,v in base.items() if k!='disable_ns'},'FAIL'),
 'out_of_tolerance':(dict(base,disable_ns=50),'FAIL'),
 'overlap_wrong_high':({'status':'COMPLETED','what':'overlap','corner':0,'other_output_peak_V':12,'disable_ns':33},'FAIL'),
}
results={}
for name,(row,expected) in cases.items():
    actual,_=extra_fixture_outcome(row)
    assert actual==expected,(name,actual,expected)
    results[name]={'actual':actual,'expected':expected,'pass':True}
dump(HERE/'reporting-negative-checks.json',results)
print('PASS: valid fixture, aborted fixture, missing measurement, mismatch, and failed overlap reporting')
