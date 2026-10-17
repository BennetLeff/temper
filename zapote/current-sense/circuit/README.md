# Standalone current-sense deliverable

The review entry point is [standalone_interface_contract.md](standalone_interface_contract.md).
The source proposal is [current_sense_unit.ato](current_sense_unit.ato); it is noncanonical
until the root integration copies and rebuilds it. The numerical rule is
[current_sense_model.rs](current_sense_model.rs).

Replay the model from this directory with:

```text
rustc --test current_sense_model.rs -o /tmp/current-sense-tests
/tmp/current-sense-tests
rustc current_sense_model.rs -O -o /tmp/current-sense-model
/tmp/current-sense-model > model_output.json
```

The model reports a nominal 50.116 A trip for each polarity and an enumerated
conditional 46.175–54.157 A bounded DC corner band including the 25 °C clamp
leakage, 10 MΩ host monitor load, comparator input loading, VOS, and CMRR
error. This does not establish the overall 45–55 A requirement because CT
ratio/frequency behavior, hysteresis, and other physical effects remain
outside the model. It records physical timing, CT
thermal/saturation, primary copper/terminal capability, 12.6 mm PD3 isolation,
and hardware tests as INDETERMINATE or NOT RUN. See
[source_and_datasheet_evidence.md](source_and_datasheet_evidence.md) and
[source_receipt.json](source_receipt.json) for source identities.
