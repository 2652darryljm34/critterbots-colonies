# Bot guide

You write one Python function, `act(view)`. Every tick the game calls it with what your colony can see and you answer
with orders for your critters. After 400 ticks the colony with the most **stores** wins.

## Quick start

### In the browser (nothing to install)
1. Open the **Play** page. The editor starts with the template bot.
2. Pick an opponent and a seed, press **Run match**. The replay plays as soon as the match finishes.
3. Edit, **Run** again. Errors appear under the editor with the line number.
4. **Copy share link** gives a link that re-plays your bot against the same opponent and seed.

### On your computer
You need Python 3.8 or newer and nothing else (no pip packages).

```
python run_match.py mybot.py bots/forager.py --seed 3
```

This plays the match, prints the scoreboard and writes `replay.json`. Without `--no-open` it opens the viewer in your
browser. Use two or four bot files. `python ladder.py bots/*.py --seeds 1-10` plays every pair, both seats, over seeds 1-10.

## A minimal bot (works when pasted into `mybot.py`)

```python
import random

def act(view):
    den = [tuple(c) for c in view["me"]["den"]]
    seeds = [tuple(s["pos"]) for s in view["seeds"] if s["value"] == 1]
    units = {}
    for u in view["units"]:
        x, y = u["pos"]
        if (x, y) in den and u["load"]:
            units[u["id"]] = {"do": "bank"}
        elif (x, y) in seeds and u["load"] < u["capacity"]:
            units[u["id"]] = {"do": "pickup"}
        else:
            goal = den[0] if u["load"] >= 3 or not seeds else min(seeds, key=lambda s: abs(s[0] - x) + abs(s[1] - y))
            dx, dy = goal[0] - x, goal[1] - y
            d = ("E" if dx > 0 else "W") if abs(dx) >= abs(dy) and dx else ("S" if dy > 0 else "N")
            units[u["id"]] = {"do": "move", "dir": d if seeds or u["load"] else random.choice("NESW")}
    return {"units": units}
```

It walks straight at the nearest visible seed (bumping into walls sometimes), picks it up, and banks when it has 3 or
more. It is deliberately naive. `bots/forager.py` is the next step: it plans routes around walls with a breadth-first search.

## The game in one page

- 24 x 24 grid, coordinates `[x, y]`, x grows east, y grows south, `[0, 0]` is the top-left cell. 400 ticks (0 to 399).
- Each colony has a **den**, a 2 x 2 block in a corner: colony 0 top-left, 1 bottom-right, 2 top-right, 3 bottom-left.
  Your critters may share den cells. Rival critters can never enter your den. A critter standing in its own den cannot be
  snatched or bonked.
- **Wild seeds** appear all over the map (never within 6 steps of a den). Brown seeds are worth 1. Golden seeds are worth 3
  and only appear near the middle. Walk onto a seed and `pickup`; carry it to your den and `bank` it.
- **Stores** are your score: banked seeds minus what you spend. Load you are still carrying, growing crops and living
  critters are worth **nothing** at the end of tick 399. Every investment has to pay itself back in time.
- You start with 2 workers and 4 stores.

### Terrain
Terrain is fully known from tick 0, in `view["terrain"]`: a list of strings, one per row, one character per cell.

| char | meaning |
|---|---|
| `.` | open ground |
| `#` | wall: nothing can enter |
| `m` | mud: entering it makes the critter lose its **next** action (`stuck`), except scouts |
| `g` | grass: a critter standing in grass is hidden from rivals unless one of their critters is orthogonally adjacent |
| `s` | soil: the only place a seed can be planted |

### Critters

| type | carries | sees | can do |
|---|---|---|---|
| worker | 5 | 4 | `move` `pickup` `bank` `snatch` `plant` `harvest` `build` `wait` |
| scout | 2 | 7 | `move` `dash` `pickup` `bank` `wait`; ignores mud |
| brute | 0 | 3 | `move` `bonk` `shove` `break` `wait`; cannot carry |

Hatching (colony action) costs stores up front: worker 5, scout 3, brute 7. It takes 6 ticks and the newcomer appears on a free
den cell. One hatch at a time, at most 6 living critters.

**Upkeep:** every 30 ticks (charged at the end of ticks 29, 59, 89, ...) every critter beyond the oldest two costs 1 store.
If you cannot pay, the newest critters starve first (removed; their load drops as seeds).

## What `act(view)` receives

`view` is a fresh dictionary every call. Change it however you like; nothing carries over.

