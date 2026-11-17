"""Game state and tick resolution. Pure Python, standard library only, deterministic for a given seed.

ORDER INSIDE ONE TICK (this is the contract; BOT_GUIDE.md repeats it):
  0. Bots are called with their views (done by match.py) and return actions.
  1. Actions are validated. An invalid unit action becomes `wait` and one error is logged.
  2. Colony actions (hatch) in colony order: stores are charged up front.
  3. Stunned or mud-stuck units: their action becomes `wait`; the stun counter then drops by 1 (stuck clears).
  4. Movement (`move`, `dash`): fixpoint, see _move(). Then `shove`, one unit at a time in the seeded random order.
  5. pickup / harvest / bank / plant / build / break / snatch / bonk, one unit at a time in the seeded random order
     (positions are the ones after movement).
  6. End of tick: trample, cooldowns -1, hatching progress (+ spawn), upkeep (every 30th tick), wild seed spawn.
RNG (one random.Random(seed)) is consumed in this order: terrain generation, initial seed spawns, then each tick one
shuffle of the unit order followed by the seed spawn draws.
"""
import random
from collections import defaultdict, deque
from . import rules as R, world, fog

TYPE_IDX = dict((t, i) for i, t in enumerate(R.TYPES))
ACTS = ["wait", "move", "dash", "pickup", "harvest", "bank", "plant", "build", "break", "snatch", "bonk", "shove"]
ALLOWED = {
    "worker": {"wait", "move", "pickup", "harvest", "bank", "plant", "build", "snatch"},
    "scout": {"wait", "move", "dash", "pickup", "bank"},
    "brute": {"wait", "move", "bonk", "shove", "break"},
}
NEEDS_DIR = {"move", "dash", "build", "break", "snatch", "bonk", "shove"}
ORTHO = ((0, -1), (1, 0), (0, 1), (-1, 0))


class Unit(object):
    def __init__(self, uid, colony, typ, x, y, born):
        self.id, self.colony, self.type, self.x, self.y, self.born = uid, colony, typ, x, y, born
        self.load = 0
        self.stun = 0
        self.stuck = False
        self.cd = dict((k, 0) for k in R.COOLDOWN)
        self.build = None            # [cell, kind, progress]
        self.last = ["wait", 1]      # last action and whether it worked


class Colony(object):
    def __init__(self, i, den):
        self.id, self.den = i, den
        self.stores = R.START_STORES
        self.hatching = None         # [type, ticks_left]
        self.fences = {}             # cell -> colony id (always self.id)
        self.errors = 0
        self.last_bank = -999
        self.seen = {}               # rival id -> rival critters seen the last time any was visible
        self.stats = dict((k, 0) for k in ("banked", "snatches", "bonks", "hatches", "planted", "harvested",
                                           "stolen_crops", "starved", "fences", "trampled"))


