# Exact-device simulation access

On 2026-09-10 the user explicitly authorized accepting TI's WEBENCH Notice
and Site Terms. The required checkbox was accepted in the TI browser UI.

WEBENCH results for 13.5–16.5 V input, 3.3 V output, 1 A maximum load and
70 °C ambient offered an enabled SIMULATE action for LMR51430XDDC at 500 kHz.
Opening it required myTI authentication. The user completed sign-in later
on September 10, and WEBENCH then displayed MY DESIGNS. Authentication is
resolved; the result below supersedes the earlier login blocker.

## Signed-in result

The host generated design ID 1, explicitly titled
`LMR51430XDDCR 13.5V-16.5V to 3.30V @ 1A`, at 70 °C ambient. The selection
card exposed an enabled SIMULATE action for the X variant at 500 kHz. Opening
it created the design but returned the Customize page. Clicking SIMULATE
there, and again on Export, displayed **“Simulation not enabled for this
design”**. The [retained screenshot](ti-webench-live/simulation-disabled.png)
captures that result.

The [complete Export-page accessibility text](ti-webench-live/export-page.txt)
contains the exact device, design ID URL, operating envelope, schematic,
BOM, charts, operating-value estimates and print/download controls. It
offers no simulation-export format or model/netlist download. No model bytes,
simulation rawfiles, export license or simulator compatibility were obtained.
This observation establishes the limitation of this exact generated design;
it does not prove that TI has no internal model or that every other design
configuration is unsupported.

The automatically selected TI circuit also differs from Temper: L1 is
4.7 µH, Cout is one 100 µF part, Cin is three 1 µF parts, and the bootstrap
and resistor MPNs differ. TI labels the operating values as estimates.
They cannot qualify the current Temper BOM or replace its raw-waveform tests.

The [public LMR51430 product page](https://www.ti.com/product/LMR51430), checked
on September 10, links the EVM, datasheet, WEBENCH and CAD libraries but does
not list a downloadable transient model. General WEBENCH documentation about
TINA-TI/PSpice export is not evidence that this device supports those exports.
The exploratory behavioral model remains unapproved.

## Selected resolution — datasheet model

After this investigation the user directed us to build and use a model from
the part's datasheet, with Luna doing the implementation. The active path keeps
LMR51430XDDCR and uses the [reusable model package](../../engineering/models/lmr51430-datasheet/README.md).
The missing WEBENCH download is no longer a dependency for model development.
The [TPS54302 screen](ti-webench-live/tps54302-candidate/README.md) is retained
as investigation history; no regulator substitution was selected.

The datasheet model supports design exploration within its documented
assumptions. Its accuracy for qualification still needs comparison evidence,
especially for unpublished control-loop behavior. Vendor authorship alone
would not establish that accuracy either.

## Optional vendor evidence

TI's supported exact X-variant transient model could supply additional
comparison evidence; a [draft request](ti-webench-live/ti-support-request-draft.md)
is prepared but has not been sent. If an artifact becomes available, preserve
model/deck bytes, permitted use, simulator version and raw outputs, then
verify the adopted BOM and all thirteen cases before reviewing an approval
receipt. A vendor-hosted simulation with no model export cannot be relabeled
as a reproducible ngspice run. A regulator substitution requires an explicit
design decision and fresh circuit/model qualification.

Entry: <https://webench.ti.com/power-designer/switching-regulator?base_pn=LMR51430&litsection=features&origin=ODS>

The public TI product page and support search did not establish a standalone
download for this exact X variant. The older support answer about XF is not
evidence that the X model cannot exist.
