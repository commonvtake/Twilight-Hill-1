"""Old Silent Hill 0.8.0: town blocks + building interiors + doors, one stage (D_SB01).

Builds on build_town.py (0.7.0 town chunks and street portals) and adds:
  * Interiors: every THR tile with SH grid y >= 5 that a door leads to. Touching tiles form one
    building ("cluster"); each building is one room.
  * Doors: SysState_LoadRoom events from the SH decomp (src/maps/map2_s00, see sh_doors.py).
    Each door is a native Twilight Princess knob door (kdoor) on the wall the SH door point faces,
    with the 0.3.1 supported crossing behind it and a scnChg fallback trigger. Arrival = the SH
    destination point, turned away from the nearest wall.
  * ONE global exit table (SCLS) shared by the stage and every room. 0.7.0 used per-room tables,
    but while Link is between rooms (door demo, mid-air) the engine reads the stage table with the
    room's exit index; a 1-entry stage table then read past its end -> the 0.7.0 crash
    ("Destination buffer too small! Need 17, have 8").
      exit 0           = cafe (template record)
      exit 1..62       = doors (kdoor exit field is 6 bits)
      exit 63..255     = street portals (scnChg arg0 is 8 bits)
Outputs town/chunks/<room>/{model.bmd,room.dzb,room.dzr,collision_source.npz,report.json},
town/exits.json, town/town_report.json.
"""
from pathlib import Path
import os, sys, struct, json, math
import numpy as np

TOOLS = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS))
import build_town as bt
import build_district as bd
import place_enemies
from district_coverage import analyse, barrier_quads, STEP
from sh_doors import load_points, load_doors

ROOT = bt.ROOT; P = bt.P
OUT = P / 'town/chunks'
SH_MAP = Path(os.environ.get('SH_DECOMP', str(ROOT / 'silent-hill-decomp'))) / 'src/maps/map2_s00'
DOOR_SUPPORT = True
MAX_DOOR_EXITS = 62


# ------------------------------------------------------------------ geometry helpers
def tile_xy():
    tiles = {}
    for f in sorted((ROOT / 'sh_work/assets/BG').glob('THR*.IPD')):
        d = f.read_bytes(); tiles[f.stem] = struct.unpack_from('bb', d, 2)
    return tiles


def obj_bounds(name):
    v = np.array([[float(a) for a in l.split()[1:4]] for l in (bt.TILES / (name + '.OBJ')).read_text().splitlines() if l.startswith('v ')])
    return v.min(0), v.max(0)


def collision_with_walls(vs, groups, bounds_cm):
    tris = np.array([[a for a, _ in tri] for g in groups.values() for tri in g])
    keep = vs[tris][:, :, 1].min(1) < 450.0
    V = list(map(tuple, vs)); F = [list(t) for t in tris[keep]]
    x0, x1, z0, z1 = bounds_cm
    corners = [(x0, z0), (x1, z0), (x1, z1), (x0, z1)]
    for i in range(4):
        a, b = corners[i], corners[(i + 1) % 4]; s = len(V)
        V.extend([(a[0], -1500, a[1]), (b[0], -1500, b[1]), (b[0], 1500, b[1]), (a[0], 1500, a[1])])
        F.extend([[s + j for j in f] for f in [(0, 1, 2), (0, 2, 3), (2, 1, 0), (3, 2, 0)]])
    return np.array(V, float), np.array(F)


def floor_near(cov, x, z, radius_cells=4):
    H, lo = cov['H'], cov['lo']
    r0 = int(round((z - lo[2]) / STEP)); c0 = int(round((x - lo[0]) / STEP))
    best = None
    for rad in range(radius_cells + 1):
        for dr in range(-rad, rad + 1):
            for dc in range(-rad, rad + 1):
                r, c = r0 + dr, c0 + dc
                if 0 <= r < H.shape[0] and 0 <= c < H.shape[1] and not np.isnan(H[r, c]):
                    d = dr * dr + dc * dc
                    if best is None or d < best[0]:
                        best = (d, H[r, c], lo[0] + c * STEP, lo[2] + r * STEP)
        if best is not None:
            return best[1], best[2], best[3]
    return None


