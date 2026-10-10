"""Plot every loop polygon (filled) over the board outline; one panel per loop group."""
import json, matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Polygon
R = json.load(open('loops_result.json'))
groups = {'ocp_overview': (['OCP_kelvin_A_pour_straight'], (25, 125, 0, 80)),
          'ocp_r5': (['OCP_kelvin_A_pour_straight'], (33, 46, 5, 46)),
          'ocp_cluster': (['OCP_kelvin_A_pour_straight', 'OCP_kelvin_B_pour_hugging', 'OCP_node_local', 'OCP_thresh_local', 'OCP_ref25'], (98, 124, 40, 78)),
          'ct': (['CT_ZC_cmp', 'CT_OC_cmp', 'CT_MON_to_J4', 'CT_secondary_burden', 'CT_ZC_to_J4'], (0, 150, 118, 190)),
          'linezc': (['LINE_ZC_raw_straight', 'LINE_ZC_input', 'LINE_ZC_out_to_J4'], (0, 290, 0, 190))}
cols = plt.cm.tab10.colors
for g, (names, (x0, x1, y0, y1)) in groups.items():
    fig, ax = plt.subplots(figsize=(12, max(3, 12 * (y1 - y0) / (x1 - x0))))
    for i, n in enumerate(names):
        p = [(a, b) for a, b, l in R['polylines'][n]]
        ax.add_patch(Polygon(p, closed=True, fc=cols[i], ec=cols[i], alpha=0.25, lw=0.8, label=n))
        ax.plot(*zip(*(p + p[:1])), color=cols[i], lw=0.6)
    ax.plot([0, 290, 290, 91, 91, 0, 0], [0, 0, 140, 140, 190, 190, 0], 'k-', lw=0.5)
    ax.plot(141, -25, 'r+')
    ax.set_xlim(x0, x1); ax.set_ylim(y1, y0); ax.set_aspect('equal'); ax.legend(fontsize=7)
    fig.savefig(f'loops_{g}.png', dpi=100, bbox_inches='tight')
