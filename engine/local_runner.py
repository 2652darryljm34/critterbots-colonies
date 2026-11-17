"""CPython-only extras for the command line and the public ladder. The website never imports this file.

run_isolated() plays one match in a child process so that a bot that hangs inside C code, eats memory, or tries the
network cannot take the caller down:
  - wall clock: the parent kills the child after `timeout` seconds and reports the match as aborted;
  - memory: RLIMIT_AS where the `resource` module exists (Linux/macOS). On Windows there is no portable equivalent in the
    standard library, so only the wall-clock limit applies there (the ladder runs on GitHub's Linux runners);
  - network: the child makes `socket.socket` raise before any bot is loaded. That is a mitigation, not a sandbox.
"""
import json, os, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)


def run_isolated(bots, seed=1, ticks=400, timeout=120, mem_mb=1024, summary=False, python=None):
    """Returns the replay dict (or, with summary=True, a small dict without frames). On abort returns {"aborted": reason}."""
    payload = json.dumps({"bots": bots, "seed": seed, "ticks": ticks, "mem_mb": mem_mb, "summary": summary})
    try:
        p = subprocess.run([python or sys.executable, "-I", os.path.join(HERE, "local_runner.py"), "--child"], input=payload,
                           capture_output=True, text=True, timeout=timeout, cwd=ROOT)
    except subprocess.TimeoutExpired:
        return {"aborted": "match killed after %d s of wall-clock time (a bot is probably stuck in a long C call or time.sleep)" % timeout}
    if p.returncode != 0:
        tail = (p.stderr or "").strip().splitlines()[-1:] or ["exit code %d" % p.returncode]
        return {"aborted": "match process failed: " + tail[0][:300]}
    try:
        return json.loads(p.stdout)
    except ValueError:
        return {"aborted": "match produced unreadable output"}


def _child():
    req = json.loads(sys.stdin.read())
    try:
        import resource
        lim = int(req["mem_mb"]) * 1024 * 1024
        resource.setrlimit(resource.RLIMIT_AS, (lim, lim))
    except Exception:                                    # no resource module (Windows) or the limit was refused
        pass
    import socket

    def _no_network(*a, **k):
        raise OSError("network access is disabled for bots")
    socket.socket = _no_network
    socket.create_connection = _no_network
    sys.path.insert(0, ROOT)
    from engine import run_match, BotLoadError, rules
    tune = os.environ.get('CRITTERBOTS_TUNE')           # dev only: balance experiments, e.g. '{"CROP_VALUE": 3}'
    if tune:
        rules.__dict__.update(json.loads(tune))
    try:
        replay = run_match(req["bots"], seed=req["seed"], ticks=req["ticks"])
    except BotLoadError as e:
        out = {"load_error": str(e)}
    else:
        if req.get("summary"):
            replay = {k: v for k, v in replay.items() if k not in ("frames", "terrain")}
        out = replay
    sys.stdout.write(json.dumps(out, separators=(",", ":"), sort_keys=True))


if __name__ == "__main__":
    if "--child" in sys.argv:
        _child()
