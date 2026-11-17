"""python ladder.py bots/*.py --seeds 1-10 [--json out.json] [--timeout 120]

Round robin of 2-bot matches, every pair in both seat orders on every seed. Each match runs in its own subprocess
(engine/local_runner.py: wall-clock kill, memory limit where the OS has one, no network), so it is safe on submitted bots.
Prints the win matrix (ties count half) and per-bot averages."""
import argparse, itertools, json, os, sys
from concurrent.futures import ThreadPoolExecutor

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from engine import rules                                  # noqa: E402
from engine.local_runner import run_isolated              # noqa: E402

STATS = ("snatches", "bonks", "hatches", "harvested", "starved", "stolen_crops", "trampled", "banked", "planted")


def parse_seeds(text):
    if "-" in text:
        a, b = text.split("-")
        return list(range(int(a), int(b) + 1))
    return [int(x) for x in text.split(",")]


def load_bot(path):
    return {"name": os.path.splitext(os.path.basename(path))[0], "source": open(path, encoding="utf-8").read(), "path": path}


def play_all(bots, seeds, timeout=120, workers=None, progress=None):
    """Returns one record per match: {a, b, seed, scores:[sa, sb], winners:[idx...], stats:[{..},{..}], errors:[n,n], aborted}."""
    jobs = [(x, y, s) for x, y in itertools.permutations(bots, 2) for s in seeds]

    def one(job):
        x, y, seed = job
        r = run_isolated([{"name": x["name"], "source": x["source"]}, {"name": y["name"], "source": y["source"]}], seed=seed,
                         timeout=timeout, summary=True)
        rec = {"a": x["name"], "b": y["name"], "seed": seed}
        if "aborted" in r or "load_error" in r:
            rec["aborted"] = r.get("aborted") or r["load_error"]
            return rec
        sc = r["result"]["scores"]
        rec.update(scores=[sc[0]["stores"], sc[1]["stores"]], winners=r["result"]["winners"], stats=[sc[0]["stats"], sc[1]["stats"]],
                   errors=[sc[0]["errors"], sc[1]["errors"]], diag=r.get("diag"))
        return rec
    out = []
    with ThreadPoolExecutor(max_workers=workers or max(2, (os.cpu_count() or 2))) as ex:
        for i, rec in enumerate(ex.map(one, jobs)):
            out.append(rec)
            if progress:
                progress(i + 1, len(jobs))
    return out


def summarize(bots, records):
    """Per bot: overall win rate, head-to-head rates, and averages of score and the interaction stats."""
    names = [b["name"] for b in bots]
    agg = dict((n, {"games": 0, "wins": 0.0, "score": 0.0, "h2h": {}, "stats": dict((k, 0) for k in STATS), "aborted": 0}) for n in names)
    pair = {}
    for r in records:
        if "aborted" in r:
            for n in (r["a"], r["b"]):
                agg[n]["aborted"] += 1
            continue
        for idx, (me, opp) in enumerate(((r["a"], r["b"]), (r["b"], r["a"]))):
            a = agg[me]
            win = (1.0 / len(r["winners"])) if idx in r["winners"] else 0.0
            a["games"] += 1; a["wins"] += win; a["score"] += r["scores"][idx]
            for k in STATS:
                a["stats"][k] += r["stats"][idx][k]
            h = pair.setdefault((me, opp), [0, 0.0])
            h[0] += 1; h[1] += win
    for n in names:
        a = agg[n]
        a["overall"] = a["wins"] / a["games"] if a["games"] else 0.0
        a["avg_score"] = a["score"] / a["games"] if a["games"] else 0.0
        a["avg_stats"] = dict((k, v / a["games"] if a["games"] else 0.0) for k, v in a["stats"].items())
        a["h2h"] = dict((o, pair[(n, o)][1] / pair[(n, o)][0]) for o in names if (n, o) in pair)
    return agg


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("bots", nargs="*", help="bot files (default: every bot in bots/manifest.json)")
    ap.add_argument("--seeds", default="1-10", help="e.g. 1-10 or 3,5,8 (a plain number N means 1-N)")
    ap.add_argument("--json")
    ap.add_argument("--timeout", type=int, default=120)
    a = ap.parse_args(argv)
    seeds = parse_seeds("1-" + a.seeds if a.seeds.isdigit() else a.seeds)
    paths = a.bots or [os.path.join(HERE, "bots", b["file"]) for b in json.load(open(os.path.join(HERE, "bots", "manifest.json")))]
    bots = [load_bot(p) for p in paths]
    if len(bots) < 2:
        print("error: need at least two bots", file=sys.stderr)
        return 2
    recs = play_all(bots, seeds, timeout=a.timeout)
    agg = summarize(bots, recs)
    names = [b["name"] for b in bots]
    print("win rate of ROW vs COLUMN (%d games per cell, ties count half), engine %s" % (2 * len(seeds), rules.ENGINE_VERSION))
    print("%-12s" % "" + "".join("%11s" % n[:10] for n in names) + "   overall  avg stores")
    for n in names:
        row = "".join("%11s" % ("-" if m == n else "%d%%" % round(100 * agg[n]["h2h"].get(m, 0))) for m in names)
        print("%-12s" % n + row + "   %6d%%  %9.1f" % (round(100 * agg[n]["overall"]), agg[n]["avg_score"]))
    print("\naverage per match      " + "".join("%10s" % k[:9] for k in STATS))
    for n in names:
        print("%-22s" % n + "".join("%10.1f" % agg[n]["avg_stats"][k] for k in STATS))
    bad = [r for r in recs if "aborted" in r]
    if bad:
        print("\n%d match(es) aborted, e.g. %s vs %s seed %d: %s" % (len(bad), bad[0]["a"], bad[0]["b"], bad[0]["seed"], bad[0]["aborted"]))
    if a.json:
        out = dict((n, agg[n]["overall"]) for n in names)
        out["_detail"] = agg
        json.dump(out, open(a.json, "w"), indent=1)
    return 0


if __name__ == "__main__":
    sys.exit(main())
