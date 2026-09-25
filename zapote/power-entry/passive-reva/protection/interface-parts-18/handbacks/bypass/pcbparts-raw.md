# PCBParts raw lookup excerpts

Queries used: `10uF 100V X7R MLCC` packages 1210/1812; `1uF 50V X7R MLCC`
packages 0805/1206/1210; `100nF 50V X7R MLCC` packages 0603/0805/1206.

Selected exact records returned by `jlc_get_part`:

```json
{"lcsc":"C49296968","model":"C3225X7R2A106KT000E","manufacturer":"TDK","package":"1210","stock":1939,"specs":{"Voltage Rating":"100V","Tolerance":"±10%","Capacitance":"10uF","Temperature Coefficient":"X7R"},"has_easyeda_footprint":true}
{"lcsc":"C386166","model":"UMK325AB7106KMHP","manufacturer":"Taiyo Yuden","package":"1210","stock":186038,"specs":{"Voltage Rating":"50V","Tolerance":"±10%","Capacitance":"10uF","Temperature Coefficient":"X7R"},"has_easyeda_footprint":true}
{"lcsc":"C1848","model":"CL31B105KBHNNNE","manufacturer":"Samsung Electro-Mechanics","package":"1206","stock":658419,"specs":{"Voltage Rating":"50V","Tolerance":"±10%","Capacitance":"1uF","Temperature Coefficient":"X7R"},"has_easyeda_footprint":true}
{"lcsc":"C28323","model":"CL21B105KBFNNNE","manufacturer":"Samsung Electro-Mechanics","package":"0805","stock":2717807,"specs":{"Voltage Rating":"50V","Tolerance":"±10%","Capacitance":"1uF","Temperature Coefficient":"X7R"},"has_easyeda_footprint":true}
{"lcsc":"C24497","model":"CL31B104KBCNNNC","manufacturer":"Samsung Electro-Mechanics","package":"1206","stock":1952583,"specs":{"Voltage Rating":"50V","Tolerance":"±10%","Capacitance":"100nF","Temperature Coefficient":"X7R"},"has_easyeda_footprint":true}
{"lcsc":"C28233","model":"CL21B104KCFNNNE","manufacturer":"Samsung Electro-Mechanics","package":"0805","stock":1831579,"specs":{"Voltage Rating":"100V","Tolerance":"±10%","Capacitance":"100nF","Temperature Coefficient":"X7R"},"has_easyeda_footprint":true}
{"mpn":"C0805C105K5RACTU","lcsc":"C3018567","manufacturer":"KEMET","package":"0805","stock":1960,"specs":{"Voltage Rating":"50V","Tolerance":"±10%","Capacitance":"1uF","Temperature Coefficient":"X7R"}}
```

The MCP records contain stock/metadata and (for some parts) LCSC datasheet
URLs, but no effective-capacitance guarantee; those omissions are deliberate in
the handback.
