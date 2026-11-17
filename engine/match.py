"""Match loop. Takes bot SOURCE CODE as strings and returns the replay dict, so the same code runs on the command line
(CPython) and in the browser (Pyodide)."""
import builtins, io, random, sys, traceback, types
from . import rules as R, budget
from .game import Game

BLOCKED_IMPORTS = ("js", "pyodide", "pyodide_js", "_pyodide", "pyodide_http", "ctypes", "subprocess", "socket",
                   "threading", "_thread", "multiprocessing", "shutil", "importlib")   # a mitigation, not a guarantee


class BotLoadError(Exception):
    """Raised when a bot fails to import or has no act(view)."""


def error_text(exc, filename):
    line = ""
    for fr in reversed(traceback.extract_tb(exc.__traceback__)):
        if fr.filename == filename:
            line = "line %d: " % fr.lineno
            break
    return line + traceback.format_exception_only(type(exc), exc)[-1].strip()


def _guarded_builtins():
    real = builtins.__import__

    def guarded(name, globals=None, locals=None, fromlist=(), level=0):
        if level == 0 and name.split(".")[0] in BLOCKED_IMPORTS:
            raise ImportError("importing %r is not allowed in bots" % name)
        return real(name, globals, locals, fromlist, level)
    d = dict(builtins.__dict__)
    d["__import__"] = guarded
    return d


class Bot(object):
    def __init__(self, name, source, index, step_budget):
        self.name, self.index, self.budget = name, index, step_budget
        self.filename = "<bot %d %s>" % (index, name)
        self.overruns, self.disabled, self.max_lines = 0, False, 0
        mod = types.ModuleType("bot_%d" % index)
        mod.__dict__["__builtins__"] = _guarded_builtins()
        random.seed(index)
        try:
            exec(compile(source, self.filename, "exec"), mod.__dict__)
        except SyntaxError as e:
            raise BotLoadError("bot %s has a syntax error on line %s: %s" % (name, e.lineno, e.msg))
        except BaseException as e:
            raise BotLoadError("bot %s failed to import: %s" % (name, error_text(e, self.filename)))
        self.act = mod.__dict__.get("act")
        if not callable(self.act):
            raise BotLoadError("bot %s has no act(view) function" % name)

    def call(self, view, seed):
        """Returns (action or None, error text or None, printed text)."""
        if self.disabled:
            return None, None, ""
        random.seed(seed)
        out, old = io.StringIO(), sys.stdout
        sys.stdout = out
        try:
            result, lines = budget.run(self.act, view, self.budget)
            self.max_lines = max(self.max_lines, lines)
            return result, None, out.getvalue()
        except budget.OverBudget:
            self.overruns += 1
            msg = "over budget: act() ran more than %d lines" % self.budget
            if self.overruns >= R.MAX_OVERRUNS:
                self.disabled = True
                msg += "; bot disabled after %d overruns" % R.MAX_OVERRUNS
            return None, msg, out.getvalue()
        except BaseException as e:           # bots may raise anything, even SystemExit
            return None, error_text(e, self.filename), out.getvalue()
        finally:
            sys.stdout = old


def run_match(bots, seed=1, ticks=R.TICKS, step_budget=R.STEP_BUDGET, on_frame=None, terrain=None):
    """bots: list of {"name", "source"}. Returns the replay dict. on_frame(frame) is called as frames are produced."""
    runners = [Bot(b["name"], b["source"], i, step_budget) for i, b in enumerate(bots)]
    game = Game(n=len(runners), seed=seed, ticks=ticks, terrain=terrain)
    first = game.frame()
    frames, logs = [first], [[] for _ in runners]
    if on_frame:
        on_frame(first)
    for t in range(ticks):
        actions = {}
        for i, bot in enumerate(runners):
            act, err, printed = bot.call(game.view(i), seed * 1000003 + t * 131 + i)
            if err:
                game._err(i, err)
            if printed.strip():
                logs[i].append([t, printed.strip()[:R.LOG_LIMIT]])
            actions[i] = act
        frame = game.step(actions)
        frames.append(frame)
        if on_frame:
            on_frame(frame)
    res = game.result()
    return {
        "format": 1, "engine_version": R.ENGINE_VERSION, "seed": seed, "ticks": ticks, "size": game.W,
        "terrain": list(game.terrain), "dens": [[list(c) for c in col.den] for col in game.colonies],
        "bots": [b["name"] for b in bots], "types": list(R.TYPES),
        "frames": frames, "errors": game.errors, "logs": logs, "result": res,
        "disabled": [b.disabled for b in runners],
        "diag": {"max_lines": [b.max_lines for b in runners]},   # differs between Python versions: not part of the identical-replay contract
    }