| field | contents |
|---|---|
| `tick`, `max_ticks`, `size` | current tick, 400, 24 |
| `terrain` | list of strings, see above |
| `me` | `id`, `stores`, `den` (4 cells), `hatching` (`{"type", "ticks_left"}` or `None`), `next_upkeep_tick`, `upkeep_due` (stores the next upkeep will cost), `fences` (your fence cells) |
| `units` | your critters: `id`, `type`, `pos`, `load`, `capacity`, `vision`, `stunned` (ticks left), `stuck`, `cooldowns` (`dash`, `snatch`, `bonk`, `shove`), `build_progress`, `last` (`[action, worked]` of the previous tick) |
| `plants` | your plants and rival plants you can currently see: `pos`, `owner`, `stage` (0-3), `ripe`, `ticks_to_ripe` (only while growing) |
| `seeds` | visible seeds, wild and spilled: `pos`, `value` |
| `rivals` | visible rival critters: `colony`, `id`, `type`, `pos`, `load`, `stunned` |
| `rival_fences` | visible rival fences |
| `rival_status` | per rival colony: `units_seen` (how many you saw the last time you saw any) and `banked_recently` (did a rival bank in the last 10 ticks?). Rival stores are never shown. |
| `events_seen` | last tick's events you could see: `type`, `tick`, `by`, `on`, `pos` |

Unit ids are unique for the whole match and never reused.

## What you return

```python
return {
    "units": {unit_id: {"do": "move", "dir": "N"}, ...},   # a unit you leave out simply waits
    "colony": {"hatch": "scout"},                          # optional
}
```

Directions are `"N"`, `"E"`, `"S"`, `"W"`. A bad order (wrong type of critter, missing `dir`, unknown action, an id that is
not yours) makes **that one critter wait** and logs one error; your other orders still happen.

| action | who | needs | effect |
|---|---|---|---|
| `wait` | all | | do nothing |
| `move` + `dir` | all | target open | step one cell. Bumps (no move) into walls, the edge, a rival den, a rival fence, or in a collision (below) |
| `dash` + `dir` | scout | cooldown 0 | move two cells in a straight line if both are free of critters and passable; otherwise one cell. Cooldown 4 |
| `pickup` | worker, scout | a seed on your cell, room for it | take it |
| `bank` | worker, scout | standing on your den, load > 0 | add your whole load to stores |
| `plant` | worker | on empty soil, load >= 1 | spend 1 load, a sprout appears |
| `harvest` | worker | on a **ripe** crop (yours or a rival's), 4 free capacity | take the crop (value 4) |
| `snatch` + `dir` | worker | adjacent rival carrying load, not in its den; cooldown 3 (spent even on a miss) | take half its load (rounded up, limited by your free capacity); victim stunned 1 tick |
| `bonk` + `dir` | brute | adjacent rival, not in its den; cooldown 4 | victim drops its **entire** load as seeds around it (3s then 1s, nearest cells first) and is stunned 2 ticks |
| `shove` + `dir` | brute | adjacent rival, not in its den; cooldown 2 | push it one cell away; if that cell is blocked it is stunned 1 tick instead. Shoved into mud = stuck |
| `build` + `dir` | worker | see Fences | three consecutive `build` orders on the same neighbouring cell place a fence (2 stores) |
| `break` + `dir` | brute | adjacent rival fence | three consecutive `break` orders remove it |
| colony `hatch` | colony | stores >= cost, nothing already hatching, fewer than 6 critters | start hatching |

### Farming
`plant` turns 1 load into a sprout owned by your colony on that soil cell. Sprouts show 3 growth stages and ripen **40 ticks**
after planting into a crop worth **4**. Any worker of any colony standing on a ripe crop can `harvest` it, so a crop on the far
side of the map is a gamble. A rival **brute** standing on an *unripe* sprout at the end of a tick destroys it. Wild seeds never
spawn on planted cells.

### Fences
`build` needs: an empty open non-soil cell next to the worker, within 5 steps of your den, no plant, seed or critter on it, you
have 2 stores and fewer than 6 fences, and the fence must not cut any open cell off from a rival den (the game checks by flood
fill and refuses). Fences stop rivals only; your critters walk through them.

## Order of events inside one tick

1. Every bot's `act(view)` is called (with that colony's fog-filtered view) and the orders are checked.
2. Colony orders resolve in colony order (a `hatch` charges its cost now).
3. Stunned critters and critters stuck in mud have their order replaced by `wait`, and their counter drops by one. So a critter
   stunned for N ticks (set during step 5 of tick T) loses its orders on ticks T+1 ... T+N.
4. **Movement.** `move` and `dash` resolve together: a move succeeds if its target cell is free or is being left by a move that
   succeeds (so a column of critters can walk in a line). Two critters that swap cells, several critters entering one cell, or a
   rotation among four cells **all bump**. Own critters can share den cells. Then `shove` resolves, one critter at a time.
5. `pickup`, `harvest`, `bank`, `plant`, `build`, `break`, `snatch`, `bonk` resolve **one critter at a time in a seeded random order**
   over every critter of every colony, using positions after movement. So when two workers want the same seed, a seeded coin
   flip decides who gets it.
6. End of tick: trampling, cooldowns drop by one, hatching progresses (a newcomer appears at 0), upkeep is charged if this is tick
   29, 59, ..., and a new group of wild seeds may spawn.

