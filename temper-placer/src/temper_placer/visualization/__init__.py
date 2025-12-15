"""
Visualization module for temper-placer.

This module provides browser-based live visualization during optimization:
- Board view: component rectangles, zones, keep-out areas
- Loss curves: total and per-term losses over iterations
- Constraint status: which constraints are satisfied/violated
- Animation: placement evolution over training

Implementation:
- Plotly for rendering (interactive zoom, hover info)
- WebSocket server for real-time updates
- HTML dashboard served locally

The visualizer runs in a separate thread/process and receives updates
from the optimizer via a queue or WebSocket connection.

Usage:
    # In optimizer
    vis = Visualizer(board, netlist, port=8080)
    vis.start()

    for step in training_loop:
        vis.update(state, losses, step)

    vis.stop()
"""

# Imports will be added as modules are implemented
# from temper_placer.visualization.server import Visualizer
# from temper_placer.visualization.board_view import render_board
# from temper_placer.visualization.loss_plots import render_loss_curves
# from temper_placer.visualization.dashboard import create_dashboard

__all__ = []
