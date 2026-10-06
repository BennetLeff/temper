"""Repeat rail_campaign with ngspice's alternate KLU matrix solver.

Pass the same command-line arguments as rail_campaign.py and a distinct tag.
The generated F6.cir records the option; this wrapper does not alter physics.
"""
from __future__ import annotations

import rail_campaign

original_deck = rail_campaign.deck_text


def klu_deck(*args, **kwargs) -> str:
    return original_deck(*args, **kwargs).replace(".end", ".options klu\n.end")


if __name__ == "__main__":
    rail_campaign.deck_text = klu_deck
    rail_campaign.main()
