# STW65N65DM2AG vendor-model availability (2026-09-21)

## Result

The official ST product page confirms that an exact-part **STW65N65DM2AG PSpice
model**, version 1.0 dated 2016-01-13, is listed as a ZIP resource:

* Product page: https://www.st.com/en/power-transistors/stw65n65dm2ag.html
* Listed package URL: https://www.st.com/resource/en/spice_model/stw65n65dm2ag_spice.zip
* Primary-source search result used for this confirmation: STMicroelectronics
  product page (the page identifies the part as a 650 V, 42 mOhm typ., 60 A
  automotive N-channel MOSFET in TO-247 and exposes the exact model listing).

The exact ZIP could not be retrieved in this environment. Three direct attempts
were made, with no bytes retained. The first used the normal restricted
sandbox; the latter two were explicitly run with
`sandbox_permissions=require_escalated`, so their failures should not be read
as publisher unavailability:

1. Restricted sandbox: `curl -L --fail --silent --show-error --max-time 30 -o
   host/stw65n65dm2ag-vendor-54/stw65n65dm2ag_spice.zip
   https://www.st.com/resource/en/spice_model/stw65n65dm2ag_spice.zip`.
   Shell exit was 6 (`Could not resolve host: www.st.com`); this is an
   environment DNS failure, not evidence against ST availability.
2. Escalated: `curl --http1.1 -L --fail --silent --show-error --max-time 45 -o
   host/stw65n65dm2ag-vendor-54/stw65n65dm2ag_spice.zip
   https://www.st.com/resource/en/spice_model/stw65n65dm2ag_spice.zip`.
   The tool session returned no shell output and no file; its final shell exit
   was not surfaced by the tool wrapper, so it is recorded as **unknown**, not
   as a publisher error.
3. Escalated: the same HTTP/1.1 request with `-A 'Mozilla/5.0'` and
   `--max-time 30`. Curl explicitly returned 28 (`Operation timed out after
   30005 milliseconds with 0 bytes received`).

The web page's downloadable ZIP itself is inaccessible to the browser reader,
so the package cannot be independently hashed or extracted here. This directory
therefore intentionally contains no claimed ZIP hash, size, member list,
subcircuit name, pin order, license text, temperature behavior, encryption
status, or ngspice compatibility result. No model was executed or substituted
into the simulation.

## Consequence for the simulation claim

The current switch model remains the previously documented generic/authorial
model. The ST listing establishes availability of an exact-part vendor model,
but does **not** establish that its bytes are available locally, that it is
unencrypted, that its PSpice syntax is accepted by ngspice, or that its pin
order and temperature behavior match the present netlist. Any future use must
retain the downloaded ZIP, SHA-256, extracted text/header, and a bounded
ngspice compatibility smoke test before changing the circuit model.
