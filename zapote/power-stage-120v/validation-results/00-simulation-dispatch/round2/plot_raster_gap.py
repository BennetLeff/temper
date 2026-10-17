"""Illustrate the native-13 annulus gap found by the task-04 topology audit."""
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Circle

out = Path(__file__).resolve().parent
fig, ax = plt.subplots(figsize=(5, 6))
for y in (54.8, 56.6):
    ax.add_patch(Circle((68.5, y), 0.8, color='#d9a441', alpha=.75))
    ax.add_patch(Circle((68.5, y), 0.4, color='white'))
x = 68.344932
ax.plot([x, x], [55.575, 55.825], color='#c43131', linewidth=3, marker='o', markersize=5)
ax.annotate('False grid connection', (x, 55.70), xytext=(69.03, 55.70),
            arrowprops={'arrowstyle': '->', 'color': '#c43131'}, fontsize=10, va='center')
ax.annotate('0.20 mm gap', (68.5, 55.70), xytext=(67.9, 55.4),
            arrowprops={'arrowstyle': '->'}, fontsize=9, va='center', ha='right')
ax.set(xlim=(66.6, 70.5), ylim=(57.6, 53.8), xlabel='Board X (mm)', ylabel='Board Y (mm)',
       title='BUS_P pads: false connection on F.Cu / In1.Cu')
ax.set_aspect('equal')
ax.grid(alpha=.15)
fig.text(.5, .035, 'These vias connect through In2.Cu. The extra connection\non other layers can distort the calculated current sharing.',
         ha='center', fontsize=9)
fig.tight_layout(rect=(0, .09, 1, 1))
fig.savefig(out/'raster-gap.png', dpi=180)
