from temper_placer.io.kicad_parser import parse_kicad_pcb_v6
from temper_placer.router_v6.obstacle_map import build_obstacle_map
from pathlib import Path


def main():
    pcb_path = Path("pcb/temper.kicad_pcb")
    print(f"Loading {pcb_path}...")
    pcb = parse_kicad_pcb_v6(pcb_path)

    print(f"Loaded {len(pcb.components)} components.")

    # Check D1
    d1 = next((c for c in pcb.components if c.ref == "D1"), None)
    if d1:
        print(f"Found D1: {d1.footprint}")
    else:
        print("D1 not found!")

    # Check U_MCU
    u_mcu = next((c for c in pcb.components if c.ref == "U_MCU"), None)
    if u_mcu:
        print(f"Found U_MCU: {u_mcu.footprint}")

    # Build Obstacle Map
    print("Building Obstacle Map...")
    # Need escape_vias list (can pass empty)
    obstacles = build_obstacle_map(pcb, [])

    fcu_obs = obstacles.get("F.Cu")

    if hasattr(fcu_obs, "geoms"):
        print(f"F.Cu Obstacles: {len(fcu_obs.geoms)} polygons")
    else:
        print(f"F.Cu Obstacles: 1 polygon (Simple)")
        fcu_obs = [fcu_obs]  # Wrap in list for iteration if needed

    # Check if D1 location is covered
    # D1 is at 30.0, 30.0 (from DRC log)
    from shapely.geometry import Point

    p = Point(30.0, 30.0)

    # Check directly against MultiPolygon
    if fcu_obs.contains(p):
        print(f"  Point (30,30) is EXACTLY INSIDE an obstacle.")
    elif fcu_obs.distance(p) < 0.1:
        print(f"  Point (30,30) is within {fcu_obs.distance(p):.4f}mm of an obstacle.")
    else:
        print(
            f"  Point (30,30) is FAR ({fcu_obs.distance(p):.4f}mm) from obstacles! (Ghost Trace Confirmed)"
        )

    # Check U_MCU Pad 1
    # Pos: x: 76.55, y: 102.8
    p2 = Point(76.55, 102.8)
    if fcu_obs.contains(p2):
        print(f"  Point (76.55, 102.8) is EXACTLY INSIDE an obstacle.")
    elif fcu_obs.distance(p2) < 0.1:
        print(f"  Point (76.55, 102.8) is within {fcu_obs.distance(p2):.4f}mm of an obstacle.")
    else:
        print(
            f"  Point (76.55, 102.8) is FAR ({fcu_obs.distance(p2):.4f}mm) from obstacles! (Ghost Trace Confirmed)"
        )


if __name__ == "__main__":
    main()
