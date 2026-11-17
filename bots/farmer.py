"""Farmer: forages, plants seeds on soil (1 seed becomes a crop worth 4 after 40 ticks), harvests, banks, and hatches
extra workers early. It stops investing when the ticks left cannot pay the cost back.
raider.py and warlord.py are generated from this file by tools/make_bots.py (same code, different constants below)."""
import random
from collections import deque

DIRS = {"N": (0, -1), "E": (1, 0), "S": (0, 1), "W": (-1, 0)}
COST = {"worker": 5, "scout": 3, "brute": 7}
PLAN = ["worker", "worker"]      # critters to hatch, in order, on top of the starting two workers
MAX_PLANTS = 6                   # crops growing at once
SNATCH = False                   # workers steal from adjacent loaded rivals
RAID = False                     # brutes hunt loaded rivals and camp beside the rival den; scouts patrol rival fields
GUARD = False                    # brutes first chase rivals that come near our own den
THIEF = False                    # the newest worker steals rival crops it remembers (needs a scout for eyes)
RESERVE = 2                      # stores kept back when hatching


def first_step(view, start, goals, blocked):
    """Breadth-first search; returns the first direction of a shortest path to any goal, or None."""
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


def near(p, q):
    """Sort key for goal q seen from p: distance, then the cell itself, so ties never depend on set order."""
    return (abs(p[0] - q[0]) + abs(p[1] - q[1]), q)


def go(view, pos, goals, ctx):
    d = first_step(view, pos, goals, ctx["blocked"])
    return {"do": "move", "dir": d} if d else {"do": "wait"}


def adjacent(pos, cell):
    return abs(pos[0] - cell[0]) + abs(pos[1] - cell[1]) == 1


def direction(pos, cell):
    return [d for d, (dx, dy) in DIRS.items() if (pos[0] + dx, pos[1] + dy) == tuple(cell)][0]


ORDERED = [0]   # how many hatches we have ordered so far
MEM = {}   # fog memory: rival crop cell -> tick it is (or was) ripe. Lives in this module, survives between act() calls.


def remember(view, ctx):
    me, t = view["me"]["id"], view["tick"]
    for p in view["plants"]:
        if p["owner"] != me:
            MEM[tuple(p["pos"])] = t + (0 if p["ripe"] else p["ticks_to_ripe"])
    seen = set(tuple(p["pos"]) for p in view["plants"])
    for cell in list(MEM):
        near_eyes = any(abs(u["pos"][0] - cell[0]) + abs(u["pos"][1] - cell[1]) <= u["vision"] for u in view["units"])
        if MEM[cell] < t - 60 or (near_eyes and cell not in seen):        # old, or we can see it is gone
            del MEM[cell]


def thief(view, u, ctx):
    """Walk to the remembered rival crop that will be ripe soonest on arrival, wait there, harvest, bank. None = act normally."""
    pos, free, load, t = tuple(u["pos"]), u["capacity"] - u["load"], u["load"], view["tick"]
    if pos in ctx["den"] and load > 0:
        return {"do": "bank"}
    if pos in ctx["ripe"] and free >= 4:
        return {"do": "harvest"}
    if load > 0 and (free < 4 or ctx["left"] < 30):
        return go(view, pos, ctx["den"], ctx)
    cands = [(max(ripe_at, t + near(pos, c)[0]), c) for c, ripe_at in sorted(MEM.items()) if ripe_at - t < ctx["left"] - 20]
    if not cands:
        return None
    when, cell = min(cands)
    if pos == cell:
        return {"do": "wait"}                                           # stand on it until it ripens
    return go(view, pos, set([cell]), ctx)


