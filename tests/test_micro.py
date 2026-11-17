"""Hand-built micro-scenarios, one per rule. No bots involved: tiny boards, actions fed straight to Game.step().
Run: python tests/test_micro.py   (exits 1 on any failure)"""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from engine import rules as R, world
from engine.game import Game

OPEN6 = ["......", "......", "......", "......", "......", "......"]
DENS = [[(0, 0), (1, 0), (0, 1), (1, 1)], [(4, 4), (5, 4), (4, 5), (5, 5)]]


def mk(rows=OPEN6, units=(), dens=DENS, stores=None):
    g = Game(n=2, seed=1, terrain=rows, dens=dens, units=list(units), wild=False)
    if stores is not None:
        for c, s in zip(g.colonies, stores):
            c.stores = s
    return g


def go(g, *pairs, colony=None):
    """go(g, (uid, {...}), ...) all for one colony, or go(g, {0: {...}, 1: {...}})."""
    acts = {}
    for p in pairs:
        if isinstance(p, dict):
            acts.update(p)
        else:
            c = g.units[p[0]].colony
            acts.setdefault(c, {"units": {}})["units"][p[0]] = p[1]
    return g.step(acts)


def pos(g, uid):
    return (g.units[uid].x, g.units[uid].y)


def mv(d):
    return {"do": "move", "dir": d}


RESULTS = []


def test(f):
    try:
        f()
        RESULTS.append((f.__name__, True, ""))
    except Exception as e:                       # noqa: BLE001
        RESULTS.append((f.__name__, False, "%s: %s" % (type(e).__name__, e)))
    return f


@test
def swap_bump():
    g = mk(units=[(0, "worker", (2, 2)), (0, "worker", (3, 2))])
    go(g, (1, mv("E")), (2, mv("W")))
    assert pos(g, 1) == (2, 2) and pos(g, 2) == (3, 2), "two units swapping cells must both bump"


@test
def convoy_follow():
    g = mk(units=[(0, "worker", (1, 3)), (0, "worker", (2, 3)), (0, "worker", (3, 3))])
    go(g, (1, mv("E")), (2, mv("E")), (3, mv("E")))
    assert [pos(g, i) for i in (1, 2, 3)] == [(2, 3), (3, 3), (4, 3)], "a column moving in one direction all advances"


@test
def three_way_bump():
    g = mk(units=[(0, "worker", (1, 2)), (0, "worker", (3, 2)), (1, "worker", (2, 1))])
    go(g, {0: {"units": {1: mv("E"), 2: mv("W")}}, 1: {"units": {3: mv("S")}}})
    assert pos(g, 1) == (1, 2) and pos(g, 2) == (3, 2) and pos(g, 3) == (2, 1), "three into one cell: nobody moves"


@test
def rotation_bump():
    g = mk(units=[(0, "worker", (2, 2)), (0, "worker", (3, 2)), (0, "worker", (3, 3)), (0, "worker", (2, 3))])
    go(g, (1, mv("E")), (2, mv("S")), (3, mv("W")), (4, mv("N")))
    assert [pos(g, i) for i in (1, 2, 3, 4)] == [(2, 2), (3, 2), (3, 3), (2, 3)], "a 4-cycle can never resolve"


@test
def own_den_stacking_and_rival_den_blocked():
    g = mk(units=[(0, "worker", (2, 0)), (0, "worker", (2, 1)), (1, "worker", (3, 4))])
    go(g, (1, mv("W")), (2, mv("W")))
    assert pos(g, 1) == (1, 0) and pos(g, 2) == (1, 1)
    go(g, (1, mv("W")), (2, mv("N")))
    assert pos(g, 1) == (0, 0) and pos(g, 2) == (1, 0), "own units may share den cells"
    go(g, (3, mv("E")))
    assert pos(g, 3) == (4, 4), "a unit may enter its own den"
    g2 = mk(units=[(0, "worker", (3, 4))])
    go(g2, (1, mv("E")))
    assert pos(g2, 1) == (3, 4), "rivals can never enter a den"


