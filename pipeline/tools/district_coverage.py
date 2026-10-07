"""Walkable-ground analysis shared by build_district.py and validate_district.py.

Rasterises walkable floor (normal.y > 0.7, below 300 cm) onto a 25 cm grid, flood-fills from a spawn
with a 45 cm step limit, and finds reachable cells that border floor-less cells with no wall nearby
(places where Link could walk off into the void).
"""
from collections import deque
import numpy as np

STEP = 25.0
STEP_HEIGHT = 45.0


def analyse(V, F, spawn_xz, bounds=None):
    """spawn_xz: one (x, z) seed or a list of seeds. bounds: optional (x0, x1, z0, z1) grid extent."""
    seeds = [spawn_xz] if np.isscalar(spawn_xz[0]) else list(spawn_xz)
    T = V[F]
    n = np.cross(T[:, 1] - T[:, 0], T[:, 2] - T[:, 0])
    n /= np.maximum(np.linalg.norm(n, axis=1)[:, None], 1e-9)
    floor_tris = T[n[:, 1] > 0.7]
    wall_tris = T[np.abs(n[:, 1]) < 0.3]
    lo = V.min(0).astype(float); hi = V.max(0).astype(float)
    if bounds is not None:
        lo[0], hi[0], lo[2], hi[2] = bounds[0], bounds[1], bounds[2], bounds[3]
    xs = np.arange(lo[0], hi[0], STEP); zs = np.arange(lo[2], hi[2], STEP)
    H = np.full((len(zs), len(xs)), np.nan)
    for t in floor_tris:
        p = t[:, [0, 2]]
        x0, z0 = p.min(0); x1, z1 = p.max(0)
        ix = np.arange(max(0, int((x0 - lo[0]) / STEP)), min(len(xs), int((x1 - lo[0]) / STEP) + 2))
        iz = np.arange(max(0, int((z0 - lo[2]) / STEP)), min(len(zs), int((z1 - lo[2]) / STEP) + 2))
        if not len(ix) or not len(iz):
            continue
        M = np.array([p[1] - p[0], p[2] - p[0]]).T
        if abs(np.linalg.det(M)) < 1e-6:
            continue
        gx, gz = np.meshgrid(xs[ix], zs[iz]); pts = np.stack([gx.ravel(), gz.ravel()], 1)
        uw = np.linalg.solve(M, (pts - p[0]).T).T
        inside = (uw[:, 0] >= -1e-6) & (uw[:, 1] >= -1e-6) & (uw.sum(1) <= 1 + 1e-6)
        if not inside.any():
            continue
        y = t[0, 1] + uw[:, 0] * (t[1, 1] - t[0, 1]) + uw[:, 1] * (t[2, 1] - t[0, 1])
        y = np.where(inside & (y < 300), y, np.nan).reshape(gx.shape)
        sub = H[np.ix_(iz, ix)]
        H[np.ix_(iz, ix)] = np.where(np.isnan(sub), y, np.fmin(sub, y))

    def cell(x, z):
        return int(round((z - lo[2]) / STEP)), int(round((x - lo[0]) / STEP))

    reach = np.zeros(H.shape, bool)
    q = deque()
    for seed in seeds:
        start = cell(*seed)
        if 0 <= start[0] < H.shape[0] and 0 <= start[1] < H.shape[1] and not np.isnan(H[start]) and not reach[start]:
            reach[start] = True; q.append(start)
    assert q, 'no seed has floor'
    while q:
        r, c = q.popleft()
        for dr, dc in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            rr, cc = r + dr, c + dc
            if 0 <= rr < H.shape[0] and 0 <= cc < H.shape[1] and not reach[rr, cc] \
                    and not np.isnan(H[rr, cc]) and abs(H[rr, cc] - H[r, c]) <= STEP_HEIGHT:
                reach[rr, cc] = True; q.append((rr, cc))

    wall_grid = np.zeros(H.shape, bool)
    pts = []
    for t in wall_tris:
        if t[:, 1].min() >= 200:
            continue
        for a, b in ((0, 1), (1, 2), (2, 0)):
            seg = t[b, [0, 2]] - t[a, [0, 2]]
            for s in np.linspace(0, 1, max(2, int(np.linalg.norm(seg) / 10) + 1)):
                pts.append(t[a, [0, 2]] + s * seg)
    if pts:
        pts = np.array(pts)
        wr = np.clip(np.round((pts[:, 1] - lo[2]) / STEP).astype(int), 0, H.shape[0] - 1)
        wc = np.clip(np.round((pts[:, 0] - lo[0]) / STEP).astype(int), 0, H.shape[1] - 1)
        wall_grid[wr, wc] = True
    near_wall = np.zeros(H.shape, bool)
    for dr in (-2, -1, 0, 1, 2):
        for dc in (-2, -1, 0, 1, 2):
            near_wall |= np.roll(wall_grid, (dr, dc), (0, 1))

    nofloor = np.isnan(H)
    border = np.zeros(H.shape, bool); border[:3, :] = border[-3:, :] = border[:, :3] = border[:, -3:] = True
    # open drops: (row, col, dr, dc) for each reachable cell edge that faces a floor-less cell
    drops = []
    for dr, dc in ((1, 0), (-1, 0), (0, 1), (0, -1)):
        rr = np.arange(H.shape[0])[:, None] + dr; cc = np.arange(H.shape[1])[None, :] + dc
        valid = (rr >= 0) & (rr < H.shape[0]) & (cc >= 0) & (cc < H.shape[1])
        nb = np.ones(H.shape, bool)
        nb[valid] = nofloor[np.clip(rr, 0, H.shape[0] - 1), np.clip(cc, 0, H.shape[1] - 1)][valid]
        mask = reach & nb & ~near_wall & ~border
        for r, c in zip(*np.nonzero(mask)):
            drops.append((int(r), int(c), dr, dc))
    return {'H': H, 'reach': reach, 'wall_grid': wall_grid, 'drops': drops, 'lo': lo, 'cell': cell}


def barrier_quads(result):
    """Vertical two-sided collision quads on each open-drop cell edge."""
    H, lo = result['H'], result['lo']
    quads = []
    for r, c, dr, dc in result['drops']:
        x = lo[0] + c * STEP; z = lo[2] + r * STEP; y = H[r, c]
        h = STEP / 2
        if dc:   # edge perpendicular to x
            ex = x + dc * h
            a, b = (ex, z - h), (ex, z + h)
        else:
            ez = z + dr * h
            a, b = (x - h, ez), (x + h, ez)
        quads.append([(a[0], y - 60, a[1]), (b[0], y - 60, b[1]), (b[0], y + 400, b[1]), (a[0], y + 400, a[1])])
    return quads
