#!/usr/bin/env python3
"""Keep reference-mismatch cases separate from positive nominal intervals."""
from __future__ import annotations
import json
from pathlib import Path
HERE=Path(__file__).resolve().parent
p=HERE/'outputs'
d=json.loads((p/'ct_sweep.json').read_text())
r=d['rows']
v=json.loads((p/'timestep.json').read_text())
s={'cases':len(r),'independent_analog_runs':len({x['analog_run'] for x in r}),
   'reference_cases':len(d['reference_comparisons']),
   'max_original_reference_error_ns':max(abs(x) for c in d['reference_comparisons'] for x in c['delta_ns'].values()),
   'max_half_step_error_ns':v['maximum_crossing_change_ns'],
   'positive_nominal_reference_intervals_ns':[min(x['detection_delay_ns'] for x in r if x['detection_delay_ns']>=0),max(x['detection_delay_ns'] for x in r)],
   'threshold_reference_mismatches':[x for x in r if x['detection_delay_ns']<0],
   'max_absolute_primary_at_model_trip_a':max(abs(x['primary_at_detection_a']) for x in r),
   'verdict':'BLOCKED for physical protection; numerical CT grid complete under fixed-delay assumption'}
(p/'summary.json').write_text(json.dumps(s,indent=2)+'\n')