@test
def mud_costs_next_action():
    g = mk(rows=["......", ".m....", "......", "......", "......", "......"], units=[(0, "worker", (0, 1)), (0, "scout", (0, 2))])
    go(g, (1, mv("E")), (2, mv("N")))
    assert pos(g, 1) == (1, 1) and g.units[1].stuck
    go(g, (1, mv("E")))
    assert pos(g, 1) == (1, 1), "the action after entering mud is lost"
    go(g, (1, mv("E")))
    assert pos(g, 1) == (2, 1)
    g = mk(rows=["......", ".m....", "......", "......", "......", "......"], units=[(0, "scout", (0, 1))])
    go(g, (1, mv("E")))
    go(g, (1, mv("E")))
    assert pos(g, 1) == (2, 1), "scouts ignore mud"


@test
def shove_into_wall_stuns_and_open_cell_pushes():
    rows = [".....#", "......", "......", "......", "......", "......"]
    g = mk(rows=rows, units=[(0, "brute", (3, 2)), (1, "worker", (4, 2))])
    go(g, (1, {"do": "shove", "dir": "E"}))
    assert pos(g, 2) == (5, 2), "shove pushes one cell away"
    go(g, (1, {"do": "shove", "dir": "E"}))     # cooldown 2: still cooling, nothing happens
    g = mk(rows=["......", "....##", "......", "......", "......", "......"], units=[(0, "brute", (3, 1)), (1, "worker", (4, 1))])
    go(g, (1, {"do": "shove", "dir": "E"}))
    assert pos(g, 2) == (4, 1) and g.units[2].stun == 1, "blocked shove stuns for 1 tick instead"
    go(g, (2, mv("W")))
    assert pos(g, 2) == (4, 1) and g.units[2].stun == 0, "the stunned unit loses exactly one action"


@test
def shove_into_mud_sticks():
    g = mk(rows=["......", "....m.", "......", "......", "......", "......"], units=[(0, "brute", (3, 1)), (1, "worker", (4, 1))])
    go(g, (1, {"do": "shove", "dir": "E"}))
    assert pos(g, 2) == (5, 1) or g.terrain[1][5] != "m"
    g = mk(rows=["......", ".....m", "......", "......", "......", "......"], units=[(0, "brute", (3, 1)), (1, "worker", (4, 1))])
    go(g, (1, {"do": "shove", "dir": "E"}))
    assert pos(g, 2) == (5, 1) and g.units[2].stuck, "a unit shoved into mud gets stuck"


@test
def snatch_takes_half_and_stuns():
    g = mk(units=[(0, "worker", (2, 3)), (1, "worker", (3, 3))])
    g.units[2].load = 4
    go(g, (1, {"do": "snatch", "dir": "E"}))
    assert g.units[1].load == 2 and g.units[2].load == 2 and g.units[2].stun == 1
    assert g.colonies[0].stats["snatches"] == 1


@test
def snatch_on_den_refused_and_cooldown_spent_on_miss():
    g = mk(units=[(0, "worker", (3, 4)), (1, "worker", (4, 4))])
    g.units[2].load = 4
    go(g, (1, {"do": "snatch", "dir": "E"}))
    assert g.units[2].load == 4 and g.units[1].cd["snatch"] == R.COOLDOWN["snatch"] - 1, "den = safe; the miss still costs the cooldown"
    g = mk(units=[(0, "brute", (3, 4)), (1, "worker", (4, 4))])
    g.units[2].load = 4
    go(g, (1, {"do": "bonk", "dir": "E"}))
    assert g.units[2].load == 4 and not g.seeds, "bonk on a critter in its own den is refused"