def wall_hits(V, F, origin, max_cm=350.0, n_dirs=64):
    """Nearest vertical-wall hit per horizontal direction from origin (Moller-Trumbore)."""
    T = V[F]
    n = np.cross(T[:, 1] - T[:, 0], T[:, 2] - T[:, 0])
    nn = np.linalg.norm(n, axis=1); ok = nn > 1e-6
    vertical = ok & (np.abs(n[:, 1] / np.where(ok, nn, 1)) < 0.35)
    near = np.all(T.min(1) - max_cm <= origin, axis=1) & np.all(T.max(1) + max_cm >= origin, axis=1)
    T = T[vertical & near]
    out = []
    for k in range(n_dirs):
        a = 2 * math.pi * k / n_dirs; d = np.array([math.sin(a), 0.0, math.cos(a)])
        if not len(T):
            out.append((a, None)); continue
        e1 = T[:, 1] - T[:, 0]; e2 = T[:, 2] - T[:, 0]
        p = np.cross(d, e2); det = np.einsum('ij,ij->i', e1, p)
        good = np.abs(det) > 1e-9; inv = np.where(good, 1.0 / np.where(good, det, 1), 0)
        s = origin - T[:, 0]; u = np.einsum('ij,ij->i', s, p) * inv
        q = np.cross(s, e1); v = np.einsum('j,ij->i', d, q) * inv
        t = np.einsum('ij,ij->i', e2, q) * inv
        hit = good & (u >= 0) & (v >= 0) & (u + v <= 1) & (t > 1) & (t < max_cm)
        out.append((a, float(t[hit].min()) if hit.any() else None))
    return out


def door_on_wall(V, F, x, y, z, max_cm=350.0):
    hits = [(t, a) for a, t in wall_hits(V, F, np.array([x, y + 100.0, z]), max_cm) if t is not None]
    if not hits:
        return None
    t, a = min(hits)
    d = np.array([math.sin(a), math.cos(a)])
    wx, wz = x + d[0] * (t - 3.0), z + d[1] * (t - 3.0)
    # kdoor local +Z points back to the player's side of the wall.
    return {'pos': [float(wx), float(y), float(wz)], 'yaw': bt.yaw_towards(-d[0], -d[1]), 'dist_cm': t,
            'into_dir': d.tolist()}


def door_support_quads(door):
    """Supported crossing behind a knob door (door_threshold.supported_collision, 0.3.1)."""
    a = door['yaw'] * math.pi / 32768; s, c = math.sin(a), math.cos(a)
    ox, oy, oz = door['pos']

    def w(px, py, pz):
        return (ox + c * px + s * pz, oy + py, oz - s * px + c * pz)
    quads = [([w(-120, -10, 50), w(120, -10, 50), w(120, -10, -650), w(-120, -10, -650)], False),
             ([w(-120, -20, -650), w(120, -20, -650), w(120, 350, -650), w(-120, 350, -650)], True)]
    for x in (-120, 120):
        quads.append(([w(x, -20, 0), w(x, -20, -650), w(x, 350, -650), w(x, 350, 0)], True))
    return quads


def door_trigger(door, exit_index):
    a = door['yaw'] * math.pi / 32768; s, c = math.sin(a), math.cos(a)
    ox, oy, oz = door['pos']; lz = -305.0
    px, pz = ox + s * lz, oz + c * lz
    return struct.pack('>8sI3f3hH4B', b'scnChg', 0xffff0100 | exit_index, px, oy - 300.0, pz,
                       -1, bt.s16(door['yaw']), -1, 0xFFFF, 15, 80, 40, 255)


def kdoor_actor(door, exit_index):
    assert exit_index <= MAX_DOOR_EXITS
    return struct.pack('>8sI3f3hH', b'kdoor', exit_index << 25, *door['pos'], -1, bt.s16(door['yaw']), 0, 0xFFFF)


