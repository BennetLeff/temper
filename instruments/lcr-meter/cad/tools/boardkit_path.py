"""Put instruments/boardkit/src on sys.path (import this before `from temper_boardkit import ...`).

Works under KiCad's bundled Python as well as python3: the pure boardkit modules need neither shapely nor numpy.
"""
import sys
from pathlib import Path

SRC = Path(__file__).resolve().parents[3] / 'boardkit' / 'src'
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))