@test
def bonk_spills_entire_load_nearest_cells():
    g = mk(units=[(0, "brute", (1, 3)), (1, "worker", (2, 3))])
    g.units[2].load = 5
    go(g, (1, {"do": "bonk", "dir": "E"}))
    assert g.units[2].load == 0 and g.units[2].stun == 2
    assert g.seeds == {(2, 3): 3, (2, 2): 1, (1, 3): 1}, "5 = 3+1+1 on the victim cell then nearest cells by (y,x): %r" % g.seeds


@test
def hatch_costs_upfront_takes_six_ticks():
    g = mk(units=[(0, "worker", (3, 3))], stores=[10, 0])
    go(g, {0: {"colony": {"hatch": "scout"}}})
    assert g.colonies[0].stores == 7 and g.colonies[0].hatching[0] == "scout"
    for _ in range(4):
        g.step({})
    assert len(g.units_of(0)) == 1
    g.step({})
    assert len(g.units_of(0)) == 2, "the newborn appears at the end of the 6th tick"
    go(g, {0: {"colony": {"hatch": "brute"}}})
    go(g, {0: {"colony": {"hatch": "brute"}}})
    assert g.errors, "hatching while already hatching is an error"


@test
def plant_ripen_harvest_trample():
    rows = ["......", "......", "..s...", "......", "......", "......"]
    g = mk(rows=rows, units=[(0, "worker", (2, 2)), (1, "brute", (2, 3))])
    g.units[1].load = 2
    go(g, (1, {"do": "plant"}))
    assert (2, 2) in g.plants and g.units[1].load == 1
    go(g, (2, mv("N")))
    go(g, (2, mv("N")))
    go(g, (2, mv("W")))                     # step off, then back later
    g.plants[(2, 2)] = [0, g.tick - R.RIPEN]   # fast-forward: ripe now
    g.units[1].x, g.units[1].y = 2, 2
    go(g, (1, {"do": "harvest"}))
    assert g.units[1].load == 1 + R.CROP_VALUE and (2, 2) not in g.plants
    g = mk(rows=rows, units=[(0, "worker", (2, 2)), (1, "brute", (2, 2))])
    g.plants[(2, 2)] = [0, g.tick]
    g.step({})
    assert (2, 2) not in g.plants and g.colonies[0].stats["trampled"] == 1, "a rival brute on an unripe sprout destroys it"


@test
def brute_tramples_sprout_but_not_ripe_crop():
    g = mk(units=[(0, "worker", (0, 0)), (1, "brute", (3, 3))])
    g.plants[(3, 3)] = [0, g.tick]
    g.step({})
    assert (3, 3) not in g.plants, "a rival brute standing on an unripe sprout destroys it"
    g = mk(units=[(0, "worker", (0, 0)), (1, "brute", (3, 3))])
    g.plants[(3, 3)] = [0, g.tick - R.RIPEN - 5]
    g.step({})
    assert (3, 3) in g.plants, "a ripe crop is not trampled"


@test
def fence_blocks_rivals_and_flood_fill_refusal():
    rows = ["..######", "........", "######..", "######.."]
    dens = [[(0, 0), (1, 0), (0, 1), (1, 1)], [(6, 2), (7, 2), (6, 3), (7, 3)]]
    g = mk(rows=rows, dens=dens, units=[(0, "worker", (2, 1))], stores=[9, 0])
    for _ in range(4):
        go(g, (1, {"do": "build", "dir": "E"}))
    assert (3, 1) not in g.colonies[0].fences and g.colonies[0].stores == 9, "a fence that cuts the only corridor is refused"
    rows2 = ["........", "........", "......##", "......##"]
    g = mk(rows=rows2, dens=dens, units=[(0, "worker", (2, 1)), (1, "worker", (4, 1))], stores=[9, 0])
    for _ in range(3):
        go(g, {0: {"units": {1: {"do": "build", "dir": "E"}}}})
    assert (3, 1) in g.colonies[0].fences and g.colonies[0].stores == 7, "build takes 3 consecutive actions and 2 stores"
    go(g, {1: {"units": {2: mv("W")}}})
    assert pos(g, 2) == (4, 1), "fences block rival critters"
    go(g, {0: {"units": {1: mv("E")}}})
    assert pos(g, 1) == (3, 1), "own critters walk through own fences"


