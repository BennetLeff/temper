"""3D models for the LCR footprints that have none in KiCad's library (CAD-env Python, OCP).

~/.local/share/temper/cadenv/bin/python -I cad/tools/models_3d.py [--refresh]

Exact-part models come from the EasyEDA/LCSC library of each part's LCSC code: the record already
cached in sources/placement-library/<LCSC>-product.json names the model (outline3D uuid, origin, z,
rotation). The STEP is fetched from modules.easyeda.com into build/models-3d/raw/ and is not
committed (vendor model, like the SPICE models). It is then placed in the KiCad footprint frame, so
that the footprint's model entry needs no offset or rotation, and written with its colours to
cad/3dmodels/ (gitignored; rerun this script after a fresh checkout).  The placement (EasyEDA's own
placement, the pad-number rigid fit, the 'seat' and 'bnc' corrections) is temper_boardkit.jlc.models_3d.
cad/3dmodels/models-3d.json records the source, hashes, fit and corrections per part.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import boardkit_path  # noqa: E402,F401
from temper_boardkit.jlc import models_3d  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'cad' / '3dmodels'

# footprint -> (LCSC code of the fitted part, correction)
PARTS = {
    'Relay_DPDT_Panasonic_TQ2SA_SMD': ('C2684450', 'seat'),
    'BNC_SAMZO_KYWE-295-W4-N_Horizontal': ('C41416668', 'bnc'),
    'USB_C_Receptacle_HRO_TYPE-C-31-M-12': ('C165948', 'seat'),
    'LED_LiteOn_LTST-S270KFKT_SideView': ('C160472', 'seat'),
}

manifest = models_3d.build(PARTS, ROOT / 'cad' / 'LCR.pretty', ROOT / 'sources' / 'placement-library',
                           ROOT / 'build' / 'models-3d' / 'raw', OUT, refresh='--refresh' in sys.argv)
(OUT / 'models-3d.json').write_text(json.dumps(manifest, indent=1) + '\n')
