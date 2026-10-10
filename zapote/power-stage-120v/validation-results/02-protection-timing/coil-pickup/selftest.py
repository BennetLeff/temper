"""Check the A.dl flux against direct integration for a planar rectangle and a vertical strip."""
import numpy as np
from loops import flux
from field import profiles, CASES
P = profiles()[CASES[0]]
x0, x1, y0, y1 = 60, 100, 40, 45
loop = [(x0, y0, 'F.Cu'), (x1, y0, 'F.Cu'), (x1, y1, 'F.Cu'), (x0, y1, 'F.Cu')]
tot, bz, br = flux(loop, P)
xs = np.linspace(x0, x1, 401); ys = np.linspace(y0, y1, 51)
X, Y = np.meshgrid(xs, ys); Bz = P.at(X, Y)[0]
direct = np.trapezoid(np.trapezoid(Bz, xs, axis=1), ys)
# board y-down -> world y-up: CCW in board coords (as listed, y down) is CW in world -> sign flip
print('rect A.dl %.1f  direct (world +z, sign-flipped) %.1f' % (bz, -direct))
# vertical strip: along a line at board y=40 x 60..100 on F, back on B.Cu: area 1.5 mm x 40 mm, normal = horizontal
loop = [(x0, 40, 'F.Cu'), (x1, 40, 'F.Cu'), (x1, 40, 'B.Cu'), (x0, 40, 'B.Cu')]
tot, bz, br = flux(loop, P)
xs = np.linspace(x0, x1, 401)
_, Br, r = P.at(xs, 40 + 0 * xs)
# radial unit vector (world) dotted with strip normal: strip along world x, normal = world y
rel_y = (236 - 40) - 261.0
ny = rel_y / r
direct = np.trapezoid(Br * ny, xs) * 1.5
print('strip A.dl %.2f  direct +-%.2f' % (br, direct))