@test
def build_must_be_consecutive():
    g = mk(units=[(0, "worker", (2, 2))], stores=[9, 0])
    go(g, (1, {"do": "build", "dir": "E"}))
    go(g, (1, {"do": "build", "dir": "E"}))
    go(g, (1, {"do": "wait"}))
    go(g, (1, {"do": "build", "dir": "E"}))
    assert not g.colonies[0].fences, "a wait in between resets the build"


@test
def upkeep_starves_newest_first():
    g = mk(units=[(0, "worker", (2, 2)), (0, "worker", (2, 3)), (0, "scout", (3, 3)), (0, "brute", (3, 2))], stores=[1, 4])
    g.tick = 29                                   # upkeep is charged at the end of ticks 29, 59, ...
    g.step({})
    assert sorted(g.units_of(0), key=lambda u: u.id)[-1].id == 3, "the newest (id 4) starved"
    assert [u.id for u in g.units_of(0)] == [1, 2, 3] and g.colonies[0].stores == 0
    assert g.colonies[0].stats["starved"] == 1


@test
def upkeep_paid_when_affordable():
    g = mk(units=[(0, "worker", (2, 2)), (0, "worker", (2, 3)), (0, "scout", (3, 3)), (0, "brute", (3, 2))], stores=[5, 4])
    g.tick = 29
    g.step({})
    assert len(g.units_of(0)) == 4 and g.colonies[0].stores == 3, "2 critters beyond the free two cost 1 each"


@test
def fog_and_grass():
    rows = ["......", "......", "....g.", "......", "......", "......"]
    g = mk(rows=rows, units=[(0, "worker", (2, 2)), (1, "worker", (4, 2))])
    v = g.view(0)
    assert v["rivals"] == [], "a rival standing in grass is invisible at range"
    g.add_unit(0, "scout", (4, 1))                # now an own unit is orthogonally adjacent
    v = g.view(0)
    assert [r["id"] for r in v["rivals"]] == [2], "adjacent own unit reveals it"
    g2 = mk(rows=rows, units=[(0, "worker", (0, 0)), (1, "worker", (5, 5))])
    assert g2.view(0)["rivals"] == [], "out of vision range"
    assert "stores" not in str(g2.view(0)["rival_status"]), "rival stores are never visible"


@test
def invalid_action_only_costs_that_unit():
    g = mk(units=[(0, "worker", (2, 2)), (0, "worker", (2, 3))])
    go(g, (1, {"do": "fly"}), (2, mv("E")))
    assert pos(g, 2) == (3, 3) and pos(g, 1) == (2, 2) and len(g.errors) == 1
    go(g, (1, {"do": "bonk", "dir": "N"}))
    assert len(g.errors) == 2, "a worker cannot bonk"


@test
def bank_moves_load_into_stores():
    g = mk(units=[(0, "worker", (0, 0))], stores=[4, 0])
    g.units[1].load = 5
    go(g, (1, {"do": "bank"}))
    assert g.colonies[0].stores == 9 and g.units[1].load == 0


@test
def dash_two_cells_then_cooldown():
    g = mk(units=[(0, "scout", (0, 3))])
    go(g, (1, {"do": "dash", "dir": "E"}))
    assert pos(g, 1) == (2, 3)
    go(g, (1, {"do": "dash", "dir": "E"}))
    assert pos(g, 1) == (3, 3), "on cooldown a dash is a plain 1-step move"


if __name__ == "__main__":
    bad = 0
    for name, ok, msg in RESULTS:
        print("%s  %s %s" % ("PASS" if ok else "FAIL", name, msg))
        bad += not ok
    print("%d/%d micro-scenarios passed" % (len(RESULTS) - bad, len(RESULTS)))
    sys.exit(1 if bad else 0)
