"""python run_match.py a.py b.py [c.py d.py] [--seed N] [--ticks N] [--out FILE] [--no-open]"""
import argparse, json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from engine import run_match, BotLoadError, rules          # noqa: E402
from engine.local_runner import run_isolated                # noqa: E402


def main(argv=None):
    ap = argparse.ArgumentParser(description="Critterbots: Colonies match runner")
    ap.add_argument("bots", nargs="+", help="2 to 4 bot files")
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--ticks", type=int, default=rules.TICKS)
    ap.add_argument("--out", default=os.path.join(HERE, "replay.json"))
    ap.add_argument("--no-open", action="store_true", help="do not open the viewer")
    ap.add_argument("--timeout", type=int, default=120, help="wall-clock limit for the whole match in seconds")
    a = ap.parse_args(argv)
    if not 2 <= len(a.bots) <= 4:
        print("error: give 2 to 4 bot files", file=sys.stderr)
        return 2
    bots = []
    for path in a.bots:
        if not os.path.isfile(path):
            print("error: bot file not found: %s" % path, file=sys.stderr)
            return 2
        name = os.path.splitext(os.path.basename(path))[0]
        names = [b["name"] for b in bots]
        bots.append({"name": name if name not in names else "%s#%d" % (name, len(bots) + 1),
                     "source": open(path, encoding="utf-8").read()})
    replay = run_isolated(bots, seed=a.seed, ticks=a.ticks, timeout=a.timeout)      # child process: a stuck bot cannot hang this command
    if "load_error" in replay:
        print("error: %s" % replay["load_error"], file=sys.stderr)
        return 2
    if "aborted" in replay:
        print("error: match aborted: %s" % replay["aborted"], file=sys.stderr)
        return 3
    with open(a.out, "w", encoding="utf-8") as f:
        json.dump(replay, f, separators=(",", ":"), sort_keys=True)
    print("Critterbots: Colonies  seed=%d ticks=%d  engine %s" % (a.seed, a.ticks, rules.ENGINE_VERSION))
    print("%-4s %-14s %6s %6s %5s %5s %5s %5s %5s %5s" % ("rank", "bot", "stores", "errors", "snat", "bonk", "hatch", "plnt", "harv", "starv"))
    rows = sorted(replay["result"]["scores"], key=lambda r: (-r["stores"], r["errors"]))
    for i, r in enumerate(rows, 1):
        s = r["stats"]
        print("%-4d %-14s %6d %6d %5d %5d %5d %5d %5d %5d" % (i, replay["bots"][r["colony"]], r["stores"], r["errors"], s["snatches"],
              s["bonks"], s["hatches"], s["planted"], s["harvested"], s["starved"]))
    print("Winner: " + ", ".join(replay["bots"][c] for c in replay["result"]["winners"]))
    print("Replay written to %s (%d KB)" % (a.out, os.path.getsize(a.out) // 1024))
    return 0


if __name__ == "__main__":
    sys.exit(main())
