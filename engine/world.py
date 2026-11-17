"""Terrain generation and grid helpers. Terrain chars: '#' wall, 'm' mud, 'g' grass, 's' soil, '.' open.

The map is generated for one quadrant and mirrored on both axes, so all four dens are exactly equivalent.
"""
from collections import deque
from .rules import SIZE


def den_cells(colony, size=SIZE):
    """2x2 den in a corner: 0 top-left, 1 bottom-right, 2 top-right, 3 bottom-left."""
    x, y = [(0, 0), (size - 2, size - 2), (size - 2, 0), (0, size - 2)][colony]
    return [(x, y), (x + 1, y), (x, y + 1), (x + 1, y + 1)]


def bfs(terrain, starts, blocked=None):
    """Step distance from `starts` over non-wall cells (plus optional extra blocked set)."""
    h, w = len(terrain), len(terrain[0])
    dist = dict((s, 0) for s in starts)
    q = deque(starts)
    while q:
        x, y = q.popleft()
        for dx, dy in ((0, -1), (1, 0), (0, 1), (-1, 0)):
            n = (x + dx, y + dy)
            if 0 <= n[0] < w and 0 <= n[1] < h and n not in dist and terrain[n[1]][n[0]] != "#" \
                    and not (blocked and n in blocked):
                dist[n] = dist[(x, y)] + 1
                q.append(n)
    return dist


def center_cells(size=SIZE):
    a = size // 2
    return [(a - 1, a - 1), (a, a - 1), (a - 1, a), (a, a)]


def _grow(rng, q, start, count, ok):
    """Grow a blob of `count` cells from `start` over cells accepted by ok(x, y)."""
    cells, frontier = [start], [start]
    while len(cells) < count and frontier:
        x, y = frontier[rng.randrange(len(frontier))]
        opts = [(x + dx, y + dy) for dx, dy in ((0, -1), (1, 0), (0, 1), (-1, 0))
                if (x + dx, y + dy) not in cells and ok(x + dx, y + dy)]
        if not opts:
            frontier.remove((x, y))
            continue
        n = opts[rng.randrange(len(opts))]
        cells.append(n)
        frontier.append(n)
    return cells


def generate(rng, size=SIZE, max_tries=500):
    """Returns terrain as a list of strings. Consumes `rng` in a fixed order (see DECISIONS.md)."""
    half = size // 2
    mid = half - 1                       # quadrant cell next to the centre
    for _ in range(max_tries):
        q = [["."] * half for _ in range(half)]

        def inside(x, y):
            return 0 <= x < half and 0 <= y < half

        def free(x, y, mind):            # empty, away from the den, centre kept clear
            return inside(x, y) and q[y][x] == "." and x + y >= mind and abs(x - mid) + abs(y - mid) > 1

        for _s in range(rng.randint(4, 8)):                       # wall segments
            x, y, horiz, ln = rng.randrange(half), rng.randrange(half), rng.random() < 0.5, rng.randint(2, 4)
            for i in range(ln):
                cx, cy = (x + i, y) if horiz else (x, y + i)
                if free(cx, cy, 4):
                    q[cy][cx] = "#"
        for _s in range(rng.randint(8, 14)):                      # mud
            x, y = rng.randrange(half), rng.randrange(half)
            if free(x, y, 3):
                q[y][x] = "m"
        for _s in range(rng.randint(10, 16)):                     # grass clumps
            x, y = rng.randrange(half), rng.randrange(half)
            for cx, cy in ((x, y), (x + 1, y) if rng.random() < 0.5 else (x, y + 1)):
                if free(cx, cy, 2):
                    q[cy][cx] = "g"
        # soil: a patch near the den and one in the middle (both may replace grass/mud, never walls or the den)
        near_ok = lambda x, y: inside(x, y) and q[y][x] != "#" and 3 <= x + y <= 8
        sx, sy = rng.randrange(half), rng.randrange(half)
        near = _grow(rng, q, (sx, sy), rng.randint(5, 7), near_ok) if near_ok(sx, sy) else []
        mid_ok = lambda x, y: inside(x, y) and q[y][x] != "#" and 2 <= abs(x - mid) + abs(y - mid) <= 5
        mx, my = rng.randrange(half), rng.randrange(half)
        middle = _grow(rng, q, (mx, my), rng.randint(3, 5), mid_ok) if mid_ok(mx, my) else []
        if len(near) < 4 or len(middle) < 3:
            continue
        for x, y in near + middle:
            q[y][x] = "s"
        rows = []
        for y in range(size):
            qy = y if y < half else size - 1 - y
            rows.append("".join(q[qy][x if x < half else size - 1 - x] for x in range(size)))
        walls = sum(r.count("#") for r in rows)
        opens = [(x, y) for y in range(size) for x in range(size) if rows[y][x] != "#"]
        if not 12 <= walls <= 90 or len(bfs(rows, [(0, 0)])) != len(opens):
            continue
        return rows
    raise RuntimeError("map generation failed")
