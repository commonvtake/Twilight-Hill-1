"""Old Silent Hill as one Twilight Princess stage (0.7.0+).

Layout
  * Every outdoor THR tile (SH grid y -6..4) is assigned to a 3 x 3 tile block ("chunk"):
        cx = (x + 1) // 3, cy = y // 3      (the 0.6 central district is chunk (0, 0))
  * Each chunk is one room of stage D_SB01 (Cave of Ordeals: 50 room slots, minimal stage-name
    special cases). Only the current room is loaded, so memory per room matches 0.6 (~2.4 MB).
  * Chunk origin (metres, SH exporter space) = [-120 cx - 20, 0, 120 cy + 60]; the central chunk
    keeps the 0.6 origin, so its spawns and the cafe door coordinates are unchanged.
  * Where floor continues across a chunk edge (|dh| < 40 cm, >= 1.5 m wide) a "portal" is made:
    a native scnChg trigger (TGSC, arg1 = 1 walk-out area change, arg0 = exit index) 0..3 m inside
    the edge, an SCLS exit to the neighbour room, and a PLYR arrival 6 m inside the neighbour.
  * Collision: reachable-geometry triangles + perimeter walls + automatic drop barriers seeded from
    every arrival point (district_coverage.py). Enemies scale with reachable area.
Outputs: town/chunks/<room>/{model.bmd,room.dzb,room.dzr,report.json}, town/stage.dzs,
town/town_report.json. Packaging: tools/package_town_stage.py.
"""
from pathlib import Path
from io import BytesIO
import sys, struct, json, math, shutil
import numpy as np

ROOT = Path(__file__).resolve().parents[2]; P = ROOT / 'sh_tp_project'
TOOLS = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / 'gclib')); sys.path.insert(0, str(ROOT / 'dzb_tools/dzb_tools')); sys.path.insert(0, str(TOOLS))
import build_district as bd          # compact BMD + DZB encoders proven in 0.6
from district_coverage import analyse, barrier_quads, STEP
import place_enemies
from door_threshold import supported_collision
from gclib.j3d import BMD
from gclib.gx_enums import FogType

TILES = ROOT / 'tp_work/tiles'          # every THR tile exported by the pinned sh_ipd2obj
OUT = P / 'town/chunks'
STAGE = 'D_SB01'
HALF = 6000.0                           # chunk half size, cm
INSET = 30.0
CENTRAL_SPAWNS = [(500.0, 5.0, 0.0, 0), (160.0, 19.84375, -350.0, 16384)]   # 0.6 spawns 0/1
CAFE_DOOR = {'door': [-60., 14.84375, -350.], 'facing': 16384}


def tile_grid():
    tiles = {}
    for f in sorted((ROOT / 'sh_work/assets/BG').glob('THR*.IPD')):
        d = f.read_bytes(); x, y = struct.unpack_from('bb', d, 2)
        if -6 <= y <= 4:
            tiles[f.stem] = (x, y)
    return tiles


