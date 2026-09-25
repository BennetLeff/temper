# Würth vendor-model availability

The official Würth catalog lists these electric-model packages for the WE-TORPFC series, including order code 760800301:

- LTSpice_WE-TORPFC (rev25a): <https://www.we-online.com/components/products/download/LTSpice_WE-TORPFC%20%28rev25a%29.zip>
- PSpice_WE-TORPFC (rev25a): <https://www.we-online.com/components/products/download/PSpice_WE-TORPFC%20%28rev25a%29.zip>

The official catalog and datasheet were reachable through the web research source, but direct file retrieval from this sandbox failed with DNS resolution (`curl: (6) Could not resolve host: www.we-online.com`). No vendor ZIP or PDF was saved, and no model contents were inferred from the listing. Consequently this audit makes no claim about whether the exact 760800301 model implements nonlinear DC-bias inductance, winding resistance versus temperature, core loss, or ngspice compatibility.

The availability listing itself is not a model or simulation result. No project model or circuit file was changed.