def worker(view, u, ctx):
    pos, free, load = tuple(u["pos"]), u["capacity"] - u["load"], u["load"]
    if SNATCH and not u["cooldowns"]["snatch"]:
        for r in view["rivals"]:
            if r["load"] > 1 and adjacent(pos, r["pos"]) and tuple(r["pos"]) not in ctx["all_dens"]:
                return {"do": "snatch", "dir": direction(pos, r["pos"])}
    if pos in ctx["den"] and load > 0:
        return {"do": "bank"}
    if pos in ctx["ripe"] and free >= 4:
        return {"do": "harvest"}
    planting = ctx["left"] > 52 and len(ctx["mine"]) + len(ctx["claimed"]) < MAX_PLANTS
    if load >= 1 and planting and ctx["soil"]:
        if pos in ctx["soil"] and pos not in ctx["planted"]:
            ctx["claimed"].add(pos)
            return {"do": "plant"}
        goals = set(ctx["soil"]) - ctx["planted"] - ctx["claimed"]
        if goals:
            ctx["claimed"].add(min(goals, key=lambda p: near(pos, p)))
            return go(view, pos, goals, ctx)
    if pos in ctx["seeds"] and ctx["seeds"][pos] <= free:
        return {"do": "pickup"}
    goals = set(p for p in ctx["ripe"] if free >= 4 and p not in ctx["taken"])
    goals |= set(p for p, v in ctx["seeds"].items() if v <= free and p not in ctx["taken"])
    if RAID and ctx["brutes"]:                                       # sweep up what our brutes just knocked loose
        spill = set(p for p in goals if any(near(p, b)[0] <= 4 for b in ctx["brutes"]) and p in ctx["seeds"])
        goals = spill or goals
    if load >= u["capacity"] - 1 or not goals or (ctx["left"] < 25 and load > 0):
        goals = ctx["den"] if load > 0 else goals
    if not goals:
        c = view["size"] // 2
        goals = set([(c - 1, c - 1), (c, c - 1), (c - 1, c), (c, c)]) - set([pos])
        if abs(pos[0] - c) + abs(pos[1] - c) <= 2:
            return {"do": "move", "dir": random.choice("NESW")}
    if goals is not ctx["den"]:
        ctx["taken"].add(min(goals, key=lambda p: near(pos, p)))
    return go(view, pos, goals, ctx)


def brute(view, u, ctx):
    pos, cd = tuple(u["pos"]), u["cooldowns"]
    foes = [r for r in view["rivals"] if tuple(r["pos"]) not in ctx["all_dens"]]
    for r in sorted(foes, key=lambda r: (-r["load"], r["id"])):                     # hit the richest neighbour first
        if adjacent(pos, r["pos"]):
            if not cd["bonk"] and not r["stunned"]:
                return {"do": "bonk", "dir": direction(pos, r["pos"])}
            if not cd["shove"] and r["load"] > 0:
                return {"do": "shove", "dir": direction(pos, r["pos"])}
    loaded = [tuple(r["pos"]) for r in foes if r["load"] > 0]
    if GUARD:
        home = ctx["den_cell"]
        close = [p for p in loaded + [tuple(r["pos"]) for r in foes] if abs(p[0] - home[0]) + abs(p[1] - home[1]) <= 7]
        if close:
            return go(view, pos, set(close), ctx)
    if not RAID:
        return {"do": "wait"}
    if loaded:
        return go(view, pos, set(loaded), ctx)
    sprouts = set(tuple(p["pos"]) for p in view["plants"] if p["owner"] != view["me"]["id"] and not p["ripe"])
    if sprouts:
        return go(view, pos, sprouts, ctx)
    if pos in ctx["camp"]:
        return {"do": "wait"}                                                         # ambush: carriers must pass here
    return go(view, pos, ctx["camp"], ctx)