def chunk_of(x, y):
    return ((x + 1) // 3, y // 3)


def origin_m(c):
    return np.array([-120.0 * c[0] - 20.0, 0.0, 120.0 * c[1] + 60.0])


# ------------------------------------------------------------------ geometry
def load_chunk(names, origin):
    vs, uv, groups, paths = [], [], {}, {}
    for name in names:
        mat = None; tile_mtl = {}
        for line in (TILES / (name + '.MTL')).read_text().splitlines():
            s = line.split()
            if s and s[0] == 'newmtl': mat = s[1]
            elif s and s[0] == 'map_Kd': tile_mtl[mat] = TILES / s[1]; paths[mat] = TILES / s[1]
        v0, t0 = len(vs), len(uv)
        mat = None
        for line in (TILES / (name + '.OBJ')).read_text().splitlines():
            s = line.split()
            if not s: continue
            if s[0] == 'v': vs.append([float(a) for a in s[1:4]])
            elif s[0] == 'vt': uv.append([float(s[1]), 1 - float(s[2])])
            elif s[0] == 'usemtl': mat = s[1]
            elif s[0] == 'f':
                idx = [tuple(int(a) - 1 if a else -1 for a in it.split('/')[:2]) for it in s[1:]]
                idx = [(a + v0, b + t0 if b >= 0 else -1) for a, b in idx]
                for i in range(1, len(idx) - 1):
                    tri = [idx[0], idx[i], idx[i + 1]]
                    groups.setdefault(mat if all(t[1] >= 0 for t in tri) else '_untextured', []).append(tri)
    vs = (np.asarray(vs) - origin) * 100.0
    uv.append([0.0, 0.0]); blank = len(uv) - 1
    out = {}
    for m, tris in groups.items():
        for tri in tris:
            p = vs[[a for a, _ in tri]]
            if np.linalg.norm(np.cross(p[1] - p[0], p[2] - p[0])) < 1e-6: continue
            out.setdefault(m, []).append([(a, b if b >= 0 else blank) for a, b in tri])
    return vs, np.asarray(uv), out, paths


def fog_model(raw):
    settings = json.loads((P / 'fog/settings.json').read_text())
    model = BMD(BytesIO(raw))
    for m in model.mat3.materials:
        f = m.fog_info; f.fog_type = FogType.LINEAR; f.start_z = settings['start_cm']; f.end_z = settings['end_cm']
        f.color.r, f.color.g, f.color.b = settings['color_rgb']; f.color.a = 255
    model.mat3.save(); chunks = []; off = 32
    for _ in range(struct.unpack_from('>I', raw, 12)[0]):
        size = struct.unpack_from('>I', raw, off + 4)[0]; c = raw[off:off + size]
        chunks.append(model.mat3.data.getvalue() if c[:4] == b'MAT3' else c); off += size
    header = bytearray(raw[:32]); struct.pack_into('>I', header, 8, 32 + sum(map(len, chunks)))
    return bytes(header) + b''.join(chunks)


def base_collision(vs, groups):
    tris = np.array([[a for a, _ in tri] for g in groups.values() for tri in g])
    keep = vs[tris][:, :, 1].min(1) < 450.0
    V = list(map(tuple, vs)); F = [list(t) for t in tris[keep]]
    x0, x1, z0, z1 = -HALF + INSET, HALF - INSET, -HALF + INSET, HALF - INSET
    corners = [(x0, z0), (x1, z0), (x1, z1), (x0, z1)]
    for i in range(4):
        a, b = corners[i], corners[(i + 1) % 4]; s = len(V)
        V.extend([(a[0], -1500, a[1]), (b[0], -1500, b[1]), (b[0], 1500, b[1]), (a[0], 1500, a[1])])
        F.extend([[s + j for j in f] for f in [(0, 1, 2), (0, 2, 3), (2, 1, 0), (3, 2, 0)]])
    return np.array(V, float), np.array(F), int(keep.sum())


def encode_dzb(V, F, room):
    d = bd.BoundedDZB(); g = d.add_group('town'); g.room_index = room; prop = d.add_property()
    for face in F:
        d.add_face([tuple(map(float, p)) for p in V[face]], prop, g)
    d.save_changes(); raw = bytearray(d.data.getvalue())
    prop_off = struct.unpack_from('>I', raw, 0x2c)[0]; group_off = struct.unpack_from('>I', raw, 0x24)[0]
    struct.pack_into('>4I', raw, prop_off, 0x3fff, 0xff, 0xffffff00, 0)
    struct.pack_into('>I', raw, group_off + 0x30, 0)
    return bytes(raw), len(d.octree_nodes)


# ------------------------------------------------------------------ portals
def floor_lookup(cov):
    H, lo = cov['H'], cov['lo']
    def at(x, z):
        r = int(round((z - lo[2]) / STEP)); c = int(round((x - lo[0]) / STEP))
        if 0 <= r < H.shape[0] and 0 <= c < H.shape[1]:
            return H[r, c]
        return np.nan
    return at


def find_portals(ca, cb, cov):
    """Edge between chunk ca and cb (grid neighbours). Returns runs in world metres."""
    oa, ob = origin_m(ca), origin_m(cb)
    axis = 0 if ca[0] != cb[0] else 2           # world axis crossing the edge
    other = 2 if axis == 0 else 0
    edge = (oa[axis] + ob[axis]) / 2.0          # world metres
    da = np.sign(oa[axis] - edge); db = np.sign(ob[axis] - edge)
    fa, fb = floor_lookup(cov[ca]), floor_lookup(cov[cb])
    lo = max(oa[other], ob[other]) - 60.0; hi = min(oa[other], ob[other]) + 60.0
    samples = np.arange(lo + 0.5, hi - 0.5, STEP / 100.0)
    ok = []
    for s in samples:
        pa = np.zeros(3); pa[axis] = edge + da * 1.0; pa[other] = s
        pb = np.zeros(3); pb[axis] = edge + db * 1.0; pb[other] = s
        la = (pa - oa) * 100; lb = (pb - ob) * 100
        ha, hb = fa(la[0], la[2]), fb(lb[0], lb[2])
        ok.append(not np.isnan(ha) and not np.isnan(hb) and abs(ha - hb) < 40 and
                  cov[ca]['reach_any'][int(round((la[2] - cov[ca]['lo'][2]) / STEP)), int(round((la[0] - cov[ca]['lo'][0]) / STEP))])
    runs = []; start = None
    for i, v in enumerate(ok + [False]):
        if v and start is None: start = i
        if not v and start is not None:
            a, b = samples[start], samples[i - 1]
            if b - a >= 1.5:
                # split long runs so each trigger stays within the 38 m TGSC width limit
                n = int(math.ceil((b - a) / 30.0))
                for k in range(n):
                    runs.append((a + (b - a) * k / n, a + (b - a) * (k + 1) / n))
            start = None
    return [{'a': ca, 'b': cb, 'axis': axis, 'other': other, 'edge': edge, 'da': da, 'db': db,
             'from': r[0], 'to': r[1]} for r in runs]


def yaw_towards(dx, dz):
    return int(round(math.atan2(dx, dz) / (2 * math.pi) * 65536)) & 0xFFFF


def s16(v):
    v &= 0xFFFF
    return v - 0x10000 if v >= 0x8000 else v


# ------------------------------------------------------------------ room / stage data
def chunk_blobs(dzr):
    n = struct.unpack_from('>I', dzr, 0)[0]
    rows = [struct.unpack_from('>4sII', dzr, 4 + i * 12) for i in range(n)]
    order = sorted(rows, key=lambda r: r[2]); out = {}
    for k, (tag, cnt, off) in enumerate(order):
        end = order[k + 1][2] if k + 1 < len(order) else len(dzr)
        out[tag] = (cnt, bytes(dzr[off:end]))
    return out


def write_dz(chunks):
    """chunks: list of (tag, count, blob). Writes a DZR/DZS with a fresh chunk table."""
    out = bytearray(4 + 12 * len(chunks)); offs = []
    for tag, cnt, blob in chunks:
        while len(out) % 4: out.append(0)
        offs.append(len(out)); out.extend(blob)
    struct.pack_into('>I', out, 0, len(chunks))
    for i, ((tag, cnt, _), off) in enumerate(zip(chunks, offs)):
        struct.pack_into('>4sII', out, 4 + i * 12, tag, cnt, off)
    while len(out) % 32: out.append(0)
    return bytes(out)


def plyr(x, y, z, yaw, spawn_id):
    return struct.pack('>8sI3f3hH', b'Link', 0xff000000, x, y, z, 0, s16(yaw), s16(0xFF00 | spawn_id), 0xFFFF)


def scls(room, spawn_id):
    return struct.pack('>8s5B', STAGE.encode(), spawn_id, room, 0xf0, 0x10, 0)


def scnchg(exit_index, x, y, z, yaw, half_width_cm):
    sx = min(255, int(math.ceil(half_width_cm * 10 / 75.0)))
    return struct.pack('>8sI3f3hH4B', b'scnChg', 0xffff0100 | exit_index, x, y, z, -1, s16(yaw), -1, 0xFFFF, sx, 80, 20, 255)


def main():
    tiles = tile_grid()
    chunks = {}
    for name, (x, y) in tiles.items():
        chunks.setdefault(chunk_of(x, y), []).append(name)
    keys = sorted(chunks, key=lambda c: (c != (0, 0), c[1], c[0]))
    room_of = {c: i for i, c in enumerate(keys)}
    assert room_of[(0, 0)] == 0 and len(keys) <= 50
    print('chunks', len(keys), {str(k): len(v) for k, v in chunks.items()})

    geo, cov = {}, {}
    for c in keys:
        vs, uv, groups, paths = load_chunk(sorted(chunks[c]), origin_m(c))
        V, F, kept = base_collision(vs, groups)
        geo[c] = (vs, uv, groups, paths, V, F, kept)
        # Floor grid only (portals are found before reachability is known): seed a 2 m lattice.
        H_probe = analyse(V, F, [(x, z) for x in np.arange(-5900, 5901, 200.0) for z in np.arange(-5900, 5901, 200.0)],
                      bounds=(-HALF, HALF, -HALF, HALF))
        H_probe['reach_any'] = ~np.isnan(H_probe['H'])
        cov[c] = H_probe

    # portals between grid neighbours
    portals = []
    for c in keys:
        for d in ((1, 0), (0, 1)):
            n = (c[0] + d[0], c[1] + d[1])
            if n in room_of:
                portals.extend(find_portals(c, n, cov))
    # Make every run two-way: A->B and B->A share the same span.
    links = []
    for p in portals:
        links.append(p)
        links.append(dict(p, a=p['b'], b=p['a'], da=p['db'], db=p['da']))

    rooms = {c: {'plyr': [], 'scls': [], 'tgsc': [], 'arrivals': [], 'triggers': []} for c in keys}
    # spawn ids: 0/1 reserved (central: launch + cafe), portal arrivals from 2
    next_spawn = {c: 2 for c in keys}
    for L in links:
        a, b = L['a'], L['b']; oa, ob = origin_m(a), origin_m(b)
        mid = (L['from'] + L['to']) / 2.0
        # arrival in b, 6 m inside, facing into b
        pb = np.zeros(3); pb[L['axis']] = L['edge'] + L['db'] * 6.0; pb[L['other']] = mid
        lb = (pb - ob) * 100
        fb = floor_lookup(cov[b]); hb = fb(lb[0], lb[2])
        step = 0.0
        while np.isnan(hb) and step < 6.0:      # walk further in if 6 m lands on a gap
            step += 0.5; pb[L['axis']] = L['edge'] + L['db'] * (6.0 + step); lb = (pb - ob) * 100; hb = fb(lb[0], lb[2])
        if np.isnan(hb):
            continue
        inward = np.zeros(3); inward[L['axis']] = L['db']
        yaw_b = yaw_towards(inward[0], inward[2])
        sid = next_spawn[b]; next_spawn[b] += 1
        rooms[b]['plyr'].append(plyr(lb[0], hb + 5.0, lb[2], yaw_b, sid))
        rooms[b]['arrivals'].append((lb[0], lb[2]))
        # trigger in a: 0..3 m inside the edge
        pa = np.zeros(3); pa[L['axis']] = L['edge'] + L['da'] * 1.5; pa[L['other']] = mid
        la = (pa - oa) * 100
        fa = floor_lookup(cov[a]); ha = fa(la[0], la[2])
        if np.isnan(ha):
            ha = hb   # same street level across the edge (|dh| < 40 cm by construction)
        exit_index = len(rooms[a]['scls']) + (1 if a == (0, 0) else 0)   # central exit 0 = cafe door
        rooms[a]['scls'].append(scls(room_of[b], sid))
        half_width = (L['to'] - L['from']) * 100 / 2.0 + 50.0
        yaw_a = 0x4000 if L['axis'] == 0 else 0      # local x of the box runs along the edge
        rooms[a]['tgsc'].append(scnchg(exit_index, la[0], ha - 300.0, la[2], yaw_a, half_width))
        rooms[a]['triggers'].append({'center': [la[0], ha, la[2]], 'half_width_cm': half_width, 'axis': L['axis'],
                                     'to_room': room_of[b], 'spawn': sid})

    template = chunk_blobs((P / 'district/template_room.dzr').read_bytes())
    report = {'stage': STAGE, 'rooms': []}
    for c in keys:
        r = room_of[c]; vs, uv, groups, paths, V, F, kept = geo[c]
        R = rooms[c]; dest = OUT / f'{r:02d}'; dest.mkdir(parents=True, exist_ok=True)
        seeds = list(R['arrivals'])
        if c == (0, 0):
            seeds = [(s[0], s[2]) for s in CENTRAL_SPAWNS] + seeds
        if not seeds:
            report['rooms'].append({'room': r, 'chunk': c, 'skipped': 'no connection'}); continue
        cv = analyse(V, F, seeds, bounds=(-HALF, HALF, -HALF, HALF))
        quads = barrier_quads(cv); VL = list(map(tuple, V)); FL = [list(f) for f in F]
        for q in quads:
            s = len(VL); VL.extend(q)
            FL.extend([[s + j for j in f] for f in [(0, 1, 2), (0, 2, 3), (2, 1, 0), (3, 2, 0)]])
        V2, F2 = np.array(VL, float), np.array(FL)
        cv2 = analyse(V2, F2, seeds, bounds=(-HALF, HALF, -HALF, HALF))
        np.savez(dest / 'collision_source.npz', vertices=V2, faces=F2)
        dzb, nodes = encode_dzb(V2, F2, r)
        door_faces = 0
        if c == (0, 0):
            dzb, added = supported_collision(dzb, CAFE_DOOR); door_faces = len(added)
        model, mrep = bd.build_model(vs, uv, groups, paths)
        model = fog_model(model)
        # enemies
        area = float(cv2['reach'].sum() * STEP * STEP / 1e4)
        n_sh = int(round(area / 1250.0)); n_ge = int(round(area / 2000.0))
        away = list(seeds) + [(t['center'][0], t['center'][2]) for t in R['triggers']]
        spots = place_enemies.choose_positions(cv2, away, n_sh + n_ge, seed=7 + r) if n_sh + n_ge else []
        actors = []
        for k, (x, z, y) in enumerate(spots):
            kind = 'groaner' if k < n_sh else 'air_screamer'
            actors.append(place_enemies.actor_record(kind, x, y, z, yaw_towards(-x, -z)))
        # spawns 0/1
        if c == (0, 0):
            sp = [plyr(x, y, z, yaw, i) for i, (x, y, z, yaw) in enumerate(CENTRAL_SPAWNS)]
        else:
            first = R['plyr'][0]
            sp = [first[:0x1c] + struct.pack('>h', s16(0xFF00 | i)) + first[0x1e:] for i in (0, 1)]
        plyr_all = sp + R['plyr']
        dz = [(b'FILI', template[b'FILI'][0], template[b'FILI'][1]),
              (b'LBNK', template[b'LBNK'][0], template[b'LBNK'][1]),
              (b'PLYR', len(plyr_all), b''.join(plyr_all))]
        door_actor = template[b'ACTR'][1][:0x20] if c == (0, 0) else b''
        dz.append((b'ACTR', (1 if door_actor else 0) + len(actors), door_actor + b''.join(actors)))
        exits = ([template[b'SCLS'][1][:13]] if c == (0, 0) else []) + R['scls']
        if exits:
            dz.append((b'SCLS', len(exits), b''.join(exits)))
        trig = ([template[b'TGSC'][1][:0x24]] if c == (0, 0) else []) + R['tgsc']
        if trig:
            dz.append((b'TGSC', len(trig), b''.join(trig)))
        dzr = write_dz(dz)
        (dest / 'model.bmd').write_bytes(model); (dest / 'room.dzb').write_bytes(dzb); (dest / 'room.dzr').write_bytes(dzr)
        rep = {'room': r, 'chunk': list(c), 'tiles': sorted(chunks[c]), 'origin_m': origin_m(c).tolist(),
               'triangles': sum(map(len, groups.values())), 'collision_faces': len(F2), 'tree_nodes': nodes,
               'drop_barriers': len(quads), 'door_support_faces': door_faces,
               'model_bytes': len(model), 'collision_bytes': len(dzb), 'room_bytes_estimate': len(model) + len(dzb) + len(dzr),
               'reachable_m2': area, 'stalhounds': n_sh, 'guays': n_ge, 'spawns': len(plyr_all),
               'exits': len(exits), 'triggers': R['triggers'], 'open_drop_edges_after': len(cv2['drops'])}
        (dest / 'report.json').write_text(json.dumps(rep, indent=1) + '\n')
        report['rooms'].append(rep)
        print(f"room {r:2d} chunk {c}: {len(chunks[c])} tiles, {rep['triangles']} tris, {rep['room_bytes_estimate']//1024} KB, "
              f"{area:.0f} m2, {n_sh}+{n_ge} enemies, {len(R['triggers'])} exits, drops left {rep['open_drop_edges_after']}")
    report['portals'] = len(links)
    (P / 'town/town_report.json').write_text(json.dumps(report, indent=1) + '\n')


if __name__ == '__main__':
    main()
