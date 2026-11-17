"""Sleepwalker: the weakest opponent. Every critter wanders at random and the colony never hatches anything."""
import random


def act(view):
    units = {}
    for u in view["units"]:
        units[u["id"]] = {"do": "move", "dir": random.choice("NESW")}
    return {"units": units}