# ------------------------------------------------------------------ main
def main():
    tiles = tile_xy()
    # Town chunks (0.7.0 layout) ------------------------------------------------------------
    chunks = {}
    for name, (x, y) in tiles.items():
        if -6 <= y <= 4:
            chunks.setdefault(bt.chunk_of(x, y), []).append(name)
    keys = sorted(chunks, key=lambda c: (c != (0, 0), c[1], c[0]))
    rooms = {}
    for c in keys:
        origin = bt.origin_m(c)
        rooms[('town', c)] = {'kind': 'town', 'chunk': c, 'tiles': sorted(chunks[c]), 'origin': origin,
                              'bounds': (-bt.HALF + bt.INSET, bt.HALF - bt.INSET, -bt.HALF + bt.INSET, bt.HALF - bt.INSET),
                              'grid': (-bt.HALF, bt.HALF, -bt.HALF, bt.HALF)}

    # Doors and interiors -------------------------------------------------------------------
    pts = load_points(SH_MAP); events = load_doors(SH_MAP)
    tile_at = {v: k for k, v in tiles.items()}

    def tile_of_point(p):
        return tile_at.get((math.floor(p['positionX'] / 40), math.floor(p['positionZ'] / 40)))
    interior_tiles = set()
    for e in events:
        for idx in (e['src'], e['dst']):
            t = tile_of_point(pts[idx])
            if t and tiles[t][1] >= 5:
                interior_tiles.add(t)
    # cluster touching interior tiles
    bounds = {t: obj_bounds(t) for t in interior_tiles}
    clusters = []
    for t in sorted(interior_tiles):
        merged = [cl for cl in clusters if any(
            bounds[t][0][0] - 1 <= bounds[o][1][0] and bounds[o][0][0] - 1 <= bounds[t][1][0] and
            bounds[t][0][2] - 1 <= bounds[o][1][2] and bounds[o][0][2] - 1 <= bounds[t][1][2] for o in cl)]
        new = {t}.union(*merged) if merged else {t}
        clusters = [cl for cl in clusters if cl not in merged] + [new]
    for cl in sorted(clusters, key=lambda s: sorted(s)[0]):
        lo = np.min([bounds[t][0] for t in cl], 0); hi = np.max([bounds[t][1] for t in cl], 0)
        origin = np.array([(lo[0] + hi[0]) / 2, 0.0, (lo[2] + hi[2]) / 2])
        hx = (hi[0] - lo[0]) * 50 + 150; hz = (hi[2] - lo[2]) * 50 + 150
        key = ('interior', tuple(sorted(cl)))
        rooms[key] = {'kind': 'interior', 'tiles': sorted(cl), 'origin': origin,
                      'bounds': (-hx, hx, -hz, hz), 'grid': (-hx - 100, hx + 100, -hz - 100, hz + 100)}
    order = [('town', c) for c in keys] + sorted([k for k in rooms if k[0] == 'interior'], key=lambda k: k[1])
    room_no = {k: i for i, k in enumerate(order)}
    assert len(order) <= 50

    def room_of_tile(t):
        x, y = tiles[t]
        if -6 <= y <= 4:
            return ('town', bt.chunk_of(x, y))
        for k in rooms:
            if k[0] == 'interior' and t in k[1]:
                return k
        return None

    # Geometry + floor grids ----------------------------------------------------------------
    geo, cov = {}, {}
    for k in order:
        R = rooms[k]
        vs, uv, groups, paths = bt.load_chunk(R['tiles'], R['origin'])
        V, F = collision_with_walls(vs, groups, R['bounds'])
        g = R['grid']
        lattice = [(x, z) for x in np.arange(g[0] + 100, g[1] - 99, 200.0) for z in np.arange(g[2] + 100, g[3] - 99, 200.0)]
        cv = analyse(V, F, lattice, bounds=g)
        cv['reach_any'] = ~np.isnan(cv['H'])
        geo[k] = (vs, uv, groups, paths, V, F); cov[k] = cv
        print('geometry', room_no[k], k[0], R['tiles'][:3], len(F), 'faces', flush=True)

    # Global exit table ---------------------------------------------------------------------
    template = bt.chunk_blobs((P / 'district/template_room.dzr').read_bytes())
    exits = [template[b'SCLS'][1][:13]]          # exit 0: cafe
    room_data = {k: {'plyr': [], 'actr': [], 'tgsc': [], 'arrivals': [], 'triggers': [], 'doors': [],
                     'quads': []} for k in order}
    next_spawn = {k: 2 for k in order}
    links = []

    def add_arrival(k, x, y, z, yaw):
        sid = next_spawn[k]; next_spawn[k] += 1
        room_data[k]['plyr'].append(bt.plyr(x, y, z, yaw, sid))
        room_data[k]['arrivals'].append((x, z))
        return sid

    # doors first (exit indices must fit in 6 bits)
    seen = []
    door_report = []
    for e in events:
        sp, dp = pts[e['src']], pts[e['dst']]
        ts, td = tile_of_point(sp), tile_of_point(dp)
        if not ts or not td:
            continue
        ks, kd = room_of_tile(ts), room_of_tile(td)
        if ks is None or kd is None:
            continue
        sx, sz = -sp['positionX'], sp['positionZ']; dx, dz = -dp['positionX'], dp['positionZ']
        if any(s[0] == ks and s[1] == kd and math.hypot(s[2] - sx, s[3] - sz) < 3.0 for s in seen):
            continue
        seen.append((ks, kd, sx, sz))
        ls = (np.array([sx, 0, sz]) - rooms[ks]['origin']) * 100
        ld = (np.array([dx, 0, dz]) - rooms[kd]['origin']) * 100
        fs = floor_near(cov[ks], ls[0], ls[2]); fd = floor_near(cov[kd], ld[0], ld[2])
        if fs is None or fd is None:
            print('skip door (no floor)', e['event'], ts, td); continue
        door = door_on_wall(geo[ks][4], geo[ks][5], fs[1], fs[0], fs[2])
        if door is None:
            print('skip door (no wall)', e['event'], ts); continue
        # arrival: SH destination point, pushed >= 1.5 m from the wall it faces, turned away from it
        Vd, Fd = geo[kd][4], geo[kd][5]
        wall = door_on_wall(Vd, Fd, fd[1], fd[0], fd[2])
        ax, az, ayaw = fd[1], fd[2], 0
        if wall:
            # step away from the door (up to 1.5 m) while the floor stays level and nothing blocks
            back = -np.array(wall['into_dir'])
            clear = [t for a_, t in wall_hits(Vd, Fd, np.array([fd[1], fd[0] + 100.0, fd[2]]), 400.0, 64)
                     if abs(math.atan2(math.sin(a_), math.cos(a_)) - math.atan2(back[0], back[1])) < 0.1 and t is not None]
            limit = min(clear) - 60.0 if clear else 400.0
            for push in range(150, 50, -10):
                if push > limit:
                    continue
                cand = floor_near(cov[kd], ax + back[0] * push, az + back[1] * push, 0)
                if cand is not None and abs(cand[0] - fd[0]) < 30:
                    ax, az = ax + back[0] * push, az + back[1] * push
                    break
            ayaw = bt.yaw_towards(back[0], back[1])
        ay = floor_near(cov[kd], ax, az)[0]
        exit_index = len(exits)
        assert exit_index <= MAX_DOOR_EXITS, 'too many doors for the 6-bit kdoor exit field'
        sid = add_arrival(kd, ax, ay + 5.0, az, ayaw)
        exits.append(struct.pack('>8s5B', bt.STAGE.encode(), sid, room_no[kd], 0xf0, 0x10, 0))
        room_data[ks]['actr'].append(kdoor_actor(door, exit_index))
        room_data[ks]['tgsc'].append(door_trigger(door, exit_index))
        room_data[ks]['quads'] += door_support_quads(door)
        room_data[ks]['doors'].append({'exit': exit_index, 'pos': door['pos'], 'yaw': door['yaw'],
                                       'to_room': room_no[kd], 'spawn': sid, 'wall_dist_cm': door['dist_cm']})
        links.append((room_no[ks], room_no[kd], 'door'))
        door_report.append({'sh_event': e['event'], 'from_tile': ts, 'to_tile': td, 'from_room': room_no[ks],
                            'to_room': room_no[kd], 'exit': exit_index, 'sh_flag': e['required_flag']})
    # An arrival that lands on the return door (whose support floor sits 10 cm below the street)
    # is moved in front of that door, on the side Link opens it from, and turned to face away.
    moved = 0
    for k, D in room_data.items():
        for i, rec in enumerate(D['plyr']):
            x, y, z = struct.unpack_from('>3f', rec, 12)
            sid = rec[0x1d]
            for d in D['doors']:
                if math.hypot(d['pos'][0] - x, d['pos'][2] - z) > 200.0:
                    continue
                yaw = d['yaw'] * math.pi / 32768
                fx, fz = math.sin(yaw), math.cos(yaw)
                for dist in range(160, 80, -10):
                    nx, nz = d['pos'][0] + fx * dist, d['pos'][2] + fz * dist
                    cand = floor_near(cov[k], nx, nz, 0)
                    if cand is not None and abs(cand[0] - (y - 5.0)) < 30:
                        D['plyr'][i] = bt.plyr(nx, cand[0] + 5.0, nz, bt.yaw_towards(fx, fz), sid)
                        D['arrivals'][i] = (nx, nz)
                        moved += 1
                        break
                break
    print('doors', len(door_report), 'arrivals moved off doors', moved, flush=True)

    # street portals (as 0.7.0, but global exit indices)
    tcov = {k[1]: cov[k] for k in order if k[0] == 'town'}
    portals = []
    for c in keys:
        for dd in ((1, 0), (0, 1)):
            n = (c[0] + dd[0], c[1] + dd[1])
            if n in chunks:
                portals.extend(bt.find_portals(c, n, tcov))
    plinks = []
    for p in portals:
        plinks.append(p); plinks.append(dict(p, a=p['b'], b=p['a'], da=p['db'], db=p['da']))
    for L in plinks:
        a, b = ('town', L['a']), ('town', L['b'])
        oa, ob = bt.origin_m(L['a']), bt.origin_m(L['b'])
        mid = (L['from'] + L['to']) / 2.0
        pb = np.zeros(3); pb[L['axis']] = L['edge'] + L['db'] * 6.0; pb[L['other']] = mid
        lb = (pb - ob) * 100; fb = bt.floor_lookup(cov[b]); hb = fb(lb[0], lb[2]); step = 0.0
        while np.isnan(hb) and step < 6.0:
            step += 0.5; pb[L['axis']] = L['edge'] + L['db'] * (6.0 + step); lb = (pb - ob) * 100; hb = fb(lb[0], lb[2])
        if np.isnan(hb):
            continue
        inward = np.zeros(3); inward[L['axis']] = L['db']
        sid = add_arrival(b, lb[0], hb + 5.0, lb[2], bt.yaw_towards(inward[0], inward[2]))
        pa = np.zeros(3); pa[L['axis']] = L['edge'] + L['da'] * 1.5; pa[L['other']] = mid
        la = (pa - oa) * 100; ha = bt.floor_lookup(cov[a])(la[0], la[2])
        if np.isnan(ha):
            ha = hb
        exit_index = len(exits)
        assert exit_index <= 255
        exits.append(struct.pack('>8s5B', bt.STAGE.encode(), sid, room_no[b], 0xf0, 0x10, 0))
        half_width = (L['to'] - L['from']) * 100 / 2.0 + 50.0
        yaw_a = 0x4000 if L['axis'] == 0 else 0
        room_data[a]['tgsc'].append(bt.scnchg(exit_index, la[0], ha - 300.0, la[2], yaw_a, half_width))
        room_data[a]['triggers'].append({'center': [la[0], ha, la[2]], 'half_width_cm': half_width,
                                         'to_room': room_no[b], 'spawn': sid, 'exit': exit_index})
        links.append((room_no[a], room_no[b], 'street'))
    print('exits', len(exits), flush=True)

    # Reachability over rooms (from room 0) -------------------------------------------------
    graph = {}
    for u, v, _ in links:
        graph.setdefault(u, set()).add(v)
    seen_r = {0}; stack = [0]
    while stack:
        u = stack.pop()
        for v in graph.get(u, ()):
            if v not in seen_r:
                seen_r.add(v); stack.append(v)

    # Per-room output ----------------------------------------------------------------------
    OUT.mkdir(parents=True, exist_ok=True)
    report = {'stage': bt.STAGE, 'version': '0.8.0', 'rooms': [], 'doors': door_report,
              'exit_count': len(exits), 'links': len(links)}
    for k in order:
        r = room_no[k]; R = rooms[k]; D = room_data[k]
        vs, uv, groups, paths, V, F = geo[k]
        seeds = list(D['arrivals'])
        if k == ('town', (0, 0)):
            seeds = [(s[0], s[2]) for s in bt.CENTRAL_SPAWNS] + seeds
        if r not in seen_r or not seeds:
            report['rooms'].append({'room': r, 'kind': R['kind'], 'tiles': R['tiles'], 'skipped': 'not reachable'})
            continue
        VL = list(map(tuple, V)); FL = [list(f) for f in F]
        for quad, two in D['quads']:
            s = len(VL); VL.extend(quad)
            FL.extend([[s + j for j in f] for f in ([(0, 1, 2), (0, 2, 3)] + ([(2, 1, 0), (3, 2, 0)] if two else []))])
        V1, F1 = np.array(VL, float), np.array(FL)
        cv = analyse(V1, F1, seeds, bounds=R['grid'])
        for q in barrier_quads(cv):
            s = len(VL); VL.extend(q)
            FL.extend([[s + j for j in f] for f in [(0, 1, 2), (0, 2, 3), (2, 1, 0), (3, 2, 0)]])
        V2, F2 = np.array(VL, float), np.array(FL)
        cv2 = analyse(V2, F2, seeds, bounds=R['grid'])
        dest = OUT / f'{r:02d}'; dest.mkdir(parents=True, exist_ok=True)
        np.savez(dest / 'collision_source.npz', vertices=V2, faces=F2)
        dzb, nodes = bt.encode_dzb(V2, F2, r)
        model, mrep = bd.build_model(vs, uv, groups, paths)
        model = bt.fog_model(model)
        area = float(cv2['reach'].sum() * STEP * STEP / 1e4)
        actors = list(D['actr'])
        n_sh = n_ge = 0
        if R['kind'] == 'town':
            n_sh = int(round(area / 1250.0)); n_ge = int(round(area / 2000.0))
            away = list(seeds) + [(t['center'][0], t['center'][2]) for t in D['triggers']] + \
                   [(d['pos'][0], d['pos'][2]) for d in D['doors']]
            spots = place_enemies.choose_positions(cv2, away, n_sh + n_ge, seed=7 + r) if n_sh + n_ge else []
            n_sh = min(n_sh, len(spots)); n_ge = len(spots) - n_sh
            for i, (x, z, y) in enumerate(spots):
                actors.append(place_enemies.actor_record('groaner' if i < n_sh else 'air_screamer', x, y, z,
                                                         bt.yaw_towards(-x, -z)))
        if k == ('town', (0, 0)):
            sp = [bt.plyr(x, y, z, yaw, i) for i, (x, y, z, yaw) in enumerate(bt.CENTRAL_SPAWNS)]
            actors = [template[b'ACTR'][1][:0x20]] + actors          # cafe kdoor, exit 0
            trig = [template[b'TGSC'][1][:0x24]] + D['tgsc']           # cafe fallback trigger, exit 0
        else:
            first = D['plyr'][0]
            sp = [first[:0x1c] + struct.pack('>h', bt.s16(0xFF00 | i)) + first[0x1e:] for i in (0, 1)]
            trig = D['tgsc']
        plyr_all = sp + D['plyr']
        dz = [(b'FILI', template[b'FILI'][0], template[b'FILI'][1]),
              (b'LBNK', template[b'LBNK'][0], template[b'LBNK'][1]),
              (b'PLYR', len(plyr_all), b''.join(plyr_all)),
              (b'ACTR', len(actors), b''.join(actors)),
              (b'SCLS', len(exits), b''.join(exits))]
        if trig:
            dz.append((b'TGSC', len(trig), b''.join(trig)))
        dzr = bt.write_dz(dz)
        (dest / 'model.bmd').write_bytes(model); (dest / 'room.dzb').write_bytes(dzb); (dest / 'room.dzr').write_bytes(dzr)
        rep = {'room': r, 'kind': R['kind'], 'chunk': list(R.get('chunk', ())), 'tiles': R['tiles'],
               'origin_m': [float(v) for v in R['origin']], 'grid_cm': list(R['grid']),
               'triangles': sum(map(len, groups.values())), 'collision_faces': len(F2), 'tree_nodes': nodes,
               'model_bytes': len(model), 'collision_bytes': len(dzb), 'dzr_bytes': len(dzr),
               'reachable_m2': area, 'stalhounds': n_sh, 'guays': n_ge, 'spawns': len(plyr_all),
               'doors': D['doors'], 'triggers': D['triggers'], 'open_drop_edges_after': len(cv2['drops'])}
        (dest / 'report.json').write_text(json.dumps(rep, indent=1) + '\n')
        report['rooms'].append(rep)
        print(f"room {r:2d} {R['kind']:8s} {len(R['tiles'])} tiles {rep['triangles']} tris "
              f"{(len(model) + len(dzb) + len(dzr)) // 1024} KB {area:.0f} m2 enemies {n_sh}+{n_ge} "
              f"doors {len(D['doors'])} portals {len(D['triggers'])} drops {rep['open_drop_edges_after']}", flush=True)
    (P / 'town/exits.json').write_text(json.dumps([{'index': i, 'stage': e[:8].rstrip(b'\0').decode(),
                                                     'spawn': e[8], 'room': e[9]} for i, e in enumerate(exits)], indent=1))
    (P / 'town/town_report.json').write_text(json.dumps(report, indent=1) + '\n')


if __name__ == '__main__':
    main()
