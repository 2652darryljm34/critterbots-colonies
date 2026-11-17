"""Deterministic step budget: count executed Python lines with sys.settrace.

Unlike a wall-clock limit this gives the same answer on every machine and in Pyodide. It cannot stop code that is
stuck inside one C call (sorted(range(10**9)), time.sleep) or a bot that swallows BaseException in a loop; the outer
watchdog (Web Worker terminate in the browser, process kill in local_runner.py) covers those.
"""
import sys


class OverBudget(BaseException):
    """BaseException so a bot's `except Exception:` does not swallow it."""


def run(fn, arg, limit):
    """Call fn(arg) allowed `limit` executed lines. Returns (result, lines_used). Raises OverBudget."""
    count = [0]

    def local(frame, event, _arg):
        if event == "line":
            count[0] += 1
            if count[0] > limit:
                raise OverBudget("over budget: more than %d lines" % limit)
        return local

    def glob(frame, event, _arg):
        return local

    old = sys.gettrace()
    sys.settrace(glob)
    try:
        result = fn(arg)
    finally:
        sys.settrace(old)
    return result, count[0]
