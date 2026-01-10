
from kiutils.items.common import Position
# Inspect Pad
try:
    from kiutils.items.fpitems import FpPad
    p = FpPad()
    print(f"FpPad attributes: {dir(p)}")
    if hasattr(p, 'position'):
        print(f"FpPad.position type: {type(p.position)}")
except Exception as e:
    print(e)
