# zapote-drc test fixtures

`active-rectifier-native.json` is a frozen native KiCad export of the archived
PFC active-rectifier board (`zapote/power-entry/active-rectifier/evidence/native.json`
at tag `archive/zapote-coil-intake-2026-09-25`). It is kept only as test data:
it is the one saved board with electrically unassigned pads, which the generic
`native_binding::validate` tests need. It is not product evidence.
