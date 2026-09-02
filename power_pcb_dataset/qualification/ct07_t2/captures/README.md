# CT07 U5/U9 raw captures

This directory is intentionally empty of representative hardware captures.
U6 is stopped-indeterminate (`pending-u6-freeze`) because the required five
serialized assemblies from two independently built lots do not exist. A
capture may be added only after the U6 construction digest and this protocol
revision are frozen.

Each capture directory must contain `manifest.json` and `waveform.json` with
the same capture, construction, protocol, sample, lot, calibration, and raw
buffer identities. The Rust CT07 kernel replays the normalized waveform and
derives all numeric axes; callers may not submit precomputed pass/fail values.

U9 post-stress records use the `u9_manifest.json` and `u9_waveform.json`
templates. Each record names one required checkpoint and one serialized
sample. The Rust U9 evaluator requires the complete R2-R12
sample/checkpoint matrix and every production-control challenge before it can
return `pass`. Templates are placeholders only and contain no sample, stress,
repair, or control result.
