"""Forager: the template to copy. Each worker walks to the nearest seed it can carry and banks when full.
It never hatches, plants or fights. Keep the line count low: every executed line costs step budget."""
import random
from collections import deque

DIRS = {"N": (0, -1), "E": (1, 0), "S": (0, 1), "W": (-1, 0)}


def first_step(view, start, goals, blocked):
    """Breadth-first search. Returns the first direction of a shortest path to any goal cell, or None."""
    size, terrain = view["size"], view["terrain"]
    queue, seen = deque([(start, None)]), {start}
    while queue:
        (x, y), first = queue.popleft()
        if (x, y) in goals:
            return first
        for name, (dx, dy) in DIRS.items():
            n = (x + dx, y + dy)
            if 0 <= n[0] < size and 0 <= n[1] < size and n not in seen and terrain[n[1]][n[0]] != "#" and n not in blocked:
                seen.add(n)
                queue.append((n, first or name))
    return None


def act(view):
    size = view["size"]
    mine = set(map(tuple, view["me"]["den"]))
    corners = [(0, 0), (size - 2, size - 2), (size - 2, 0), (0, size - 2)]       # rival dens are off limits
    blocked = set((cx + dx, cy + dy) for cx, cy in corners for dx in (0, 1) for dy in (0, 1)) - mine
    seeds = dict((tuple(s["pos"]), s["value"]) for s in view["seeds"])
    taken, units = set(), {}                                                       # seeds already claimed this tick
    for u in view["units"]:
        pos, free = tuple(u["pos"]), u["capacity"] - u["load"]
        if u["last"] == ["move", 0] and random.random() < 0.5:                     # bumped last tick: break the deadlock
            units[u["id"]] = {"do": "move", "dir": random.choice("NESW")}
            continue
        if pos in mine and u["load"] > 0:
            units[u["id"]] = {"do": "bank"}
            continue
        if pos in seeds and seeds[pos] <= free:
            units[u["id"]] = {"do": "pickup"}
            continue
        goals = set(p for p, v in seeds.items() if v <= free and p not in taken)
        if u["load"] >= u["capacity"] - 1 or not goals:
            goals = mine if u["load"] > 0 else goals                               # full, or nothing to fetch: go home
        if not goals:                                                              # nothing in sight: explore the middle
            c = size // 2
            goals = set([(c - 1, c - 1), (c, c - 1), (c - 1, c), (c, c)]) - set([pos])
            if pos not in goals and abs(pos[0] - c) + abs(pos[1] - c) <= 2:
                units[u["id"]] = {"do": "move", "dir": random.choice("NESW")}          # already there: wander
                continue
        d = first_step(view, pos, goals, blocked)
        if d:
            units[u["id"]] = {"do": "move", "dir": d}
            if goals is not mine:
                taken.add(min(goals, key=lambda p: (abs(p[0] - pos[0]) + abs(p[1] - pos[1]), p)))
    return {"units": units}


_forage = act


def act(view):
    """Test bot: forages like the forager, and hatches a brute whenever it can afford one (it starves itself)."""
    out = _forage(view)
    if view["me"]["stores"] >= 7 and len(view["units"]) < 6 and not view["me"]["hatching"]:
        out["colony"] = {"hatch": "brute"}
    return out
