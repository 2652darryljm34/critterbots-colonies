"""python tools/validate_bot.py ladder/bots/name.py [...]   Exit 0 only if every file is a valid ladder submission:
name is <github-username>.py, at most 50 KB, loads, defines act(view), and beats the sleepwalker (5 of 6 games on seeds 1-3, both seats).
Matches run in isolated subprocesses (engine/local_runner.py). Prints a markdown summary (also written to $GITHUB_STEP_SUMMARY)."""
import os, re, sys
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..")
sys.path.insert(0, ROOT)
from ladder import load_bot, play_all                    # noqa: E402

MAX_BYTES = 50 * 1024
NAME = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})\.py$")


def validate(path):
    base = os.path.basename(path)
    if not NAME.match(base):
        return False, "file name must be <github-username>.py (letters, digits, hyphen)"
    if os.path.getsize(path) > MAX_BYTES:
        return False, "larger than 50 KB"
    bot, sleep = load_bot(path), load_bot(os.path.join(ROOT, "bots", "sleepwalker.py"))
    pts = 0
    for r in play_all([bot, sleep], [1, 2, 3], timeout=120):
        if "aborted" in r:
            return False, "match failed: %s" % r["aborted"]
        mine, theirs = (r["scores"] if r["a"] == bot["name"] else r["scores"][::-1])
        pts += mine > theirs
    return (pts >= 5), "beat the sleepwalker in %d of 6 games (need 5)" % pts


def main(paths):
    lines, ok = ["| bot | result |", "|---|---|"], True
    for p in paths:
        good, msg = validate(p)
        ok &= good
        lines.append("| %s | %s %s |" % (os.path.basename(p), "PASS" if good else "FAIL", msg))
    text = "\n".join(lines)
    print(text)
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        open(os.environ["GITHUB_STEP_SUMMARY"], "a").write(text + "\n")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