def scout(view, u, ctx):
    """Patrol in front of the rival den: the colony shares what a scout sees (vision 7)."""
    pos, size = tuple(u["pos"]), view["size"]
    pts = ctx["patrol"]
    goal = pts[(view["tick"] // 30 + u["id"]) % len(pts)]
    if pos == goal or adjacent(pos, goal):
        return {"do": "move", "dir": random.choice("NESW")}
    d = first_step(view, pos, set([goal]), ctx["blocked"])
    if d and not u["cooldowns"]["dash"] and random.random() < 0.5:
        return {"do": "dash", "dir": d}
    return {"do": "move", "dir": d} if d else {"do": "wait"}


STATIC = {}   # terrain and dens never change, so work them out once per match (a big saving in step budget)


def static(view):
    me = view["me"]["id"]
    if STATIC.get("me") == me and STATIC.get("size") == view["size"]:
        return STATIC
    STATIC.clear()
    size, t = view["size"], view["terrain"]
    den = set(map(tuple, view["me"]["den"]))
    corners = [(0, 0), (size - 2, size - 2), (size - 2, 0), (0, size - 2)]
    dens = [set((cx + dx, cy + dy) for dx in (0, 1) for dy in (0, 1)) for cx, cy in corners]
    all_dens = set().union(*dens)
    cells = [(x, y) for y in range(size) for x in range(size) if t[y][x] != "#"]
    home = sorted(den)[0]
    soil = [p for _, p in sorted(near(home, p) for p in cells if t[p[1]][p[0]] == "s") if near(home, p)[0] <= 12]
    camp, patrol = set(), []
    for d in dens:
        if d == den:
            continue
        camp |= set(p for p in cells if p not in all_dens and any(adjacent(p, q) for q in d))
        x0, y0 = min(x for x, _ in d), min(y for _, y in d)
        goal = (4 if x0 == 0 else size - 5, 4 if y0 == 0 else size - 5)
        patrol.append(min(cells, key=lambda p: near(goal, p)))
    STATIC.update(me=me, size=size, den=den, home=home, all_dens=all_dens, blocked0=all_dens - den, soil=soil,
                  camp=camp or set(cells), patrol=patrol or [home])
    return STATIC


def build(view):
    st, me = static(view), view["me"]
    return {"den": st["den"], "den_cell": st["home"], "all_dens": st["all_dens"], "camp": st["camp"], "patrol": st["patrol"],
            "blocked": st["blocked0"] | set(map(tuple, view["rival_fences"])), "soil": st["soil"], "claimed": set(), "taken": set(),
            "left": view["max_ticks"] - view["tick"], "planted": set(tuple(p["pos"]) for p in view["plants"]),
            "mine": [p for p in view["plants"] if p["owner"] == me["id"] and not p["ripe"]],
            "ripe": set(tuple(p["pos"]) for p in view["plants"] if p["ripe"]),
            "seeds": dict((tuple(s["pos"]), s["value"]) for s in view["seeds"]),
            "brutes": [tuple(u["pos"]) for u in view["units"] if u["type"] == "brute"]}


def act(view):
    me, ctx, units = view["me"], build(view), {}
    remember(view, ctx)
    workers = sorted(u["id"] for u in view["units"] if u["type"] == "worker")
    thief_id = workers[-1] if THIEF and len(workers) >= 3 else None
    for u in view["units"]:
        if u["last"] == ["move", 0] and random.random() < 0.5:
            units[u["id"]] = {"do": "move", "dir": random.choice("NESW")}
        elif u["type"] == "brute":
            units[u["id"]] = brute(view, u, ctx)
        elif u["type"] == "scout":
            units[u["id"]] = scout(view, u, ctx) if RAID else worker(view, u, ctx)
        else:
            units[u["id"]] = (thief(view, u, ctx) if u["id"] == thief_id else None) or worker(view, u, ctx)
    out = {"units": units}
    have = [u["type"] for u in view["units"]]
    want = [t for i, t in enumerate(PLAN) if have.count(t) < PLAN[: i + 1].count(t) + (2 if t == "worker" else 0)]
    spare = RESERVE + max(0, len(have) - 1)                          # keep enough to pay the next upkeep with one more critter
    if want and ORDERED[0] < len(PLAN) and ctx["left"] > 100 and not me["hatching"] and len(have) < 6 and me["stores"] - COST[want[0]] >= spare:
        out["colony"] = {"hatch": want[0]}
        ORDERED[0] += 1                                              # never re-hatch a critter that starved
    return out
