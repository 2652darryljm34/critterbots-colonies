"""Vision. A colony sees every cell within Manhattan `vision` of any of its critters plus radius DEN_VISION of its den.
Walls do not block sight. A critter standing in grass is hidden from rivals unless a rival unit is orthogonally adjacent."""
from .rules import VISION, DEN_VISION


def visible_cells(game, ci):
    vis = set()
    W, H = game.W, game.H
    centers = [(u.x, u.y, VISION[u.type]) for u in game.units.values() if u.colony == ci]
    centers += [(x, y, DEN_VISION) for x, y in game.colonies[ci].den]
    for cx, cy, r in centers:
        for y in range(max(0, cy - r), min(H, cy + r + 1)):
            rem = r - abs(y - cy)
            for x in range(max(0, cx - rem), min(W, cx + rem + 1)):
                vis.add((x, y))
    return vis


def sees_unit(game, ci, u, vis, own_cells):
    """True if colony ci can see rival unit u this tick."""
    if (u.x, u.y) not in vis:
        return False
    if game.terrain[u.y][u.x] == "g":
        return any(((u.x + dx, u.y + dy) in own_cells) for dx, dy in ((0, -1), (1, 0), (0, 1), (-1, 0)))
    return True
