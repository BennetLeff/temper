#!/bin/bash
export PYTHONPATH=packages/temper-placer/src:$PYTHONPATH
.venv/bin/python3 packages/temper-placer/scripts/profile_routing.py
