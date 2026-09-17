# Source register

| ID | Primary source | Exact identity and pages | SHA-256 / status | Conditions or use |
|---|---|---|---|---|
| TI-TIDA-00779 | https://www.ti.com/lit/ug/tidube1d/tidube1d.pdf | TIDUBE1D Rev D, revised Aug 2024; pp. 4-6, 9, 13-14 | `1f2abaf8f7460ec110186d59f3d01624bdbd260d57ae7b7b698d0754c717d465`; captured as `TIDUBE1D.pdf` | 230-V design; 45 kHz; Table 3-1 measured Pin/Pout/PF/THDi; p. 13 channel 4 is AC input current, not switch drain current, so plots have no source-bound ID/time axes for Eon/Eoff extraction |
| INF-AN201408 | https://www.infineon.com/assets/row/public/documents/24/42/infineon-applicationnote-eval-2.5kw-ccm-4pin-applicationnotes-en.pdf | `AN201408`, `EVAL_2.5KW_CCM_4PIN`, Rev 1.3, 2026-01-20; PDF index 18 (Table 2), plus indices 2, 12-17, 26 | **not available**: CloudFront response `202`, `x-amzn-waf-action: challenge`; web-rendered PDF retained by URL/page citation only | 85-265 VAC, 400 VDC, 65/100 kHz; Table 2 measured efficiency at 60 C heatsink; 4-pin IPZ60R040C7; driver/BOM and gate setting context |
| INF-IPZ-DS | https://www.infineon.com/assets/row/public/documents/24/49/infineon-ipz60r040c7-datasheet-en.pdf | IPZ60R040C7 datasheet Rev 2.0 (2015-05-08); pp. 4-6 | **not available**: same WAF challenge; web-rendered primary text only | Qg/Qgd/Qgs/Vplateau/Rg/RDS and Co(er) source anchors; not board measurements |

The Infineon citations were read through the primary PDF renderer (`web` PDF
pages), not through a reseller. The missing hashes are recorded as a source gap,
not replaced with a hash of an access-denied response.