The map and the seed spawns come from one seeded random number generator, so a match is fully determined by the bots and the seed.

## Fog of war
You see every cell within Manhattan distance `vision` of any of your critters, plus radius 3 around your den. Walls do not block
sight. Rival critters in grass stay hidden unless one of your critters is right next to them. Terrain is always known. Rival
stores are never shown. Keep your own memory in module-level variables: your module stays loaded for the whole match.

## Scoring and ties
Final score = **stores** after the last tick. Ties: higher stores, then fewer errors, then more critters alive, then shared win.

## Guards: what can and cannot go wrong
- **Step budget.** Each `act()` call may execute **200,000 lines** of Python (counted with `sys.settrace`, including functions you
  call). This is the same on every computer, unlike a time limit. Going over cancels that tick's orders and logs `over budget`; after
  three overruns your bot is switched off for the rest of the match. The example bots use 16,000 to 35,000 lines per tick.
  A breadth-first search over the whole map costs a few thousand lines; do heavy work once and keep the result in a global.
- **Watchdog.** Code that runs inside one long C call (`sorted(range(10**9))`, `time.sleep(60)`) is not counted by the step budget.
  The website stops the match after 10 seconds without progress; the command line kills the match process after 120 seconds.
  Either way you get a clear "aborted" message, never a hang.
- **Errors** are logged with the line number in your file. `print()` output is captured (200 characters per tick) and shown in your
  bot's tab in the viewer.
- `random` is reseeded before every call from (seed, tick, colony), so a bot that uses `random` still replays identically.
- **Never let the order of a `set` decide anything.** Iteration order of a set of tuples differs between Python versions, and the
  browser and your computer may run different versions. If two goals tie, break the tie on the cell itself, for example
  `min(goals, key=lambda p: (distance(p), p))`. The example bots had this bug twice during development.
- The modules `js`, `pyodide`, `ctypes`, `subprocess`, `socket`, `threading` and a few more cannot be imported by bots. This is a
  mitigation, not a guarantee; the real isolation is the browser's Web Worker.

## Tips
- **Payback math.** A worker costs 5 now plus 1 per 30 ticks. If it banks 0.1 seed per tick it needs about 60 ticks to repay. Do
  not hatch with fewer than about 100 ticks left. A sprout costs 1 load and returns 4 after 40 ticks; stop planting when fewer than
  ~52 ticks remain.
- **Soil is limited.** A few soil cells sit near each den and a few in the middle. Plant them as soon as you can, harvest the tick
  they ripen, plant again.
- **Fog memory.** A rival crop you saw earlier will be ripe at `tick + ticks_to_ripe`; remember it in a global and arrive on time.
  `bots/warlord.py` keeps such a memory for its crop thief.
- **Why a bonk needs a worker nearby.** A bonk only spills the victim's seeds onto the floor, where anyone can pick them up. Your
  own worker standing close collects them while the victim is stunned.
- **Convoys.** Because a critter may step into a cell another critter is leaving, a line of critters can march together. Two
  critters that want each other's cell both bump; give them different routes or random tie-breaks (`last` tells you a move failed).
- **Hatching a scout (3 stores)** gives the whole colony vision 7 around it. It also lets a thief find rival crops.
- **Mud costs a full action**, so route around it unless you are a scout.

## The replay format (`replay.json`)

One JSON object, keys sorted, no spaces.

| key | contents |
|---|---|
| `format`, `engine_version`, `seed`, `ticks`, `size` | |
| `terrain` | list of strings |
| `dens` | per colony, its 4 den cells |
| `bots` | bot names |
| `frames` | `ticks + 1` frames (frame 0 is the start, frame `t + 1` is the state after tick `t`) |
| `errors` | `[tick, colony, text]` |
| `logs` | per colony, `[tick, text]` print output |
| `result` | `scores` (per colony: `stores`, `errors`, `alive`, `stats`) and `winners` |
| `diag` | line counts per bot; differs between Python versions, so it is not part of the "identical replay" guarantee |

Each frame: `t`, `u` units `[colony, id, type(0 worker/1 scout/2 brute), x, y, load, stun, stuck, last]` (`last` = action index x 2
+ worked), `p` plants `[x, y, owner, planted_tick]`, `s` seeds `[x, y, value]`, `f` fences `[x, y, colony]`, `st` stores per
colony, `h` hatching `[type, ticks_left]` or `null`, `e` events `[type, by, on, x, y, n]`. Fog is not stored: the viewer recomputes
what a colony could see from the unit positions.

## Reading `ladder.py`
`python ladder.py bots/*.py --seeds 1-10` prints a matrix: each cell is the **row bot's win rate against the column bot** over
both seat orders (ties count half). `overall` averages a row. The second table gives per-match averages of snatches, bonks,
hatches, crops harvested, starvations, crops stolen, sprouts trampled, seeds banked and seeds planted. If your bot never hatches
and never plants, those columns will tell you what you are missing.