class Game(object):
    def __init__(self, n=2, seed=1, ticks=R.TICKS, terrain=None, dens=None, units=None, wild=True):
        self.rng = random.Random(seed)
        self.seed, self.n, self.max_ticks, self.wild = seed, n, ticks, wild
        self.terrain = terrain if terrain is not None else world.generate(self.rng)
        self.H, self.W = len(self.terrain), len(self.terrain[0])
        dens = dens if dens is not None else [world.den_cells(i, self.W) for i in range(n)]
        self.colonies = [Colony(i, [tuple(c) for c in dens[i]]) for i in range(n)]
        self.den_owner = {}
        for c in self.colonies:
            for cell in c.den:
                self.den_owner[cell] = c.id
        self.units, self.plants, self.seeds = {}, {}, {}
        self.tick, self.next_id = 0, 1
        self.events, self.last_events, self.errors = [], [], []
        self.order = []
        # distances used for seed spawning (all four corner dens, so spawning does not depend on who plays)
        all_dens = [c for i in range(4) for c in world.den_cells(i, self.W)] if self.W == R.SIZE else \
            [cell for c in self.colonies for cell in c.den]
        self.den_dist = world.bfs(self.terrain, all_dens)
        self.center_dist = world.bfs(self.terrain, world.center_cells(self.W)) if self.W >= 4 else {}
        self.group_mode = 4 if n >= 3 else 2
        if units is None:
            for c in self.colonies:
                for k in range(R.START_WORKERS):
                    self.add_unit(c.id, "worker", c.den[k])
        else:
            for colony, typ, pos in units:
                self.add_unit(colony, typ, pos)
        if wild:
            tries = 0
            while len(self.seeds) < R.START_SEED_FILL and tries < 200:
                tries += 1
                self._spawn_group()

    # ---------- setup helpers ----------
    def add_unit(self, colony, typ, pos, load=0):
        u = Unit(self.next_id, colony, typ, pos[0], pos[1], self.next_id)
        u.load = load
        self.units[u.id] = u
        self.next_id += 1
        return u

    def units_of(self, ci):
        return [u for u in self.units.values() if u.colony == ci]

    def _group(self, x, y):
        W, H = self.W, self.H
        cells = set([(x, y), (W - 1 - x, H - 1 - y)])
        if self.group_mode == 4:
            cells |= set([(W - 1 - x, y), (x, H - 1 - y)])
        return tuple(sorted(cells))

    def _spawn_ok(self, cell):
        x, y = cell
        return (self.terrain[y][x] != "#" and cell not in self.den_owner and cell not in self.seeds
                and cell not in self.plants and self.den_dist.get(cell, 99) >= R.SEED_MIN_DEN_DIST
                and not any(cell in c.fences for c in self.colonies))

    def _spawn_group(self):
        cands = []
        for y in range(self.H):
            for x in range(self.W):
                grp = self._group(x, y)
                if grp[0] == (x, y) and all(self._spawn_ok(c) for c in grp):
                    cands.append(grp)
        if not cands:
            return False
        grp = cands[self.rng.randrange(len(cands))]
        if len(self.seeds) + len(grp) > R.SEED_CAP:
            return False
        val = 1
        if self.center_dist.get(grp[0], 99) <= R.GOLD_CENTER_DIST and self.rng.random() < R.GOLD_PROB:
            val = 3
        for c in grp:
            self.seeds[c] = val
        return True

    def _event(self, typ, by, on, pos, **extra):
        e = {"type": typ, "tick": self.tick, "by": by, "on": on, "pos": [pos[0], pos[1]]}
        e.update(extra)
        self.events.append(e)

    def _err(self, colony, text):
        self.errors.append([self.tick, colony, text])
        self.colonies[colony].errors += 1

    # ---------- queries ----------
    def passable(self, u, cell):
        x, y = cell
        if not (0 <= x < self.W and 0 <= y < self.H) or self.terrain[y][x] == "#":
            return False
        if cell in self.den_owner and self.den_owner[cell] != u.colony:
            return False
        for c in self.colonies:
            if c.id != u.colony and cell in c.fences:
                return False
        return True

    def _unit_at(self, cell):
        for u in self.units.values():
            if (u.x, u.y) == cell:
                return u
        return None

    def ripe(self, cell):
        p = self.plants.get(cell)
        return p is not None and self.tick >= p[1] + R.RIPEN

    # ---------- the tick ----------
    def step(self, actions):
        """actions: {colony_id: {"units": {unit_id: {...}}, "colony": {...}}}. Advances one tick, returns the frame."""
        self.events, acts = [], {}
        for c in self.colonies:                                        # 1. validate
            a = actions.get(c.id)
            if not isinstance(a, dict):
                if a is not None:
                    self._err(c.id, "act() must return a dict")
                a = {}
            ua = a.get("units") or {}
            if not isinstance(ua, dict):
                self._err(c.id, "'units' must be a dict of unit id -> action")
                ua = {}
            for key, act in ua.items():
                try:
                    uid = int(key)
                except (TypeError, ValueError):
                    self._err(c.id, "unknown unit id %r" % (key,))
                    continue
                u = self.units.get(uid)
                if u is None or u.colony != c.id:
                    self._err(c.id, "unit %r is not yours or is dead" % (key,))
                    continue
                act, bad = self._norm(u, act)
                if bad:
                    self._err(c.id, "unit %d: %s" % (uid, bad))
                acts[uid] = act
            self._colony_action(c, a.get("colony"))                    # 2. colony actions
        for u in self.units.values():
            acts.setdefault(u.id, {"do": "wait"})
            if u.stun > 0:                                             # 3. stun / mud
                u.stun -= 1
                acts[u.id] = {"do": "wait"}
            elif u.stuck:
                u.stuck = False
                acts[u.id] = {"do": "wait"}
        order = sorted(self.units)
        self.rng.shuffle(order)
        self.order = order
        done = dict((uid, 0) for uid in self.units)
        self._move(acts, done)                                         # 4. movement, then shoves
        for uid in order:
            if uid in self.units and acts[uid]["do"] == "shove":
                done[uid] = self._shove(self.units[uid], acts[uid])
        for uid in order:                                              # 5. everything else
            if uid in self.units and acts[uid]["do"] not in ("move", "dash", "wait", "shove"):
                done[uid] = self._act(self.units[uid], acts[uid])
        for uid, u in self.units.items():
            do = acts[uid]["do"]
            u.last = [do, 1 if done.get(uid) else 0]
            if not (u.build and do == u.build[1]):                     # build/break must be consecutive
                u.build = None
        self._end_of_tick()                                            # 6. end of tick
        self.last_events = self.events
        self.tick += 1
        return self.frame()

    def _norm(self, u, act):
        if act is None:
            return {"do": "wait"}, None
        if not isinstance(act, dict):
            return {"do": "wait"}, "action must be a dict like {'do': 'move', 'dir': 'N'}"
        do = act.get("do")
        if do not in ACTS:
            return {"do": "wait"}, "unknown action %r" % (do,)
        if do not in ALLOWED[u.type]:
            return {"do": "wait"}, "a %s cannot %s" % (u.type, do)
        if do in NEEDS_DIR and act.get("dir") not in R.DIRS:
            return {"do": "wait"}, "%s needs dir N, E, S or W" % do
        return {"do": do, "dir": act.get("dir")}, None

    def _colony_action(self, c, a):
        if a is None:
            return
        if not isinstance(a, dict) or "hatch" not in a:
            self._err(c.id, "colony action must look like {'hatch': 'scout'}")
            return
        typ = a["hatch"]
        if typ not in R.HATCH_COST:
            self._err(c.id, "cannot hatch %r" % (typ,))
        elif c.hatching is not None:
            self._err(c.id, "already hatching")
        elif len(self.units_of(c.id)) + 1 > R.MAX_UNITS:
            self._err(c.id, "colony is full (%d critters)" % R.MAX_UNITS)
        elif c.stores < R.HATCH_COST[typ]:
            self._err(c.id, "not enough stores to hatch a %s (need %d)" % (typ, R.HATCH_COST[typ]))
        else:
            c.stores -= R.HATCH_COST[typ]
            c.hatching = [typ, R.HATCH_TICKS]
            c.stats["hatches"] += 1

    # ---------- movement ----------
    def _move(self, acts, done):
        cand = {}
        at = defaultdict(list)
        for u in self.units.values():
            at[(u.x, u.y)].append(u)
        for uid in sorted(self.units):
            u, a = self.units[uid], acts[uid]
            if a["do"] not in ("move", "dash"):
                continue
            dx, dy = R.DIRS[a["dir"]]
            c1 = (u.x + dx, u.y + dy)
            if not self.passable(u, c1):
                continue
            tgt = c1
            if a["do"] == "dash" and u.cd["dash"] == 0:
                u.cd["dash"] = R.COOLDOWN["dash"]
                c2 = (c1[0] + dx, c1[1] + dy)
                if self.passable(u, c2) and not at.get(c1) and not at.get(c2):
                    tgt = c2
            cand[uid] = tgt

        def own_den(u, cell):
            return self.den_owner.get(cell) == u.colony
        groups = defaultdict(list)
        for uid, tgt in cand.items():
            if not own_den(self.units[uid], tgt):
                groups[tgt].append(uid)
        pending = {}
        for uid, tgt in cand.items():
            if own_den(self.units[uid], tgt) or len(groups[tgt]) == 1:
                pending[uid] = tgt                 # contested cells: every mover into them bumps
        success, changed = set(), True
        while changed:                             # a move works if its target is empty or being vacated by a success
            changed = False
            for uid in sorted(pending):
                if uid in success:
                    continue
                u, tgt = self.units[uid], pending[uid]
                if own_den(u, tgt) or all(o.id in success for o in at.get(tgt, ())):
                    success.add(uid)
                    changed = True
        for uid in sorted(success):
            u = self.units[uid]
            u.x, u.y = pending[uid]
            if self.terrain[u.y][u.x] == "m" and u.type != "scout":
                u.stuck = True
            done[uid] = 1

    def _shove(self, u, a):
        if u.cd["shove"] > 0:
            return 0
        dx, dy = R.DIRS[a["dir"]]
        v = self._unit_at((u.x + dx, u.y + dy))
        if v is None or v.colony == u.colony or self.den_owner.get((v.x, v.y)) == v.colony:
            return 0
        u.cd["shove"] = R.COOLDOWN["shove"]
        dest = (v.x + dx, v.y + dy)
        if self.passable(v, dest) and self._unit_at(dest) is None:
            v.x, v.y = dest
            if self.terrain[v.y][v.x] == "m" and v.type != "scout":
                v.stuck = True
            self._event("shove", u.colony, v.colony, dest, unit=v.id)
        else:
            v.stun = max(v.stun, R.STUN["shove"])
            self._event("shove", u.colony, v.colony, (v.x, v.y), unit=v.id, blocked=1)
        return 1

    # ---------- other actions ----------
    def _act(self, u, a):
        do, c = a["do"], self.colonies[u.colony]
        pos = (u.x, u.y)
        cap = R.CAPACITY[u.type]
        if do == "pickup":
            v = self.seeds.get(pos)
            if v is None or u.load + v > cap:
                return 0
            u.load += v
            del self.seeds[pos]
            return 1
        if do == "harvest":
            if not self.ripe(pos) or u.load + R.CROP_VALUE > cap:
                return 0
            owner = self.plants.pop(pos)[0]
            u.load += R.CROP_VALUE
            c.stats["harvested"] += 1
            if owner != u.colony:
                c.stats["stolen_crops"] += 1
            self._event("harvest", u.colony, owner, pos)
            return 1
        if do == "bank":
            if self.den_owner.get(pos) != u.colony or u.load <= 0:
                return 0
            c.stores += u.load
            c.stats["banked"] += u.load
            c.last_bank = self.tick
            self._event("bank", u.colony, None, pos, n=u.load)
            u.load = 0
            return 1
        if do == "plant":
            if self.terrain[u.y][u.x] != "s" or pos in self.plants or u.load < 1:
                return 0
            u.load -= 1
            self.plants[pos] = [u.colony, self.tick]
            c.stats["planted"] += 1
            return 1
        dx, dy = R.DIRS[a["dir"]]
        tgt = (u.x + dx, u.y + dy)
        if do in ("build", "break"):
            return self._build(u, c, do, tgt)
        v = self._unit_at(tgt)
        if do == "snatch":
            if u.cd["snatch"] > 0:
                return 0
            u.cd["snatch"] = R.COOLDOWN["snatch"]                          # spent even on a miss
            if v is None or v.colony == u.colony or v.load <= 0 or self.den_owner.get(tgt) == v.colony:
                return 0
            take = min((v.load + 1) // 2, cap - u.load)
            if take <= 0:
                return 0
            v.load -= take
            u.load += take
            v.stun = max(v.stun, R.STUN["snatch"])
            c.stats["snatches"] += 1
            self._event("snatch", u.colony, v.colony, tgt, n=take)
            return 1
        if do == "bonk":
            if u.cd["bonk"] > 0 or v is None or v.colony == u.colony or self.den_owner.get(tgt) == v.colony:
                return 0
            u.cd["bonk"] = R.COOLDOWN["bonk"]
            n = v.load
            self._spill(tgt, n)
            v.load = 0
            v.stun = max(v.stun, R.STUN["bonk"])
            c.stats["bonks"] += 1
            self._event("bonk", u.colony, v.colony, tgt, n=n)
            return 1
        return 0

    def _spill(self, pos, n):
        """Drop n load as loose seeds (3s then 1s) on pos and the nearest free cells, nearest first, ties by (y, x)."""
        chunks = [3] * (n // 3) + [1] * (n % 3)
        if not chunks:
            return
        seen, q, cells = set([pos]), deque([pos]), []
        while q and len(cells) < len(chunks) + 8:
            cur = q.popleft()
            cells.append(cur)
            nxt = []
            for dx, dy in ORTHO:
                nb = (cur[0] + dx, cur[1] + dy)
                if 0 <= nb[0] < self.W and 0 <= nb[1] < self.H and nb not in seen and self.terrain[nb[1]][nb[0]] != "#":
                    seen.add(nb)
                    nxt.append(nb)
            for nb in sorted(nxt, key=lambda p: (p[1], p[0])):
                q.append(nb)
        free = [c for c in cells if c not in self.seeds and c not in self.den_owner]
        for chunk, cell in zip(chunks, free):
            self.seeds[cell] = chunk                                       # anything that does not fit is lost

    def _fence_ok(self, ci, cell):
        """Placing a fence must keep every open cell reachable from every rival den."""
        for r in self.colonies:
            if r.id == ci:
                continue
            blocked = set([cell])
            for o in self.colonies:
                if o.id != r.id:
                    blocked |= set(o.fences)
                    blocked |= set(o.den)
            reach = world.bfs(self.terrain, list(r.den), blocked)
            for y in range(self.H):
                for x in range(self.W):
                    p = (x, y)
                    if self.terrain[y][x] != "#" and p not in blocked and p not in reach:
                        return False
        return True

    def _build(self, u, c, do, tgt):
        x, y = tgt
        if not (0 <= x < self.W and 0 <= y < self.H):
            return 0
        if do == "break":
            if not any(tgt in o.fences for o in self.colonies if o.id != u.colony):
                return 0
        else:
            near = world.bfs(self.terrain, list(c.den))
            if (self.terrain[y][x] in "#s" or tgt in self.den_owner or tgt in self.plants or tgt in self.seeds
                    or self._unit_at(tgt) is not None or any(tgt in o.fences for o in self.colonies)
                    or near.get(tgt, 99) > R.FENCE_RANGE or len(c.fences) >= R.MAX_FENCES):
                return 0
        need = R.BUILD_TICKS if do == "build" else R.BREAK_TICKS
        prog = u.build[2] + 1 if u.build and u.build[0] == tgt and u.build[1] == do else 1
        u.build = [tgt, do, prog]
        if prog < need:
            return 1
        u.build = None
        if do == "break":
            for o in self.colonies:
                o.fences.pop(tgt, None)
            self._event("break", u.colony, None, tgt)
            return 1
        if c.stores < R.FENCE_COST or not self._fence_ok(u.colony, tgt):
            return 0
        c.stores -= R.FENCE_COST
        c.fences[tgt] = u.colony
        c.stats["fences"] += 1
        self._event("fence", u.colony, None, tgt)
        return 1

    # ---------- end of tick ----------
    def _end_of_tick(self):
        for pos, (owner, t0) in list(self.plants.items()):             # trample: only unripe sprouts
            if self.tick < t0 + R.RIPEN:
                for u in self.units.values():
                    if (u.x, u.y) == pos and u.type == "brute" and u.colony != owner:
                        del self.plants[pos]
                        self.colonies[owner].stats["trampled"] += 1
                        self._event("trample", u.colony, owner, pos)
                        break
        for u in self.units.values():
            for k in u.cd:
                if u.cd[k] > 0:
                    u.cd[k] -= 1
        for c in self.colonies:                                        # hatching
            if c.hatching is not None:
                c.hatching[1] = max(0, c.hatching[1] - 1)
                if c.hatching[1] == 0:
                    free = [d for d in c.den if self._unit_at(d) is None]
                    if free:
                        u = self.add_unit(c.id, c.hatching[0], free[0])
                        self._event("hatch", c.id, None, free[0], unit=u.id, type=u.type)
                        c.hatching = None
        if (self.tick + 1) % R.UPKEEP_EVERY == 0:                      # upkeep, newest critters starve first
            for c in self.colonies:
                mine = sorted(self.units_of(c.id), key=lambda u: u.born)
                while len(mine) > R.FREE_UNITS and c.stores < len(mine) - R.FREE_UNITS:
                    dead = mine.pop()
                    self._spill((dead.x, dead.y), dead.load)
                    del self.units[dead.id]
                    c.stats["starved"] += 1
                    self._event("starve", c.id, None, (dead.x, dead.y), unit=dead.id)
                c.stores -= max(0, len(mine) - R.FREE_UNITS)
        if self.wild and self.tick % R.SEED_EVERY == 0:
            self._spawn_group()

    # ---------- views and frames ----------
    def view(self, ci):
        c = self.colonies[ci]
        vis = fog.visible_cells(self, ci)
        own = self.units_of(ci)
        own_cells = set((u.x, u.y) for u in own)
        rivals, counts = [], defaultdict(int)
        for u in self.units.values():
            if u.colony != ci and fog.sees_unit(self, ci, u, vis, own_cells):
                counts[u.colony] += 1
                rivals.append({"colony": u.colony, "id": u.id, "type": u.type, "pos": [u.x, u.y], "load": u.load,
                               "stunned": u.stun > 0})
        for r, k in counts.items():
            c.seen[r] = k
        status = {}
        for r in self.colonies:
            if r.id != ci:
                status[r.id] = {"units_seen": c.seen.get(r.id, 0),
                                "banked_recently": self.tick - r.last_bank <= R.BANK_RECENT}
        plants = []
        for pos, (owner, t0) in sorted(self.plants.items()):
            if owner == ci or pos in vis:
                age = self.tick - t0
                p = {"pos": [pos[0], pos[1]], "owner": owner, "ripe": age >= R.RIPEN,
                     "stage": min(R.STAGES, age * R.STAGES // R.RIPEN) if age < R.RIPEN else R.STAGES}
                if age < R.RIPEN:
                    p["ticks_to_ripe"] = R.RIPEN - age
                plants.append(p)
        evs = [e for e in self.last_events if e["by"] == ci or e["on"] == ci or tuple(e["pos"]) in vis]
        return {
            "tick": self.tick, "max_ticks": self.max_ticks, "size": self.W, "terrain": list(self.terrain),
            "me": {"id": ci, "stores": c.stores, "den": [list(d) for d in c.den],
                   "hatching": {"type": c.hatching[0], "ticks_left": c.hatching[1]} if c.hatching else None,
                   "next_upkeep_tick": -(-(self.tick + 1) // R.UPKEEP_EVERY) * R.UPKEEP_EVERY - 1,
                   "upkeep_due": max(0, len(own) - R.FREE_UNITS),
                   "fences": [list(f) for f in sorted(c.fences)]},
            "units": [{"id": u.id, "type": u.type, "pos": [u.x, u.y], "load": u.load, "capacity": R.CAPACITY[u.type],
                       "vision": R.VISION[u.type], "stunned": u.stun, "stuck": u.stuck, "cooldowns": dict(u.cd),
                       "build_progress": u.build[2] if u.build else 0, "last": list(u.last)} for u in own],
            "plants": plants,
            "seeds": [{"pos": [p[0], p[1]], "value": v} for p, v in sorted(self.seeds.items()) if p in vis],
            "rivals": rivals,
            "rival_fences": [list(f) for r in self.colonies if r.id != ci for f in sorted(r.fences) if f in vis],
            "rival_status": status,
            "events_seen": evs,
        }

    def frame(self):
        """Full state after the tick just resolved, in the compact replay format (documented in BOT_GUIDE.md)."""
        return {
            "t": self.tick,
            "u": [[u.colony, u.id, TYPE_IDX[u.type], u.x, u.y, u.load, u.stun, 1 if u.stuck else 0,
                   ACTS.index(u.last[0]) * 2 + u.last[1]] for u in sorted(self.units.values(), key=lambda u: u.id)],
            "p": [[p[0], p[1], o, t0] for p, (o, t0) in sorted(self.plants.items())],
            "s": [[p[0], p[1], v] for p, v in sorted(self.seeds.items())],
            "f": [[p[0], p[1], c.id] for c in self.colonies for p in sorted(c.fences)],
            "st": [c.stores for c in self.colonies],
            "h": [[c.hatching[0], c.hatching[1]] if c.hatching else None for c in self.colonies],
            "e": [[e["type"], e["by"], e["on"], e["pos"][0], e["pos"][1], e.get("n", 0)] for e in self.events],
        }

    def result(self):
        rows = []
        for c in self.colonies:
            rows.append({"colony": c.id, "stores": c.stores, "errors": c.errors, "alive": len(self.units_of(c.id)),
                         "stats": dict(c.stats)})
        key = lambda r: (r["stores"], -r["errors"], r["alive"])
        best = max(key(r) for r in rows)
        return {"scores": rows, "winners": [r["colony"] for r in rows if key(r) == best]}
