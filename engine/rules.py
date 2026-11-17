"""All tunable numbers. Change a number here and log the change in DECISIONS.md."""
ENGINE_VERSION = "0.1.0"        # bump whenever rules change (it is part of every shared match recipe)

SIZE = 24
TICKS = 400
TYPES = ("worker", "scout", "brute")
CAPACITY = {"worker": 5, "scout": 2, "brute": 0}
VISION = {"worker": 4, "scout": 7, "brute": 3}
HATCH_COST = {"worker": 5, "scout": 3, "brute": 7}
HATCH_TICKS = 6
MAX_UNITS = 6
START_WORKERS = 2
START_STORES = 4
UPKEEP_EVERY = 30               # upkeep is charged at the end of ticks 29, 59, 89, ...
FREE_UNITS = 2                  # the two oldest critters are free; every other one costs 1 store per upkeep

SEED_EVERY = 3                  # wild seed group spawns at the end of ticks 0, 3, 6, ...
SEED_CAP = 24
SEED_MIN_DEN_DIST = 7           # "never within 6 steps of a den"
GOLD_PROB = 0.25
GOLD_CENTER_DIST = 5            # golden seeds (value 3) only within 5 steps of the centre
START_SEED_FILL = 12            # the map starts half full

RIPEN = 40                      # ticks from planting to a ripe crop
CROP_VALUE = 4
STAGES = 3                      # visible growth stages before ripe

FENCE_COST = 2
BUILD_TICKS = 3                 # consecutive build actions on the same cell
BREAK_TICKS = 3
MAX_FENCES = 6
FENCE_RANGE = 5                 # steps from the den

DEN_VISION = 3
BANK_RECENT = 10                # "rival_banked_recently" window

COOLDOWN = {"dash": 4, "snatch": 3, "bonk": 4, "shove": 2}
STUN = {"snatch": 1, "bonk": 2, "shove": 1}

STEP_BUDGET = 200000            # executed Python lines per act() call
MAX_OVERRUNS = 3                # a bot that overruns this many times is disabled
LOG_LIMIT = 200                 # characters of print() output kept per tick

DIRS = {"N": (0, -1), "E": (1, 0), "S": (0, 1), "W": (-1, 0)}
