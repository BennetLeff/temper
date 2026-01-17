
from shapely.geometry import Polygon, box
import numpy as np

def test_buffer():
    # 100x150 board
    board = box(0, 0, 100, 150)
    # Pad at 30.3, 30.7 (approx 1x1mm)
    pad = box(29.8, 30.2, 30.8, 31.2)
    
    available = board.difference(pad)
    
    # Erode by 7.5mm
    eroded = available.buffer(-7.5, quad_segs=4)
    
    # Check if point (31.3, 30.7) is in eroded area
    test_pt = (31.3, 30.7)
    from shapely.geometry import Point
    is_in = eroded.contains(Point(test_pt))
    
    print(f"Is {test_pt} in eroded area? {is_in}")
    
    # Check distance from test point to pad
    dist = Point(test_pt).distance(pad)
    print(f"Distance from pt to pad: {dist:.2f}mm")
    
    if not is_in and dist < 7.5:
        print("Success: buffer correctly excluded point close to hole.")
    else:
        print("Failure: buffer logic or expectation mismatch.")

if __name__ == "__main__":
                test_buffer()
