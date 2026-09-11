# Murata live data retrieval — 2026-09-10

The user explicitly authorized accepting Murata SimSurfing's terms, and the
host accepted the displayed agreement. The tool loaded its 2026-09-02 catalog.
This follow-up supersedes the earlier blanket statement that the Murata
capacitor curves were unavailable. No BOM, frozen contract or approved registry
was changed.

## C11/C12: exact part found and curves retrieved

The live catalog returned one exact base-part match for `GRM32ER71E226KE15`:
in production, 22 uF, 25 V, X7R, 1210, maximum thickness 2.7 mm, +/-10%.
Packaging suffix L is already independently identified in the retained TI EVM
BOM; SimSurfing models the base part rather than packaging variants.

The UI displayed capacitance-versus-bias curves at 25°C with both available
AC amplitudes, 0.5 Vrms and 0.01 Vrms. The low-amplitude curve is the more
relevant screening condition for small rail ripple; these conditions must not
be conflated. The host also requested capacitance versus temperature at
3.465 V DC and 0.01 Vrms AC. The browser's CSV action did not return a usable
local file path, so the exact observed numerical-response endpoint was fetched
directly and retained as JSON instead. No curve was digitized from a screenshot.

| Condition | Typical capacitance per part | Two-part total |
|---|---:|---:|
| 3.3 V, 25°C, 0.01 Vrms | approximately 17.03 uF | approximately 34.05 uF |
| 3.465 V, 0°C, 0.01 Vrms | 15.2885 uF | 30.5769 uF |
| 3.465 V, 25°C, 0.01 Vrms | 16.9117 uF | 33.8234 uF |
| 3.465 V, 70°C, 0.01 Vrms | 19.6239 uF | 39.2477 uF |
| 3.465 V, 105°C, 0.01 Vrms | 18.8175 uF | 37.6350 uF |

The 3.3 V entry is linear interpolation between the 3.25 and 3.375 V samples;
the temperature entries are direct response samples. The sampled minimum
over both 0–70°C and 0–105°C at 3.465 V is at 0°C, 15.2885 uF per part.
Those are component temperatures; ambient temperature is not automatically
component temperature. C13's parallel 100 nF was omitted from these totals.

This is typical vendor-model evidence. It does not include a proven production
minimum, aging allowance, or a complete converter ripple/transient result.
Applying an extra tolerance factor would be an explicit engineering assumption,
not a new manufacturer guarantee. Do not score the component qualification as
passed merely because the data are now available.

TI's LMR51430 Rev. A Table 9-1 recommends nominal 5.6 uH and two 22 uF/25 V
ceramics for 3.3 V at 500 kHz, matching the nominal output network. It does not
say that 44 uF must remain after all derating. These retrieved curves provide
a credible basis for the next model sensitivity analysis; they provide no
present reason to replace the output capacitors solely because of data access.

## C9: exact identity remains unverified

The same live part filter returned **zero matches** for the current base MPN
`GRM32ER71E106KA12`. Murata's published model inventory lists
`GRM32DR71E106KA12` as 10 uF/25 V/X7R/1210, but this is a different part:
the E/D thickness code cannot be silently changed or treated as equivalent.
Zero matches do not prove the current MPN never existed; they do mean we have
not validated it as the intended orderable component.

The [repository provenance audit](c9-provenance.md) traces the current MPN to
`ded9c25422283979f759be82ea1ecb59af69c52b` during the July 15 buck redesign.
Subsequent BOM, stress limits and harness artifacts repeat that source string.
The audit found no retained exact manufacturer evidence establishing it.
Earlier statements that all Murata nominal identities were supported were too
broad: C9 remains a source-declared, unverified identity.

Resolve C9's identity before attempting a bias calculation for it. If an exact
manufacturer confirmation cannot be obtained, qualify a documented orderable
replacement explicitly. TI section 9.2.2.6 recommends an input-capacitor voltage
rating of twice maximum VIN to allow for derating: for 16.5 V maximum, that
points toward at least a 35 V rated candidate. This is application guidance,
not an absolute minimum rating; actual effective capacitance and input ripple
still determine suitability. No replacement has been selected here.

## Retained data and reproduction

Endpoint: `https://ds.murata.com/simserve/characteristics`

Requests used GET fields `callback=nothing`, `ReqType=Characteristics`,
`CallBack=mycallback`, and `ReqChara` containing a one-element JSON array.
Each array entry used `partnumber=GRM32ER71E226KE15`, the following
`chara_type` and `parameter` object, plus UI WorkInfo (`color=#ea002a`,
`supply_status=B`, `graph_set_y_name` empty). The response's `error` fields
are empty. `data` stores each coordinate in a singleton array; capacitance
uses `y_unit=F` and `y_subunit=u`, so its numeric values are in microfarads.

| File | chara_type | parameter | Samples |
|---|---|---|---:|
| [cout-bias-25.json](cout-bias-25.json) | c_dcbias_capacitance | tc=25, ac=0.5 | 201 |
| [cout-bias-25-lowac.json](cout-bias-25-lowac.json) | c_dcbias_capacitance | tc=25, ac=0.01 | 201 |
| [cout-temperature-3v465-lowac.json](cout-temperature-3v465-lowac.json) | c_temp_capacitance_capchange | dc=3.465, ac=0.01 | 361 |

SHA-256:

```text
9feebea0f44f8a3edc898f1e43e0aade53ff75f16b71be7d9e21523c52cba628  cout-bias-25.json
6f47cf05dc55fd7ead0a41ae8970d7dd6abf80320f97010c047faf7f77c2c292  cout-bias-25-lowac.json
4072aee1f55057c4e64c12bdb1ed856fcad18bfdf9ac2686d9fc96d462a537d0  cout-temperature-3v465-lowac.json
```

Primary sources:

- [Murata SimSurfing](https://ds.murata.com/simsurfing/mlcc.html)
- [Murata explanation of bias and temperature models](https://www.murata.com/en-us/tool/help)
- [Murata model part-number inventory](https://www.murata.com/-/media/webrenewal/tool/library/common-pdf/dynamic-model/component-list-d-mlcc-2504.ashx?cvid=20250523010405000000&la=en)
- [TI LMR51430 datasheet, Table 9-1 and section 9.2.2.6](https://www.ti.com/lit/ds/symlink/lmr51430.pdf)
