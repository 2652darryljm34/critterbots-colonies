"""python tools/build_site.py   (standard library only)

Makes site/ self-contained so a plain static server in site/ (or GitHub Pages) can serve it:
  site/engine/*.py        copy of engine/ (without local_runner.py, which is CPython-only)
  site/bots/*             copy of bots/ (the example bots and manifest.json)
  site/engine_files.json  {"version", "hash", "files"}: what the Web Worker loads into Pyodide
  site/guide.html         BOT_GUIDE.md rendered with the tiny converter below
  site/docs/*.md          the other docs, linked from the footer
Everything it writes is generated; edit the sources, not the copies."""
import hashlib, html, json, os, re, shutil, sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SITE = os.path.join(ROOT, "site")
sys.path.insert(0, ROOT)
from engine.rules import ENGINE_VERSION   # noqa: E402


# ---------- tiny markdown converter: headings, fences, tables, lists, paragraphs, inline code/bold/italic/links ----------
def inline(t):
    t = html.escape(t, quote=False)
    t = re.sub(r"`([^`]+)`", lambda m: "<code>%s</code>" % m.group(1), t)
    t = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", t)
    t = re.sub(r"(?<![\w*])\*([^*\n]+)\*(?![\w*])", r"<em>\1</em>", t)
    return re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r'<a href="\2">\1</a>', t)


def slug(t):
    return re.sub(r"[^a-z0-9]+", "-", re.sub(r"<[^>]+>", "", t).lower()).strip("-")


def markdown(src):
    out, lines, i = [], src.split("\n"), 0
    while i < len(lines):
        ln = lines[i]
        if ln.startswith("```"):
            j = i + 1
            while j < len(lines) and not lines[j].startswith("```"):
                j += 1
            out.append("<pre><code>%s</code></pre>" % html.escape("\n".join(lines[i + 1:j])))
            i = j + 1
        elif re.match(r"#{1,4} ", ln):
            n = len(ln.split(" ")[0])
            out.append('<h%d id="%s">%s</h%d>' % (n, slug(ln[n + 1:]), inline(ln[n + 1:]), n))
            i += 1
        elif ln.startswith("|") and i + 1 < len(lines) and re.match(r"\|[\s:|-]+\|?\s*$", lines[i + 1]):
            head = [c.strip() for c in ln.strip().strip("|").split("|")]
            rows, j = [], i + 2
            while j < len(lines) and lines[j].startswith("|"):
                rows.append([c.strip() for c in lines[j].strip().strip("|").split("|")])
                j += 1
            out.append("<table><thead><tr>%s</tr></thead><tbody>%s</tbody></table>" % (
                "".join("<th>%s</th>" % inline(c) for c in head),
                "".join("<tr>%s</tr>" % "".join("<td>%s</td>" % inline(c) for c in r) for r in rows)))
            i = j
        elif re.match(r"\s*([-*]|\d+\.) ", ln):
            tag = "ol" if re.match(r"\s*\d+\. ", ln) else "ul"
            items = []
            while i < len(lines) and re.match(r"\s*([-*]|\d+\.) ", lines[i]):
                item = re.sub(r"^\s*([-*]|\d+\.) ", "", lines[i])
                i += 1
                while i < len(lines) and lines[i].startswith("  ") and lines[i].strip() and not re.match(r"\s*([-*]|\d+\.) ", lines[i]):
                    item += " " + lines[i].strip()
                    i += 1
                items.append("<li>%s</li>" % inline(item))
            out.append("<%s>%s</%s>" % (tag, "".join(items), tag))
        elif not ln.strip():
            i += 1
        elif ln.strip() == "---":
            out.append("<hr>")
            i += 1
        else:
            para = [ln]
            i += 1
            while i < len(lines) and lines[i].strip() and not re.match(r"(#{1,4} |```|\||\s*([-*]|\d+\.) )", lines[i]):
                para.append(lines[i])
                i += 1
            out.append("<p>%s</p>" % inline(" ".join(para)))
    return "\n".join(out)


PAGE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title} · Critterbots: Colonies</title><link rel="stylesheet" href="site.css"><link rel="icon" href="data:,"></head>
<body>
<nav><b>CRITTERBOTS: COLONIES</b><a href="index.html">Home</a><a href="play.html">Play</a><a class="cur" href="guide.html">Guide</a><a href="ladder.html">Ladder</a></nav>
<main class="doc">{body}<hr><p class="mut">Engine version {version}. Other docs: <a href="docs/EXTENDING.md">EXTENDING</a> · <a href="docs/DECISIONS.md">DECISIONS</a> · <a href="docs/CONTRIBUTING.md">CONTRIBUTING</a> · <a href="docs/SPEC.md">SPEC</a></p></main>
</body></html>
"""


def copy_tree(src, dst, skip=()):
    if os.path.isdir(dst):
        shutil.rmtree(dst)
    os.makedirs(dst)
    for name in sorted(os.listdir(src)):
        p = os.path.join(src, name)
        if os.path.isfile(p) and name not in skip and not name.endswith(".pyc"):
            shutil.copy2(p, os.path.join(dst, name))


def main():
    copy_tree(os.path.join(ROOT, "engine"), os.path.join(SITE, "engine"), skip=("local_runner.py",))
    copy_tree(os.path.join(ROOT, "bots"), os.path.join(SITE, "bots"))
    files = sorted("engine/" + n for n in os.listdir(os.path.join(SITE, "engine")) if n.endswith(".py"))
    h = hashlib.sha256()
    for f in files:
        h.update(f.encode() + open(os.path.join(SITE, f), "rb").read())
    with open(os.path.join(SITE, "engine_files.json"), "w") as f:
        json.dump({"version": ENGINE_VERSION, "hash": h.hexdigest()[:16], "files": files}, f, indent=1)
    docs = os.path.join(SITE, "docs")
    os.makedirs(docs, exist_ok=True)
    for name in ("EXTENDING.md", "DECISIONS.md", "CONTRIBUTING.md", "SPEC.md", "BOT_GUIDE.md", "README.md"):
        if os.path.exists(os.path.join(ROOT, name)):
            shutil.copy2(os.path.join(ROOT, name), os.path.join(docs, name))
    guide = os.path.join(ROOT, "BOT_GUIDE.md")
    body = markdown(open(guide, encoding="utf-8").read()) if os.path.exists(guide) else "<h1>Guide</h1><p>BOT_GUIDE.md is missing.</p>"
    with open(os.path.join(SITE, "guide.html"), "w", encoding="utf-8") as f:
        f.write(PAGE.format(title="Guide", body=body, version=ENGINE_VERSION))
    print("site built: %d engine files, hash %s, engine %s" % (len(files), h.hexdigest()[:16], ENGINE_VERSION))


if __name__ == "__main__":
    main()
